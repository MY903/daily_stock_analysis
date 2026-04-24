# -*- coding: utf-8 -*-
"""
T+0 / Swing Trading Stock Screener for HK & US Markets
======================================================

Based on the existing A-share t0_stock_screener.py framework, extended for:
  - HK stocks: intraday T+0 (no PDT restriction)
  - US stocks: 1-5 day swing trades (PDT restriction applies for < 25K USD accounts)

Data sources:
  - HK stock list: akshare (ak.stock_hk_spot_em) or Tushare (hk_basic)
  - US stock list: predefined pool + optional Tushare (us_basic)
  - HK daily data: DataFetcherManager -> AkshareFetcher / YfinanceFetcher / TushareFetcher
  - US daily data: DataFetcherManager -> YfinanceFetcher / LongbridgeFetcher

Capital allocation (30K HKD total):
  - HK: ~15,000 HKD for intraday T+0
  - US: ~1,800 USD (15,000 HKD equivalent) for swing trades
"""

import argparse
import logging
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

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

OUTPUT_DIR = PROJECT_ROOT / "data"

# ============================================================
# Screening parameters - HK Market
# ============================================================
HK_AMP_LOW = 2.5
HK_AMP_HIGH = 5.0
HK_PRICE_MIN = 1.0       # HKD, filter out penny stocks
HK_PRICE_MAX = 15.0      # HKD, suitable for small capital
HK_MIN_AVG_TURNOVER_HKD = 10.0   # million HKD daily turnover
HK_MIN_AVG_VOLUME = 2_000_000    # shares
HK_AMP_LOOKBACK_DAYS = 30
HK_YEAR_RETURN_MAX = 30.0
HK_MIN_DISTANCE_FROM_HIGH = 10.0
HK_AMP_CV_MAX = 0.7

# ============================================================
# Screening parameters - US Market
# ============================================================
US_AMP_LOW = 2.0
US_AMP_HIGH = 5.0
US_PRICE_MIN = 5.0       # USD
US_PRICE_MAX = 100.0     # USD
US_MIN_AVG_TURNOVER_USD = 20.0   # million USD daily turnover
US_MIN_AVG_VOLUME = 3_000_000    # shares
US_AMP_LOOKBACK_DAYS = 30
US_YEAR_RETURN_MAX = 30.0
US_MIN_DISTANCE_FROM_HIGH = 10.0
US_AMP_CV_MAX = 0.7

# ============================================================
# Capital & risk parameters
# ============================================================
TOTAL_CAPITAL_HKD = 30000
HK_ALLOCATION_HKD = 15000
US_ALLOCATION_USD = 1800   # ~15K HKD equivalent
MAX_SINGLE_POSITION_PCT = 0.40  # 40% max single position
HK_STOP_LOSS_PCT = 2.0    # intraday stop loss
US_STOP_LOSS_PCT = 3.0    # swing stop loss

# ============================================================
# Predefined US stock pool (high liquidity)
# ============================================================
US_STOCK_POOL = {
    # Chinese ADRs
    "BABA": "阿里巴巴", "PDD": "拼多多", "JD": "京东", "BIDU": "百度",
    "NIO": "蔚来", "XPEV": "小鹏汽车", "LI": "理想汽车",
    "TME": "腾讯音乐", "IQ": "爱奇艺", "BILI": "哔哩哔哩",
    "FUTU": "富途", "TIGR": "老虎证券", "VIPS": "唯品会",
    "ZTO": "中通快递", "MNSO": "名创优品", "YMM": "满帮",
    "HKIT": "盈喜集团", "FXI": "中国大盘ETF",
    # Big tech
    "AAPL": "苹果", "MSFT": "微软", "GOOGL": "谷歌A", "AMZN": "亚马逊",
    "NVDA": "英伟达", "META": "Meta", "AMD": "AMD", "INTC": "英特尔",
    "TSLA": "特斯拉", "NFLX": "奈飞", "CRM": "赛富时",
    # High volatility tech
    "PLTR": "Palantir", "COIN": "Coinbase", "SOFI": "SoFi",
    "RIVN": "Rivian", "LCID": "Lucid", "MARA": "Marathon Digital",
    "RIOT": "Riot Platforms", "MSTR": "MicroStrategy",
    # Sector ETFs (swing tools)
    "QQQ": "纳指100ETF", "SPY": "标普500ETF", "IWM": "罗素2000ETF",
    "XLF": "金融ETF", "XLE": "能源ETF", "XLK": "科技ETF",
    "ARKK": "ARK创新ETF", "TQQQ": "纳指3倍ETF", "SQQQ": "纳指反向3倍ETF",
    # Other high-volume stocks
    "F": "福特", "T": "AT&T", "PFE": "辉瑞", "CCL": "嘉年华",
    "BAC": "美国银行", "WFC": "富国银行", "DIS": "迪士尼",
    "UBER": "Uber", "ABNB": "Airbnb", "SNAP": "Snap",
    "PYPL": "PayPal", "SQ": "Block", "SHOP": "Shopify",
    "SE": "Sea", "MELI": "MercadoLibre",
}


