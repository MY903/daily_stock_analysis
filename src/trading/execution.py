"""
Tiger 交易执行层

接收确认后的信号 → 风控审核 → TigerClient 下单 → 审计日志 → 飞书回传。
Phase 1 强制模拟盘，禁止实盘交易。
"""

import logging

from config.settings import settings
from src.trading.signal import Signal, SignalStatus
from src.trading.risk_manager import RiskManager, RiskVerdict
from src.trading.audit_logger import AuditLogger
from src.trading.tiger_client import TigerClient
from src.trading.config import load_config, AppConfig

logger = logging.getLogger(__name__)


class ExecutionEngine:
    """
    交易执行引擎。
    
    流程：Signal → RiskManager 审核 → TigerClient 下单 → AuditLogger 记录 → 结果回传
    """

    def __init__(self, tiger_client: TigerClient, risk_manager: RiskManager,
                 audit_logger: AuditLogger):
        self._tiger = tiger_client
        self._risk = risk_manager
        self._audit = audit_logger
        self._config: AppConfig = load_config()

    def execute(self, signal: Signal, ref_price: float = 0) -> dict:
        """
        执行交易信号。
        
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
        # Phase 1 安全锁：仅允许模拟/纸交，禁止实盘
        if settings.is_prod:
            return self._fail(signal, "Phase 1 强制模拟盘模式，禁止实盘交易")

        # 检查 dry-run 模式
        if settings.QUANT_DRY_RUN:
            logger.info("[DRY-RUN] 模拟执行信号: %s %s %s x%d",
                        signal.symbol, signal.action.value,
                        f"${signal.price_target:.2f}" if signal.price_target else "",
                        signal.quantity or 0)
            self._audit.log_executed(signal.signal_id, "dry-run-order-000")
            self._audit.log_completed(signal.signal_id)
            return {
                "success": True,
                "order_id": "dry-run-order-000",
                "message": "[DRY-RUN] 模拟执行成功",
                "risk_blocked": False,
            }

        if signal.action.value == "HOLD":
            return self._success(signal, "HOLD - 无需下单")

        # 风控检查
        estimated_price = signal.price_target or ref_price
        risk_result = self._risk.is_allowed(signal, estimated_price, ref_price)
        if risk_result.verdict == RiskVerdict.REJECT:
            return self._fail(signal, f"风控拦截: {risk_result.reason}", risk_blocked=True)

        # 检查连接
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
                return {
                    "success": True,
                    "order_id": str(order_id),
                    "message": f"订单已提交: {order_id}",
                    "risk_blocked": False,
                }
            else:
                return self._fail(signal, "下单失败: order_id 为空")
        except Exception as e:
            return self._fail(signal, f"下单异常: {e}")

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
