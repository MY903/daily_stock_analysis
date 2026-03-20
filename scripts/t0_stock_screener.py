# -*- coding: utf-8 -*-
"""
T+0 Swing Trading Stock Screener
=================================

Screening strategy based on practical T+0 day-trading experience:
1. Financial health: exclude loss-making stocks (ST/*, negative PE)
2. Daily amplitude: average daily amplitude 2%-5% (sweet spot ~3%)
3. Price position: near historical bottom, not rallied significantly in 1 year
4. Liquidity: sufficient daily turnover, not "zombie stocks"
5. Price range: moderate price level suitable for 50K-200K capital

Data source: Tushare Pro API
"""

import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import requests

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ============================================================
# Tushare API helper (lightweight, no SDK dependency issues)
# ============================================================
TUSHARE_API_URL = "http://api.tushare.pro"
TUSHARE_TOKEN = os.getenv("TUSHARE_TOKEN", "")

_call_count = 0
_minute_start = None
RATE_LIMIT = 75  # stay under 80/min free tier


def _check_rate_limit():
    """Simple per-minute rate limiter."""
    global _call_count, _minute_start
    now = time.time()
    if _minute_start is None:
        _minute_start = now
        _call_count = 0
    elif now - _minute_start >= 60:
        _minute_start = now
        _call_count = 0

    if _call_count >= RATE_LIMIT:
        sleep_sec = max(0, 60 - (now - _minute_start)) + 1.5
        logger.info(f"Rate limit reached ({_call_count}/{RATE_LIMIT}/min), sleeping {sleep_sec:.1f}s ...")
        time.sleep(sleep_sec)
        _minute_start = time.time()
        _call_count = 0

    _call_count += 1


def ts_query(api_name: str, fields: str = "", **kwargs) -> pd.DataFrame:
    """Call Tushare Pro HTTP API directly."""
    _check_rate_limit()
    req = {
        "api_name": api_name,
        "token": TUSHARE_TOKEN,
        "params": kwargs,
        "fields": fields,
    }
    for attempt in range(3):
        try:
            resp = requests.post(TUSHARE_API_URL, json=req, timeout=30)
            result = json.loads(resp.text)
            if result["code"] != 0:
                raise RuntimeError(result.get("msg", "Unknown error"))
            data = result["data"]
            return pd.DataFrame(data["items"], columns=data["fields"])
        except (requests.ConnectionError, requests.Timeout) as e:
            logger.warning(f"Tushare request failed (attempt {attempt+1}/3): {e}")
            time.sleep(2 ** attempt)
    return pd.DataFrame()


# ============================================================
# Screening parameters (tuneable)
# ============================================================
# Amplitude filter: average daily amplitude between these pcts
AMP_LOW = 2.5
AMP_HIGH = 4.0

# Lookback for amplitude calculation (trading days)
AMP_LOOKBACK_DAYS = 30

# One-year return threshold: stock price should not have risen more than this
YEAR_RETURN_MAX = 20.0  # percent

# Minimum average daily turnover (million CNY)
MIN_AVG_TURNOVER = 50.0  # 5000 wan = 5000 * 10000

# Price range filter (CNY)
PRICE_MIN = 5.0
PRICE_MAX = 30.0

# Minimum average daily volume (shares)
MIN_AVG_VOLUME = 8_000_000  # 800 wan shares

# Amplitude stability: coefficient of variation of daily amplitude should be moderate
AMP_CV_MAX = 0.6  # max coefficient of variation - tighter = more predictable pattern

# Minimum distance from 1-year high (%) - ensures stock is near bottom
MIN_DISTANCE_FROM_HIGH = 10.0

# Output file
OUTPUT_DIR = PROJECT_ROOT / "data"
OUTPUT_FILE = OUTPUT_DIR / "t0_stock_pool.csv"


def get_trade_dates(n_days: int = 300) -> list:
    """Get recent N trading dates from trade calendar."""
    end_date = datetime.now().strftime("%Y%m%d")
    start_date = (datetime.now() - timedelta(days=n_days + 60)).strftime("%Y%m%d")
    logger.info(f"Fetching trade calendar {start_date} ~ {end_date} ...")
    df = ts_query("trade_cal", exchange="", start_date=start_date, end_date=end_date, is_open="1")
    if df.empty:
        logger.error("Failed to fetch trade calendar")
        return []
    dates = sorted(df["cal_date"].tolist())
    return dates


