"""
飞书互动卡片确认流程

处理信号从推送→人工确认/拒绝→触发执行的全流程。
"""

import logging
from typing import Any, Optional, Callable
from datetime import datetime

from src.trading.signal import Signal, SignalStatus, ConfirmResult, ConfirmAction
from src.trading.audit_logger import AuditLogger
from bot.platforms.lark_interactive import (
    LarkCardBuilder,
    LarkInteractiveBot,
    CARD_SIGNAL_CONFIRM,
    CARD_SIGNAL_EXPIRED,
    CARD_EXECUTION_RESULT,
    CARD_RISK_INTERCEPT,
)

logger = logging.getLogger(__name__)


class SignalConfirmHandler:
    """
    信号确认流程处理器。

    流程：推送卡片 → 用户确认/拒绝 → 状态更新 → 审计日志 → 卡面更新 → 触发执行
    """

    def __init__(self, bot: LarkInteractiveBot, logger: AuditLogger,
                 reply_client: Optional[Any] = None):
        """
        Args:
            bot: LarkInteractiveBot 实例，用于注册 confirm/reject 回调
            logger: AuditLogger 实例
            reply_client: FeishuReplyClient 实例，用于确认/拒绝后更新卡面
        """
        self._bot = bot
        self._audit_logger = logger
        self._reply_client = reply_client
        self._pending_signals: dict[str, Signal] = {}
        self._execution_handler: Optional[Callable] = None

        # 注册 Bot 回调
        bot.on_confirm(self._on_confirm)
        bot.on_reject(self._on_reject)

    def wire_card_action_handler(self, card_handler: Any) -> None:
        """
        Wire this handler's confirm/reject callbacks to a FeishuCardActionHandler.

        This bridges the P2CardActionTriggerV1 event flow from the SDK
        to the SignalConfirmHandler lifecycle.

        Args:
            card_handler: FeishuCardActionHandler instance
        """
        card_handler.set_confirm_handler(self._on_confirm)
        card_handler.set_reject_handler(self._on_reject)
        logger.debug("[SignalConfirm] 已绑定 FeishuCardActionHandler 回调")

    async def _on_confirm(self, signal_id: str, **kwargs):
        """确认回调：更新信号状态 + 卡面"""
        result = await self.handle_card_action(signal_id, "confirm")
        # 更新原卡片，替换按钮为"已确认"文本（防重复点击）
        message_id = kwargs.get('message_id')
        if message_id and self._reply_client:
            signal = self._pending_signals.get(signal_id)
            if signal:
                card = LarkCardBuilder.confirmed_card(
                    signal_id=signal.signal_id,
                    symbol=signal.symbol,
                    action=signal.action.value,
                    price=signal.price_target or 0,
                    quantity=signal.quantity or 0,
                )
                self._reply_client.update_card(message_id, card)
                logger.info("卡片已更新为已确认状态: signal=%s msg=%s", signal_id, message_id)
        return result

    async def _on_reject(self, signal_id: str, **kwargs):
        """拒绝回调：更新信号状态 + 推送拒绝卡片"""
        result = await self.handle_card_action(signal_id, "reject")
        # 发送新的拒绝卡片
        chat_id = kwargs.get('chat_id')
        if chat_id and self._reply_client:
            signal = self._pending_signals.get(signal_id)
            if signal:
                card = LarkCardBuilder.rejected_card(
                    signal_id=signal.signal_id,
                    symbol=signal.symbol,
                    action=signal.action.value,
                    price=signal.price_target or 0,
                    quantity=signal.quantity or 0,
                )
                self._reply_client.send_card(card, chat_id)
                logger.info("已发送拒绝卡片: signal=%s chat=%s", signal_id, chat_id)
        return result

    def on_execution(self, handler: Callable[[Signal], None]):
        """注册执行回调（确认后触发）"""
        self._execution_handler = handler

    async def push_signal_card(self, signal: Signal, chat_id: str = "") -> bool:
        """
        推送信号确认卡片到飞书。

        1. 记录信号到待确认列表
        2. 推送互动卡片
        3. 记录审计日志
        """
        self._pending_signals[signal.signal_id] = signal

        card = LarkCardBuilder.signal_confirm_card(
            signal_id=signal.signal_id,
            symbol=signal.symbol,
            action=signal.action.value,
            price=signal.price_target or 0,
            quantity=signal.quantity or 0,
            confidence=signal.confidence,
            rationale=signal.rationale,
        )

        success = await self._bot.push_card(card, chat_id)
        if success:
            self._audit_logger.log_pushed(signal.signal_id)
            logger.info("信号卡片已推送: %s %s %s", signal.symbol, signal.action.value, signal.signal_id)
        return success

    async def push_execution_result(self, signal: Signal, order_id: str, success: bool, chat_id: str = ""):
        """推送执行结果卡片"""
        card = LarkCardBuilder.execution_result_card(
            symbol=signal.symbol,
            action=signal.action.value,
            quantity=signal.quantity or 0,
            price=signal.price_target or 0,
            order_id=order_id,
            success=success,
        )
        return await self._bot.push_card(card, chat_id)

    async def push_risk_intercept(self, signal: Signal, reason: str, chat_id: str = ""):
        """推送风控拦截卡片"""
        card = LarkCardBuilder.risk_intercept_card(
            symbol=signal.symbol,
            action=signal.action.value,
            quantity=signal.quantity or 0,
            reason=reason,
        )
        return await self._bot.push_card(card, chat_id)

    async def push_signal_expired(self, signal: Signal, chat_id: str = ""):
        """推送信号过期卡片"""
        card = LarkCardBuilder.signal_expired_card(
            signal_id=signal.signal_id,
            symbol=signal.symbol,
        )
        return await self._bot.push_card(card, chat_id)

    async def handle_card_action(self, signal_id: str, action: str, modified_quantity: Optional[int] = None) -> ConfirmResult:
        """
        处理卡片 action 回调。

        Args:
            signal_id: 信号 ID
            action: confirm / reject / modify
            modified_quantity: 修改后的数量（modify 时使用）
        """
        confirm_action = ConfirmAction.CONFIRM if action == "confirm" else ConfirmAction.REJECT

        result = ConfirmResult(
            signal_id=signal_id,
            action=confirm_action,
            modified_quantity=modified_quantity,
        )

        # 记录审计
        self._audit_logger.log_confirmed(signal_id, result)

        # 触发执行（仅当确认时）
        signal = self._pending_signals.get(signal_id)
        if signal and confirm_action == ConfirmAction.CONFIRM:
            if modified_quantity:
                signal.quantity = modified_quantity
            signal.status = SignalStatus.CONFIRMED
            if self._execution_handler:
                self._execution_handler(signal)
                logger.info("信号确认，触发执行: %s", signal_id)
            else:
                logger.warning("信号已确认但未注册执行处理器: %s", signal_id)

        if signal and confirm_action == ConfirmAction.REJECT:
            signal.status = SignalStatus.REJECTED
            logger.info("信号已拒绝: %s", signal_id)

        return result

    def check_expired_signals(self) -> list[Signal]:
        """
        检查并处理过期信号。
        应在定时任务中定期调用。
        """
        expired = []
        expired_ids = []
        for sid, signal in self._pending_signals.items():
            if signal.status == SignalStatus.PENDING and signal.is_expired():
                signal.status = SignalStatus.EXPIRED
                expired.append(signal)
                expired_ids.append(sid)
                self._audit_logger.log_completed(sid)
                logger.info("信号已过期: %s %s", signal.symbol, sid)

        # 清理过期信号
        for sid in expired_ids:
            del self._pending_signals[sid]

        return expired

    @property
    def pending_count(self) -> int:
        """待确认信号数量"""
        return sum(1 for s in self._pending_signals.values() if s.status == SignalStatus.PENDING)
