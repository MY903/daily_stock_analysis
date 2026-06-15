# -*- coding: utf-8 -*-
"""
飞书互动卡片 Bot

使用 lark-oapi SDK Stream 模式，实现双向交互卡片。
支持信号确认卡片推送和回调处理。
"""

import logging
from typing import Any, Optional, Callable

logger = logging.getLogger(__name__)

# 卡片消息类型常量
CARD_SIGNAL_CONFIRM = "signal_confirm"      # 信号确认卡
CARD_EXECUTION_RESULT = "execution_result"   # 执行结果卡
CARD_RISK_INTERCEPT = "risk_intercept"       # 风控拦截卡
CARD_SIGNAL_EXPIRED = "signal_expired"       # 信号过期卡


class LarkCardBuilder:
    """飞书互动卡片构建器（使用卡片 JSON 格式）"""

    @staticmethod
    def signal_confirm_card(signal_id: str, symbol: str, action: str,
                           price: float, quantity: int, confidence: float,
                           rationale: str) -> dict:
        """
        构建信号确认卡片，包含确认/拒绝按钮。

        卡片使用飞书消息卡片 JSON 格式 v4。
        """
        return {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": f"🤖 交易信号确认 - {symbol}"},
                "template": "blue"
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {"tag": "lark_md", "content": f"**标的**: {symbol}\n**方向**: {action}\n**价格**: ${price:.2f}\n**数量**: {quantity}股\n**置信度**: {confidence*100:.0f}%\n**理据**: {rationale}\n**信号ID**: `{signal_id}`"}
                },
                {"tag": "hr"},
                {
                    "tag": "action",
                    "actions": [
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "✅ 确认交易"},
                            "type": "primary",
                            "value": {"action": "confirm", "signal_id": signal_id}
                        },
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "❌ 拒绝"},
                            "type": "danger",
                            "value": {"action": "reject", "signal_id": signal_id}
                        }
                    ]
                }
            ]
        }

    @staticmethod
    def execution_result_card(symbol: str, action: str, quantity: int,
                            price: float, order_id: str, success: bool) -> dict:
        """执行结果卡片"""
        template = "green" if success else "red"
        title = f"✅ {symbol} 订单已执行" if success else f"❌ {symbol} 订单执行失败"
        return {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": title},
                "template": template
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {"tag": "lark_md", "content": f"**标的**: {symbol}\n**方向**: {action}\n**数量**: {quantity}股\n**价格**: ${price:.2f}\n**订单ID**: {order_id}"}
                }
            ]
        }

    @staticmethod
    def risk_intercept_card(symbol: str, action: str, quantity: int,
                           reason: str) -> dict:
        """风控拦截卡片"""
        return {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": f"⚠️ 风控拦截 - {symbol}"},
                "template": "yellow"
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {"tag": "lark_md", "content": f"**标的**: {symbol}\n**方向**: {action}\n**数量**: {quantity}股\n**拦截原因**: {reason}"}
                }
            ]
        }

    @staticmethod
    def signal_expired_card(signal_id: str, symbol: str) -> dict:
        """信号过期卡片"""
        return {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": f"⏰ 信号已过期 - {symbol}"},
                "template": "grey"
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {"tag": "lark_md", "content": f"**信号ID**: `{signal_id}`\n该信号在有效期内未获得确认，已自动过期。"}
                }
            ]
        }


