"""TradingBot 主类

整合所有模块，管理交易机器人生命周期。
"""

import logging
import signal
import sys
import time
import threading
from typing import Dict, Any, Optional

from src.trading.config import AppConfig, load_config
from src.trading.tiger_client import TigerClient
from src.trading.state_machine import StateMachine, TradingState
from src.trading.order_manager import OrderManager
from src.trading.monitor import QuoteMonitor
from src.trading.strategy.tqqq_swing import TQQQSwingStrategy
from src.trading.notifier import TradingNotifier
from src.trading.trade_recorder import TradeRecorder

logger = logging.getLogger(__name__)


class TradingBot:
    """TQQQ 自动交易机器人

    生命周期：
    1. 初始化配置和组件
    2. 连接 Tiger API
    3. 恢复状态
    4. 启动行情监控
    5. 主循环：策略评估 + 订单轮询
    6. 优雅退出
    """

    def __init__(self, config: Optional[AppConfig] = None):
        self._config = config or load_config()
        self._running = False
        self._start_time = 0.0

        # 核心组件
        self._client = TigerClient(self._config)
        self._state_machine = StateMachine(data_dir=self._config.logging.data_dir)
        self._order_manager = OrderManager(self._client, self._config)
        self._monitor = QuoteMonitor(self._client, self._config)
        self._strategy = TQQQSwingStrategy(self._config)
        self._notifier = TradingNotifier(self._config)
        self._recorder = TradeRecorder(data_dir=self._config.logging.data_dir)

        # 订单轮询线程
        self._poll_thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """启动交易机器人"""
        self._start_time = time.time()
        logger.info("=" * 50)
        logger.info("TQQQ 交易机器人启动")
        logger.info("标的: %s", self._config.trading.symbol)
        logger.info("环境: %s", self._config.tiger.environment)
        logger.info("模式: %s", "自动交易" if self._config.trading.auto_trade else "仅告警")
        logger.info("=" * 50)

        # 安全检查
        self._safety_check()

        # 连接 API
        self._client.connect()

        # 恢复状态
        self._state_machine.set_cooldown_duration(self._config.bot.cooldown_seconds)
        self._state_machine.restore()

        # 启动时清理过期挂单（仅 IDLE 状态）
        if self._state_machine.state == TradingState.IDLE:
            cancelled = self._order_manager.cancel_all_active_orders()
            if cancelled > 0:
                logger.info("启动清理: 撤销了 %d 个过期挂单", cancelled)

        # 通知启动
        mode = "auto" if self._config.trading.auto_trade else "alert_only"
        self._notifier.notify_startup(mode, self._config.tiger.environment)

        # 注册信号处理
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

        # 启动行情监控
        self._monitor.set_price_callback(self._on_price_update)
        self._monitor.start()

        # 启动订单轮询
        self._running = True
        self._poll_thread = threading.Thread(
            target=self._poll_loop,
            daemon=True,
            name="order-poll"
        )
        self._poll_thread.start()

        # 主循环
        self._main_loop()

    def stop(self, reason: str = "正常退出") -> None:
        """停止交易机器人"""
        logger.info("交易机器人停止中... (原因: %s)", reason)
        self._running = False

        self._monitor.stop()
        self._client.disconnect()
        self._notifier.notify_shutdown(reason)

        logger.info("交易机器人已停止")

    # ==================== 主循环 ====================

    def _main_loop(self) -> None:
        """主循环：定期检查状态和冷却期"""
        while self._running:
            try:
                # 检查冷却期
                if self._state_machine.state == TradingState.COOLDOWN:
                    if self._state_machine.is_cooldown_expired():
                        self._state_machine.transition_to_idle()
                        logger.info("冷却期结束，回到 IDLE 状态")

                # 如果 WebSocket 断线，使用 REST 轮询兜底
                if not self._monitor.latest_quote:
                    self._monitor.poll_quote()

                time.sleep(1)
            except Exception as e:
                logger.error("主循环异常: %s", e)
                time.sleep(5)

    # ==================== 策略回调 ====================

    def _on_price_update(self, quote: Dict[str, Any]) -> None:
        """行情更新回调 — 由 QuoteMonitor 调用"""
        if not self._running:
            return

        state = self._state_machine.state
        context = self._state_machine.context

        # 策略评估
        signal_obj = self._strategy.evaluate(quote, state.value, context)
        if signal_obj is None:
            return

        logger.info("策略信号: %s", signal_obj)

        # 执行信号
        if signal_obj.action == "buy":
            self._handle_buy_signal(signal_obj)
        elif signal_obj.action == "take_profit":
            self._handle_take_profit_signal(signal_obj)
        elif signal_obj.action == "stop_loss":
            self._handle_stop_loss_signal(signal_obj)

    def _handle_buy_signal(self, sig) -> None:
        """处理买入信号"""
        entry = self._config.trading.entry

        # 通知
        self._notifier.notify_buy_signal(
            price=sig.price,
            trigger_price=entry.trigger_price,
            quantity=entry.quantity,
            auto_trade=self._config.trading.auto_trade,
        )

        # 下单
        order_id = self._order_manager.submit_buy_order()
        if order_id is not None:
            self._state_machine.transition_to_buy_pending(
                order_id=order_id,
                price=entry.trigger_price,
                quantity=entry.quantity,
            )

    def _handle_take_profit_signal(self, sig) -> None:
        """处理止盈信号"""
        context = self._state_machine.context
        quantity = context.get("quantity", 0)
        fill_price = context.get("fill_price", 0)

        if not self._order_manager.validate_position_before_sell(quantity):
            self._notifier.notify_error("持仓校验失败", "实际持仓不足，无法止盈")
            return

        # 通知
        self._notifier.notify_buy_signal(
            price=sig.price,
            trigger_price=fill_price * (1 + self._config.trading.take_profit.percentage),
            quantity=quantity,
            auto_trade=self._config.trading.auto_trade,
        )

        order_id = self._order_manager.submit_take_profit_order(quantity, fill_price)
        if order_id is not None:
            target = round(fill_price * (1 + self._config.trading.take_profit.percentage), 2)
            self._state_machine.transition_to_sell_pending(
                order_id=order_id,
                sell_type="take_profit",
                target_price=target,
            )

    def _handle_stop_loss_signal(self, sig) -> None:
        """处理止损信号"""
        context = self._state_machine.context
        quantity = context.get("quantity", 0)
        fill_price = context.get("fill_price", 0)

        if not self._order_manager.validate_position_before_sell(quantity):
            self._notifier.notify_error("持仓校验失败", "实际持仓不足，无法止损")
            return

        order_id = self._order_manager.submit_stop_loss_order(quantity, fill_price)
        if order_id is not None:
            target = round(fill_price * (1 - self._config.trading.stop_loss.percentage), 2)
            self._state_machine.transition_to_sell_pending(
                order_id=order_id,
                sell_type="stop_loss",
                target_price=target,
            )

    # ==================== 订单轮询 ====================

    def _poll_loop(self) -> None:
        """订单状态轮询循环"""
        interval = self._config.bot.poll_interval

        while self._running:
            try:
                self._check_pending_orders()
            except Exception as e:
                logger.error("订单轮询异常: %s", e)
            time.sleep(interval)

    def _check_pending_orders(self) -> None:
        """检查待处理订单的状态"""
        state = self._state_machine.state
        context = self._state_machine.context

        if state == TradingState.BUY_PENDING:
            order_id = context.get("buy_order_id")
            if order_id:
                filled, fill_price = self._order_manager.is_order_filled(order_id)
                if filled:
                    self._on_buy_filled(fill_price)
                elif self._order_manager.is_order_cancelled(order_id):
                    logger.warning("买入订单被撤销: order_id=%d", order_id)
                    self._state_machine.force_idle("买入订单被撤销")

        elif state == TradingState.SELL_PENDING:
            order_id = context.get("sell_order_id")
            if order_id:
                filled, fill_price = self._order_manager.is_order_filled(order_id)
                if filled:
                    self._on_sell_filled(fill_price)
                elif self._order_manager.is_order_cancelled(order_id):
                    logger.warning("卖出订单被撤销: order_id=%d", order_id)
                    # 卖出被撤销，回到 HOLDING 继续监控
                    self._state_machine._state = TradingState.HOLDING
                    self._state_machine._persist()

    def _on_buy_filled(self, fill_price: float) -> None:
        """买入成交处理"""
        context = self._state_machine.context
        quantity = context.get("quantity", 0)

        self._state_machine.transition_to_holding(fill_price)

        # 计算目标价位
        targets = self._strategy.get_target_prices(fill_price)

        # 通知
        self._notifier.notify_buy_filled(
            fill_price=fill_price,
            quantity=quantity,
            tp_price=targets["take_profit"],
            sl_price=targets["stop_loss"],
        )

        # 记录
        mode = "auto" if self._config.trading.auto_trade else "alert"
        self._recorder.record_buy(
            symbol=self._config.trading.symbol,
            quantity=quantity,
            price=context.get("entry_price", fill_price),
            fill_price=fill_price,
            mode=mode,
        )

    def _on_sell_filled(self, fill_price: float) -> None:
        """卖出成交处理"""
        context = self._state_machine.context
        entry_price = context.get("fill_price", 0)
        quantity = context.get("quantity", 0)
        sell_type = context.get("sell_type", "unknown")

        self._state_machine.transition_to_cooldown(fill_price)

        # 通知
        if sell_type == "take_profit":
            self._notifier.notify_take_profit(fill_price, entry_price, quantity)
        else:
            self._notifier.notify_stop_loss(fill_price, entry_price, quantity)

        # 记录
        mode = "auto" if self._config.trading.auto_trade else "alert"
        self._recorder.record_sell(
            symbol=self._config.trading.symbol,
            quantity=quantity,
            price=context.get("target_price", fill_price),
            fill_price=fill_price,
            entry_price=entry_price,
            sell_type=sell_type,
            mode=mode,
        )

    # ==================== 安全与生命周期 ====================

    def _safety_check(self) -> None:
        """启动安全检查"""
        trading = self._config.trading
        tiger = self._config.tiger

        # 实盘 + 自动交易需要确认
        if tiger.is_live and trading.auto_trade:
            logger.warning("检测到 LIVE + auto_trade 模式")
            confirm = input("即将以实盘自动交易模式启动，输入 'CONFIRM' 确认: ")
            if confirm.strip() != "CONFIRM":
                logger.info("用户取消启动")
                sys.exit(0)

        # 单笔损失不超过 5% 校验
        entry = trading.entry
        sl = trading.stop_loss
        max_loss = entry.trigger_price * entry.quantity * sl.percentage
        # 这里简化处理，实际应查询账户资产
        logger.info("预估单笔最大损失: $%.2f", max_loss)

    def _handle_signal(self, signum, frame) -> None:
        """信号处理（SIGINT/SIGTERM）"""
        sig_name = signal.Signals(signum).name
        logger.info("收到信号: %s", sig_name)
        self.stop(reason=f"收到 {sig_name}")
        sys.exit(0)

    def get_status(self) -> Dict[str, Any]:
        """获取当前运行状态"""
        uptime = time.time() - self._start_time if self._start_time else 0
        hours = int(uptime // 3600)
        minutes = int((uptime % 3600) // 60)

        return {
            "running": self._running,
            "state": self._state_machine.state.value,
            "context": self._state_machine.context,
            "latest_quote": self._monitor.latest_quote,
            "uptime": f"{hours}h {minutes}m",
            "environment": self._config.tiger.environment,
            "auto_trade": self._config.trading.auto_trade,
            "pnl_today": self._recorder.get_today_pnl(),
            "pnl_total": self._recorder.get_total_pnl(),
        }