# ============================================================
# Data fetching via DataFetcherManager
# ============================================================
_manager = None


def _get_manager():
    """Lazily initialize DataFetcherManager."""
    global _manager
    if _manager is not None:
        return _manager
    from data_provider import DataFetcherManager
    _manager = DataFetcherManager()
    return _manager


def fetch_daily_data(stock_code: str, days: int = 60) -> Optional[pd.DataFrame]:
    """Fetch daily OHLCV data for a stock via DataFetcherManager."""
    try:
        manager = _get_manager()
        df, source = manager.get_daily_data(stock_code, days=days)
        if df is not None and not df.empty:
            logger.debug(f"  {stock_code}: got {len(df)} rows from {source}")
            return df
    except Exception as e:
        logger.warning(f"  {stock_code}: data fetch failed: {e}")
    return None


# ============================================================
# HK Stock List
# ============================================================
def get_hk_stock_list() -> pd.DataFrame:
    """Get HK stock list via akshare or Tushare."""
    # Try akshare first (no token required)
    try:
        import akshare as ak
        logger.info("Fetching HK stock list via akshare...")
        df = ak.stock_hk_spot_em()
        if df is not None and not df.empty:
            # Rename columns
            col_map = {
                "代码": "code",
                "名称": "name",
                "最新价": "price",
                "涨跌幅": "change_pct",
                "成交量": "volume",
                "成交额": "amount",
                "振幅": "amplitude",
                "换手率": "turnover_rate",
            }
            existing = {k: v for k, v in col_map.items() if k in df.columns}
            df = df.rename(columns=existing)

            # Filter out penny stocks and suspicious names
            if "price" in df.columns:
                df = df[df["price"] >= HK_PRICE_MIN]
            if "name" in df.columns:
                # Exclude stocks with special markers
                mask = df["name"].str.contains(
                    r"退|停|PT|澄清|公告|供股|合股|拆股",
                    case=False, na=False,
                )
                df = df[~mask]

            # Filter: main board only (codes starting with 0)
            if "code" in df.columns:
                df["code"] = df["code"].astype(str).str.zfill(5)
                # Keep main board (0xxxx) and GEM (8xxx) but prefer main board
                df = df[df["code"].str.match(r"^[0-9]\d{4}$")]

            logger.info(f"HK stock list: {len(df)} stocks after filtering")
            return df
    except Exception as e:
        logger.warning(f"akshare HK stock list failed: {e}")

    # Fallback: Tushare
    try:
        import tushare as ts
        token = os.getenv("TUSHARE_TOKEN", "")
        if token:
            logger.info("Fetching HK stock list via Tushare...")
            api = ts.pro_api(token)
            df = api.hk_basic(list_status="L")
            if df is not None and not df.empty:
                # Normalize code format: 00001.HK -> 00001
                df["code"] = df["ts_code"].str.replace(".HK", "", regex=False)
                df["code"] = df["code"].astype(str).str.zfill(5)
                # Filter price range (Tushare hk_basic has no price, skip)
                logger.info(f"Tushare HK stock list: {len(df)} stocks")
                return df
    except Exception as e:
        logger.warning(f"Tushare HK stock list failed: {e}")

    logger.error("All HK stock list sources failed!")
    return pd.DataFrame()


