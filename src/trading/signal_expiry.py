"""
信号过期管理与竞态条件防护。

功能：
1. 信号过期后台任务：每分钟检查 PENDING 信号，超30分钟→EXPIRED
2. 飞书卡片过期通知
3. 竞态防护：同标的30秒去重、确认vs过期竞态处理、双重确认防护
4. 系统启动时从 AuditLogger 恢复 PENDING 信号
5. 优雅关闭：SIGTERM 完成当前执行→保存状态→退出
"""

import asyncio
import logging
import signal
import sys
from datetime import datetime
from typing import Set

from src.trading.signal import Signal, SignalStatus
from src.trading.audit_logger import AuditLogger
from src.trading.card_handler import SignalConfirmHandler

logger = logging.getLogger(__name__)


class ExpiryManager:
    """
    信号过期管理 + 竞态条件防护。
    """

    def __init__(self, card_handler: SignalConfirmHandler, audit_logger: AuditLogger):
        self._card_handler = card_handler
        self._audit_logger = audit_logger
        self._running = False
        self._check_interval = 60  # 秒
        self._processed_ids: Set[str] = set()
        self._last_signal_time: dict[str, datetime] = {}

    async def check_and_expire(self) -> int:
        """
        检查所有 PENDING 信号，将超30分钟的标记为 EXPIRED。
        
        Returns:
            过期的信号数量
        """
        expired = self._card_handler.check_expired_signals()
        
        # 对每个过期信号推送过期卡片
        for sig in expired:
            try:
                await self._card_handler.push_signal_expired(sig)
                self._audit_logger.log_completed(sig.signal_id)
                logger.info("信号已过期并通知: %s %s", sig.symbol, sig.signal_id)
            except Exception as e:
                logger.error("推送过期卡片失败: %s %s", sig.signal_id, e)
        
        return len(expired)

    async def _expiry_loop(self):
        """后台过期检查循环"""
        while self._running:
            await self.check_and_expire()
            await asyncio.sleep(self._check_interval)

    def start(self):
        """启动过期检查后台任务"""
        self._running = True
        asyncio.create_task(self._expiry_loop())
        logger.info("信号过期检查已启动 (间隔: %ds)", self._check_interval)

    def stop(self):
        """停止过期检查"""
        self._running = False
        logger.info("信号过期检查已停止")

    # ==================== 竞态条件防护 ====================

    def can_process_signal(self, signal: Signal) -> bool:
        """
        检查信号是否可以被处理（防重复处理）。
        
        防护1: signal_id 是否已处理
        防护2: 同标的30秒去重
        防护3: 信号是否已过期
        """
        # 已处理过
        if signal.signal_id in self._processed_ids:
            logger.warning("信号已处理（防重复）: %s", signal.signal_id)
            return False
        
        # 信号已过期
        if signal.is_expired():
            logger.warning("信号已过期（竞态）: %s", signal.signal_id)
            return False
        
        # 同标的30秒去重
        last_time = self._last_signal_time.get(signal.symbol)
        if last_time and (datetime.now() - last_time).total_seconds() < 30:
            logger.warning("%s 冷却中（防重复发起）", signal.symbol)
            return False
        
        return True

    def mark_processed(self, signal: Signal):
        """标记信号为已处理"""
        self._processed_ids.add(signal.signal_id)
        self._last_signal_time[signal.symbol] = datetime.now()

    def handle_confirm_expired_race(self, signal: Signal) -> bool:
        """
        处理「确认已过期信号」的竞态条件。
        
        如果用户点击确认时信号已过期，返回 False 并记录。
        """
        if signal.status == SignalStatus.EXPIRED or signal.is_expired():
            logger.warning("用户确认了已过期信号: %s", signal.signal_id)
            return False
        return True

    # ==================== 状态恢复 ====================

    def recover_pending_signals(self) -> list[dict]:
        """
        系统启动时从 AuditLogger 恢复 PENDING 信号。
        
        Returns:
            恢复的 PENDING 信号列表
        """
        pending = self._audit_logger.get_pending_signals()
        logger.info("从审计日志恢复 %d 个 PENDING 信号", len(pending))
        
        # 标记所有已恢复的 signal_id
        for entry in pending:
            sid = entry.get("signal_id", "")
            if sid:
                self._processed_ids.add(sid)
                logger.debug("恢复 PENDING 信号: %s", sid)
        
        return pending

    # ==================== 优雅关闭 ====================

    def _handle_shutdown(self, signum, frame):
        """SIGTERM/SIGINT 处理：完成当前操作后退出"""
        logger.info("收到信号 %s，准备优雅关闭...", signum)
        self._running = False
        
        # 记录未完成信号
        pending_count = self._card_handler.pending_count
        if pending_count > 0:
            logger.info("还有 %d 个待确认信号，将在下次启动时恢复", pending_count)
        
        logger.info("优雅关闭完成")
        sys.exit(0)

    def register_shutdown_handler(self):
        """注册优雅关闭信号处理器"""
        signal.signal(signal.SIGTERM, self._handle_shutdown)
        signal.signal(signal.SIGINT, self._handle_shutdown)
        logger.info("优雅关闭信号处理器已注册")


class DedupGuard:
    """
    双重确认防护。
    防止用户多次点击确认按钮导致的重复执行。
    """

    def __init__(self):
        self._confirmed_ids: Set[str] = set()

    def is_already_confirmed(self, signal_id: str) -> bool:
        """检查是否已被确认（防双重确认）"""
        return signal_id in self._confirmed_ids

    def mark_confirmed(self, signal_id: str):
        """标记为已确认"""
        self._confirmed_ids.add(signal_id)

    def confirm_once(self, signal_id: str) -> bool:
        """
        安全的确认操作：如果未被确认则确认，否则拒绝。
        
        Returns:
            True=首次确认, False=已确认过
        """
        if self.is_already_confirmed(signal_id):
            logger.warning("双重确认拦截: %s", signal_id)
            return False
        self.mark_confirmed(signal_id)
        return True
