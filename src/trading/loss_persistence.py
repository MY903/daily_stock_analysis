"""
日亏损 SQLite 持久化存储。

提供 DailyLossStore 类，用于将每日交易亏损写入 SQLite 数据库，
支持跨进程/跨重启恢复每日累计亏损数据。
"""

import sqlite3
import logging
from datetime import datetime, date
from typing import Optional

logger = logging.getLogger(__name__)


class DailyLossStore:
    """日亏损 SQLite 持久化存储。"""

    def __init__(self, db_path: str = "data/daily_loss.db"):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """获取数据库连接（每次调用创建新连接以确保线程安全）"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """初始化数据库表结构"""
        conn = self._get_connection()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS daily_loss (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    loss_pct REAL NOT NULL,
                    timestamp TEXT NOT NULL,
                    date TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_daily_loss_date
                ON daily_loss(date)
            """)
            conn.commit()
        finally:
            conn.close()

    def load_today_loss(self) -> float:
        """加载今日累计亏损百分比。

        Returns:
            今日所有亏损记录的 loss_pct 之和，无记录时返回 0.0。
        """
        today_str = date.today().isoformat()
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                "SELECT COALESCE(SUM(loss_pct), 0.0) AS total FROM daily_loss WHERE date = ?",
                (today_str,),
            )
            row = cursor.fetchone()
            return float(row["total"])
        finally:
            conn.close()

    def append_loss(self, symbol: str, loss_pct: float, timestamp: Optional[datetime] = None):
        """追加一笔亏损记录。

        Args:
            symbol: 标的代码
            loss_pct: 亏损百分比（正数）
            timestamp: 交易时间戳，默认为当前时间
        """
        if timestamp is None:
            timestamp = datetime.now()
        today_str = timestamp.date().isoformat()
        ts_str = timestamp.isoformat()

        conn = self._get_connection()
        try:
            conn.execute(
                "INSERT INTO daily_loss (symbol, loss_pct, timestamp, date) VALUES (?, ?, ?, ?)",
                (symbol, loss_pct, ts_str, today_str),
            )
            conn.commit()
        finally:
            conn.close()

    def reset_daily(self):
        """清空今日的所有亏损记录。"""
        today_str = date.today().isoformat()
        conn = self._get_connection()
        try:
            conn.execute("DELETE FROM daily_loss WHERE date = ?", (today_str,))
            conn.commit()
        finally:
            conn.close()
