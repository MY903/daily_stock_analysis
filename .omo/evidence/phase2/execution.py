"""
Tiger 交易执行层

接收确认后的信号 → 风控审核 → TigerClient 下单 → 审计日志 → 飞书回传。
支持三种运行模式：SANDBOX（纯模拟）/ PAPER（纸交）/ PROD（实盘待确认）。
"""

import asyncio
import logging
import time

from config.settings import settings, TradingMode
from src.trading.signal import Signal, SignalStatus
from src.trading.risk_manager import RiskManager, RiskVerdict
from src.trading.audit_logger import AuditLogger
from src.trading.tiger_client import TigerClient
from src.trading.config import load_config, AppConfig
from bot.platforms.lark_interactive import LarkInteractiveBot, LarkCardBuilder

logger = logging.getLogger(__name__)


class ExecutionEngine:
    """
    交易执行引擎。

    流程：Signal → RiskManager 审核 → TigerClient 下单 → AuditLogger 记录 → 结果回传
    运行模式由 settings.TRADING_MODE 决定：
      - SANDBOX: 纯模拟，不下真实订单（原 Phase 1 dry-run 行为）
      - PAPER:   纸交，调用 TigerClient 模拟环境 + 飞书通知
      - PROD:    实盘，风控检查后等待 Lark 双确认（L3 完成完整流程）
    """

    def __init__(self, tiger_client: TigerClient, risk_manager: RiskManager,
                 audit_logger: AuditLogger, lark_bot: LarkInteractiveBot = None):
        self._tiger = tiger_client
        self._risk = risk_manager
        self._audit = audit_logger
        self._lark_bot = lark_bot or LarkInteractiveBot()
        self._config: AppConfig = load_config()

    def execute(self, signal: Signal, ref_price: float = 0) -> dict:
        """
        执行交易信号。

        根据 settings.TRADING_MODE 路由到对应执行方法：
          - SANDBOX → _sandbox_execute
          - PAPER   → _paper_execute
          - PROD    → _prod_execute

        Args:
            signal: 已确认的 Signal
            ref_price: 参考价格（用于异常价格检测）

        Returns:
            {
                "success": bool,
                "order_id": Optional[str],
                "message": str,
                "risk_blocked": bool,
            }
        """
        mode = settings.TRADING_MODE

        if mode == TradingMode.SANDBOX:
            return self._sandbox_execute(signal)
        elif mode == TradingMode.PAPER:
            return self._paper_execute(signal, ref_price)
        elif mode == TradingMode.PROD:
            return self._prod_execute(signal, ref_price)
        else:
            return self._fail(signal, f"未知交易模式: {mode}")

    # ==================== SANDBOX: 纯模拟 ====================

    def _sandbox_execute(self, signal: Signal) -> dict:
        """纯模拟执行：仅记录日志，不下真实订单（原 Phase 1 dry-run 行为）"""
        logger.info("[SANDBOX] 模拟执行信号: %s %s %s x%d",
                    signal.symbol, signal.action.value,
                    f"${signal.price_target:.2f}" if signal.price_target else "",
                    signal.quantity or 0)

        if signal.action.value == "HOLD":
            return self._success(signal, "HOLD - 无需下单")

        dry_run_id = f"dry-run-order-{int(time.time())}"
        self._audit.log_executed(signal.signal_id, dry_run_id)
        self._audit.log_completed(signal.signal_id)
        return {
            "success": True,
            "order_id": dry_run_id,
            "message": "[SANDBOX] 模拟执行成功",
            "risk_blocked": False,
        }

    # ==================== PAPER: 纸交 ====================

    def _paper_execute(self, signal: Signal, ref_price: float) -> dict:
        """纸交执行：调用 TigerClient（PAPER 环境）+ 飞书通知"""
        if signal.action.value == "HOLD":
            return self._success(signal, "HOLD - 无需下单")

        # 风控检查
        estimated_price = signal.price_target or ref_price
        risk_result = self._risk.is_allowed(signal, estimated_price, ref_price)
        if risk_result.verdict == RiskVerdict.REJECT:
            return self._fail(signal, f"风控拦截: {risk_result.reason}", risk_blocked=True)

        # 连接 TigerClient
        if not self._tiger.is_connected:
            try:
                self._tiger.connect()
            except Exception as e:
                return self._fail(signal, f"Tiger 连接失败: {e}")

        # 下单
        try:
            if signal.action.value == "BUY":
                order_id = self._tiger.place_limit_buy(
                    symbol=signal.symbol,
                    quantity=signal.quantity or 0,
                    price=estimated_price,
                )
            elif signal.action.value == "SELL":
                order_id = self._tiger.place_limit_sell(
                    symbol=signal.symbol,
                    quantity=signal.quantity or 0,
                    price=estimated_price,
                )
            else:
                return self._success(signal, "HOLD - 无需下单")

            if order_id:
                self._audit.log_executed(signal.signal_id, str(order_id))
                self._audit.log_completed(signal.signal_id)
                signal.status = SignalStatus.EXECUTED

                # 发送飞书通知
                self._send_lark_notification(signal, order_id)

                return {
                    "success": True,
                    "order_id": str(order_id),
                    "message": f"[PAPER] 纸交订单已提交: {order_id}",
                    "risk_blocked": False,
                }
            else:
                return self._fail(signal, "下单失败: order_id 为空")
        except Exception as e:
            return self._fail(signal, f"下单异常: {e}")

    # ==================== PROD: 实盘 ====================

    def _prod_execute(self, signal: Signal, ref_price: float) -> dict:
        """实盘执行：风控检查 → 等待 Lark 双确认（L3/I1 完成完整流程）"""
        if signal.action.value == "HOLD":
            return self._success(signal, "HOLD - 无需下单")

        # 风控检查
        estimated_price = signal.price_target or ref_price
        risk_result = self._risk.is_allowed(signal, estimated_price, ref_price)
        if risk_result.verdict == RiskVerdict.REJECT:
            return self._fail(signal, f"风控拦截: {risk_result.reason}", risk_blocked=True)

        # 风控通过，返回等待确认状态
        # TODO(L3/I1): 接入 Lark 双确认流程后再执行实际下单
        self._audit.log_executed(signal.signal_id, "pending-confirmation")
        return {
            "success": True,
            "order_id": None,
            "message": "风控已通过，等待 Lark 双确认后执行 (PROD)",
            "risk_blocked": False,
            "awaiting_confirmation": True,
        }

    # ==================== Lark 通知 ====================

    def _send_lark_notification(self, signal: Signal, order_id: int) -> None:
        """发送执行结果通知到飞书"""
        try:
            card = LarkCardBuilder.execution_result_card(
                symbol=signal.symbol,
                action=signal.action.value,
                quantity=signal.quantity or 0,
                price=signal.price_target or 0,
                order_id=str(order_id),
                success=True,
            )
            asyncio.run(self._lark_bot.push_card(card))
            logger.info("[PAPER] 飞书通知已发送: %s %s order=%s",
                        signal.symbol, signal.action.value, order_id)
        except Exception as e:
            logger.warning("飞书通知发送失败: %s", e)

    # ==================== 辅助方法 ====================

    def _fail(self, signal: Signal, message: str, risk_blocked: bool = False) -> dict:
        """记录执行失败"""
        self._audit.log_failed(signal.signal_id, message)
        signal.status = SignalStatus.FAILED
        logger.error("交易执行失败 %s: %s", signal.signal_id, message)
        return {
            "success": False,
            "order_id": None,
            "message": message,
            "risk_blocked": risk_blocked,
        }

    def _success(self, signal: Signal, message: str) -> dict:
        """记录执行成功"""
        self._audit.log_completed(signal.signal_id)
        signal.status = SignalStatus.EXECUTED
        return {
            "success": True,
            "order_id": "hold",
            "message": message,
            "risk_blocked": False,
        }
