"""
QuantWeasel 端到端集成管道。

整合所有模块：SignalGenerator → RiskManager → 飞书卡片 → 确认 → ExecutionEngine → 回传
"""

import argparse
import asyncio
import logging
from typing import Any, Optional

from src.trading.config import load_config
from src.trading.signal import Signal, SignalAction, SignalSource
from src.trading.signal_generator import SignalGenerator
from src.trading.risk_manager import RiskManager
from src.trading.card_handler import SignalConfirmHandler
from src.trading.execution import ExecutionEngine
from src.trading.audit_logger import AuditLogger
from src.trading.tiger_client import TigerClient
from src.trading.signal_scheduler import (
    SignalScheduler, PreMarketScheduler, IntradayScheduler, TradingCalendar
)
from src.trading.signal_expiry import ExpiryManager, DedupGuard
from bot.platforms.lark_interactive import LarkInteractiveBot

logger = logging.getLogger(__name__)


class QuantWeaselPipeline:
    """
    QuantWeasel 主管道。

    端到端流程：Signal → RiskCheck → 飞书卡片 → 人工确认 → Tiger下单 → 审计日志 → 结果回传
    """

    def __init__(self, reply_client: Optional[Any] = None):
        """
        Args:
            reply_client: FeishuReplyClient 实例（可选），用于确认/拒绝后更新卡面
        """
        self._config = load_config()
        self._bot = LarkInteractiveBot()
        self._audit_logger = AuditLogger()
        self._risk_manager = RiskManager()
        self._tiger_client = TigerClient(self._config)
        self._signal_generator = SignalGenerator()
        self._card_handler = SignalConfirmHandler(
            self._bot, self._audit_logger, reply_client=reply_client,
        )
        self._execution_engine = ExecutionEngine(
            self._tiger_client, self._risk_manager, self._audit_logger
        )
        self._pre_market = PreMarketScheduler(self._signal_generator, self._card_handler)
        self._intraday = IntradayScheduler(self._signal_generator, self._card_handler)
        self._scheduler = SignalScheduler(self._pre_market, self._intraday)
        self._expiry_manager = ExpiryManager(self._card_handler, self._audit_logger)
        self._dedup_guard = DedupGuard()
        self._running = False

    # ==================== 单条信号流程 ====================

    async def generate_and_push_signal(self, symbol: str, action: str,
                                      quantity: Optional[int] = None,
                                      confidence: float = 0.8,
                                      rationale: str = "") -> Optional[Signal]:
        """
        生成单条信号并推送飞书。

        流程：创建 Signal → 风控 → 审计 → 推送飞书
        """
        signal = Signal(
            symbol=symbol,
            action=SignalAction(action.upper()),
            quantity=quantity,
            confidence=confidence,
            rationale=rationale or f"手动触发 {symbol} {action}",
            source=SignalSource.AI,
        )

        # 审计日志：已创建
        self._audit_logger.log_created(signal)
        logger.info("信号已创建: %s %s %s", signal.symbol, signal.action.value, signal.signal_id)

        # 推送飞书
        success = await self._card_handler.push_signal_card(signal)
        if not success:
            logger.error("信号卡片推送失败: %s", signal.signal_id)
            return None

        return signal

    async def process_confirmed_signal(self, signal_id: str) -> dict:
        """
        处理已确认的信号：执行交易。

        流程：去重检查 → ExecutionEngine.execute()
        """
        # 双重确认防护
        if not self._dedup_guard.confirm_once(signal_id):
            return {"success": False, "message": "信号已被确认（防重复执行）"}

        # 从 AuditLogger 获取信号信息
        history = self._audit_logger.get_signal_history(signal_id)
        if not history:
            return {"success": False, "message": f"信号 {signal_id} 不存在"}

        # 重建 Signal 对象
        signal = Signal.model_validate_json(history["signal_json"])

        # 执行
        result = self._execution_engine.execute(signal)

        # 推送结果卡片
        if result["success"]:
            await self._card_handler.push_execution_result(
                signal, result.get("order_id", ""), True
            )
        elif result.get("risk_blocked"):
            await self._card_handler.push_risk_intercept(
                signal, result.get("message", "风控拦截")
            )

        return result

    # ==================== 运行模式 ====================

    async def run_pre_market(self):
        """运行盘前信号生成"""
        count = await self._pre_market.run()
        logger.info("盘前模式完成: 生成 %d 条信号", count)
        return count

    async def run_intraday(self):
        """运行盘中信号生成"""
        if not TradingCalendar.is_market_hours():
            logger.info("当前非交易时间，跳过盘中模式")
            return 0
        count = await self._intraday.run()
        if count > 0:
            logger.info("盘中模式: 发现 %d 条新信号", count)
        return count

    # ==================== 完整启动 ====================

    def start(self):
        """启动完整管道（调度 + 过期检查）"""
        self._running = True

        # 连接 Tiger API 并同步实际资产
        self._tiger_client.connect()
        self._risk_manager.sync_equity(self._tiger_client)

        # 启动过期检查
        self._expiry_manager.start()

        # 注册优雅关闭
        self._expiry_manager.register_shutdown_handler()

        # 启动双调度
        self._scheduler.start()

        logger.info("QuantWeasel 管道已启动 (调度+过期检查)")
        return self

    def stop(self):
        """停止管道"""
        self._running = False
        self._scheduler.stop()
        self._expiry_manager.stop()
        logger.info("QuantWeasel 管道已停止")

    @property
    def is_running(self) -> bool:
        return self._running

    # ==================== CLI 构建 ====================

    @staticmethod
    def build_parser() -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(
            description="QuantWeasel - AI 量化交易系统",
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )
        parser.add_argument("--dry-run", action="store_true", default=True,
                           help="Dry-run 模式（不下真实订单）")
        parser.add_argument("--mode", choices=["premarket", "intraday", "manual", "daemon"],
                           default="manual", help="运行模式")
        parser.add_argument("--symbol", default="TQQQ", help="交易标的")
        parser.add_argument("--action", choices=["BUY", "SELL", "HOLD"],
                           default="BUY", help="交易方向")
        parser.add_argument("--quantity", type=int, help="数量")
        parser.add_argument("--confidence", type=float, default=0.8, help="置信度 0-1")
        parser.add_argument("--rationale", default="", help="交易理据")
        return parser

    async def run_cli(self, args: argparse.Namespace):
        """CLI 入口"""
        mode = args.mode

        if mode == "premarket":
            count = await self.run_pre_market()
            logger.info("盘前模式完成: 生成 %d 条信号", count)

        elif mode == "intraday":
            count = await self.run_intraday()
            logger.info("盘中模式完成: 生成 %d 条信号", count)

        elif mode == "manual":
            signal = await self.generate_and_push_signal(
                symbol=args.symbol,
                action=args.action,
                quantity=args.quantity,
                confidence=args.confidence,
                rationale=args.rationale,
            )
            if signal:
                logger.info("信号已推送: %s %s (ID: %s)", signal.symbol, signal.action.value, signal.signal_id)
            else:
                logger.error("信号推送失败")

        elif mode == "daemon":
            logger.info("启动 QuantWeasel 守护模式...")
            self.start()
            # 保持运行
            try:
                while self._running:
                    await asyncio.sleep(60)
            except KeyboardInterrupt:
                self.stop()
                logger.info("QuantWeasel 已停止")
