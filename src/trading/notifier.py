"""交易通知模块

复用现有飞书 Webhook 能力，发送交易事件通知。
"""

import logging
import time
from typing import Dict, Any, Optional

import requests

from src.trading.config import AppConfig

logger = logging.getLogger(__name__)


class TradingNotifier:
    """交易事件通知器

    通过飞书 Webhook 发送交易机器人的各类事件通知：
    - 启动/停止
    - 买入/卖出信号
    - 订单成交
    - 异常告警
    - 每日汇总
    """

    def __init__(self, config: AppConfig):
        self._config = config.notification
        self._symbol = config.trading.symbol
        self._enabled = config.notification.enabled
        self._webhook_url = config.notification.webhook_url
        self._webhook_secret = config.notification.webhook_secret

    def notify_startup(self, mode: str, environment: str) -> None:
        """通知机器人启动"""
        self._send(
            title="交易机器人启动",
            content=(
                f"标的: {self._symbol}\n"
                f"模式: {'自动交易' if mode == 'auto' else '仅告警'}\n"
                f"环境: {environment}\n"
                f"时间: {self._now()}"
            ),
            level="info",
        )

    def notify_shutdown(self, reason: str = "正常退出") -> None:
        """通知机器人停止"""
        self._send(
            title="交易机器人停止",
            content=f"原因: {reason}\n时间: {self._now()}",
            level="warning",
        )

    def notify_buy_signal(self, price: float, trigger_price: float,
                          quantity: int, auto_trade: bool) -> None:
        """通知买入信号触发"""
        action = "已提交买入单" if auto_trade else "仅通知（未开启自动交易）"
        self._send(
            title=f"买入信号 - {self._symbol}",
            content=(
                f"当前价: ${price:.2f}\n"
                f"触发价: ${trigger_price:.2f}\n"
                f"数量: {quantity} 股\n"
                f"操作: {action}\n"
                f"时间: {self._now()}"
            ),
            level="info",
        )

    def notify_buy_filled(self, fill_price: float, quantity: int,
                          tp_price: float, sl_price: float) -> None:
        """通知买入成交"""
        cost = fill_price * quantity
        self._send(
            title=f"买入成交 - {self._symbol}",
            content=(
                f"成交价: ${fill_price:.2f}\n"
                f"数量: {quantity} 股\n"
                f"成本: ${cost:.2f}\n"
                f"止盈目标: ${tp_price:.2f} (+{((tp_price/fill_price)-1)*100:.1f}%)\n"
                f"止损目标: ${sl_price:.2f} (-{(1-(sl_price/fill_price))*100:.1f}%)\n"
                f"时间: {self._now()}"
            ),
            level="info",
        )

    def notify_take_profit(self, fill_price: float, entry_price: float,
                           quantity: int) -> None:
        """通知止盈成交"""
        pnl = (fill_price - entry_price) * quantity
        pnl_pct = (fill_price - entry_price) / entry_price * 100
        self._send(
            title=f"止盈成交 - {self._symbol}",
            content=(
                f"卖出价: ${fill_price:.2f}\n"
                f"买入价: ${entry_price:.2f}\n"
                f"数量: {quantity} 股\n"
                f"盈利: ${pnl:.2f} (+{pnl_pct:.1f}%)\n"
                f"时间: {self._now()}"
            ),
            level="info",
        )

    def notify_stop_loss(self, fill_price: float, entry_price: float,
                         quantity: int) -> None:
        """通知止损成交"""
        pnl = (fill_price - entry_price) * quantity
        pnl_pct = (fill_price - entry_price) / entry_price * 100
        self._send(
            title=f"止损成交 - {self._symbol}",
            content=(
                f"卖出价: ${fill_price:.2f}\n"
                f"买入价: ${entry_price:.2f}\n"
                f"数量: {quantity} 股\n"
                f"亏损: ${pnl:.2f} ({pnl_pct:.1f}%)\n"
                f"时间: {self._now()}"
            ),
            level="warning",
        )

    def notify_error(self, error_type: str, detail: str) -> None:
        """通知异常"""
        self._send(
            title=f"异常告警 - {self._symbol}",
            content=(
                f"类型: {error_type}\n"
                f"详情: {detail}\n"
                f"时间: {self._now()}"
            ),
            level="error",
        )

    def notify_reconnect(self, attempt: int, success: bool) -> None:
        """通知重连事件"""
        status = "成功" if success else "失败"
        self._send(
            title=f"WebSocket 重连{status}",
            content=(
                f"尝试次数: {attempt}\n"
                f"时间: {self._now()}"
            ),
            level="warning" if not success else "info",
        )

    def notify_daily_summary(self, summary: Dict[str, Any]) -> None:
        """发送每日汇总"""
        self._send(
            title=f"每日汇总 - {self._symbol}",
            content=(
                f"状态: {summary.get('state', 'N/A')}\n"
                f"持仓: {summary.get('position', 0)} 股\n"
                f"今日交易: {summary.get('trades_today', 0)} 笔\n"
                f"今日盈亏: ${summary.get('pnl_today', 0):.2f}\n"
                f"累计盈亏: ${summary.get('pnl_total', 0):.2f}\n"
                f"运行时长: {summary.get('uptime', 'N/A')}\n"
                f"时间: {self._now()}"
            ),
            level="info",
        )

    # ==================== 内部方法 ====================

    def _send(self, title: str, content: str, level: str = "info") -> None:
        """发送通知消息

        Args:
            title: 消息标题
            content: 消息正文
            level: 消息级别 (info/warning/error)
        """
        if not self._enabled:
            return

        if not self._webhook_url:
            logger.debug("Webhook URL 未配置，跳过通知: %s", title)
            return

        # 构建飞书消息
        full_text = f"【{title}】\n{content}"

        payload = {
            "msg_type": "text",
            "content": {
                "text": full_text
            }
        }

        try:
            response = requests.post(
                self._webhook_url,
                json=payload,
                timeout=10,
            )
            if response.status_code == 200:
                result = response.json()
                if result.get("code") == 0 or result.get("StatusCode") == 0:
                    logger.debug("通知发送成功: %s", title)
                else:
                    logger.warning("通知发送返回异常: %s, response=%s", title, result)
            else:
                logger.warning("通知发送失败: %s, status=%d", title, response.status_code)
        except Exception as e:
            logger.error("通知发送异常: %s, error=%s", title, e)

    @staticmethod
    def _now() -> str:
        """格式化当前时间"""
        return time.strftime("%Y-%m-%d %H:%M:%S")
