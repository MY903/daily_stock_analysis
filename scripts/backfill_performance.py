"""
自动化战绩回填脚本：
1. 查找数据库中尚未结算且 prediction_date 超过 5 个自然日的预测。
2. 通过 DataFetcherManager 获取 5 日后的真实收盘价涨跌幅。
3. 调用 PerformanceTracker.backfill_result() 判定胜负（幂等，可重复执行）。

使用方式：
    python scripts/backfill_performance.py
    python scripts/backfill_performance.py --dry-run   # 仅打印待结算记录，不写库
"""
import os
import sys
import sqlite3
import argparse
from datetime import datetime, timedelta
import logging

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.services.performance_tracker import PerformanceTracker
from data_provider.base import DataFetcherManager

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def get_5d_return(fetcher: DataFetcherManager, ticker: str, pred_date_str: str) -> float | None:
    """
    计算从 pred_date 起约 5 个自然日后的收盘价涨跌幅。
    使用预测日往后约 10 个交易日的数据窗口，取首个 >= pred_date+5 的交易日收盘价。

    Returns:
        (close_later - close_pred) / close_pred，或 None（数据不足时）
    """
    try:
        pred_date = datetime.strptime(pred_date_str, "%Y-%m-%d")
        window_end = pred_date + timedelta(days=15)  # 多取一些，保证覆盖节假日

        df, _source = fetcher.get_daily_data(
            ticker,
            start_date=pred_date_str,
            end_date=window_end.strftime("%Y-%m-%d"),
            days=15
        )

        if df is None or df.empty:
            logger.warning(f"[Backfill] {ticker} 无价格数据（{pred_date_str}）")
            return None

        # 按日期排序，确保从早到晚
        df = df.sort_values("date").reset_index(drop=True)

        # 找到预测日当天或最近后一天的收盘价
        pred_rows = df[df["date"] >= pred_date_str]
        if pred_rows.empty:
            logger.warning(f"[Backfill] {ticker} 找不到预测日 {pred_date_str} 的价格")
            return None
        close_pred = float(pred_rows.iloc[0]["close"])

        # 找到 5 个自然日后的首个交易日收盘价
        target_date = pred_date + timedelta(days=5)
        later_rows = df[df["date"] >= target_date.strftime("%Y-%m-%d")]
        if later_rows.empty:
            logger.warning(f"[Backfill] {ticker} 5 日后数据不足（预测日 {pred_date_str}）")
            return None
        close_later = float(later_rows.iloc[0]["close"])

        actual_return = (close_later - close_pred) / close_pred
        return round(actual_return, 6)

    except Exception as e:
        logger.error(f"[Backfill] 获取 {ticker} 价格失败: {e}")
        return None


def backfill_analyst_performance(dry_run: bool = False):
    """主回填逻辑。"""
    db_path = "workspace/analyst_performance.db"
    if not os.path.exists(db_path):
        logger.warning("数据库不存在，跳过回填。")
        return

    tracker = PerformanceTracker(db_path=db_path)
    fetcher = DataFetcherManager()

    # 只结算 prediction_date 超过 5 个自然日的记录（股价已可获取）
    cutoff_date = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, analyst_id, ticker, prediction_date, signal
            FROM track_record
            WHERE is_correct IS NULL
              AND prediction_date <= ?
            ORDER BY prediction_date ASC
        """, (cutoff_date,))
        pending_records = cursor.fetchall()

    if not pending_records:
        logger.info("没有待结算的战绩记录。")
        return

    logger.info(f"待结算 {len(pending_records)} 条记录（截止 {cutoff_date}）...")

    settled, skipped, failed = 0, 0, 0
    for rec in pending_records:
        ticker = rec['ticker']
        pred_date = rec['prediction_date']

        if dry_run:
            logger.info(f"[DryRun] [{rec['analyst_id']}] {ticker} @ {pred_date}: {rec['signal']}")
            continue

        actual_return = get_5d_return(fetcher, ticker, pred_date)
        if actual_return is None:
            logger.warning(f"[Backfill] 跳过 {ticker}（{pred_date}）：无法获取真实收益率")
            skipped += 1
            continue

        try:
            tracker.backfill_result(rec['id'], actual_return)
            logger.info(
                f"[Backfill] [{rec['analyst_id']}] {ticker} @ {pred_date}: "
                f"signal={rec['signal']}, return={actual_return:+.2%}"
            )
            settled += 1
        except Exception as e:
            logger.error(f"[Backfill] 结算 {ticker} 失败: {e}")
            failed += 1

    if not dry_run:
        logger.info(f"回填完成：已结算 {settled}，跳过 {skipped}，失败 {failed}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="专家预测战绩回填脚本")
    parser.add_argument("--dry-run", action="store_true", help="仅打印待结算记录，不写库")
    args = parser.parse_args()
    backfill_analyst_performance(dry_run=args.dry_run)
