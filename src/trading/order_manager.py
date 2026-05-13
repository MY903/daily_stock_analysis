"""订单管理器

负责订单的创建、监控、撤销和状态同步。
包含防重复下单和 GTC 订单清理逻辑。
"""

import logging
import time
from typing import Optional, Dict, Any, Tuple

from src.trading.config import AppConfig
from src.trading.tiger_client import TigerClient

logger = logging.getLogger(__name__)


class OrderManager:
    """订单管理器

    功能：
    - 提交买入/止盈/止损订单
    - 轮询订单状态
    - 防重复下单（signal_cooldown 内不重复触发）
    - 清理过期 GTC 挂单
    """

    def __init__(self, client: TigerClient, config: AppConfig):
        self._client = client
        self._config = config
        self._last_signal_time: Dict[str, float] = {}

    def can_place_order(self, signal_type: str) -> bool:
        """检查是否可以下单（防重复）

        Args:
            signal_type: 信号类型，如 "buy", "take_profit", "stop_loss"

        Returns:
            是否允许下单
        """
        cooldown = self._config.bot.signal_cooldown
        last_time = self._last_signal_time.get(signal_type, 0)
        elapsed = time.time() - last_time
        if elapsed < cooldown:
            logger.debug("信号冷却中: %s (剩余 %.0f 秒)", signal_type, cooldown - elapsed)
            return False
        return True

    def record_signal(self, signal_type: str) -> None:
        """记录信号触发时间"""
        self._last_signal_time[signal_type] = time.time()

    def submit_buy_order(self) -> Optional[int]:
        """提交买入限价单

        Returns:
            订单 ID，失败或模式限制返回 None
        """
        trading = self._config.trading
        symbol = trading.symbol
        entry = trading.entry

        if not self.can_place_order("buy"):
            return None

        if not trading.auto_trade:
            logger.info("[ALERT-ONLY] 买入信号触发，但未开启自动交易: "
                        "symbol=%s, price=%.2f, qty=%d",
                        symbol, entry.trigger_price, entry.quantity)
            self.record_signal("buy")
            return None

        order_id = self._client.place_limit_buy(
            symbol=symbol,
            quantity=entry.quantity,
            price=entry.trigger_price,
            time_in_force=entry.time_in_force,
        )

        if order_id is not None:
            self.record_signal("buy")
        return order_id

    def submit_take_profit_order(self, quantity: int,
                                  fill_price: float) -> Optional[int]:
        """提交止盈限价单

        Args:
            quantity: 卖出数量
            fill_price: 买入成交价（用于计算止盈价）

        Returns:
            订单 ID
        """
        trading = self._config.trading
        tp = trading.take_profit
        target_price = round(fill_price * (1 + tp.percentage), 2)

        if not self.can_place_order("take_profit"):
            return None

        if not trading.auto_trade:
            logger.info("[ALERT-ONLY] 止盈条件满足（仅通知）: target=%.2f", target_price)
            self.record_signal("take_profit")
            return None

        order_id = self._client.place_limit_sell(
            symbol=trading.symbol,
            quantity=quantity,
            price=target_price,
            time_in_force=tp.time_in_force,
        )

        if order_id is not None:
            self.record_signal("take_profit")
        return order_id

    def submit_stop_loss_order(self, quantity: int,
                                fill_price: float) -> Optional[int]:
        """提交止损限价单

        Args:
            quantity: 卖出数量
            fill_price: 买入成交价（用于计算止损价）

        Returns:
            订单 ID
        """
        trading = self._config.trading
        sl = trading.stop_loss
        stop_price = round(fill_price * (1 - sl.percentage), 2)
        limit_price = round(stop_price * (1 - sl.limit_offset), 2)

        if not self.can_place_order("stop_loss"):
            return None

        if not trading.auto_trade:
            logger.info("[ALERT-ONLY] 止损条件满足（仅通知）: stop=%.2f", stop_price)
            self.record_signal("stop_loss")
            return None

        order_id = self._client.place_stop_limit_sell(
            symbol=trading.symbol,
            quantity=quantity,
            stop_price=stop_price,
            limit_price=limit_price,
            time_in_force=sl.time_in_force,
        )

        if order_id is not None:
            self.record_signal("stop_loss")
        return order_id

    def submit_exit_orders(self, quantity: int,
                           fill_price: float) -> Tuple[Optional[int], Optional[int]]:
        """同时提交止盈和止损订单（买入成交后调用）

        Returns:
            (止盈订单ID, 止损订单ID)
        """
        tp_id = self.submit_take_profit_order(quantity, fill_price)
        sl_id = self.submit_stop_loss_order(quantity, fill_price)
        return tp_id, sl_id

    def check_order_status(self, order_id: int) -> Optional[Dict[str, Any]]:
        """查询订单当前状态

        Returns:
            订单信息字典，包含 status, filled_quantity, avg_fill_price 等
        """
        return self._client.get_order(order_id)

    def is_order_filled(self, order_id: int) -> Tuple[bool, float]:
        """检查订单是否完全成交

        Returns:
            (是否成交, 成交均价)
        """
        info = self.check_order_status(order_id)
        if info is None:
            return False, 0.0

        status = info.get("status", "")
        # tigeropen 的订单状态: Filled, Cancelled, Inactive, etc.
        if status in ("Filled",):
            return True, info.get("avg_fill_price", 0.0)
        return False, 0.0

    def is_order_cancelled(self, order_id: int) -> bool:
        """检查订单是否已被撤销"""
        info = self.check_order_status(order_id)
        if info is None:
            return False
        status = info.get("status", "")
        return status in ("Cancelled", "Inactive", "ApiCancelled")

    def cancel_order(self, order_id: int) -> bool:
        """撤销指定订单"""
        return self._client.cancel_order(order_id)

    def cancel_all_active_orders(self) -> int:
        """撤销所有活跃订单（启动时清理用）

        Returns:
            撤销的订单数量
        """
        active = self._client.get_active_orders()
        cancelled = 0
        for order in active:
            oid = order.get("id") or order.get("order_id")
            if oid:
                if self._client.cancel_order(int(oid)):
                    cancelled += 1
        if cancelled > 0:
            logger.info("已撤销 %d 个活跃订单", cancelled)
        return cancelled

    def get_position_quantity(self) -> int:
        """获取当前持仓数量"""
        positions = self._client.get_positions(symbol=self._config.trading.symbol)
        if positions:
            total = sum(int(p.get("quantity", 0)) for p in positions)
            return total
        return 0

    def validate_position_before_sell(self, expected_qty: int) -> bool:
        """卖出前校验持仓数量"""
        actual = self.get_position_quantity()
        if actual < expected_qty:
            logger.error("持仓校验失败: 预期 %d 股，实际 %d 股", expected_qty, actual)
            return False
        return True
