"""交易记录器

记录所有交易到 CSV 文件，支持每日报告生成。
"""

import csv
import json
import logging
import time
from pathlib import Path
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class TradeRecorder:
    """交易记录持久化

    - 交易记录：data/trades.csv
    - 每日报告：data/daily_report_YYYY-MM-DD.json
    """

    CSV_HEADERS = [
        "trade_id", "timestamp", "symbol", "action", "order_type",
        "quantity", "price", "fill_price", "pnl", "pnl_pct",
        "mode", "state_before", "state_after",
    ]

    def __init__(self, data_dir: str = "./data"):
        self._data_dir = Path(data_dir)
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._trades_file = self._data_dir / "trades.csv"
        self._trade_count = 0

        # 确保 CSV 文件存在且有表头
        if not self._trades_file.exists():
            self._write_csv_header()
        else:
            # 统计已有记录数（用于生成 trade_id）
            self._trade_count = self._count_existing_trades()

    def record_buy(self, symbol: str, quantity: int, price: float,
                   fill_price: float, mode: str) -> str:
        """记录买入交易"""
        trade_id = self._generate_id("BUY")
        self._append_trade({
            "trade_id": trade_id,
            "timestamp": self._now(),
            "symbol": symbol,
            "action": "BUY",
            "order_type": "LMT",
            "quantity": quantity,
            "price": price,
            "fill_price": fill_price,
            "pnl": 0,
            "pnl_pct": 0,
            "mode": mode,
            "state_before": "BUY_PENDING",
            "state_after": "HOLDING",
        })
        return trade_id

    def record_sell(self, symbol: str, quantity: int, price: float,
                    fill_price: float, entry_price: float,
                    sell_type: str, mode: str) -> str:
        """记录卖出交易（止盈或止损）"""
        pnl = (fill_price - entry_price) * quantity
        pnl_pct = (fill_price - entry_price) / entry_price * 100 if entry_price else 0

        trade_id = self._generate_id("SELL")
        self._append_trade({
            "trade_id": trade_id,
            "timestamp": self._now(),
            "symbol": symbol,
            "action": f"SELL_{sell_type.upper()}",
            "order_type": "LMT" if sell_type == "take_profit" else "STP_LMT",
            "quantity": quantity,
            "price": price,
            "fill_price": fill_price,
            "pnl": round(pnl, 2),
            "pnl_pct": round(pnl_pct, 2),
            "mode": mode,
            "state_before": "SELL_PENDING",
            "state_after": "COOLDOWN",
        })
        return trade_id

    def get_today_trades(self) -> List[Dict[str, Any]]:
        """获取今日交易记录"""
        today = time.strftime("%Y-%m-%d")
        trades = []
        try:
            with open(self._trades_file, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get("timestamp", "").startswith(today):
                        trades.append(row)
        except Exception as e:
            logger.error("读取交易记录失败: %s", e)
        return trades

    def get_today_pnl(self) -> float:
        """计算今日累计盈亏"""
        trades = self.get_today_trades()
        return sum(float(t.get("pnl", 0)) for t in trades)

    def get_total_pnl(self) -> float:
        """计算历史累计盈亏"""
        total = 0.0
        try:
            with open(self._trades_file, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    total += float(row.get("pnl", 0))
        except Exception as e:
            logger.error("计算累计盈亏失败: %s", e)
        return total

    def save_daily_report(self, report: Dict[str, Any]) -> None:
        """保存每日报告"""
        today = time.strftime("%Y-%m-%d")
        report_file = self._data_dir / f"daily_report_{today}.json"
        try:
            with open(report_file, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            logger.info("每日报告已保存: %s", report_file)
        except Exception as e:
            logger.error("保存每日报告失败: %s", e)

    # ==================== 内部方法 ====================

    def _write_csv_header(self) -> None:
        with open(self._trades_file, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(self.CSV_HEADERS)

    def _append_trade(self, trade: Dict[str, Any]) -> None:
        try:
            with open(self._trades_file, "a", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=self.CSV_HEADERS)
                writer.writerow(trade)
            self._trade_count += 1
            logger.info("交易已记录: %s", trade.get("trade_id"))
        except Exception as e:
            logger.error("记录交易失败: %s", e)

    def _count_existing_trades(self) -> int:
        try:
            with open(self._trades_file, "r", encoding="utf-8") as f:
                return sum(1 for _ in f) - 1  # 减去表头
        except Exception:
            return 0

    def _generate_id(self, action: str) -> str:
        self._trade_count += 1
        ts = time.strftime("%Y%m%d%H%M%S")
        return f"{action}_{ts}_{self._trade_count:04d}"

    @staticmethod
    def _now() -> str:
        return time.strftime("%Y-%m-%d %H:%M:%S")