# ============================================================
# US Stock List
# ============================================================
def get_us_stock_list() -> pd.DataFrame:
    """Get US stock list from predefined pool + optional Tushare expansion."""
    # Start with predefined pool
    rows = [
        {"code": code, "name": name}
        for code, name in US_STOCK_POOL.items()
    ]
    df = pd.DataFrame(rows)

    # Optionally expand with Tushare
    try:
        import tushare as ts
        token = os.getenv("TUSHARE_TOKEN", "")
        if token:
            logger.info("Expanding US stock list via Tushare...")
            api = ts.pro_api(token)
            us_df = api.us_basic(limit=5000)
            if us_df is not None and not us_df.empty:
                # Add new stocks not already in pool
                existing = set(US_STOCK_POOL.keys())
                for _, row in us_df.iterrows():
                    code = str(row.get("ts_code", "")).split(".")[0]
                    if code and code not in existing and len(code) <= 5:
                        name = str(row.get("name", ""))
                        rows.append({"code": code, "name": name})
                        existing.add(code)
                df = pd.DataFrame(rows)
    except Exception as e:
        logger.debug(f"Tushare US expansion skipped: {e}")

    logger.info(f"US stock pool: {len(df)} stocks")
    return df


# ============================================================
# Screening metrics calculation
# ============================================================
def calculate_metrics(
    stock_code: str,
    df: pd.DataFrame,
    lookback_days: int = 30,
) -> Optional[Dict]:
    """Calculate screening metrics for a single stock from its daily data."""
    if df is None or len(df) < 10:
        return None

    df = df.copy()

    # Ensure date column
    if "date" not in df.columns:
        return None
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date")

    # Use recent lookback period
    recent = df.tail(lookback_days)
    if len(recent) < 10:
        return None

    # Latest price
    latest_price = float(recent.iloc[-1]["close"])

    # Calculate daily amplitude: (high - low) / prev_close * 100
    if "pre_close" in recent.columns and recent["pre_close"].notna().any():
        prev_close = recent["pre_close"].fillna(recent["close"].shift(1))
        amplitude = (recent["high"] - recent["low"]) / prev_close * 100
    else:
        prev_close = recent["close"].shift(1)
        amplitude = (recent["high"] - recent["low"]) / prev_close * 100

    amp_values = amplitude.dropna()
    if len(amp_values) < 5:
        return None

    avg_amplitude = amp_values.mean()
    amp_std = amp_values.std()
    amp_cv = amp_std / avg_amplitude if avg_amplitude > 0 else 999

    # Volume and turnover
    avg_volume = float(recent["volume"].mean()) if "volume" in recent.columns else 0
    avg_turnover = float(recent["amount"].mean()) if "amount" in recent.columns else 0

    # Year return
    earliest_close = float(df.iloc[0]["close"])
    year_return = (latest_price - earliest_close) / earliest_close * 100 if earliest_close > 0 else 0

    # Distance from high
    period_high = float(df["high"].max())
    distance_from_high = (period_high - latest_price) / period_high * 100 if period_high > 0 else 0

    return {
        "code": stock_code,
        "latest_price": round(latest_price, 3),
        "avg_amplitude": round(avg_amplitude, 2),
        "amp_std": round(amp_std, 2),
        "amp_cv": round(amp_cv, 3),
        "avg_volume": int(avg_volume),
        "avg_turnover": round(avg_turnover, 0),
        "year_return": round(year_return, 2),
        "distance_from_high": round(distance_from_high, 2),
        "trading_days": len(recent),
    }


