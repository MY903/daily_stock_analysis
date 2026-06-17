"""
信号审计日志模块

追踪信号生命周期：created → pushed → confirmed/rejected/expired → executed → completed/failed
使用 SQLite 存储，提供查询和自动清理功能。
"""

import logging
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List

from src.trading.signal import Signal, SignalStatus, ConfirmResult

logger = logging.getLogger(__name__)

DB_DIR = Path(__file__).resolve().parent.parent.parent / "data"
DB_PATH = DB_DIR / "audit_log.db"


class AuditLogger:
    """信号审计日志管理器"""

    def __init__(self, db_path: str = str(DB_PATH)):
        self._db_path = db_path
        self._ensure_db()

    def _ensure_db(self):
        """确保数据库和表存在"""
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS signal_audit (
                    log_id TEXT PRIMARY KEY,
                    signal_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    action TEXT NOT NULL,
                    signal_json TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'PENDING',
                    created_at TEXT NOT NULL,
                    pushed_at TEXT,
                    confirm_action TEXT,
                    confirm_result_json TEXT,
                    executed_at TEXT,
                    execution_result TEXT,
                    completed_at TEXT,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_signal_audit_signal_id
                ON signal_audit(signal_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_signal_audit_status
                ON signal_audit(status)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_signal_audit_created
                ON signal_audit(created_at)
            """)
            conn.commit()

    def _get_conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path)

    # ==================== 写操作 ====================

    def log_created(self, signal: Signal) -> str:
        """记录信号创建"""
        now = datetime.now().isoformat()
        with self._get_conn() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO signal_audit
                (log_id, signal_id, symbol, action, signal_json, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                str(signal.signal_id),
                signal.signal_id,
                signal.symbol,
                signal.action.value,
                signal.model_dump_json(),
                signal.status.value,
                now,
                now,
            ))
            conn.commit()
        logger.debug("审计日志: 信号创建 %s (%s %s)", signal.signal_id, signal.symbol, signal.action.value)
        return str(signal.signal_id)

    def log_pushed(self, signal_id: str):
        """记录信号已推送到飞书"""
        now = datetime.now().isoformat()
        with self._get_conn() as conn:
            conn.execute(
                "UPDATE signal_audit SET pushed_at=?, updated_at=? WHERE signal_id=?",
                (now, now, signal_id),
            )
            conn.commit()

    def log_confirmed(self, signal_id: str, confirm: ConfirmResult):
        """记录人工确认结果"""
        now = datetime.now().isoformat()
        with self._get_conn() as conn:
            conn.execute("""
                UPDATE signal_audit
                SET status=?, confirm_action=?, confirm_result_json=?, updated_at=?
                WHERE signal_id=?
            """, (
                SignalStatus.CONFIRMED.value if confirm.action.value == "CONFIRM"
                else SignalStatus.REJECTED.value,
                confirm.action.value,
                confirm.model_dump_json(),
                now,
                signal_id,
            ))
            conn.commit()

    def log_executed(self, signal_id: str, order_id: str):
        """记录订单已执行"""
        now = datetime.now().isoformat()
        with self._get_conn() as conn:
            conn.execute("""
                UPDATE signal_audit
                SET status=?, executed_at=?, execution_result=?, updated_at=?
                WHERE signal_id=?
            """, (SignalStatus.EXECUTED.value, now, f"order_id={order_id}", now, signal_id))
            conn.commit()

    def log_failed(self, signal_id: str, error: str):
        """记录执行失败"""
        now = datetime.now().isoformat()
        with self._get_conn() as conn:
            conn.execute("""
                UPDATE signal_audit
                SET status=?, execution_result=?, updated_at=?
                WHERE signal_id=?
            """, (SignalStatus.FAILED.value, f"error={error}", now, signal_id))
            conn.commit()

    def log_completed(self, signal_id: str):
        """记录信号完成（最终状态）"""
        now = datetime.now().isoformat()
        with self._get_conn() as conn:
            conn.execute(
                "UPDATE signal_audit SET completed_at=?, updated_at=? WHERE signal_id=?",
                (now, now, signal_id),
            )
            conn.commit()

    # ==================== 查询操作 ====================

    def get_signal_history(self, signal_id: str) -> Optional[dict]:
        """查询单个信号的历史记录"""
        with self._get_conn() as conn:
            cursor = conn.execute(
                "SELECT * FROM signal_audit WHERE signal_id=?",
                (signal_id,),
            )
            row = cursor.fetchone()
            if row:
                columns = [d[0] for d in cursor.description]
                return dict(zip(columns, row))
            return None

    def get_pending_signals(self) -> List[dict]:
        """查询所有 PENDING 状态的信号"""
        with self._get_conn() as conn:
            cursor = conn.execute(
                "SELECT * FROM signal_audit WHERE status='PENDING' ORDER BY created_at DESC"
            )
            columns = [d[0] for d in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def get_daily_stats(self, date: Optional[str] = None) -> dict:
        """获取指定日期的统计信息"""
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
        with self._get_conn() as conn:
            cursor = conn.execute(
                "SELECT status, COUNT(*) as cnt FROM signal_audit WHERE created_at LIKE ? GROUP BY status",
                (f"{date}%",),
            )
            rows = cursor.fetchall()
            stats = {
                "date": date,
                "total": 0,
                "confirmed": 0,
                "rejected": 0,
                "expired": 0,
                "executed": 0,
                "failed": 0,
                "pending": 0,
            }
            for row in rows:
                status, count = row
                stats["total"] += count
                status_key = status.lower()
                if status_key in stats:
                    stats[status_key] = count
            return stats

    def get_all_signals(self, limit: int = 50, offset: int = 0, status: Optional[str] = None) -> List[dict]:
        """查询所有信号记录，支持分页和可选的 status 筛选

        Args:
            limit: 返回记录数上限
            offset: 分页偏移量
            status: 按状态筛选（PENDING/CONFIRMED/REJECTED/EXPIRED/EXECUTED/FAILED）

        Returns:
            按 created_at DESC 排序的信号记录列表
        """
        with self._get_conn() as conn:
            if status:
                cursor = conn.execute(
                    "SELECT * FROM signal_audit WHERE status=? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                    (status, limit, offset),
                )
            else:
                cursor = conn.execute(
                    "SELECT * FROM signal_audit ORDER BY created_at DESC LIMIT ? OFFSET ?",
                    (limit, offset),
                )
            columns = [d[0] for d in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

    # ==================== 维护操作 ====================

    def clean_old_records(self, days: int = 90):
        """清理指定天数前的记录"""
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        with self._get_conn() as conn:
            cursor = conn.execute(
                "DELETE FROM signal_audit WHERE created_at < ?",
                (cutoff,),
            )
            deleted = cursor.rowcount
            conn.commit()
        if deleted > 0:
            logger.info("审计日志清理: 删除了 %d 条 %d 天前的记录", deleted, days)
        return deleted
