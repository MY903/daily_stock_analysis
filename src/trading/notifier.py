"""交易通知模块

复用现有飞书 Webhook 能力，发送交易事件通知。
"""

import base64
import hashlib
import hmac
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

    通知抑制策略（降低重复通知干扰）：
    1. 时间冷却：同类通知在 cooldown_seconds 内不重复发送
    2. 次数限流：同类通知最多发 max_notifications_per_signal 次，
       之后在 reset_hours 小时内静默
    3. 活跃期抑制：标记为 "active_period" 的信号在活跃期内只发首次
    """

    # 活跃期信号类型 - 这些信号在活跃期内只发送一次
    ACTIVE_PERIOD_SIGNALS = {
        "买入信号",
        "止盈成交",
        "止损成交",
        "买入成交",
    }

    def __init__(self, config: AppConfig):
        self._config = config.notification
        self._symbol = config.trading.symbol
        self._enabled = config.notification.enabled
        self._webhook_url = config.notification.webhook_url
        self._webhook_secret = (config.notification.webhook_secret or "").strip()
        self._cooldown = max(0, int(config.notification.cooldown_seconds or 0))
        self._max_notifications = max(0, int(config.notification.max_notifications_per_signal or 0))
        self._reset_hours = max(1, int(config.notification.reset_hours or 24))
        self._last_sent: Dict[str, float] = {}
        self._sent_count: Dict[str, int] = {}
        self._session_start = time.time()

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

    def _should_suppress(self, title: str) -> bool:
        """判断是否应抑制此通知

        三层抑制策略：
        1. 活跃期抑制：ACTIVE_PERIOD_SIGNALS 在 session 内只发一次
        2. 时间冷却：同 title 在 cooldown_seconds 内不重复
        3. 次数限流：同 title 超过 max_notifications_per_signal 次后静默

        Returns:
            True=抑制（不发送）, False=可以发送
        """
        if not self._enabled:
            return True

        if not self._webhook_url:
            logger.debug("Webhook URL 未配置，跳过通知: %s", title)
            return True

        # === 检查重置 ===
        # 如果超出重置周期，清空该 title 的计数
        elapsed_since_start = time.time() - self._session_start
        if elapsed_since_start > self._reset_hours * 3600:
            self._sent_count.clear()
            self._last_sent.clear()
            self._session_start = time.time()
            logger.info("通知计数已重置（超过 %.1f 小时）", self._reset_hours)

        # === 1. 活跃期抑制 ===
        # 提取信号基础类型（取 title 中 " - " 前的部分）
        base_type = title.split(" - ")[0] if " - " in title else title
        if base_type in self.ACTIVE_PERIOD_SIGNALS:
            if self._sent_count.get(title, 0) >= 1:
                logger.info("活跃期抑制: %s（已发过通知，session 内不再重复）", title)
                return True

        # === 2. 时间冷却 ===
        if self._cooldown > 0:
            last = self._last_sent.get(title, 0.0)
            elapsed = time.time() - last
            if elapsed < self._cooldown:
                logger.debug("通知冷却中，跳过: %s (剩余 %.0f 秒)", title, self._cooldown - elapsed)
                return True

        # === 3. 次数限流 ===
        if self._max_notifications > 0:
            count = self._sent_count.get(title, 0)
            if count >= self._max_notifications:
                logger.info("次数限流: %s（已达上限 %d 次，%.1f 小时内不再发送）",
                            title, self._max_notifications, self._reset_hours)
                return True

        return False

    def _send(self, title: str, content: str, level: str = "info") -> None:
        """发送通知消息

        Args:
            title: 消息标题
            content: 消息正文
            level: 消息级别 (info/warning/error)
        """
        # 检查是否应抑制
        if self._should_suppress(title):
            return

        # 记录发送
        self._last_sent[title] = time.time()
        self._sent_count[title] = self._sent_count.get(title, 0) + 1

        # 构建飞书消息
        full_text = f"【{title}】\n{content}"

        payload: Dict[str, Any] = {
            "msg_type": "text",
            "content": {
                "text": full_text
            }
        }

        # 如果配置了 webhook 签名，添加 timestamp 和 sign
        if self._webhook_secret:
            timestamp = str(int(time.time()))
            string_to_sign = f"{timestamp}\n{self._webhook_secret}"
            sign = base64.b64encode(
                hmac.new(
                    string_to_sign.encode("utf-8"),
                    digestmod=hashlib.sha256,
                ).digest()
            ).decode("utf-8")
            payload["timestamp"] = timestamp
            payload["sign"] = sign

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