def get_stock_list() -> pd.DataFrame:
    """Get all listed A-share stocks, excluding ST and special stocks."""
    logger.info("Fetching stock list ...")
    df = ts_query(
        "stock_basic",
        fields="ts_code,name,industry,area,market,list_date,list_status,is_hs",
        exchange="",
        list_status="L",
    )
    if df.empty:
        logger.error("Failed to fetch stock list")
        return pd.DataFrame()

    total = len(df)

    # Filter out ST / *ST / PT stocks
    mask_st = df["name"].str.contains(r"ST|PT|\*", case=False, na=False)
    df = df[~mask_st]
    logger.info(f"After removing ST/PT: {len(df)} / {total}")

    # Filter out stocks listed less than 1 year (need enough history)
    one_year_ago = (datetime.now() - timedelta(days=365)).strftime("%Y%m%d")
    df = df[df["list_date"] <= one_year_ago]
    logger.info(f"After removing stocks listed < 1 year: {len(df)}")

    # Filter out B-shares (market not in main boards)
    # Keep: main board, SME board, ChiNext, STAR market
    df["code"] = df["ts_code"].apply(lambda x: x.split(".")[0])
    valid_prefix = ("000", "001", "002", "003", "300", "301", "600", "601", "603", "605")
    df = df[df["code"].str.startswith(valid_prefix)]
    logger.info(f"After keeping main A-share prefixes: {len(df)}")

    return df


def fetch_daily_data_by_dates(trade_dates: list) -> pd.DataFrame:
    """
    Fetch daily OHLCV data for ALL stocks on given trade dates.
    Uses trade_date parameter for efficiency (1 call per date, gets all stocks).
    """
    all_frames = []
    for i, td in enumerate(trade_dates):
        logger.info(f"  Fetching daily data for {td} ({i+1}/{len(trade_dates)}) ...")
        df = ts_query(
            "daily",
            ts_code="",
            trade_date=td,
        )
        if not df.empty:
            all_frames.append(df)
        else:
            logger.warning(f"  No data for {td}")

    if not all_frames:
        return pd.DataFrame()

    result = pd.concat(all_frames, ignore_index=True)
    logger.info(f"Total daily records fetched: {len(result)}")
    return result