# ============================================================
# HK Screener
# ============================================================
def run_hk_screener(send_notification: bool = False) -> Optional[pd.DataFrame]:
    """Run T+0 screening for HK stocks."""
    logger.info("=" * 60)
    logger.info("HK Market T+0 Stock Screener")
    logger.info("=" * 60)
    logger.info(f"  Amplitude: {HK_AMP_LOW}% ~ {HK_AMP_HIGH}%")
    logger.info(f"  Price: {HK_PRICE_MIN} ~ {HK_PRICE_MAX} HKD")
    logger.info(f"  Min avg turnover: {HK_MIN_AVG_TURNOVER_HKD}M HKD")
    logger.info(f"  Capital: {HK_ALLOCATION_HKD:,.0f} HKD")
    logger.info("=" * 60)

    # Step 1: Get stock list
    stocks_df = get_hk_stock_list()
    if stocks_df.empty:
        logger.error("No HK stock list available")
        return None

    # Step 2: Pre-filter by price
    if "price" in stocks_df.columns:
        stocks_df = stocks_df[
            (stocks_df["price"] >= HK_PRICE_MIN)
            & (stocks_df["price"] <= HK_PRICE_MAX)
        ]
    logger.info(f"After price filter ({HK_PRICE_MIN}-{HK_PRICE_MAX} HKD): {len(stocks_df)} stocks")

    # Limit to manageable batch for data fetching
    # Sort by volume/turnover if available to prioritize liquid stocks
    if "amount" in stocks_df.columns:
        stocks_df = stocks_df.sort_values("amount", ascending=False)
    elif "volume" in stocks_df.columns:
        stocks_df = stocks_df.sort_values("volume", ascending=False)

    max_stocks = 150
    if len(stocks_df) > max_stocks:
        stocks_df = stocks_df.head(max_stocks)
        logger.info(f"Limited to top {max_stocks} by liquidity")

    # Step 3: Fetch daily data and calculate metrics
    metrics = []
    code_col = "code" if "code" in stocks_df.columns else stocks_df.columns[0]
    name_col = "name" if "name" in stocks_df.columns else None

    for i, (_, row) in enumerate(stocks_df.iterrows()):
        raw_code = str(row[code_col]).zfill(5)
        # Convert to internal HK format
        hk_code = f"HK{raw_code}"

        logger.info(f"  [{i+1}/{len(stocks_df)}] Fetching {raw_code} ({row.get('name', '?')})...")

        df = fetch_daily_data(hk_code, days=60)
        if df is None:
            continue

        m = calculate_metrics(hk_code, df, lookback_days=HK_AMP_LOOKBACK_DAYS)
        if m is None:
            continue

        # Add name from list
        if name_col and name_col in row.index:
            m["name"] = row[name_col]

        metrics.append(m)

        # Rate limiting
        time.sleep(0.3)

    if not metrics:
        logger.warning("No HK stocks had sufficient data")
        return None

    metrics_df = pd.DataFrame(metrics)

    # Step 4: Apply T+0 filters
    result_df = _apply_hk_filters(metrics_df)

    if result_df.empty:
        logger.warning("No HK stocks passed all filters!")
        return None

    # Step 5: Add trading recommendations
    result_df = _add_hk_recommendations(result_df)

    # Step 6: Save
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_file = OUTPUT_DIR / "t0_hk_stock_pool.csv"
    result_df.to_csv(output_file, index=False, encoding="utf-8-sig")

    logger.info("=" * 60)
    logger.info(f"HK SCREENING COMPLETE: {len(result_df)} stocks selected")
    logger.info(f"Results saved to: {output_file}")
    logger.info("=" * 60)

    # Print top results
    _print_results(result_df, market="HK")

    if send_notification:
        _send_notification(result_df, market="HK")

    return result_df


def _apply_hk_filters(df: pd.DataFrame) -> pd.DataFrame:
    """Apply HK T+0 trading strategy filters."""
    total = len(df)

    # Price filter
    df = df[(df["latest_price"] >= HK_PRICE_MIN) & (df["latest_price"] <= HK_PRICE_MAX)]
    logger.info(f"[HK Filter] Price {HK_PRICE_MIN}-{HK_PRICE_MAX}: {len(df)} / {total}")

    # Amplitude filter
    df = df[(df["avg_amplitude"] >= HK_AMP_LOW) & (df["avg_amplitude"] <= HK_AMP_HIGH)]
    logger.info(f"[HK Filter] Amplitude {HK_AMP_LOW}%-{HK_AMP_HIGH}%: {len(df)}")

    # Amplitude stability
    df = df[df["amp_cv"] <= HK_AMP_CV_MAX]
    logger.info(f"[HK Filter] Amp CV <= {HK_AMP_CV_MAX}: {len(df)}")

    # Year return filter
    df = df[df["year_return"] <= HK_YEAR_RETURN_MAX]
    logger.info(f"[HK Filter] Year return <= {HK_YEAR_RETURN_MAX}%: {len(df)}")

    # Volume filter
    df = df[df["avg_volume"] >= HK_MIN_AVG_VOLUME]
    logger.info(f"[HK Filter] Avg volume >= {HK_MIN_AVG_VOLUME:,}: {len(df)}")

    # Turnover filter (avg_turnover is in original currency units)
    # Rough filter: avg_turnover >= 10M HKD = 10,000,000
    min_turnover = HK_MIN_AVG_TURNOVER_HKD * 1_000_000
    df = df[df["avg_turnover"] >= min_turnover]
    logger.info(f"[HK Filter] Avg turnover >= {HK_MIN_AVG_TURNOVER_HKD}M HKD: {len(df)}")

    # Distance from high
    df = df[df["distance_from_high"] >= HK_MIN_DISTANCE_FROM_HIGH]
    logger.info(f"[HK Filter] Distance from high >= {HK_MIN_DISTANCE_FROM_HIGH}%: {len(df)}")

    # Composite score
    df["amp_score"] = abs(df["avg_amplitude"] - 3.0)
    df["composite_score"] = df["amp_score"] * 2 + df["amp_cv"] * 3 - df["distance_from_high"] * 0.05
    df = df.sort_values("composite_score", ascending=True)
    df = df.drop(columns=["amp_score", "composite_score"])

    return df


