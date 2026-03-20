# -*- coding: utf-8 -*-
"""
T+0 Day-Trading Backtest Engine + HTML Report Generator
========================================================

Backtests the "2.5% T" swing-trading strategy on daily OHLC bars:
- For each stock, each trading day: check if amplitude allows a 2.5% T trade
- Use expected-value method (deterministic, reproducible) to calculate daily PnL
- Generate a self-contained HTML report with embedded matplotlib charts

Usage:
    python scripts/t0_backtest.py                  # full run (top 30, 1 year)
    python scripts/t0_backtest.py --top-n 5 --days 60   # quick test
    python scripts/t0_backtest.py --refresh         # force re-fetch data

Dependencies: matplotlib, pandas, numpy, requests, python-dotenv
"""

import argparse
import base64
import io
import json
import logging
import os
import pickle
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

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
# Section 1: Tushare API Helper
# ============================================================
TUSHARE_API_URL = "http://api.tushare.pro"
TUSHARE_TOKEN = os.getenv("TUSHARE_TOKEN", "")

_call_count = 0
_minute_start = None
RATE_LIMIT = 75


def _check_rate_limit():
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
    _check_rate_limit()
    req = {"api_name": api_name, "token": TUSHARE_TOKEN, "params": kwargs, "fields": fields}
    for attempt in range(3):
        try:
            resp = requests.post(TUSHARE_API_URL, json=req, timeout=30)
            result = json.loads(resp.text)
            if result["code"] != 0:
                raise RuntimeError(result.get("msg", "Unknown error"))
            data = result["data"]
            return pd.DataFrame(data["items"], columns=data["fields"])
        except (requests.ConnectionError, requests.Timeout) as e:
            logger.warning(f"Tushare request failed (attempt {attempt + 1}/3): {e}")
            time.sleep(2**attempt)
    return pd.DataFrame()


# ============================================================
# Section 2: Configuration Constants
# ============================================================
T_CAPITAL = 20000           # CNY per T trade
T_SPREAD_TARGET = 2.5       # target spread %
COMMISSION_RATE = 0.025     # one-side commission %
STAMP_TAX_RATE = 0.05       # stamp tax % (sell-side only)
FAIL_LOSS_PCT = 1.0         # assumed loss % on failed T
DOUBLE_T_THRESHOLD = 5.0    # amplitude % threshold for 2 T trades

# Success rate tiers based on daily amplitude
SUCCESS_RATE_TIERS = [
    (5.0, 0.90),   # amplitude >= 5%: 90% success
    (4.0, 0.90),   # amplitude >= 4%: 90%
    (3.0, 0.80),   # amplitude >= 3%: 80%
    (2.5, 0.65),   # amplitude >= 2.5%: 65%
]

# Trading cost per round trip
GROSS_PROFIT = T_CAPITAL * T_SPREAD_TARGET / 100              # 500
ROUND_TRIP_COST = T_CAPITAL * (2 * COMMISSION_RATE + STAMP_TAX_RATE) / 100  # ~20
NET_PROFIT = GROSS_PROFIT - ROUND_TRIP_COST                   # ~480
FAIL_LOSS = T_CAPITAL * FAIL_LOSS_PCT / 100 + ROUND_TRIP_COST  # ~220

# File paths
STOCK_POOL_CSV = PROJECT_ROOT / "data" / "t0_stock_pool.csv"
CACHE_FILE = PROJECT_ROOT / "data" / "t0_backtest_cache.pkl"
OUTPUT_DIR = PROJECT_ROOT / "reports"