def calculate_screening_metrics(daily_df: pd.DataFrame, stocks_df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate screening metrics for each stock.

    Metrics:
    - avg_amplitude: average daily amplitude (high-low)/prev_close * 100
    - amplitude_cv: coefficient of variation of daily amplitude
    - avg_volume: average daily volume
    - avg_turnover: average daily turnover amount (CNY)
    - latest_price: most recent closing price
    - year_return: approximate 1-year return %
    - trading_days: number of trading days with data
    """
    if daily_df.empty:
        return pd.DataFrame()

    # Sort by ts_code and trade_date
    daily_df = daily_df.sort_values(["ts_code", "trade_date"]).copy()

    # Calculate daily amplitude: (high - low) / pre_close * 100
    daily_df["amplitude"] = (daily_df["high"] - daily_df["low"]) / daily_df["pre_close"] * 100

    # Group by stock
    grouped = daily_df.groupby("ts_code")

    metrics = []
    valid_codes = set(stocks_df["ts_code"].values)

    for ts_code, group in grouped:
        if ts_code not in valid_codes:
            continue

        group = group.sort_values("trade_date")

        if len(group) < 10:
            continue

        # Latest price
        latest_price = group.iloc[-1]["close"]

        # Earliest and latest close for return calculation
        earliest_close = group.iloc[0]["close"]
        year_return = (latest_price - earliest_close) / earliest_close * 100 if earliest_close > 0 else 999

        # Amplitude stats (use most recent AMP_LOOKBACK_DAYS)
        recent = group.tail(AMP_LOOKBACK_DAYS)
        amp_values = recent["amplitude"].dropna()

        if len(amp_values) < 10:
            continue

        avg_amplitude = amp_values.mean()
        amp_std = amp_values.std()
        amp_cv = amp_std / avg_amplitude if avg_amplitude > 0 else 999

        # Volume and turnover
        avg_volume = recent["vol"].mean() * 100  # Tushare vol is in lots (手), convert to shares
        avg_turnover = recent["amount"].mean() * 1000  # Tushare amount is in 1000 CNY

        # Highest price in the period
        period_high = group["high"].max()
        # Distance from high: how far current price is from period high
        distance_from_high = (period_high - latest_price) / period_high * 100 if period_high > 0 else 0

        metrics.append({
            "ts_code": ts_code,
            "latest_price": round(latest_price, 2),
            "avg_amplitude": round(avg_amplitude, 2),
            "amp_std": round(amp_std, 2),
            "amp_cv": round(amp_cv, 3),
            "avg_volume": int(avg_volume),
            "avg_turnover_wan": round(avg_turnover / 10000, 1),  # Convert to 万 for readability
            "year_return": round(year_return, 2),
            "distance_from_high": round(distance_from_high, 2),
            "trading_days": len(group),
        })

    result = pd.DataFrame(metrics)
    logger.info(f"Metrics calculated for {len(result)} stocks")
    return result


def apply_filters(metrics_df: pd.DataFrame, stocks_df: pd.DataFrame) -> pd.DataFrame:
    """Apply T+0 trading strategy filters."""
    df = metrics_df.copy()
    total = len(df)

    # 1. Price range filter
    df = df[(df["latest_price"] >= PRICE_MIN) & (df["latest_price"] <= PRICE_MAX)]
    logger.info(f"[Filter] Price {PRICE_MIN}-{PRICE_MAX}: {len(df)} / {total}")

    # 2. Amplitude filter: sweet spot for T+0
    df = df[(df["avg_amplitude"] >= AMP_LOW) & (df["avg_amplitude"] <= AMP_HIGH)]
    logger.info(f"[Filter] Amplitude {AMP_LOW}%-{AMP_HIGH}%: {len(df)}")

    # 3. Amplitude stability: not too erratic
    df = df[df["amp_cv"] <= AMP_CV_MAX]
    logger.info(f"[Filter] Amplitude CV <= {AMP_CV_MAX}: {len(df)}")

    # 4. One-year return: not rallied too much (near bottom)
    df = df[df["year_return"] <= YEAR_RETURN_MAX]
    logger.info(f"[Filter] Year return <= {YEAR_RETURN_MAX}%: {len(df)}")

    # 5. Liquidity: sufficient volume
    df = df[df["avg_volume"] >= MIN_AVG_VOLUME]
    logger.info(f"[Filter] Avg volume >= {MIN_AVG_VOLUME/10000:.0f}万股: {len(df)}")

    # 6. Turnover filter
    min_turnover_wan = MIN_AVG_TURNOVER * 100  # Convert to 万 (50 million = 5000 万)
    df = df[df["avg_turnover_wan"] >= min_turnover_wan]
    logger.info(f"[Filter] Avg turnover >= {min_turnover_wan}万: {len(df)}")

    # 7. Distance from high: stock should be meaningfully below its high (near bottom)
    df = df[df["distance_from_high"] >= MIN_DISTANCE_FROM_HIGH]
    logger.info(f"[Filter] Distance from high >= {MIN_DISTANCE_FROM_HIGH}%: {len(df)}")

    # Merge stock info
    df = df.merge(
        stocks_df[["ts_code", "name", "industry"]],
        on="ts_code",
        how="left",
    )

    # Composite score: closer to 3% amplitude, more stable, more near bottom
    df["amp_score"] = abs(df["avg_amplitude"] - 3.0)  # 0 = perfect
    df["composite_score"] = df["amp_score"] * 2 + df["amp_cv"] * 3 - df["distance_from_high"] * 0.05
    df = df.sort_values("composite_score", ascending=True)
    df = df.drop(columns=["amp_score", "composite_score"])

    return df


def run_screener(send_notification: bool = False):
    """Main screening pipeline.
    
    Args:
        send_notification: Whether to send notification via Feishu bot
    """
    if not TUSHARE_TOKEN:
        logger.error("TUSHARE_TOKEN not set in .env file!")
        sys.exit(1)

    logger.info("=" * 60)
    logger.info("T+0 Swing Trading Stock Screener")
    logger.info("=" * 60)
    logger.info(f"Parameters:")
    logger.info(f"  Amplitude range: {AMP_LOW}% ~ {AMP_HIGH}%")
    logger.info(f"  Max year return: {YEAR_RETURN_MAX}%")
    logger.info(f"  Price range: {PRICE_MIN} ~ {PRICE_MAX} CNY")
    logger.info(f"  Min avg volume: {MIN_AVG_VOLUME/10000:.0f}万股")
    logger.info(f"  Min avg turnover: {MIN_AVG_TURNOVER}百万")
    logger.info(f"  Amplitude lookback: {AMP_LOOKBACK_DAYS} trading days")
    logger.info("=" * 60)

    # Step 1: Get trade calendar
    trade_dates = get_trade_dates(n_days=400)
    if not trade_dates:
        logger.error("Cannot get trade dates")
        sys.exit(1)

    # Get recent dates for amplitude calculation + historical for year return
    # Use last ~60 trading days for detailed analysis
    recent_dates = trade_dates[-60:]
    # Also include some dates from ~250 trading days ago for year return
    if len(trade_dates) >= 260:
        historical_dates = [trade_dates[-260], trade_dates[-250]]
    elif len(trade_dates) >= 200:
        historical_dates = [trade_dates[0]]
    else:
        historical_dates = []

    all_dates_to_fetch = sorted(set(historical_dates + recent_dates))
    logger.info(f"Will fetch daily data for {len(all_dates_to_fetch)} trading dates")
    logger.info(f"  Recent: {recent_dates[0]} ~ {recent_dates[-1]}")
    if historical_dates:
        logger.info(f"  Historical: {historical_dates}")

    # Step 2: Get stock list
    stocks_df = get_stock_list()
    if stocks_df.empty:
        logger.error("Stock list is empty")
        sys.exit(1)

    # Step 3: Fetch daily data
    logger.info("Fetching daily data (this may take 1-2 minutes) ...")
    daily_df = fetch_daily_data_by_dates(all_dates_to_fetch)
    if daily_df.empty:
        logger.error("No daily data fetched")
        sys.exit(1)

    # Step 4: Calculate metrics
    logger.info("Calculating screening metrics ...")
    metrics_df = calculate_screening_metrics(daily_df, stocks_df)
    if metrics_df.empty:
        logger.error("No metrics calculated")
        sys.exit(1)

    # Step 5: Apply filters
    logger.info("Applying T+0 strategy filters ...")
    result_df = apply_filters(metrics_df, stocks_df)

    if result_df.empty:
        logger.warning("No stocks passed all filters! Consider relaxing parameters.")
        return

    # Step 6: Output results
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    result_df.to_csv(OUTPUT_FILE, index=False, encoding="utf-8-sig")

    logger.info("=" * 60)
    logger.info(f"SCREENING COMPLETE: {len(result_df)} stocks selected")
    logger.info(f"Results saved to: {OUTPUT_FILE}")
    logger.info("=" * 60)

    # Print top results
    display_cols = [
        "ts_code", "name", "industry", "latest_price",
        "avg_amplitude", "amp_cv", "year_return",
        "distance_from_high", "avg_turnover_wan",
    ]
    existing_cols = [c for c in display_cols if c in result_df.columns]

    print("\n" + "=" * 100)
    print(f"  T+0 Stock Pool - Top {min(30, len(result_df))} Candidates")
    print(f"  Selection criteria: amplitude {AMP_LOW}-{AMP_HIGH}%, year return <={YEAR_RETURN_MAX}%, "
          f"price {PRICE_MIN}-{PRICE_MAX}")
    print("=" * 100)

    pd.set_option("display.max_columns", 20)
    pd.set_option("display.width", 120)
    pd.set_option("display.float_format", "{:.2f}".format)

    top_n = result_df.head(30)[existing_cols].reset_index(drop=True)
    top_n.index = top_n.index + 1
    print(top_n.to_string())

    print(f"\nTotal: {len(result_df)} stocks in pool")
    print(f"Full list saved to: {OUTPUT_FILE}")

    # Summary statistics
    print("\n--- Pool Statistics ---")
    print(f"Avg amplitude:  {result_df['avg_amplitude'].mean():.2f}%")
    print(f"Avg price:      {result_df['latest_price'].mean():.2f} CNY")
    print(f"Avg year return: {result_df['year_return'].mean():.2f}%")
    print(f"Industries:     {result_df['industry'].nunique()} sectors represented")

    # Send notification if requested
    if send_notification:
        try:
            _send_feishu_notification(result_df)
        except Exception as e:
            logger.error(f"Failed to send Feishu notification: {e}")

    return result_df


def _send_feishu_notification(result_df: pd.DataFrame):
    """
    Send screening results via Feishu bot.
    
    Args:
        result_df: DataFrame with screening results
    """
    from src.notification import NotificationService
    
    logger.info("Preparing Feishu notification...")
    
    # Generate Markdown report
    total_stocks = len(result_df)
    avg_amplitude = result_df['avg_amplitude'].mean()
    avg_price = result_df['latest_price'].mean()
    avg_return = result_df['year_return'].mean()
    industries = result_df['industry'].nunique()
    
    # Build report content
    report_lines = [
        "## 📊 T+0 选股池周报",
        f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        "### 📈 筛选统计",
        f"- **入选股票数量**: {total_stocks} 只",
        f"- **平均振幅**: {avg_amplitude:.2f}%",
        f"- **平均股价**: {avg_price:.2f} 元",
        f"- **平均年化收益**: {avg_return:.2f}%",
        f"- **覆盖行业数**: {industries} 个",
        "",
        "### 🎯 筛选条件",
        f"- 振幅范围：{AMP_LOW}% ~ {AMP_HIGH}%",
        f"- 年涨幅限制：≤ {YEAR_RETURN_MAX}%",
        f"- 股价范围：{PRICE_MIN} ~ {PRICE_MAX} 元",
        f"- 最小日均量：≥ {MIN_AVG_VOLUME/10000:.0f} 万股",
        f"- 最小日均成交额：≥ {MIN_AVG_TURNOVER} 百万",
        "",
        "### 🏆 优选标的（Top 15）",
    ]
    
    # Add top 15 stocks
    display_cols = ["ts_code", "name", "industry", "latest_price", "avg_amplitude", "amp_cv", "year_return"]
    existing_cols = [c for c in display_cols if c in result_df.columns]
    
    if not existing_cols:
        logger.warning("No valid columns to display in notification")
        return
    
    top_stocks = result_df.head(15)[existing_cols]
    
    for idx, row in top_stocks.iterrows():
        stock_info = f"\n**{row.get('name', 'N/A')} ({row.get('ts_code', 'N/A')})**\n"
        stock_info += f"- 行业：{row.get('industry', 'N/A')}\n"
        stock_info += f"- 股价：{row.get('latest_price', 0):.2f} 元\n"
        stock_info += f"- 平均振幅：{row.get('avg_amplitude', 0):.2f}%\n"
        if 'year_return' in row:
            stock_info += f"- 年收益：{row.get('year_return', 0):.2f}%\n"
        if 'amp_cv' in row:
            stock_info += f"- 振幅稳定性：{row.get('amp_cv', 0):.3f}\n"
        
        report_lines.append(stock_info)
    
    report_lines.extend([
        "",
        "---",
        "📄 **完整清单已保存至**: `data/t0_stock_pool.csv`",
        "💡 **提示**: 以上股票仅供研究参考，不构成投资建议"
    ])
    
    report_content = "\n".join(report_lines)
    
    # Send via NotificationService
    notifier = NotificationService()
    success = notifier.send_to_feishu(report_content)
    
    if success:
        logger.info("✅ Feishu notification sent successfully")
    else:
        logger.warning("⚠️ Failed to send Feishu notification")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="T+0 Swing Trading Stock Screener")
    parser.add_argument(
        "--notify", 
        action="store_true",
        help="Send notification via Feishu bot after screening"
    )
    
    args = parser.parse_args()
    run_screener(send_notification=args.notify)