class FeishuCardActionHandler:
    """
    飞书卡片回调事件处理器 (POC)

    处理来自飞书的 P2CardActionTriggerV1 事件（用户点击卡片按钮后的回调），
    解析 action（confirm/reject）和 signal_id，记录日志并回复确认消息。

    使用方式：
        handler = FeishuCardActionHandler(reply_client)
        event_handler_builder = handler.register_card_handler(event_handler_builder)
    """

    def __init__(self, reply_client: Optional[Any] = None):
        """
        Args:
            reply_client: FeishuReplyClient 实例，用于发送回复消息
        """
        self._reply_client = reply_client

    def register_card_handler(self, event_handler_builder) -> object:
        """
        向 EventDispatcherHandlerBuilder 注册 P2CardActionTriggerV1 事件处理器。

        Args:
            event_handler_builder: lark.EventDispatcherHandler.builder() 返回的 builder

        Returns:
            注册后的 builder（支持链式调用）
        """
        try:
            event_handler_builder.register_p2_card_action_trigger(self.handle_card_action)
            logger.info("[FeishuCardAction] P2CardActionTriggerV1 事件处理器已注册")
        except Exception as e:
            logger.error(f"[FeishuCardAction] 注册事件处理器失败: {e}")
        return event_handler_builder

    def handle_card_action(self, event) -> object:
        """
        处理卡片按钮回调事件（P2CardActionTriggerV1）。

        解析用户点击的按钮 value 中的 action（confirm/reject）和 signal_id，
        记录日志，并通过 FeishuReplyClient 发送"已收到"回复。

        Args:
            event: P2CardActionTrigger 事件对象

        Returns:
            P2CardActionTriggerResponse
        """
        from lark_oapi.event.callback.model.p2_card_action_trigger import (
            P2CardActionTriggerResponse,
        )

        try:
            # 解析事件数据
            event_data = getattr(event, 'event', None)
            if event_data is None:
                logger.warning("[FeishuCardAction] 收到空事件数据")
                return P2CardActionTriggerResponse({"toast": {"content": "处理失败"}})

            # 从 action.value 中提取自定义字段
            action_obj = getattr(event_data, 'action', None)
            context_obj = getattr(event_data, 'context', None)

            if action_obj is None:
                logger.warning("[FeishuCardAction] 事件缺少 action 字段")
                return P2CardActionTriggerResponse({"toast": {"content": "处理失败"}})

            value = getattr(action_obj, 'value', {}) or {}
            action = value.get('action', 'unknown')
            signal_id = value.get('signal_id', 'unknown')

            # 获取发送回复所需的 chat_id
            chat_id = None
            if context_obj is not None:
                chat_id = getattr(context_obj, 'open_chat_id', None)

            # 记录日志
            action_label = "confirm" if action == "confirm" else "reject" if action == "reject" else action
            logger.info(
                "[LarkCard] Received card action: %s for signal %s",
                action_label,
                signal_id,
            )

            # 通过 FeishuReplyClient 发送回复消息
            if self._reply_client and chat_id:
                reply_text = "已收到确认" if action == "confirm" else "已收到拒绝"
                self._reply_client.send_to_chat(chat_id, reply_text)
                logger.debug(
                    "[FeishuCardAction] 已向 chat=%s 发送回复: %s", chat_id, reply_text
                )
            elif not chat_id:
                logger.debug("[FeishuCardAction] 无法获取 chat_id，跳过回复")
            else:
                logger.debug("[FeishuCardAction] 未配置 reply_client，跳过回复")

            # 返回成功响应（含 Toast）
            toast_text = "处理成功" if action in ("confirm", "reject") else f"未知操作: {action}"
            return P2CardActionTriggerResponse({"toast": {"content": toast_text}})

        except Exception as e:
            logger.error(f"[FeishuCardAction] 处理卡片回调失败: {e}")
            logger.exception(e)
            from lark_oapi.event.callback.model.p2_card_action_trigger import (
                P2CardActionTriggerResponse,
            )
            return P2CardActionTriggerResponse({"toast": {"content": "处理失败"}})


class LarkInteractiveBot:
    """飞书互动卡片 Bot（Stream 模式骨架）"""

    def __init__(self, app_id: str = "", app_secret: str = ""):
        self._app_id = app_id
        self._app_secret = app_secret
        self._running = False
        self._confirm_handler: Optional[Callable] = None
        self._reject_handler: Optional[Callable] = None

    def on_confirm(self, handler: Callable):
        """注册确认回调"""
        self._confirm_handler = handler

    def on_reject(self, handler: Callable):
        """注册拒绝回调"""
        self._reject_handler = handler

    async def push_card(self, card: dict, chat_id: str = "") -> bool:
        """
        推送互动卡片到飞书。
        当前为骨架实现，返回 True 表示模拟成功。

        TODO: 使用 lark-oapi SDK 实现真实推送
        """
        logger.info(f"[LarkBot] Push card to {chat_id or 'default chat'}: "
                    f"{card.get('header', {}).get('title', {}).get('content', 'No title')}")
        return True

    def start(self):
        """启动 Bot（骨架）"""
        self._running = True
        logger.info("Lark Interactive Bot started (skeleton mode)")

    def stop(self):
        """停止 Bot"""
        self._running = False
        logger.info("Lark Interactive Bot stopped")