# ============================================================
# Section 3: T0BacktestEngine
# ============================================================
class T0BacktestEngine:
    """T+0 day-trading backtest engine using daily OHLC bars."""

    def __init__(self, top_n: int = 30, backtest_days: int = 250):
        self.top_n = top_n
        self.backtest_days = backtest_days
        self.stock_pool: pd.DataFrame = pd.DataFrame()
        self.daily_data: Dict[str, pd.DataFrame] = {}
        self.stock_results: Dict[str, pd.DataFrame] = {}
        self.stock_summary: pd.DataFrame = pd.DataFrame()
        self.portfolio_metrics: dict = {}
        self.portfolio_daily: pd.DataFrame = pd.DataFrame()

    def load_stock_pool(self) -> pd.DataFrame:
        """Load top N stocks from the screener CSV."""
        if not STOCK_POOL_CSV.exists():
            logger.error(f"Stock pool CSV not found: {STOCK_POOL_CSV}")
            logger.error("Please run scripts/t0_stock_screener.py first.")
            sys.exit(1)

        df = pd.read_csv(STOCK_POOL_CSV)
        self.stock_pool = df.head(self.top_n).copy()
        logger.info(f"Loaded {len(self.stock_pool)} stocks from pool")
        return self.stock_pool

    def fetch_daily_data(self, refresh: bool = False) -> Dict[str, pd.DataFrame]:
        """Fetch 1-year daily OHLC for each stock. Uses cache if available."""
        # Try cache first
        if not refresh and CACHE_FILE.exists():
            try:
                with open(CACHE_FILE, "rb") as f:
                    cached = pickle.load(f)
                # Validate cache has enough stocks
                needed_codes = set(self.stock_pool["ts_code"].values)
                if needed_codes.issubset(set(cached.keys())):
                    self.daily_data = {}
                    for k, v in cached.items():
                        if k in needed_codes:
                            v = v.sort_values("trade_date").reset_index(drop=True)
                            if len(v) > self.backtest_days:
                                v = v.tail(self.backtest_days).reset_index(drop=True)
                            self.daily_data[k] = v
                    logger.info(f"Loaded {len(self.daily_data)} stocks from cache (trimmed to {self.backtest_days} days)")
                    return self.daily_data
                logger.info("Cache incomplete, re-fetching ...")
            except Exception as e:
                logger.warning(f"Cache load failed: {e}")

        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=self.backtest_days + 150)).strftime("%Y%m%d")

        data = {}
        codes = self.stock_pool["ts_code"].tolist()
        for i, ts_code in enumerate(codes):
            logger.info(f"  Fetching {ts_code} ({i + 1}/{len(codes)}) ...")
            df = ts_query("daily", ts_code=ts_code, start_date=start_date, end_date=end_date)
            if df.empty:
                logger.warning(f"  No data for {ts_code}")
                continue
            df = df.sort_values("trade_date").reset_index(drop=True)
            # Keep most recent backtest_days rows
            if len(df) > self.backtest_days:
                df = df.tail(self.backtest_days).reset_index(drop=True)
            data[ts_code] = df

        self.daily_data = data
        logger.info(f"Fetched daily data for {len(data)} stocks")

        # Save cache
        try:
            CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(CACHE_FILE, "wb") as f:
                pickle.dump(data, f)
            logger.info(f"Cache saved to {CACHE_FILE}")
        except Exception as e:
            logger.warning(f"Cache save failed: {e}")

        return data

    def run_backtest(self) -> Dict[str, pd.DataFrame]:
        """Run T+0 backtest for all stocks."""
        results = {}
        for ts_code, daily_df in self.daily_data.items():
            res = self._simulate_single_stock(ts_code, daily_df)
            if res is not None and not res.empty:
                results[ts_code] = res

        self.stock_results = results
        logger.info(f"Backtest completed for {len(results)} stocks")

        self._compute_summary()
        self._compute_portfolio()
        return results

    def _simulate_single_stock(self, ts_code: str, daily_df: pd.DataFrame) -> Optional[pd.DataFrame]:
        """Simulate T+0 trading on daily bars using Monte Carlo (fixed seed).

        Uses a deterministic random seed per stock so results are reproducible,
        while still showing realistic daily win/loss variance and drawdowns.
        """
        if len(daily_df) < 5:
            return None

        # Fixed seed per stock for reproducibility
        seed = int(ts_code.replace(".", "").encode().hex()[:8], 16) % (2**31)
        rng = np.random.RandomState(seed)

        records = []
        for _, row in daily_df.iterrows():
            pre_close = row.get("pre_close", 0)
            if pre_close is None or pre_close <= 0:
                continue

            high = row["high"]
            low = row["low"]
            close = row["close"]
            amplitude = (high - low) / pre_close * 100

            # Determine T opportunity
            if amplitude < T_SPREAD_TARGET:
                records.append({
                    "date": row["trade_date"],
                    "close": close,
                    "amplitude": round(amplitude, 3),
                    "action": "skip",
                    "n_trades": 0,
                    "win_count": 0,
                    "fail_count": 0,
                    "day_pnl": 0.0,
                })
                continue

            # Determine success rate and number of trades
            success_rate = 0.0
            for threshold, rate in SUCCESS_RATE_TIERS:
                if amplitude >= threshold:
                    success_rate = rate
                    break

            n_trades = 2 if amplitude >= DOUBLE_T_THRESHOLD else 1

            # Monte Carlo: simulate each T trade with the determined success rate
            day_pnl = 0.0
            win_count = 0
            fail_count = 0
            for _ in range(n_trades):
                if rng.random() < success_rate:
                    day_pnl += NET_PROFIT
                    win_count += 1
                else:
                    day_pnl -= FAIL_LOSS
                    fail_count += 1

            records.append({
                "date": row["trade_date"],
                "close": close,
                "amplitude": round(amplitude, 3),
                "action": "double_t" if n_trades == 2 else "single_t",
                "n_trades": n_trades,
                "win_count": win_count,
                "fail_count": fail_count,
                "day_pnl": round(day_pnl, 2),
            })

        if not records:
            return None

        df = pd.DataFrame(records)
        df["cumulative_pnl"] = df["day_pnl"].cumsum()
        df["peak"] = df["cumulative_pnl"].cummax()
        df["drawdown"] = df["cumulative_pnl"] - df["peak"]
        return df

    def _compute_summary(self):
        """Compute per-stock summary statistics."""
        rows = []
        pool_info = self.stock_pool.set_index("ts_code")

        for ts_code, df in self.stock_results.items():
            total_days = len(df)
            t_days = len(df[df["action"] != "skip"])
            skip_days = total_days - t_days
            double_t_days = len(df[df["action"] == "double_t"])
            total_pnl = df["day_pnl"].sum()
            avg_daily_pnl = total_pnl / total_days if total_days > 0 else 0

            # Win rate from actual simulated trades
            total_trades = df["n_trades"].sum()
            total_wins = df["win_count"].sum()
            win_rate = total_wins / total_trades * 100 if total_trades > 0 else 0

            # Max drawdown
            max_dd = df["drawdown"].min() if not df.empty else 0

            # T opportunity rate
            t_rate = t_days / total_days * 100 if total_days > 0 else 0

            # Avg amplitude
            avg_amp = df["amplitude"].mean()

            # Win/loss day counts
            win_days = len(df[df["day_pnl"] > 0])
            loss_days = len(df[df["day_pnl"] < 0])

            info = pool_info.loc[ts_code] if ts_code in pool_info.index else {}
            name = info.get("name", ts_code) if isinstance(info, (dict, pd.Series)) else ts_code
            industry = info.get("industry", "") if isinstance(info, (dict, pd.Series)) else ""

            rows.append({
                "ts_code": ts_code,
                "name": name,
                "industry": industry,
                "total_days": total_days,
                "t_opportunity_days": t_days,
                "skip_days": skip_days,
                "double_t_days": double_t_days,
                "t_rate_pct": round(t_rate, 1),
                "total_trades": int(total_trades),
                "total_wins": int(total_wins),
                "win_rate": round(win_rate, 1),
                "win_days": win_days,
                "loss_days": loss_days,
                "total_pnl": round(total_pnl, 0),
                "avg_daily_pnl": round(avg_daily_pnl, 1),
                "max_drawdown": round(max_dd, 0),
                "avg_amplitude": round(avg_amp, 2),
            })

        self.stock_summary = pd.DataFrame(rows).sort_values("total_pnl", ascending=False).reset_index(drop=True)

    def _compute_portfolio(self):
        """Compute portfolio-level (aggregated) metrics."""
        if not self.stock_results:
            return

        # Build portfolio daily PnL by summing across all stocks
        all_dates = set()
        for df in self.stock_results.values():
            all_dates.update(df["date"].tolist())
        all_dates = sorted(all_dates)

        daily_pnl_list = []
        for d in all_dates:
            day_total = 0.0
            for df in self.stock_results.values():
                row = df[df["date"] == d]
                if not row.empty:
                    day_total += row.iloc[0]["day_pnl"]
            daily_pnl_list.append({"date": d, "daily_pnl": round(day_total, 2)})

        pdf = pd.DataFrame(daily_pnl_list)
        pdf["cumulative_pnl"] = pdf["daily_pnl"].cumsum()
        pdf["peak"] = pdf["cumulative_pnl"].cummax()
        pdf["drawdown"] = pdf["cumulative_pnl"] - pdf["peak"]
        self.portfolio_daily = pdf

        total_pnl = pdf["cumulative_pnl"].iloc[-1] if not pdf.empty else 0
        trading_days = len(pdf)
        avg_daily = pdf["daily_pnl"].mean() if not pdf.empty else 0
        std_daily = pdf["daily_pnl"].std() if not pdf.empty else 1
        max_dd = pdf["drawdown"].min() if not pdf.empty else 0
        win_days = len(pdf[pdf["daily_pnl"] > 0])
        loss_days = len(pdf[pdf["daily_pnl"] < 0])
        flat_days = len(pdf[pdf["daily_pnl"] == 0])

        # Total capital deployed = T_CAPITAL * number of stocks traded
        n_stocks = len(self.stock_results)
        total_capital = T_CAPITAL * n_stocks
        annualized_return = (total_pnl / total_capital * 100) * (250 / trading_days) if trading_days > 0 else 0
        sharpe = (avg_daily / std_daily) * np.sqrt(250) if std_daily > 0 else 0
        calmar = abs(annualized_return / (max_dd / total_capital * 100)) if max_dd != 0 else 999

        self.portfolio_metrics = {
            "total_pnl": round(total_pnl, 0),
            "total_capital": total_capital,
            "trading_days": trading_days,
            "n_stocks": n_stocks,
            "avg_daily_pnl": round(avg_daily, 1),
            "std_daily_pnl": round(std_daily, 1),
            "annualized_return_pct": round(annualized_return, 2),
            "sharpe_ratio": round(sharpe, 2),
            "calmar_ratio": round(calmar, 2),
            "max_drawdown": round(max_dd, 0),
            "max_drawdown_pct": round(max_dd / total_capital * 100, 2) if total_capital > 0 else 0,
            "win_days": win_days,
            "loss_days": loss_days,
            "flat_days": flat_days,
            "win_day_rate": round(win_days / trading_days * 100, 1) if trading_days > 0 else 0,
        }


