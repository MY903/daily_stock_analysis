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
    def confirmed_card(signal_id: str, symbol: str, action: str,
                      price: float, quantity: int) -> dict:
        """
        Build a post-confirm card with buttons replaced by '已确认' text.

        This card is used to update the original signal confirm card in-place,
        disabling further button interactions (anti-double-click).
        """
        return {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": f"✅ 信号已确认 - {symbol}"},
                "template": "green"
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {"tag": "lark_md", "content": f"**标的**: {symbol}\n**方向**: {action}\n**价格**: ${price:.2f}\n**数量**: {quantity}股\n**信号ID**: `{signal_id}`"}
                },
                {"tag": "hr"},
                {
                    "tag": "div",
                    "text": {"tag": "lark_md", "content": "✅ **交易已确认，即将执行**"}
                }
            ]
        }

    @staticmethod
    def rejected_card(signal_id: str, symbol: str, action: str,
                      price: float, quantity: int) -> dict:
        """
        Build a post-reject card showing '已拒绝'.

        This card is sent as a new message (not an update) after rejection.
        """
        return {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": f"❌ 信号已拒绝 - {symbol}"},
                "template": "red"
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {"tag": "lark_md", "content": f"**标的**: {symbol}\n**方向**: {action}\n**价格**: ${price:.2f}\n**数量**: {quantity}股\n**信号ID**: `{signal_id}`"}
                },
                {"tag": "hr"},
                {
                    "tag": "div",
                    "text": {"tag": "lark_md", "content": "❌ **交易已拒绝，不会执行**"}
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
    解析 action（confirm/reject）和 signal_id，记录日志并调用已注册的确认/拒绝回调。

    使用方式：
        handler = FeishuCardActionHandler(reply_client)
        handler.set_confirm_handler(my_on_confirm)
        handler.set_reject_handler(my_on_reject)
        event_handler_builder = handler.register_card_handler(event_handler_builder)
    """

    def __init__(self, reply_client: Optional[Any] = None):
        """
        Args:
            reply_client: FeishuReplyClient 实例，用于发送回复消息
        """
        self._reply_client = reply_client
        self._confirm_handler: Optional[Callable] = None
        self._reject_handler: Optional[Callable] = None

    def set_confirm_handler(self, handler: Callable):
        """
        Register the confirm callback.

        The handler should accept (signal_id: str, **kwargs) where kwargs
        may include message_id, chat_id for card updates.
        """
        self._confirm_handler = handler

    def set_reject_handler(self, handler: Callable):
        """
        Register the reject callback.

        The handler should accept (signal_id: str, **kwargs) where kwargs
        may include message_id, chat_id for card updates.
        """
        self._reject_handler = handler

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
        提取 message_id 和 chat_id，调用已注册的确认/拒绝回调处理器。

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

            # 获取卡片消息上下文：chat_id + message_id
            chat_id = None
            message_id = None
            if context_obj is not None:
                chat_id = getattr(context_obj, 'open_chat_id', None)
                message_id = getattr(context_obj, 'open_message_id', None)

            # 记录日志
            action_label = "confirm" if action == "confirm" else "reject" if action == "reject" else action
            logger.info(
                "[LarkCard] Received card action: %s for signal %s (msg=%s, chat=%s)",
                action_label,
                signal_id,
                message_id,
                chat_id,
            )

            # 调用已注册的回调处理器
            if action == "confirm" and self._confirm_handler:
                logger.debug("[FeishuCardAction] 调用确认回调: signal=%s", signal_id)
                self._confirm_handler(
                    signal_id,
                    message_id=message_id,
                    chat_id=chat_id,
                )
            elif action == "reject" and self._reject_handler:
                logger.debug("[FeishuCardAction] 调用拒绝回调: signal=%s", signal_id)
                self._reject_handler(
                    signal_id,
                    message_id=message_id,
                    chat_id=chat_id,
                )

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
    """飞书互动卡片 Bot（Stream 模式）"""

    def __init__(self, app_id: str = "", app_secret: str = ""):
        from config.settings import settings
        self._app_id = app_id or settings.LARK_APP_ID
        self._app_secret = app_secret or settings.LARK_APP_SECRET
        self._default_chat_id = settings.LARK_DEFAULT_CHAT_ID
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

        使用 FeishuReplyClient 的 send_card 方法发送卡片 JSON。
        如果 FeishuStreamClient 不可用，降级为日志记录。
        """
        target_chat_id = chat_id or self._default_chat_id

        if not target_chat_id:
            logger.warning("[LarkBot] 未指定 chat_id 且未配置 LARK_DEFAULT_CHAT_ID")
            return False

        try:
            from bot.platforms.feishu_stream import get_feishu_stream_client, \
                FeishuReplyClient

            # 获取 FeishuReplyClient 实例
            stream_client = get_feishu_stream_client()
            if stream_client is not None and stream_client._reply_client is not None:
                reply_client = stream_client._reply_client
            else:
                # Stream 客户端未启动时直接创建 FeishuReplyClient
                try:
                    reply_client = FeishuReplyClient(
                        self._app_id, self._app_secret
                    )
                except (ImportError, ValueError) as e:
                    logger.warning(
                        "[LarkBot] 无法创建 FeishuReplyClient: %s，"
                        "降级为日志模式", e
                    )
                    logger.info(
                        "[LarkBot] (降级) 卡片标题: %s",
                        card.get("header", {}).get("title", {}).get(
                            "content", "无标题"
                        ),
                    )
                    return True

            result = reply_client.send_card(card, target_chat_id)
            if result:
                logger.info(
                    "[LarkBot] 卡片已推送到 %s: %s",
                    target_chat_id,
                    card.get("header", {}).get("title", {}).get(
                        "content", "无标题"
                    ),
                )
            else:
                logger.error(
                    "[LarkBot] 推送卡片到 %s 失败", target_chat_id
                )
            return result

        except Exception as e:
            logger.error("[LarkBot] 推送卡片异常: %s", e)
            logger.exception(e)
            return False

    def start(self):
        """启动 Bot（骨架）"""
        self._running = True
        logger.info("Lark Interactive Bot started (skeleton mode)")

    def stop(self):
        """停止 Bot"""
        self._running = False
        logger.info("Lark Interactive Bot stopped")