def _add_hk_recommendations(df: pd.DataFrame) -> pd.DataFrame:
    """Add position sizing and risk management columns for HK stocks."""
    df = df.copy()

    # Position size: min of 40% capital and affordable by price
    max_position = HK_ALLOCATION_HKD * MAX_SINGLE_POSITION_PCT
    df["max_position_hkd"] = round(max_position, 0)
    df["stop_loss_pct"] = HK_STOP_LOSS_PCT
    df["stop_loss_hkd"] = round(df["latest_price"] * (1 - HK_STOP_LO_PCT / 100), 3)

    # Approximate shares affordable (assuming lot size 1000 for low-priced HK stocks)
    # Real lot sizes vary; this is a conservative estimate
    est_lot_size = 1000
    df["est_lot_size"] = est_lot_size
    df["est_lot_cost_hkd"] = round(df["latest_price"] * est_lot_size, 0)
    df["affordable_lots"] = (max_position // df["est_lot_cost_hkd"]).astype(int).clip(lower=0)

    return df


# ============================================================
# US Screener
# ============================================================
def run_us_screener(send_notification: bool = False) -> Optional[pd.DataFrame]:
    """Run swing trading screening for US stocks."""
    logger.info("=" * 60)
    logger.info("US Market Swing Trading Stock Screener")
    logger.info("=" * 60)
    logger.info(f"  Amplitude: {US_AMP_LOW}% ~ {US_AMP_HIGH}%")
    logger.info(f"  Price: {US_PRICE_MIN} ~ {US_PRICE_MAX} USD")
    logger.info(f"  Min avg turnover: {US_MIN_AVG_TURNOVER_USD}M USD")
    logger.info(f"  Capital: ${US_ALLOCATION_USD:,.0f} USD")
    logger.info(f"  PDT status: RESTRICTED (< $25K account)")
    logger.info("=" * 60)

    # Step 1: Get stock list
    stocks_df = get_us_stock_list()
    if stocks_df.empty:
        logger.error("No US stock list available")
        return None

    # Step 2: Fetch daily data and calculate metrics
    metrics = []
    code_col = "code" if "code" in stocks_df.columns else stocks_df.columns[0]
    name_col = "name" if "name" in stocks_df.columns else None

    for i, (_, row) in enumerate(stocks_df.iterrows()):
        code = str(row[code_col]).strip().upper()
        name = str(row.get(name_col, "")) if name_col else ""

        logger.info(f"  [{i+1}/{len(stocks_df)}] Fetching {code} ({name})...")

        df = fetch_daily_data(code, days=60)
        if df is None:
            continue

        m = calculate_metrics(code, df, lookback_days=US_AMP_LOOKBACK_DAYS)
        if m is None:
            continue

        m["name"] = name
        metrics.append(m)

        # Rate limiting (yfinance can handle burst, but be gentle)
        time.sleep(0.2)

    if not metrics:
        logger.warning("No US stocks had sufficient data")
        return None

    metrics_df = pd.DataFrame(metrics)

    # Step 3: Apply swing filters
    result_df = _apply_us_filters(metrics_df)

    if result_df.empty:
        logger.warning("No US stocks passed all filters!")
        return None

    # Step 4: Add trading recommendations
    result_df = _add_us_recommendations(result_df)

    # Step 5: Save
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_file = OUTPUT_DIR / "t0_us_stock_pool.csv"
    result_df.to_csv(output_file, index=False, encoding="utf-8-sig")

    logger.info("=" * 60)
    logger.info(f"US SCREENING COMPLETE: {len(result_df)} stocks selected")
    logger.info(f"Results saved to: {output_file}")
    logger.info("=" * 60)

    _print_results(result_df, market="US")

    if send_notification:
        _send_notification(result_df, market="US")

    return result_df


def _apply_us_filters(df: pd.DataFrame) -> pd.DataFrame:
    """Apply US swing trading strategy filters."""
    total = len(df)

    # Price filter
    df = df[(df["latest_price"] >= US_PRICE_MIN) & (df["latest_price"] <= US_PRICE_MAX)]
    logger.info(f"[US Filter] Price {US_PRICE_MIN}-{US_PRICE_MAX}: {len(df)} / {total}")

    # Amplitude filter
    df = df[(df["avg_amplitude"] >= US_AMP_LOW) & (df["avg_amplitude"] <= US_AMP_HIGH)]
    logger.info(f"[US Filter] Amplitude {US_AMP_LOW}%-{US_AMP_HIGH}%: {len(df)}")

    # Amplitude stability
    df = df[df["amp_cv"] <= US_AMP_CV_MAX]
    logger.info(f"[US Filter] Amp CV <= {US_AMP_CV_MAX}: {len(df)}")

    # Year return filter
    df = df[df["year_return"] <= US_YEAR_RETURN_MAX]
    logger.info(f"[US Filter] Year return <= {US_YEAR_RETURN_MAX}%: {len(df)}")

    # Volume filter
    df = df[df["avg_volume"] >= US_MIN_AVG_VOLUME]
    logger.info(f"[US Filter] Avg volume >= {US_MIN_AVG_VOLUME:,}: {len(df)}")

    # Turnover filter
    min_turnover = US_MIN_AVG_TURNOVER_USD * 1_000_000
    df = df[df["avg_turnover"] >= min_turnover]
    logger.info(f"[US Filter] Avg turnover >= {US_MIN_AVG_TURNOVER_USD}M USD: {len(df)}")

    # Distance from high
    df = df[df["distance_from_high"] >= US_MIN_DISTANCE_FROM_HIGH]
    logger.info(f"[US Filter] Distance from high >= {US_MIN_DISTANCE_FROM_HIGH}%: {len(df)}")

    # Composite score
    df["amp_score"] = abs(df["avg_amplitude"] - 3.0)
    df["composite_score"] = df["amp_score"] * 2 + df["amp_cv"] * 3 - df["distance_from_high"] * 0.05
    df = df.sort_values("composite_score", ascending=True)
    df = df.drop(columns=["amp_score", "composite_score"])

    return df


def _add_us_recommendations(df: pd.DataFrame) -> pd.DataFrame:
    """Add swing trading recommendations for US stocks."""
    df = df.copy()

    max_position = US_ALLOCATION_USD * MAX_SINGLE_POSITION_PCT
    df["max_position_usd"] = round(max_position, 0)
    df["stop_loss_pct"] = US_STOP_LOSS_PCT
    df["stop_loss_usd"] = round(df["latest_price"] * (1 - US_STOP_LOSS_PCT / 100), 2)

    # Shares affordable
    df["affordable_shares"] = (max_position / df["latest_price"]).astype(int).clip(lower=0)

    # PDT warning
    df["pdt_warning"] = "PDT restricted: max 3 day-trades/5days (account < $25K)"

    # Suggested holding period
    df["suggested_hold_days"] = df["avg_amplitude"].apply(
        lambda a: "1-2 days" if a >= 3.5 else ("2-3 days" if a >= 2.5 else "3-5 days")
    )

    return df


# ============================================================
# Display & notification
# ============================================================
def _print_results(df: pd.DataFrame, market: str):
    """Print screening results to console."""
    display_cols = [
        "code", "name", "latest_price", "avg_amplitude", "amp_cv",
        "year_return", "distance_from_high",
    ]
    if market == "HK":
        display_cols += ["est_lot_cost_hkd", "affordable_lots", "stop_loss_hkd"]
    else:
        display_cols += ["affordable_shares", "suggested_hold_days", "stop_loss_usd"]

    existing = [c for c in display_cols if c in df.columns]

    pd.set_option("display.max_columns", 20)
    pd.set_option("display.width", 140)
    pd.set_option("display.float_format", "{:.2f}".format)

    print(f"\n{'=' * 120}")
    print(f"  {market} {'T+0' if market == 'HK' else 'Swing'} Stock Pool - Top {min(20, len(df))}")
    print(f"  Capital: {'HKD ' + f'{HK_ALLOCATION_HKD:,}' if market == 'HK' else '$' + f'{US_ALLOCATION_USD:,}'}")
    print(f"{'=' * 120}")

    top = df.head(20)[existing].reset_index(drop=True)
    top.index = top.index + 1
    print(top.to_string())

    print(f"\nTotal: {len(df)} stocks in {market} pool")


def _send_notification(df: pd.DataFrame, market: str):
    """Send screening results via notification service."""
    try:
        from src.notification import NotificationService

        notifier = NotificationService()
        market_label = "港股" if market == "HK" else "美股"
        strategy = "T+0 日内" if market == "HK" else "波段 (1-5天)"
        currency = "HKD" if market == "HK" else "USD"
        capital = f"{HK_ALLOCATION_HKD:,} HKD" if market == "HK" else f"${US_ALLOCATION_USD:,} USD"

        lines = [
            f"## {market_label} {strategy} 选股池周报",
            f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "",
            "### 筛选统计",
            f"- **入选股票数量**: {len(df)} 只",
            f"- **平均振幅**: {df['avg_amplitude'].mean():.2f}%",
            f"- **平均股价**: {df['latest_price'].mean():.2f} {currency}",
            f"- **分配资金**: {capital}",
        ]

        if market == "US":
            lines.append(f"- **PDT状态**: 受限（账户 < $25,000）")
            lines.append(f"- **策略**: 1-5天波段，非日内T+0")

        lines.extend([
            "",
            "### 优选标的（Top 10）",
        ])

        for idx, row in df.head(10).iterrows():
            name = row.get("name", "N/A")
            code = row.get("code", "N/A")
            price = row.get("latest_price", 0)
            amp = row.get("avg_amplitude", 0)
            ret = row.get("year_return", 0)

            lines.append(f"\n**{name} ({code})**")
            lines.append(f"- 股价: {price:.2f} {currency}")
            lines.append(f"- 平均振幅: {amp:.2f}%")
            lines.append(f"- 年收益: {ret:.2f}%")

            if market == "HK":
                lots = row.get("affordable_lots", 0)
                lot_cost = row.get("est_lot_cost_hkd", 0)
                stop = row.get("stop_loss_hkd", 0)
                lines.append(f"- 估计每手成本: {lot_cost:,.0f} HKD (可买 {lots} 手)")
                lines.append(f"- 日内止损: {stop:.2f} HKD ({HK_STOP_LOSS_PCT}%)")
            else:
                shares = row.get("affordable_shares", 0)
                hold = row.get("suggested_hold_days", "3-5天")
                stop = row.get("stop_loss_usd", 0)
                lines.append(f"- 可买 {shares} 股")
                lines.append(f"- 建议持仓: {hold}")
                lines.append(f"- 波段止损: ${stop:.2f} ({US_STOP_LOSS_PCT}%)")

        lines.extend([
            "",
            "---",
            "以上股票仅供研究参考，不构成投资建议",
        ])

        content = "\n".join(lines)
        success = notifier.send_to_feishu(content)
        if success:
            logger.info(f"{market_label} notification sent successfully")
        else:
            logger.warning(f"{market_label} notification failed")

    except Exception as e:
        logger.error(f"Notification failed: {e}")


# ============================================================
# Main
# ============================================================
def run_all(markets: str = "hk,us", send_notification: bool = False):
    """Run screeners for specified markets."""
    market_list = [m.strip().lower() for m in markets.split(",")]

    results = {}
    if "hk" in market_list:
        results["hk"] = run_hk_screener(send_notification=send_notification)
    if "us" in market_list:
        results["us"] = run_us_screener(send_notification=send_notification)

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="HK/US T+0 & Swing Trading Stock Screener")
    parser.add_argument(
        "--markets",
        default="hk,us",
        help="Markets to screen: hk, us, or hk,us (default: hk,us)",
    )
    parser.add_argument(
        "--notify",
        action="store_true",
        help="Send notification via Feishu bot after screening",
    )

    args = parser.parse_args()
    run_all(markets=args.markets, send_notification=args.notify)