# ============================================================
# Section 4: HTML Report Generator
# ============================================================
class HTMLReportGenerator:
    """Generate a self-contained HTML report with matplotlib charts."""

    # A-share color convention: red = profit, green = loss
    COLOR_PROFIT = "#c23531"
    COLOR_LOSS = "#2f4554"
    COLOR_ACCENT = "#d48265"
    COLOR_BG = "#fafafa"

    def __init__(self, engine: T0BacktestEngine, output_path: Path):
        self.engine = engine
        self.output_path = output_path
        self._font_ready = False

    def generate(self):
        """Main entry: generate the full HTML report."""
        self._setup_chinese_font()

        logger.info("Generating charts ...")
        charts = {
            "equity_curve": self._chart_equity_curve(),
            "stock_ranking": self._chart_stock_ranking(),
            "win_rate": self._chart_win_rate(),
            "monthly_heatmap": self._chart_monthly_heatmap(),
            "amplitude_dist": self._chart_amplitude_distribution(),
            "pnl_dist": self._chart_daily_pnl_distribution(),
            "drawdown": self._chart_drawdown(),
        }

        logger.info("Building HTML ...")
        html = self._render_html(charts)

        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.output_path, "w", encoding="utf-8") as f:
            f.write(html)

        logger.info(f"Report saved to: {self.output_path}")

    def _setup_chinese_font(self):
        """Configure matplotlib to use a Chinese font."""
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.font_manager as fm

        # Check for Microsoft YaHei which we know exists on this system
        font_path = Path.home() / ".fonts" / "msyh.ttc"
        if font_path.exists():
            fm.fontManager.addfont(str(font_path))
            plt.rcParams["font.sans-serif"] = ["Microsoft YaHei"] + plt.rcParams.get("font.sans-serif", [])
            plt.rcParams["axes.unicode_minus"] = False
            self._font_ready = True
            logger.info(f"Chinese font loaded: Microsoft YaHei ({font_path})")
            return

        # Fallback: scan for any Chinese font
        candidates = ["SimHei", "WenQuanYi", "Noto Sans CJK", "Source Han Sans", "Alibaba PuHuiTi"]
        for name in candidates:
            matches = [f for f in fm.fontManager.ttflist if name.lower() in f.name.lower()]
            if matches:
                plt.rcParams["font.sans-serif"] = [matches[0].name] + plt.rcParams.get("font.sans-serif", [])
                plt.rcParams["axes.unicode_minus"] = False
                self._font_ready = True
                logger.info(f"Chinese font loaded: {matches[0].name}")
                return

        logger.warning("No Chinese font found. Charts will use stock codes instead of names.")
        self._font_ready = False

    def _fig_to_base64(self, fig) -> str:
        """Convert matplotlib figure to base64 data URI."""
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=150, bbox_inches="tight", facecolor="white")
        buf.seek(0)
        import matplotlib.pyplot as plt
        plt.close(fig)
        return "data:image/png;base64," + base64.b64encode(buf.read()).decode("utf-8")

    def _get_label(self, ts_code: str) -> str:
        """Get display label for a stock (name if font ready, else code)."""
        if self._font_ready:
            row = self.engine.stock_summary[self.engine.stock_summary["ts_code"] == ts_code]
            if not row.empty:
                return f'{row.iloc[0]["name"]}'
        return ts_code.split(".")[0]

    def _chart_equity_curve(self) -> str:
        import matplotlib.pyplot as plt

        pdf = self.engine.portfolio_daily
        if pdf.empty:
            return ""

        fig, ax = plt.subplots(figsize=(14, 5))
        dates = pd.to_datetime(pdf["date"], format="%Y%m%d")
        cum_pnl = pdf["cumulative_pnl"].values

        ax.fill_between(dates, cum_pnl, 0, where=(cum_pnl >= 0), alpha=0.3, color=self.COLOR_PROFIT)
        ax.fill_between(dates, cum_pnl, 0, where=(cum_pnl < 0), alpha=0.3, color=self.COLOR_LOSS)
        ax.plot(dates, cum_pnl, color=self.COLOR_PROFIT, linewidth=1.5)
        ax.axhline(y=0, color="gray", linestyle="--", linewidth=0.8)
        ax.set_title("Portfolio Cumulative PnL (Equity Curve)", fontsize=14, fontweight="bold")
        ax.set_ylabel("Cumulative PnL (CNY)")
        ax.grid(True, alpha=0.3)
        fig.autofmt_xdate()
        fig.tight_layout()
        return self._fig_to_base64(fig)

    def _chart_stock_ranking(self) -> str:
        import matplotlib.pyplot as plt

        summary = self.engine.stock_summary
        if summary.empty:
            return ""

        fig, ax = plt.subplots(figsize=(10, max(6, len(summary) * 0.35)))
        labels = [f"{r['name']}({r['ts_code'].split('.')[0]})" for _, r in summary.iterrows()]
        values = summary["total_pnl"].values
        colors = [self.COLOR_PROFIT if v >= 0 else self.COLOR_LOSS for v in values]

        y_pos = range(len(labels))
        ax.barh(y_pos, values, color=colors, height=0.7)
        ax.set_yticks(y_pos)
        ax.set_yticklabels(labels, fontsize=9)
        ax.invert_yaxis()
        ax.set_xlabel("Total PnL (CNY)")
        ax.set_title("Per-Stock Total PnL Ranking", fontsize=14, fontweight="bold")
        ax.axvline(x=0, color="gray", linewidth=0.8)
        ax.grid(True, axis="x", alpha=0.3)

        # Add value labels
        for i, v in enumerate(values):
            offset = max(abs(values.max()), abs(values.min())) * 0.02
            ax.text(v + (offset if v >= 0 else -offset), i, f"{v:,.0f}",
                    va="center", ha="left" if v >= 0 else "right", fontsize=8)

        fig.tight_layout()
        return self._fig_to_base64(fig)

    def _chart_win_rate(self) -> str:
        import matplotlib.pyplot as plt

        summary = self.engine.stock_summary.sort_values("win_rate", ascending=True)
        if summary.empty:
            return ""

        fig, ax = plt.subplots(figsize=(10, max(6, len(summary) * 0.35)))
        labels = [f"{r['name']}({r['ts_code'].split('.')[0]})" for _, r in summary.iterrows()]
        values = summary["win_rate"].values

        colors = [self.COLOR_PROFIT if v >= 80 else (self.COLOR_ACCENT if v >= 75 else self.COLOR_LOSS) for v in values]
        ax.barh(range(len(labels)), values, color=colors, height=0.7)
        ax.set_yticks(range(len(labels)))
        ax.set_yticklabels(labels, fontsize=9)
        ax.set_xlabel("Win Rate (%)")
        ax.set_title("Per-Stock T-Trade Win Rate", fontsize=14, fontweight="bold")
        avg_rate = values.mean()
        ax.axvline(x=avg_rate, color=self.COLOR_ACCENT, linestyle="--", linewidth=1.2,
                    label=f"Avg: {avg_rate:.1f}%")
        ax.legend(fontsize=10)
        ax.grid(True, axis="x", alpha=0.3)
        ax.set_xlim(0, 100)
        fig.tight_layout()
        return self._fig_to_base64(fig)

    def _chart_monthly_heatmap(self) -> str:
        import matplotlib.pyplot as plt
        from matplotlib.colors import LinearSegmentedColormap

        # Build month x stock matrix
        monthly_data = {}
        for ts_code, df in self.engine.stock_results.items():
            df_copy = df.copy()
            df_copy["month"] = df_copy["date"].astype(str).str[:6]
            monthly = df_copy.groupby("month")["day_pnl"].sum()
            name = self._get_label(ts_code)
            monthly_data[name] = monthly

        if not monthly_data:
            return ""

        matrix = pd.DataFrame(monthly_data).T.fillna(0)
        matrix = matrix.reindex(sorted(matrix.columns), axis=1)

        fig, ax = plt.subplots(figsize=(max(10, len(matrix.columns) * 1.2), max(6, len(matrix) * 0.4)))

        # Custom A-share colormap: green (loss) -> white -> red (profit)
        cmap = LinearSegmentedColormap.from_list("ashare", ["#2f9e44", "#ffffff", "#c92a2a"])
        vmax = max(abs(matrix.values.max()), abs(matrix.values.min()))
        im = ax.imshow(matrix.values, cmap=cmap, aspect="auto", vmin=-vmax, vmax=vmax)

        ax.set_xticks(range(len(matrix.columns)))
        ax.set_xticklabels([f"{c[:4]}-{c[4:]}" for c in matrix.columns], rotation=45, ha="right", fontsize=9)
        ax.set_yticks(range(len(matrix.index)))
        ax.set_yticklabels(matrix.index, fontsize=9)
        ax.set_title("Monthly PnL Heatmap (CNY)", fontsize=14, fontweight="bold")

        # Add text annotations
        for i in range(len(matrix.index)):
            for j in range(len(matrix.columns)):
                val = matrix.iloc[i, j]
                if abs(val) > 0:
                    color = "white" if abs(val) > vmax * 0.6 else "black"
                    ax.text(j, i, f"{val:,.0f}", ha="center", va="center", fontsize=7, color=color)

        fig.colorbar(im, ax=ax, shrink=0.8, label="PnL (CNY)")
        fig.tight_layout()
        return self._fig_to_base64(fig)

    def _chart_amplitude_distribution(self) -> str:
        import matplotlib.pyplot as plt

        all_amps = []
        for df in self.engine.stock_results.values():
            all_amps.extend(df["amplitude"].tolist())

        if not all_amps:
            return ""

        fig, ax = plt.subplots(figsize=(10, 5))
        ax.hist(all_amps, bins=np.arange(0, 12, 0.25), color=self.COLOR_ACCENT, alpha=0.8, edgecolor="white")
        ax.axvline(x=T_SPREAD_TARGET, color=self.COLOR_PROFIT, linestyle="--", linewidth=2,
                    label=f"T Threshold: {T_SPREAD_TARGET}%")
        ax.axvline(x=DOUBLE_T_THRESHOLD, color="#91cc75", linestyle="--", linewidth=1.5,
                    label=f"Double-T Threshold: {DOUBLE_T_THRESHOLD}%")

        # Shade T opportunity area
        ax.axvspan(T_SPREAD_TARGET, 12, alpha=0.08, color=self.COLOR_PROFIT)

        ax.set_xlabel("Daily Amplitude (%)")
        ax.set_ylabel("Frequency (days)")
        ax.set_title("Daily Amplitude Distribution (All Stocks)", fontsize=14, fontweight="bold")
        ax.legend(fontsize=10)
        ax.grid(True, axis="y", alpha=0.3)
        fig.tight_layout()
        return self._fig_to_base64(fig)

    def _chart_daily_pnl_distribution(self) -> str:
        import matplotlib.pyplot as plt

        pdf = self.engine.portfolio_daily
        if pdf.empty:
            return ""

        fig, ax = plt.subplots(figsize=(10, 5))
        pnl_values = pdf["daily_pnl"].values
        ax.hist(pnl_values, bins=50, color=self.COLOR_ACCENT, alpha=0.8, edgecolor="white")
        ax.axvline(x=np.mean(pnl_values), color=self.COLOR_PROFIT, linestyle="--", linewidth=1.5,
                    label=f"Mean: {np.mean(pnl_values):,.0f}")
        ax.axvline(x=np.median(pnl_values), color=self.COLOR_LOSS, linestyle=":", linewidth=1.5,
                    label=f"Median: {np.median(pnl_values):,.0f}")
        ax.axvline(x=0, color="gray", linewidth=0.8)
        ax.set_xlabel("Daily PnL (CNY)")
        ax.set_ylabel("Frequency")
        ax.set_title("Portfolio Daily PnL Distribution", fontsize=14, fontweight="bold")
        ax.legend(fontsize=10)
        ax.grid(True, axis="y", alpha=0.3)
        fig.tight_layout()
        return self._fig_to_base64(fig)

    def _chart_drawdown(self) -> str:
        import matplotlib.pyplot as plt

        pdf = self.engine.portfolio_daily
        if pdf.empty:
            return ""

        fig, ax = plt.subplots(figsize=(14, 4))
        dates = pd.to_datetime(pdf["date"], format="%Y%m%d")
        dd = pdf["drawdown"].values

        ax.fill_between(dates, dd, 0, alpha=0.5, color=self.COLOR_LOSS)
        ax.plot(dates, dd, color=self.COLOR_LOSS, linewidth=1)
        ax.set_title("Portfolio Drawdown", fontsize=14, fontweight="bold")
        ax.set_ylabel("Drawdown (CNY)")
        ax.grid(True, alpha=0.3)
        fig.autofmt_xdate()
        fig.tight_layout()
        return self._fig_to_base64(fig)

    def _render_html(self, charts: dict) -> str:
        """Assemble the full HTML report."""
        m = self.engine.portfolio_metrics
        summary_df = self.engine.stock_summary

        # Build stock detail table rows
        stock_rows = ""
        for i, (_, r) in enumerate(summary_df.iterrows(), 1):
            pnl_color = self.COLOR_PROFIT if r["total_pnl"] >= 0 else self.COLOR_LOSS
            stock_rows += f"""
            <tr>
                <td>{i}</td>
                <td><strong>{r['name']}</strong></td>
                <td>{r['ts_code']}</td>
                <td>{r['industry']}</td>
                <td>{r['total_days']}</td>
                <td>{r['t_opportunity_days']} ({r['t_rate_pct']}%)</td>
                <td>{r['double_t_days']}</td>
                <td>{r['total_trades']}</td>
                <td>{r['total_wins']} / {r['total_trades'] - r['total_wins']}</td>
                <td>{r['win_rate']}%</td>
                <td style="color:{pnl_color};font-weight:bold">{r['total_pnl']:,.0f}</td>
                <td>{r['avg_daily_pnl']:,.1f}</td>
                <td>{r['max_drawdown']:,.0f}</td>
                <td>{r['avg_amplitude']}%</td>
            </tr>"""

        # Monthly aggregate table
        monthly_agg = {}
        for df in self.engine.stock_results.values():
            df_copy = df.copy()
            df_copy["month"] = df_copy["date"].astype(str).str[:6]
            for month, group in df_copy.groupby("month"):
                monthly_agg[month] = monthly_agg.get(month, 0) + group["day_pnl"].sum()

        monthly_rows = ""
        for month in sorted(monthly_agg.keys()):
            val = monthly_agg[month]
            pnl_color = self.COLOR_PROFIT if val >= 0 else self.COLOR_LOSS
            month_label = f"{month[:4]}-{month[4:]}"
            monthly_rows += f"""
            <tr>
                <td>{month_label}</td>
                <td style="color:{pnl_color};font-weight:bold">{val:,.0f}</td>
            </tr>"""

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        pnl_color_total = self.COLOR_PROFIT if m.get("total_pnl", 0) >= 0 else self.COLOR_LOSS

        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>T+0 2.5% Strategy Backtest Report</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: "Microsoft YaHei", "PingFang SC", "Helvetica Neue", Arial, sans-serif;
    background: #f0f2f5; color: #333; line-height: 1.6;
  }}
  .container {{ max-width: 1200px; margin: 0 auto; padding: 20px; }}
  header {{
    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
    color: white; padding: 30px 40px; border-radius: 12px; margin-bottom: 24px;
  }}
  header h1 {{ font-size: 26px; margin-bottom: 8px; }}
  header p {{ opacity: 0.85; font-size: 14px; }}
  .kpi-grid {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 16px; margin-bottom: 24px;
  }}
  .kpi-card {{
    background: white; border-radius: 10px; padding: 20px; text-align: center;
    box-shadow: 0 2px 8px rgba(0,0,0,0.06);
  }}
  .kpi-card .label {{ font-size: 13px; color: #888; margin-bottom: 6px; }}
  .kpi-card .value {{ font-size: 24px; font-weight: bold; }}
  .section {{
    background: white; border-radius: 10px; padding: 24px;
    margin-bottom: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.06);
  }}
  .section h2 {{
    font-size: 18px; margin-bottom: 16px; padding-bottom: 8px;
    border-bottom: 2px solid #eee;
  }}
  .section img {{ width: 100%; border-radius: 6px; }}
  table {{
    width: 100%; border-collapse: collapse; font-size: 13px;
  }}
  th {{
    background: #f7f7f7; padding: 10px 8px; text-align: left;
    border-bottom: 2px solid #ddd; font-weight: 600; white-space: nowrap;
  }}
  td {{ padding: 8px; border-bottom: 1px solid #eee; }}
  tr:hover {{ background: #fafafa; }}
  .disclaimer {{
    background: #fff9db; border-left: 4px solid #fab005;
    padding: 16px 20px; border-radius: 0 8px 8px 0; margin-top: 20px;
    font-size: 13px; color: #666;
  }}
  .two-col {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }}
  .params-table td {{ padding: 6px 12px; }}
  .params-table td:first-child {{ font-weight: 600; color: #555; white-space: nowrap; }}
  footer {{
    text-align: center; color: #aaa; font-size: 12px; padding: 20px; margin-top: 16px;
  }}
  @media (max-width: 768px) {{
    .two-col {{ grid-template-columns: 1fr; }}
    .kpi-grid {{ grid-template-columns: repeat(2, 1fr); }}
  }}
</style>
</head>
<body>
<div class="container">

<header>
  <h1>T+0 2.5% Strategy Backtest Report</h1>
  <p>Generated: {now_str} | Period: {self.engine.backtest_days} trading days |
     Stocks: {m.get('n_stocks', 0)} | Capital per T: {T_CAPITAL:,} CNY</p>
</header>

<!-- KPI Cards -->
<div class="kpi-grid">
  <div class="kpi-card">
    <div class="label">Total PnL</div>
    <div class="value" style="color:{pnl_color_total}">{m.get('total_pnl', 0):,.0f} CNY</div>
  </div>
  <div class="kpi-card">
    <div class="label">Annualized Return</div>
    <div class="value">{m.get('annualized_return_pct', 0):.1f}%</div>
  </div>
  <div class="kpi-card">
    <div class="label">Win Day Rate</div>
    <div class="value">{m.get('win_day_rate', 0):.1f}%</div>
  </div>
  <div class="kpi-card">
    <div class="label">Max Drawdown</div>
    <div class="value" style="color:{self.COLOR_LOSS}">{m.get('max_drawdown', 0):,.0f}</div>
  </div>
  <div class="kpi-card">
    <div class="label">Sharpe Ratio</div>
    <div class="value">{m.get('sharpe_ratio', 0):.2f}</div>
  </div>
  <div class="kpi-card">
    <div class="label">Avg Daily PnL</div>
    <div class="value">{m.get('avg_daily_pnl', 0):,.0f} CNY</div>
  </div>
</div>

<!-- Equity Curve -->
<div class="section">
  <h2>Portfolio Equity Curve</h2>
  <img src="{charts.get('equity_curve', '')}" alt="Equity Curve">
</div>

<!-- Stock Ranking + Win Rate -->
<div class="two-col">
  <div class="section">
    <h2>Per-Stock PnL Ranking</h2>
    <img src="{charts.get('stock_ranking', '')}" alt="Stock Ranking">
  </div>
  <div class="section">
    <h2>Per-Stock Win Rate</h2>
    <img src="{charts.get('win_rate', '')}" alt="Win Rate">
  </div>
</div>

<!-- Monthly Heatmap -->
<div class="section">
  <h2>Monthly PnL Heatmap</h2>
  <img src="{charts.get('monthly_heatmap', '')}" alt="Monthly Heatmap">
</div>

<!-- Distributions -->
<div class="two-col">
  <div class="section">
    <h2>Amplitude Distribution</h2>
    <img src="{charts.get('amplitude_dist', '')}" alt="Amplitude Distribution">
  </div>
  <div class="section">
    <h2>Daily PnL Distribution</h2>
    <img src="{charts.get('pnl_dist', '')}" alt="PnL Distribution">
  </div>
</div>

<!-- Drawdown -->
<div class="section">
  <h2>Portfolio Drawdown</h2>
  <img src="{charts.get('drawdown', '')}" alt="Drawdown">
</div>

<!-- Stock Detail Table -->
<div class="section">
  <h2>Per-Stock Detail</h2>
  <div style="overflow-x:auto">
  <table>
    <thead>
      <tr>
        <th>#</th><th>Name</th><th>Code</th><th>Industry</th>
        <th>Days</th><th>T-Days</th><th>2xT</th><th>Trades</th><th>W/L</th><th>Win%</th>
        <th>Total PnL</th><th>Avg Daily</th><th>Max DD</th><th>Avg Amp</th>
      </tr>
    </thead>
    <tbody>{stock_rows}</tbody>
  </table>
  </div>
</div>

<!-- Monthly Aggregate -->
<div class="two-col">
  <div class="section">
    <h2>Monthly Summary</h2>
    <table>
      <thead><tr><th>Month</th><th>PnL (CNY)</th></tr></thead>
      <tbody>{monthly_rows}</tbody>
    </table>
  </div>
  <div class="section">
    <h2>Strategy Parameters</h2>
    <table class="params-table">
      <tr><td>T Capital</td><td>{T_CAPITAL:,} CNY / trade</td></tr>
      <tr><td>Target Spread</td><td>{T_SPREAD_TARGET}%</td></tr>
      <tr><td>Commission</td><td>{COMMISSION_RATE}% (each side)</td></tr>
      <tr><td>Stamp Tax</td><td>{STAMP_TAX_RATE}% (sell only)</td></tr>
      <tr><td>Net Profit / T</td><td>{NET_PROFIT:,.0f} CNY</td></tr>
      <tr><td>Fail Loss / T</td><td>-{FAIL_LOSS:,.0f} CNY</td></tr>
      <tr><td>Double-T Threshold</td><td>>={DOUBLE_T_THRESHOLD}% amplitude</td></tr>
      <tr><td>Win Days / Loss Days</td><td>{m.get('win_days', 0)} / {m.get('loss_days', 0)}</td></tr>
      <tr><td>Total Capital Deployed</td><td>{m.get('total_capital', 0):,} CNY</td></tr>
      <tr><td>Calmar Ratio</td><td>{m.get('calmar_ratio', 0):.2f}</td></tr>
    </table>
  </div>
</div>

<!-- Disclaimer -->
<div class="disclaimer">
  <strong>Disclaimer / Important Notes:</strong><br>
  1. This backtest uses daily OHLC bars and an expected-value model. It is a theoretical feasibility assessment,
     NOT an exact simulation of intraday T+0 trading.<br>
  2. Real-world results depend on execution timing, slippage, market conditions, and trader skill.<br>
  3. Success rates are modeled estimates based on amplitude tiers. Actual success rates vary.<br>
  4. Past performance does not guarantee future results. This report is for research purposes only.
</div>

<footer>
  T+0 Backtest Report | Generated by daily_stock_analysis | {now_str}
</footer>

</div>
</body>
</html>"""
        return html


# ============================================================
# Section 5: Main Entry Point
# ============================================================
def main():
    parser = argparse.ArgumentParser(description="T+0 2.5% Day-Trading Backtest")
    parser.add_argument("--top-n", type=int, default=30, help="Number of stocks from pool (default: 30)")
    parser.add_argument("--days", type=int, default=250, help="Backtest trading days (default: 250)")
    parser.add_argument("--capital", type=float, default=20000, help="Capital per T trade in CNY (default: 20000)")
    parser.add_argument("--spread", type=float, default=2.5, help="Target T spread %% (default: 2.5)")
    parser.add_argument("--output", type=str, default=None, help="Output HTML path")
    parser.add_argument("--refresh", action="store_true", help="Force re-fetch data (ignore cache)")
    args = parser.parse_args()

    if not TUSHARE_TOKEN:
        logger.error("TUSHARE_TOKEN not set in .env!")
        sys.exit(1)

    # Apply args to global config
    global T_CAPITAL, T_SPREAD_TARGET, GROSS_PROFIT, NET_PROFIT, FAIL_LOSS
    T_CAPITAL = args.capital
    T_SPREAD_TARGET = args.spread
    GROSS_PROFIT = T_CAPITAL * T_SPREAD_TARGET / 100
    ROUND_TRIP = T_CAPITAL * (2 * COMMISSION_RATE + STAMP_TAX_RATE) / 100
    NET_PROFIT = GROSS_PROFIT - ROUND_TRIP
    FAIL_LOSS = T_CAPITAL * FAIL_LOSS_PCT / 100 + ROUND_TRIP

    output_path = Path(args.output) if args.output else OUTPUT_DIR / "t0_backtest_report.html"

    logger.info("=" * 60)
    logger.info("T+0 2.5% Day-Trading Backtest")
    logger.info("=" * 60)
    logger.info(f"  Stocks: Top {args.top_n} | Days: {args.days}")
    logger.info(f"  Capital/T: {T_CAPITAL:,.0f} | Spread: {T_SPREAD_TARGET}%")
    logger.info(f"  Net profit/T: {NET_PROFIT:,.0f} | Fail loss/T: -{FAIL_LOSS:,.0f}")
    logger.info("=" * 60)

    # Step 1: Load stock pool
    engine = T0BacktestEngine(top_n=args.top_n, backtest_days=args.days)
    engine.load_stock_pool()

    # Step 2: Fetch data
    engine.fetch_daily_data(refresh=args.refresh)

    # Step 3: Run backtest
    logger.info("Running backtest ...")
    engine.run_backtest()

    # Print summary to console
    m = engine.portfolio_metrics
    logger.info("=" * 60)
    logger.info("BACKTEST RESULTS")
    logger.info("=" * 60)
    logger.info(f"  Total PnL:         {m['total_pnl']:>12,.0f} CNY")
    logger.info(f"  Annualized Return: {m['annualized_return_pct']:>12.1f}%")
    logger.info(f"  Win Day Rate:      {m['win_day_rate']:>12.1f}%")
    logger.info(f"  Max Drawdown:      {m['max_drawdown']:>12,.0f} CNY ({m['max_drawdown_pct']:.1f}%)")
    logger.info(f"  Sharpe Ratio:      {m['sharpe_ratio']:>12.2f}")
    logger.info(f"  Avg Daily PnL:     {m['avg_daily_pnl']:>12,.0f} CNY")
    logger.info("=" * 60)

    # Step 4: Generate report
    logger.info("Generating HTML report ...")
    reporter = HTMLReportGenerator(engine, output_path)
    reporter.generate()

    logger.info(f"\nDone! Open report: {output_path}")


if __name__ == "__main__":
    main()
