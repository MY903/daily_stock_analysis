# -*- coding: utf-8 -*-
"""
TQQQ 条件单策略回测 + 参数优化
=================================

策略逻辑（条件单模式，默认同一天出场）：
1. 每个交易日开盘后挂限价买单，价格 = 开盘价 × (1 - buy_pct%)
2. 若买单成交（日内最低价 ≤ 买入价），同时挂：
   - 止盈单：买入价 × (1 + tp_pct%)
   - 止损单：买入价 × (1 - sl_pct%)
3. 哪个先触发就按哪个价格出场
4. 若当日未触发买入条件，跳过，等下一个交易日
5. 若买入后止盈止损均未触发，收盘价出场

跨日持仓模式（--hold-mode）：
- 买入成交后持仓跨日，直到止盈或止损触发才卖出
- 模拟真实的 GTC 订单行为

Usage:
    python scripts/tqqq_condition_order_backtest.py                     # 完整运行
    python scripts/tqqq_condition_order_backtest.py --quick             # 快速测试
    python scripts/tqqq_condition_order_backtest.py --years 3           # 指定回测年限
    python scripts/tqqq_condition_order_backtest.py --hold-mode         # 跨日持仓模式
    python scripts/tqqq_condition_order_backtest.py --hold-mode --quick # 跨日+快速模式
"""

import argparse
import itertools
import logging
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

OUTPUT_DIR = PROJECT_ROOT / "reports"
TQQQ_TICKER = "TQQQ"

# ============================================================
# Tiger Trade 手续费配置
# ============================================================
# 基于 Tiger Brokers 2025年5月22日生效的费率:
# - 佣金: $0.0039/股, 最低 $0.99/笔, 最高交易额的0.5%
# - 平台费(固定式): $0.004/股, 最低 $1.00/笔, 最高交易额的0.5%
# - 外部机构费: $0.00396/股, 最低 $0.99/笔
# - SEC 规费(仅卖单): 0.00206% of 交易额, 最低 $0.01
# - 综合审计追踪费: $0.00021/股(仅卖单)
#
# 对于 35股 TQQQ: 每边约 $1.99, 双边约 $3.98
# ============================================================

# 交易数量（股），和 trading.yaml 保持一致
TRADE_QUANTITY = 35

# 费用参数（美元）
FEE_COMMISSION_PER_SHARE = 0.0039       # 佣金 $/股
FEE_COMMISSION_MIN = 0.99                # 佣金最低 $/笔
FEE_PLATFORM_PER_SHARE = 0.004           # 平台费 $/股
FEE_PLATFORM_MIN = 1.00                  # 平台费最低 $/笔
FEE_THIRD_PARTY_PER_SHARE = 0.00396      # 外部机构费 $/股
FEE_THIRD_PARTY_MIN = 0.99               # 外部机构费最低 $/笔
FEE_SEC_PCT = 0.0000206                  # SEC 规费（仅卖单）
FEE_SEC_MIN = 0.01                       # SEC 规费最低 $


# ============================================================
# 数据获取
# ============================================================

def fetch_tqqq_data(years: int = 5) -> pd.DataFrame:
    """从 Yahoo Finance 获取 TQQQ 日线 OHLC 数据。"""
    import yfinance as yf

    end_date = datetime.now()
    start_date = end_date - timedelta(days=int(years * 365) + 60)

    logger.info(f"正在获取 {TQQQ_TICKER} 日线数据 ({start_date.date()} ~ {end_date.date()}) ...")
    tqqq = yf.Ticker(TQQQ_TICKER)
    df = tqqq.history(start=start_date, end=end_date, auto_adjust=True)

    if df.empty:
        logger.error(f"未获取到 {TQQQ_TICKER} 数据！")
        sys.exit(1)

    # yfinance 列名: Open, High, Low, Close, Volume
    df = df.rename(columns={
        "Open": "open", "High": "high", "Low": "low",
        "Close": "close", "Volume": "volume"
    })
    df.index = pd.to_datetime(df.index)
    df = df.sort_index()

    # 只保留交易日
    df = df[df["volume"] > 0].copy()
    logger.info(f"获取到 {len(df)} 个交易日数据 ({df.index[0].date()} ~ {df.index[-1].date()})")
    return df


# ============================================================
# 手续费计算
# ============================================================

def calc_trade_fees(price: float, quantity: int, is_sell: bool = False) -> float:
    """
    计算 Tiger Trade 单笔交易手续费（美元）。

    Args:
        price: 成交价格
        quantity: 成交股数
        is_sell: 是否为卖出（卖出需加 SEC 规费）

    Returns:
        总手续费（美元）
    """
    trade_value = price * quantity

    # 佣金
    commission = max(quantity * FEE_COMMISSION_PER_SHARE, FEE_COMMISSION_MIN)
    commission = min(commission, trade_value * 0.005)  # 最高交易额的0.5%

    # 平台费
    platform = max(quantity * FEE_PLATFORM_PER_SHARE, FEE_PLATFORM_MIN)
    platform = min(platform, trade_value * 0.005)  # 最高交易额的0.5%

    # 外部机构费
    third_party = max(quantity * FEE_THIRD_PARTY_PER_SHARE, FEE_THIRD_PARTY_MIN)

    total = commission + platform + third_party

    # SEC 规费（仅卖单）
    if is_sell:
        sec_fee = max(trade_value * FEE_SEC_PCT, FEE_SEC_MIN)
        total += sec_fee

    return round(total, 2)


def calc_round_trip_fees(buy_price: float, sell_price: float, quantity: int) -> float:
    """计算一次完整交易（买入+卖出）的总手续费。"""
    buy_fee = calc_trade_fees(buy_price, quantity, is_sell=False)
    sell_fee = calc_trade_fees(sell_price, quantity, is_sell=True)
    return round(buy_fee + sell_fee, 2)


# ============================================================
# 单次回测引擎（固定参数）
# ============================================================

@dataclass
class TradeRecord:
    date: pd.Timestamp
    open_price: float
    buy_price: float
    buy_triggered: bool
    tp_price: Optional[float] = None
    sl_price: Optional[float] = None
    exit_price: Optional[float] = None
    exit_reason: str = "none"       # tp / sl / close / close_end / unfilled
    return_pct: Optional[float] = None  # 未扣费的收益率(%)
    net_return_pct: Optional[float] = None  # 扣费后净收益率(%)
    day_high: Optional[float] = None
    day_low: Optional[float] = None
    day_close: Optional[float] = None
    total_fees: float = 0.0      # 双边手续费($)
    gross_profit_pct: float = 0.0  # 毛利率(%)
    net_profit_pct: float = 0.0  # 净利率(%)
    hold_days: int = 0           # 持仓天数（跨日模式用）


@dataclass
class BacktestResult:
    """单组参数的回测结果。"""
    buy_pct: float
    tp_pct: float
    sl_pct: float

    total_days: int = 0
    buy_triggered_days: int = 0
    tp_hit: int = 0
    sl_hit: int = 0
    close_exit: int = 0

    total_return_pct: float = 0.0
    net_total_return_pct: float = 0.0  # 扣费后总收益率
    avg_return_pct: float = 0.0
    win_rate_pct: float = 0.0
    profit_factor: float = 0.0
    max_drawdown_pct: float = 0.0
    sharpe_ratio: float = 0.0
    win_count: int = 0
    loss_count: int = 0

    # 手续费统计
    total_fees_usd: float = 0.0        # 总手续费($)
    avg_fee_per_trade: float = 0.0     # 每笔平均手续费($)
    fee_pct_of_capital: float = 0.0    # 手续费占投入资金比例(%)

    # 累计权益曲线（用于计算回撤等）
    equity_curve: List[float] = field(default_factory=list)
    gross_equity_curve: List[float] = field(default_factory=list)  # 未扣费权益曲线
    trade_records: List[TradeRecord] = field(default_factory=list)
    cumulative_return: float = 0.0

    # 年化收益
    annualized_return_pct: float = 0.0
    net_annualized_return_pct: float = 0.0  # 扣费后年化

    # 跨日持仓统计
    avg_hold_days: float = 0.0        # 平均持仓天数
    max_hold_days: int = 0            # 最长持仓天数


def run_single_backtest(
    df: pd.DataFrame,
    buy_pct: float,
    tp_pct: float,
    sl_pct: float,
    hold_across_days: bool = False,
) -> BacktestResult:
    """
    对单组参数 run 回测。

    hold_across_days=False（旧模式 - 同一天出场）：
    - 每个交易日开盘挂限价买单，买入价 = open × (1 - buy_pct)
    - 若日内最低价 ≤ 买入价，认为成交
    - 成交后同时看止盈（买入价 × (1+tp_pct)）和止损（买入价 × (1-sl_pct)）
    - 若两者都不可达，收盘价出场
    - 每个交易日独立，不持仓过夜

    hold_across_days=True（新模式 - 跨日持仓）：
    - 买入成交后持仓跨日，直到止盈或止损触发才卖出
    - 卖出后回到 IDLE，继续等下一次买入信号
    - 模拟真实的 GTC 订单行为
    """
    result = BacktestResult(
        buy_pct=buy_pct,
        tp_pct=tp_pct,
        sl_pct=sl_pct,
    )

    trades: List[TradeRecord] = []
    equity = [1.0]          # 起始净值（扣费后）
    gross_equity = [1.0]    # 起始净值（不扣费）

    total_fees_acc = 0.0
    is_last_day = False

    # 跨日持仓状态
    pos_entry_date: Optional[pd.Timestamp] = None
    pos_entry_price: Optional[float] = None
    pos_tp_price: Optional[float] = None
    pos_sl_price: Optional[float] = None

    for day_idx, (idx, row) in enumerate(df.iterrows()):
        o, h, l, c = row["open"], row["high"], row["low"], row["close"]
        is_last_day = (day_idx == len(df) - 1)

        if pos_entry_price is not None:
            # ========== HOLDING 状态：检查止盈/止损 ==========
            tp_reachable = h >= pos_tp_price
            sl_reachable = l <= pos_sl_price

            if tp_reachable and sl_reachable:
                if c >= pos_entry_price:
                    exit_price = pos_tp_price
                    exit_reason = "tp"
                else:
                    exit_price = pos_sl_price
                    exit_reason = "sl"
            elif tp_reachable:
                exit_price = pos_tp_price
                exit_reason = "tp"
            elif sl_reachable:
                exit_price = pos_sl_price
                exit_reason = "sl"
            elif hold_across_days and not is_last_day:
                # 新模式 + 未到最后一天 → 继续持仓过夜
                rec = TradeRecord(
                    date=idx,
                    open_price=o,
                    buy_price=pos_entry_price,
                    buy_triggered=False,
                    tp_price=pos_tp_price,
                    sl_price=pos_sl_price,
                    day_high=h,
                    day_low=l,
                    day_close=c,
                )
                equity.append(equity[-1])
                gross_equity.append(gross_equity[-1])
                result.total_days += 1
                trades.append(rec)
                continue
            else:
                # 旧模式收盘强平 or 最后一天 → 收盘出场
                exit_price = c
                exit_reason = "close_end" if hold_across_days else "close"

            # ---- 出场计算 ----
            hold_days = (idx - pos_entry_date).days if pos_entry_date is not None else 0
            gross_return_pct = (exit_price / pos_entry_price - 1) * 100

            buy_fee = calc_trade_fees(pos_entry_price, TRADE_QUANTITY, is_sell=False)
            sell_fee = calc_trade_fees(exit_price, TRADE_QUANTITY, is_sell=True)
            total_fees = buy_fee + sell_fee

            capital_invested = pos_entry_price * TRADE_QUANTITY + buy_fee
            capital_recovered = exit_price * TRADE_QUANTITY - sell_fee
            net_return_pct = (capital_recovered / capital_invested - 1) * 100

            rec = TradeRecord(
                date=idx,
                open_price=o,
                buy_price=pos_entry_price,
                buy_triggered=True,
                tp_price=pos_tp_price,
                sl_price=pos_sl_price,
                exit_price=exit_price,
                exit_reason=exit_reason,
                return_pct=gross_return_pct,
                net_return_pct=net_return_pct,
                day_high=h,
                day_low=l,
                day_close=c,
                total_fees=total_fees,
                gross_profit_pct=gross_return_pct,
                net_profit_pct=net_return_pct,
                hold_days=hold_days,
            )

            net_return_dec = net_return_pct / 100
            gross_return_dec = gross_return_pct / 100

            if net_return_pct > 0:
                result.win_count += 1
            elif net_return_pct < 0:
                result.loss_count += 1

            new_equity = equity[-1] * (1 + net_return_dec)
            new_gross_equity = gross_equity[-1] * (1 + gross_return_dec)
            equity.append(new_equity)
            gross_equity.append(new_gross_equity)
            total_fees_acc += total_fees

            result.buy_triggered_days += 1
            if exit_reason == "tp":
                result.tp_hit += 1
            elif exit_reason == "sl":
                result.sl_hit += 1
            else:
                result.close_exit += 1
            result.total_days += 1
            trades.append(rec)

            # 清空持仓
            pos_entry_date = None
            pos_entry_price = None
            pos_tp_price = None
            pos_sl_price = None

        else:
            # ========== IDLE 状态：检查买入信号 ==========
            buy_price = o * (1 - buy_pct)
            triggered = l <= buy_price

            rec = TradeRecord(
                date=idx,
                open_price=o,
                buy_price=buy_price,
                buy_triggered=triggered,
                day_high=h,
                day_low=l,
                day_close=c,
            )

            if not triggered:
                equity.append(equity[-1])
                gross_equity.append(gross_equity[-1])
                result.total_days += 1
                trades.append(rec)
                continue

            # 触发买入 — 设置持仓
            buy_actual = buy_price
            tp_price = buy_actual * (1 + tp_pct)
            sl_price = buy_actual * (1 - sl_pct)

            pos_entry_date = idx
            pos_entry_price = buy_actual
            pos_tp_price = tp_price
            pos_sl_price = sl_price

            rec.tp_price = tp_price
            rec.sl_price = sl_price

            if hold_across_days:
                if is_last_day:
                    # 最后一天买入 → 收盘强平
                    exit_price = c
                    exit_reason = "close_end"
                    gross_return_pct = (exit_price / buy_actual - 1) * 100
                    buy_fee = calc_trade_fees(buy_actual, TRADE_QUANTITY, is_sell=False)
                    sell_fee = calc_trade_fees(exit_price, TRADE_QUANTITY, is_sell=True)
                    total_fees = buy_fee + sell_fee
                    capital_invested = buy_actual * TRADE_QUANTITY + buy_fee
                    capital_recovered = exit_price * TRADE_QUANTITY - sell_fee
                    net_return_pct = (capital_recovered / capital_invested - 1) * 100
                    rec.exit_price = exit_price
                    rec.exit_reason = exit_reason
                    rec.return_pct = gross_return_pct
                    rec.net_return_pct = net_return_pct
                    rec.total_fees = total_fees
                    rec.gross_profit_pct = gross_return_pct
                    rec.net_profit_pct = net_return_pct
                    rec.hold_days = 0
                    net_return_dec = net_return_pct / 100
                    gross_return_dec = gross_return_pct / 100
                    if net_return_pct > 0:
                        result.win_count += 1
                    elif net_return_pct < 0:
                        result.loss_count += 1
                    new_equity = equity[-1] * (1 + net_return_dec)
                    new_gross_equity = gross_equity[-1] * (1 + gross_return_dec)
                    equity.append(new_equity)
                    gross_equity.append(new_gross_equity)
                    total_fees_acc += total_fees
                    result.buy_triggered_days += 1
                    result.close_exit += 1
                    result.total_days += 1
                    trades.append(rec)
                    pos_entry_date = None
                    pos_entry_price = None
                    pos_tp_price = None
                    pos_sl_price = None
                    continue
                else:
                    # 非最后一天：记录买入，后续日子继续持仓
                    equity.append(equity[-1])
                    gross_equity.append(gross_equity[-1])
                    result.total_days += 1
                    trades.append(rec)
                    continue

            # 旧模式：买入当天立即判断止盈/止损
            tp_reachable = h >= tp_price
            sl_reachable = l <= sl_price

            if tp_reachable and sl_reachable:
                if c >= buy_actual:
                    exit_price = tp_price
                    exit_reason = "tp"
                else:
                    exit_price = sl_price
                    exit_reason = "sl"
            elif tp_reachable:
                exit_price = tp_price
                exit_reason = "tp"
            elif sl_reachable:
                exit_price = sl_price
                exit_reason = "sl"
            else:
                exit_price = c
                exit_reason = "close"

            gross_return_pct = (exit_price / buy_actual - 1) * 100

            buy_fee = calc_trade_fees(buy_actual, TRADE_QUANTITY, is_sell=False)
            sell_fee = calc_trade_fees(exit_price, TRADE_QUANTITY, is_sell=True)
            total_fees = buy_fee + sell_fee

            capital_invested = buy_actual * TRADE_QUANTITY + buy_fee
            capital_recovered = exit_price * TRADE_QUANTITY - sell_fee
            net_return_pct = (capital_recovered / capital_invested - 1) * 100

            rec.exit_price = exit_price
            rec.exit_reason = exit_reason
            rec.return_pct = gross_return_pct
            rec.total_fees = total_fees
            rec.gross_profit_pct = gross_return_pct
            rec.net_return_pct = net_return_pct
            rec.hold_days = 0

            # 覆盖买入日的 equity（旧模式：买入日即结算）
            net_return_dec = net_return_pct / 100
            gross_return_dec = gross_return_pct / 100

            if net_return_pct > 0:
                result.win_count += 1
            elif net_return_pct < 0:
                result.loss_count += 1

            new_equity = equity[-1] * (1 + net_return_dec)
            new_gross_equity = gross_equity[-1] * (1 + gross_return_dec)
            equity.append(new_equity)
            gross_equity.append(new_gross_equity)
            total_fees_acc += total_fees

            result.buy_triggered_days += 1
            if exit_reason == "tp":
                result.tp_hit += 1
            elif exit_reason == "sl":
                result.sl_hit += 1
            else:
                result.close_exit += 1
            result.total_days += 1
            trades.append(rec)

            # 清空持仓
            pos_entry_date = None
            pos_entry_price = None
            pos_tp_price = None
            pos_sl_price = None

    result.trade_records = trades
    result.equity_curve = equity
    result.gross_equity_curve = gross_equity

    if result.total_days > 0:
        result.total_return_pct = (gross_equity[-1] - 1) * 100
        result.net_total_return_pct = (equity[-1] - 1) * 100

        # 手续费统计
        result.total_fees_usd = round(total_fees_acc, 2)
        completed_trades = [t for t in trades if t.buy_triggered and t.exit_price is not None]
        if completed_trades:
            result.avg_fee_per_trade = round(total_fees_acc / len(completed_trades), 2)
            total_capital = sum(
                t.buy_price * TRADE_QUANTITY for t in completed_trades
            )
            if total_capital > 0:
                result.fee_pct_of_capital = round(total_fees_acc / total_capital * 100, 4)

            # 持仓天数统计
            hold_days_list = [t.hold_days for t in completed_trades]
            result.avg_hold_days = round(sum(hold_days_list) / len(hold_days_list), 1)
            result.max_hold_days = max(hold_days_list)

        total_trades = result.win_count + result.loss_count
        if total_trades > 0:
            result.win_rate_pct = result.win_count / total_trades * 100
        result.cumulative_return = equity[-1] - 1

        # 计算最大回撤
        peak = equity[0]
        max_dd = 0.0
        for val in equity:
            if val > peak:
                peak = val
            dd = (peak - val) / peak
            if dd > max_dd:
                max_dd = dd
        result.max_drawdown_pct = max_dd * 100

        # 计算 daily returns 序列
        daily_returns = []
        for i in range(1, len(equity)):
            daily_returns.append(equity[i] / equity[i-1] - 1)
        daily_returns = np.array(daily_returns)
        if len(daily_returns) > 1 and daily_returns.std() > 0:
            result.sharpe_ratio = (daily_returns.mean() / daily_returns.std()) * np.sqrt(252)

        # 计算 profit factor
        gross_profit = sum(
            tr.return_pct for tr in trades
            if tr.buy_triggered and tr.return_pct is not None and tr.return_pct > 0
        )
        gross_loss = abs(sum(
            tr.return_pct for tr in trades
            if tr.buy_triggered and tr.return_pct is not None and tr.return_pct < 0
        ))
        result.profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

        # 年化（分别计算毛和净）
        years_covered = result.total_days / 252
        if years_covered > 0:
            result.annualized_return_pct = ((1 + result.total_return_pct / 100) ** (1 / years_covered) - 1) * 100
            result.net_annualized_return_pct = ((1 + result.net_total_return_pct / 100) ** (1 / years_covered) - 1) * 100

    return result


# ============================================================
# 参数优化
# ============================================================

@dataclass
class OptimizationResult:
    all_results: List[BacktestResult] = field(default_factory=list)
    best_by_return: Optional[BacktestResult] = None
    best_by_sharpe: Optional[BacktestResult] = None
    best_by_win_rate: Optional[BacktestResult] = None
    best_by_profit_factor: Optional[BacktestResult] = None


def run_optimization(
    df: pd.DataFrame,
    buy_pcts: List[float],
    tp_pcts: List[float],
    sl_pcts: List[float],
    hold_across_days: bool = False,
) -> OptimizationResult:
    """网格搜索最优参数组合。"""
    results: List[BacktestResult] = []
    total_combos = len(buy_pcts) * len(tp_pcts) * len(sl_pcts)
    logger.info(f"开始参数优化网格搜索，共 {total_combos} 个组合 ...")

    start_time = time.time()
    for i, (bp, tp, sl) in enumerate(itertools.product(buy_pcts, tp_pcts, sl_pcts)):
        if sl >= tp:
            # 止损幅度 ≥ 止盈幅度，对于这种策略没有意义，跳过
            continue
        res = run_single_backtest(df, bp, tp, sl, hold_across_days=hold_across_days)
        results.append(res)

        if (i + 1) % 20 == 0 or (i + 1) == total_combos:
            elapsed = time.time() - start_time
            logger.info(f"  进度: {i+1}/{total_combos} ({elapsed:.1f}s)")

    elapsed = time.time() - start_time
    logger.info(f"优化完成，共 {len(results)} 个有效组合，耗时 {elapsed:.1f}s")

    opt = OptimizationResult(all_results=results)

    # 按不同指标找最优
    valid_results = [r for r in results if r.net_total_return_pct != 0]
    if valid_results:
        opt.best_by_return = max(valid_results, key=lambda r: r.net_total_return_pct)
        opt.best_by_sharpe = max(valid_results, key=lambda r: r.sharpe_ratio)
        opt.best_by_win_rate = max(valid_results, key=lambda r: r.win_rate_pct)
        opt.best_by_profit_factor = max(valid_results, key=lambda r: r.profit_factor if r.profit_factor != float("inf") else 0)

    return opt


# ============================================================
# 结果输出
# ============================================================

def print_result_header(title: str):
    print()
    print("=" * 72)
    print(f"  {title}")
    print("=" * 72)


def print_result(res: BacktestResult, label: str = "", show_fees: bool = True):
    """打印单组回测结果。"""
    prefix = f"  [{label}] " if label else "  "
    print(f"{prefix}买入-buy_pct={res.buy_pct*100:.0f}% | 止盈-tp_pct={res.tp_pct*100:.0f}% | 止损-sl_pct={res.sl_pct*100:.0f}%")
    print(f"  {'':>9}交易天数:    {res.total_days}")
    print(f"  {'':>9}触发买入:    {res.buy_triggered_days} ({res.buy_triggered_days/res.total_days*100:.1f}%)")
    print(f"  {'':>9}止盈次数:    {res.tp_hit} | 止损次数: {res.sl_hit} | 收盘出场: {res.close_exit}")
    print(f"  {'':>9}胜率:        {res.win_rate_pct:.1f}% ({res.win_count}胜/{res.loss_count}负)")
    if res.avg_hold_days > 0:
        print(f"  {'':>9}均持仓天数:  {res.avg_hold_days} 天 (最长 {res.max_hold_days} 天)")
    if show_fees:
        print(f"  {'':>9}毛收益率:    {res.total_return_pct:+.2f}% (未扣费)")
        print(f"  {'':>9}净收益率:    {res.net_total_return_pct:+.2f}% (含Tiger手续费)")
        print(f"  {'':>9}毛年化:      {res.annualized_return_pct:+.2f}%")
        print(f"  {'':>9}净年化:      {res.net_annualized_return_pct:+.2f}%")
    else:
        print(f"  {'':>9}总收益率:    {res.total_return_pct:+.2f}%")
        print(f"  {'':>9}年化收益率:  {res.annualized_return_pct:+.2f}%")
    print(f"  {'':>9}最大回撤:    {res.max_drawdown_pct:.2f}%")
    print(f"  {'':>9}夏普比率:    {res.sharpe_ratio:.2f}")
    print(f"  {'':>9}盈亏比(PF):  {res.profit_factor:.2f}")
    if show_fees:
        print(f"  {'':>9}手续费总额:  ${res.total_fees_usd:.2f}")
        print(f"  {'':>9}均手续费/笔: ${res.avg_fee_per_trade:.2f}")
        print(f"  {'':>9}费率占本金:  {res.fee_pct_of_capital:.3f}%")
        print(f"  {'':>9}交易次数:    {res.buy_triggered_days} 次 ({TRADE_QUANTITY}股/次)")


def print_optimization_summary(opt: OptimizationResult):
    """打印参数优化的 Top-N 结果。"""
    # 按净收益率排序 Top 15
    sorted_by_return = sorted(
        [r for r in opt.all_results if r.net_total_return_pct > 0],
        key=lambda r: r.net_total_return_pct,
        reverse=True,
    )

    show_hold = any(r.avg_hold_days > 0 for r in opt.all_results)
    hold_col = "均持仓" if show_hold else ""

    print_result_header(f"Top 15 参数组合（按净收益率排序，含Tiger手续费）")
    print(f"  {'排名':>4} {'买入%':>6} {'止盈%':>6} {'止损%':>6} {'毛收益%':>9} {'净收益%':>9} {'净年化%':>9} {'胜率%':>7} {'夏普':>5} {'回撤%':>7} {'持仓':>5} {'费$':>6}")
    print(f"  {'-'*84}")
    for rank, r in enumerate(sorted_by_return[:15], 1):
        hold_str = f"{r.avg_hold_days:>4.0f}d" if show_hold else ""
        print(f"  {rank:>4} {r.buy_pct*100:>5.0f}% {r.tp_pct*100:>5.0f}% {r.sl_pct*100:>5.0f}% "
              f"{r.total_return_pct:>+8.2f}% {r.net_total_return_pct:>+8.2f}% {r.net_annualized_return_pct:>+8.2f}% "
              f"{r.win_rate_pct:>6.1f}% {r.sharpe_ratio:>5.2f} "
              f"{r.max_drawdown_pct:>6.2f}% {hold_str:>5} ${r.total_fees_usd:>5.0f}")

    # 按夏普比率排序 Top 10
    sorted_by_sharpe = sorted(
        [r for r in opt.all_results if r.net_total_return_pct > 0],
        key=lambda r: r.sharpe_ratio,
        reverse=True,
    )
    print_result_header(f"Top 10 参数组合（按夏普比率排序，含Tiger手续费）")
    print(f"  {'排名':>4} {'买入%':>6} {'止盈%':>6} {'止损%':>6} {'毛收益%':>9} {'净收益%':>9} {'净年化%':>9} {'胜率%':>7} {'夏普':>5} {'回撤%':>7} {'持仓':>5} {'费$':>6}")
    print(f"  {'-'*84}")
    for rank, r in enumerate(sorted_by_sharpe[:10], 1):
        hold_str = f"{r.avg_hold_days:>4.0f}d" if show_hold else ""
        print(f"  {rank:>4} {r.buy_pct*100:>5.0f}% {r.tp_pct*100:>5.0f}% {r.sl_pct*100:>5.0f}% "
              f"{r.total_return_pct:>+8.2f}% {r.net_total_return_pct:>+8.2f}% {r.net_annualized_return_pct:>+8.2f}% "
              f"{r.win_rate_pct:>6.1f}% {r.sharpe_ratio:>5.2f} "
              f"{r.max_drawdown_pct:>6.2f}% {hold_str:>5} ${r.total_fees_usd:>5.0f}")

    # 按胜率排序 Top 10
    sorted_by_winrate = sorted(
        opt.all_results,
        key=lambda r: r.win_rate_pct,
        reverse=True,
    )
    print_result_header(f"Top 10 参数组合（按胜率排序，含Tiger手续费）")
    print(f"  {'排名':>4} {'买入%':>6} {'止盈%':>6} {'止损%':>6} {'毛收益%':>9} {'净收益%':>9} {'净年化%':>9} {'胜率%':>7} {'夏普':>5} {'回撤%':>7} {'持仓':>5} {'费$':>6}")
    print(f"  {'-'*84}")
    for rank, r in enumerate(sorted_by_winrate[:10], 1):
        hold_str = f"{r.avg_hold_days:>4.0f}d" if show_hold else ""
        print(f"  {rank:>4} {r.buy_pct*100:>5.0f}% {r.tp_pct*100:>5.0f}% {r.sl_pct*100:>5.0f}% "
              f"{r.total_return_pct:>+8.2f}% {r.net_total_return_pct:>+8.2f}% {r.net_annualized_return_pct:>+8.2f}% "
              f"{r.win_rate_pct:>6.1f}% {r.sharpe_ratio:>5.2f} "
              f"{r.max_drawdown_pct:>6.2f}% {hold_str:>5} ${r.total_fees_usd:>5.0f}")


def generate_html_report(
    opt: OptimizationResult,
    df: pd.DataFrame,
    output_path: Path,
    mode_label: str = "当日结算模式",
):
    """生成漂亮的 HTML 报告。"""
    # 准备 Top 结果表格
    sorted_by_return = sorted(
        [r for r in opt.all_results if r.total_return_pct > 0],
        key=lambda r: r.total_return_pct,
        reverse=True,
    )[:30]

    rows_html = ""
    for rank, r in enumerate(sorted_by_return, 1):
        color = "#22c55e" if r.total_return_pct >= 0 else "#ef4444"
        rows_html += f"""
        <tr>
            <td>{rank}</td>
            <td>{r.buy_pct*100:.0f}%</td>
            <td>{r.tp_pct*100:.0f}%</td>
            <td>{r.sl_pct*100:.0f}%</td>
            <td style="color:{color};font-weight:600">{r.total_return_pct:+.2f}%</td>
            <td>{r.annualized_return_pct:+.2f}%</td>
            <td>{r.win_rate_pct:.1f}%</td>
            <td>{r.sharpe_ratio:.2f}</td>
            <td>{r.max_drawdown_pct:.2f}%</td>
            <td>{r.profit_factor:.2f}</td>
            <td>{r.buy_triggered_days}/{r.total_days} ({r.buy_triggered_days/r.total_days*100:.0f}%)</td>
            <td>{r.tp_hit}/{r.sl_hit}/{r.close_exit}</td>
        </tr>"""

    # 最佳组合详细交易记录
    best = opt.best_by_return
    trade_rows = ""
    if best and best.trade_records:
        # 只显示最近 50 笔触发买入的交易
        recent_trades = [
            tr for tr in best.trade_records[-100:]
            if tr.buy_triggered
        ]
        for tr in recent_trades:
            date_str = tr.date.strftime("%Y-%m-%d")
            color = "#22c55e" if tr.return_pct is not None and tr.return_pct >= 0 else "#ef4444"
            reason_map = {"tp": "止盈✅", "sl": "止损❌", "close": "收盘⏹", "close_end": "强平⏹"}
            trade_rows += f"""
            <tr>
                <td>{date_str}</td>
                <td>{tr.open_price:.2f}</td>
                <td>{tr.buy_price:.2f}</td>
                <td>{f'{tr.tp_price:.2f}' if tr.tp_price is not None else ''}</td>
                <td>{f'{tr.sl_price:.2f}' if tr.sl_price is not None else ''}</td>
                <td>{tr.day_high:.2f}</td>
                <td>{tr.day_low:.2f}</td>
                <td>{f'{tr.exit_price:.2f}' if tr.exit_price is not None else ''}</td>
                <td>{reason_map.get(tr.exit_reason, tr.exit_reason)}</td>
                <td style="color:{color};font-weight:600">{f'{tr.return_pct:+.2f}' if tr.return_pct is not None else ''}%</td>
            </tr>"""

    best_return = opt.best_by_return
    best_sharpe = opt.best_by_sharpe
    best_winrate = opt.best_by_win_rate

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    period = f"{df.index[0].date()} ~ {df.index[-1].date()}"
    total_days = len(df)

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>TQQQ 条件单策略回测报告</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: -apple-system, "Microsoft YaHei", "PingFang SC", sans-serif;
    background: #f0f2f5; color: #1a1a2e; line-height: 1.6;
  }}
  .container {{ max-width: 1280px; margin: 0 auto; padding: 24px; }}
  header {{
    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
    color: white; padding: 32px 40px; border-radius: 12px; margin-bottom: 24px;
  }}
  header h1 {{ font-size: 28px; margin-bottom: 8px; }}
  header p {{ opacity: 0.8; font-size: 14px; }}
  .kpi-grid {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 16px; margin-bottom: 24px;
  }}
  .kpi-card {{
    background: white; border-radius: 10px; padding: 20px; text-align: center;
    box-shadow: 0 2px 8px rgba(0,0,0,0.06);
  }}
  .kpi-card .label {{ font-size: 13px; color: #888; margin-bottom: 6px; }}
  .kpi-card .value {{ font-size: 22px; font-weight: bold; }}
  .kpi-card .sub {{ font-size: 12px; color: #aaa; margin-top: 4px; }}
  .section {{
    background: white; border-radius: 10px; padding: 24px;
    margin-bottom: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.06);
  }}
  .section h2 {{
    font-size: 18px; margin-bottom: 16px; padding-bottom: 8px;
    border-bottom: 2px solid #eee;
  }}
  table {{
    width: 100%; border-collapse: collapse; font-size: 13px;
  }}
  th {{
    background: #f7f7f7; padding: 10px 8px; text-align: left;
    border-bottom: 2px solid #ddd; font-weight: 600; white-space: nowrap;
  }}
  td {{ padding: 8px; border-bottom: 1px solid #eee; }}
  tr:hover {{ background: #fafafa; }}
  .scroll-x {{ overflow-x: auto; }}
  .best-grid {{
    display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px;
    margin-bottom: 24px;
  }}
  .best-card {{
    border-radius: 10px; padding: 20px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.06);
  }}
  .best-card h3 {{ font-size: 15px; margin-bottom: 12px; }}
  .best-card .metric {{ display: flex; justify-content: space-between; padding: 4px 0; font-size: 13px; }}
  .best-card .metric .val {{ font-weight: 600; }}
  .card-return {{ background: linear-gradient(135deg, #f0fdf4, #dcfce7); border: 1px solid #bbf7d0; }}
  .card-sharpe {{ background: linear-gradient(135deg, #eff6ff, #dbeafe); border: 1px solid #bfdbfe; }}
  .card-winrate {{ background: linear-gradient(135deg, #fefce8, #fef9c3); border: 1px solid #fde68a; }}
  .badge {{
    display: inline-block; padding: 2px 8px; border-radius: 4px;
    font-size: 11px; font-weight: 600;
  }}
  .badge-profit {{ background: #dcfce7; color: #16a34a; }}
  .badge-loss {{ background: #fee2e2; color: #dc2626; }}
  .disclaimer {{
    background: #fff9db; border-left: 4px solid #fab005;
    padding: 16px 20px; border-radius: 0 8px 8px 0; margin-top: 20px;
    font-size: 13px; color: #666;
  }}
  footer {{
    text-align: center; color: #aaa; font-size: 12px; padding: 20px; margin-top: 16px;
  }}
  @media (max-width: 768px) {{
    .best-grid {{ grid-template-columns: 1fr; }}
    .kpi-grid {{ grid-template-columns: repeat(2, 1fr); }}
  }}
</style>
</head>
<body>
<div class="container">

<header>
  <h1>📈 TQQQ 条件单策略回测报告</h1>
  <p>策略：每日开盘下浮买入 → 止盈止损出场 | 模式：{mode_label} | 数据源：Yahoo Finance | 报告生成：{now_str}</p>
  <p>回测周期：{period}（共 {total_days} 个交易日）</p>
</header>

<!-- 最佳组合三卡片 -->
<div class="best-grid">
  <div class="best-card card-return">
    <h3>🏆 最佳总收益</h3>
    <div class="metric"><span>参数</span><span class="val">买入={best_return.buy_pct*100:.0f}% 止盈={best_return.tp_pct*100:.0f}% 止损={best_return.sl_pct*100:.0f}%</span></div>
    <div class="metric"><span>总收益率</span><span class="val" style="color:#16a34a">{best_return.total_return_pct:+.2f}%</span></div>
    <div class="metric"><span>年化收益率</span><span class="val">{best_return.annualized_return_pct:+.2f}%</span></div>
    <div class="metric"><span>胜率</span><span class="val">{best_return.win_rate_pct:.1f}%</span></div>
    <div class="metric"><span>夏普比率</span><span class="val">{best_return.sharpe_ratio:.2f}</span></div>
    <div class="metric"><span>最大回撤</span><span class="val">{best_return.max_drawdown_pct:.2f}%</span></div>
    <div class="metric"><span>盈亏比</span><span class="val">{best_return.profit_factor:.2f}</span></div>
  </div>
  <div class="best-card card-sharpe">
    <h3>📊 最高夏普比率</h3>
    <div class="metric"><span>参数</span><span class="val">买入={best_sharpe.buy_pct*100:.0f}% 止盈={best_sharpe.tp_pct*100:.0f}% 止损={best_sharpe.sl_pct*100:.0f}%</span></div>
    <div class="metric"><span>夏普比率</span><span class="val" style="color:#2563eb">{best_sharpe.sharpe_ratio:.2f}</span></div>
    <div class="metric"><span>总收益率</span><span class="val">{best_sharpe.total_return_pct:+.2f}%</span></div>
    <div class="metric"><span>年化收益率</span><span class="val">{best_sharpe.annualized_return_pct:+.2f}%</span></div>
    <div class="metric"><span>胜率</span><span class="val">{best_sharpe.win_rate_pct:.1f}%</span></div>
    <div class="metric"><span>最大回撤</span><span class="val">{best_sharpe.max_drawdown_pct:.2f}%</span></div>
    <div class="metric"><span>盈亏比</span><span class="val">{best_sharpe.profit_factor:.2f}</span></div>
  </div>
  <div class="best-card card-winrate">
    <h3>🎯 最高胜率</h3>
    <div class="metric"><span>参数</span><span class="val">买入={best_winrate.buy_pct*100:.0f}% 止盈={best_winrate.tp_pct*100:.0f}% 止损={best_winrate.sl_pct*100:.0f}%</span></div>
    <div class="metric"><span>胜率</span><span class="val" style="color:#ca8a04">{best_winrate.win_rate_pct:.1f}%</span></div>
    <div class="metric"><span>总收益率</span><span class="val">{best_winrate.total_return_pct:+.2f}%</span></div>
    <div class="metric"><span>年化收益率</span><span class="val">{best_winrate.annualized_return_pct:+.2f}%</span></div>
    <div class="metric"><span>夏普比率</span><span class="val">{best_winrate.sharpe_ratio:.2f}</span></div>
    <div class="metric"><span>最大回撤</span><span class="val">{best_winrate.max_drawdown_pct:.2f}%</span></div>
    <div class="metric"><span>盈亏比</span><span class="val">{best_winrate.profit_factor:.2f}</span></div>
  </div>
</div>

<!-- 参数排名表 -->
<div class="section">
  <h2>📋 参数组合排名（Top 30，按总收益率）</h2>
  <div class="scroll-x">
  <table>
    <thead>
      <tr>
        <th>#</th><th>买入</th><th>止盈</th><th>止损</th>
        <th>总收益</th><th>年化</th><th>胜率</th><th>夏普</th>
        <th>最大回撤</th><th>盈亏比</th><th>触发率</th><th>TP/SL/收盘</th>
      </tr>
    </thead>
    <tbody>{rows_html}</tbody>
  </table>
  </div>
</div>

<!-- 最佳组合详细交易记录 -->
<div class="section">
  <h2>📜 最佳组合（{best_return.tp_pct*100:.0f}%止盈 / {best_return.sl_pct*100:.0f}%止损）最后触发交易的记录</h2>
  <div class="scroll-x">
  <table>
    <thead>
      <tr>
        <th>日期</th><th>开盘</th><th>买入价</th><th>止盈价</th><th>止损价</th>
        <th>最高</th><th>最低</th><th>出场价</th><th>出场原因</th><th>收益</th>
      </tr>
    </thead>
    <tbody>{trade_rows}</tbody>
  </table>
  </div>
</div>

<!-- 策略说明 -->
<div class="section">
  <h2>📖 策略说明</h2>
  <p><strong>策略逻辑：</strong></p>
  <ol style="padding-left: 20px; line-height: 2;">
    <li>每个交易日开盘后，挂限价买单：<strong>买入价 = 开盘价 × (1 - buy_pct%)</strong></li>
    <li>若日内最低价 ≤ 买入价，视为成交（假设按买入价成交）</li>
    <li>成交后同时挂：
      <ul>
        <li><strong>止盈单</strong>：买入价 × (1 + tp_pct%)</li>
        <li><strong>止损单</strong>：买入价 × (1 - sl_pct%)</li>
      </ul>
    </li>
    <li>止盈/止损哪个先触达就按哪个价格出场</li>
    <li>若两者日内均未触达，收盘价出场</li>
    <li>若日内最低价未触及买入价，跳过该交易日</li>
  </ol>
  <p><strong>说明：</strong>由于仅有日线OHLC数据，当日线振幅覆盖了止盈和止损两个价位时，默认按收盘方向辅助判断（收盘>买入价→止盈优先，反之止损优先）。</p>
</div>

<div class="disclaimer">
  <strong>⚠️ 免责声明</strong><br>
  1. 本回测基于日线 OHLC 数据模拟，无法精确还原日内价格序列。<br>
  2. 实际交易中受滑点、手续费、流动性、订单执行延迟等因素影响，结果会有差异。<br>
  3. TQQQ 为 3x 杠杆 ETF，波动极大，请务必注意风险管理。<br>
  4. 过去表现不代表未来收益，本报告仅供研究参考，不构成投资建议。
</div>

<footer>
  TQQQ Condition Order Backtest | Generated by daily_stock_analysis | {now_str}
</footer>

</div>
</body>
</html>"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    logger.info(f"HTML 报告已保存: {output_path}")


# ============================================================
# 导出函数
# ============================================================


def export_trades_to_csv(trades: List[TradeRecord], filepath: str, mode_name: str = ""):
    """
    导出交易明细到 CSV 文件。

    Args:
        trades: 交易记录列表
        filepath: 输出文件路径
        mode_name: 模式名称（用于注释）
    """
    import csv

    records_for_export = [t for t in trades if t.buy_triggered]
    if not records_for_export:
        logger.warning("没有触发的交易记录可导出")
        return

    filepath = str(filepath)
    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["# TQQQ 条件单回测交易明细", mode_name])
        writer.writerow(["# 导出时间", datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
        writer.writerow([])
        writer.writerow([
            "日期", "开盘价", "买入价", "触发买入",
            "止盈价", "止损价", "出场价", "出场原因",
            "毛收益率%", "净收益率%", "手续费$", "持仓天数",
            "当日最高", "当日最低", "当日收盘",
        ])
        for tr in records_for_export:
            writer.writerow([
                tr.date.strftime("%Y-%m-%d"),
                f"{tr.open_price:.2f}",
                f"{tr.buy_price:.2f}",
                "是" if tr.buy_triggered else "否",
                f"{tr.tp_price:.2f}" if tr.tp_price else "",
                f"{tr.sl_price:.2f}" if tr.sl_price else "",
                f"{tr.exit_price:.2f}" if tr.exit_price else "",
                tr.exit_reason,
                f"{tr.return_pct:+.2f}" if tr.return_pct is not None else "",
                f"{tr.net_return_pct:+.2f}" if tr.net_return_pct is not None else "",
                f"{tr.total_fees:.2f}",
                tr.hold_days,
                f"{tr.day_high:.2f}" if tr.day_high else "",
                f"{tr.day_low:.2f}" if tr.day_low else "",
                f"{tr.day_close:.2f}" if tr.day_close else "",
            ])

    logger.info(f"交易明细已导出: {filepath}")


# ============================================================
# Main
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="TQQQ 条件单策略回测 + 参数优化")
    parser.add_argument("--quick", action="store_true", help="快速测试模式（减少参数组合）")
    parser.add_argument("--years", type=int, default=5, help="回测年限（默认: 5年）")
    parser.add_argument("--output", type=str, default=None, help="HTML 报告输出路径")
    parser.add_argument("--hold-mode", action="store_true", help="跨日持仓模式（模拟GTC订单）")
    parser.add_argument("--export-csv", type=str, default=None, help="导出交易明细CSV路径")
    args = parser.parse_args()

    mode_label_text = "跨日持仓模式" if args.hold_mode else "当日结算模式"

    # 1. 获取数据
    df = fetch_tqqq_data(years=args.years)
    total_years = len(df) / 252
    logger.info(f"数据概览: {len(df)} 个交易日 (~{total_years:.1f}年)")
    logger.info(f"  开盘价范围: ${df['open'].min():.2f} ~ ${df['open'].max():.2f}")
    logger.info(f"  收盘价范围: ${df['close'].min():.2f} ~ ${df['close'].max():.2f}")
    logger.info(f"  最新价: ${df['close'].iloc[-1]:.2f}")

    # 计算 TQQQ 原始 Buy & Hold 收益
    bh_return = (df['close'].iloc[-1] / df['close'].iloc[0] - 1) * 100
    logger.info(f"  同期 Buy & Hold 收益: {bh_return:+.2f}%")

    # 2. 运行指定参数回测 + 模式对比
    if args.hold_mode:
        # 对比模式：对相同参数运行新旧两种模式
        compare_params = [
            ("买入-3% / 止盈-6% / 止损-5%", 0.03, 0.06, 0.05),
            ("买入-3% / 止盈-4% / 止损-5%", 0.03, 0.04, 0.05),
        ]
        for label, bp, tp, sl in compare_params:
            print_result_header(f"对比: {label}")
            res_old = run_single_backtest(df, bp, tp, sl, hold_across_days=False)
            res_new = run_single_backtest(df, bp, tp, sl, hold_across_days=True)
            print_result(res_old, "当日结算")
            print()
            print_result(res_new, "跨日持仓")
            print()
            # 差异分析
            diff_return = res_new.net_total_return_pct - res_old.net_total_return_pct
            diff_sharpe = res_new.sharpe_ratio - res_old.sharpe_ratio
            diff_win = res_new.win_rate_pct - res_old.win_rate_pct
            print(f"  📊 差异分析（跨日 - 当日）:")
            print(f"     净收益率差异: {diff_return:+.2f}%")
            print(f"     夏普比率差异: {diff_sharpe:+.2f}")
            print(f"     胜率差异:     {diff_win:+.2f}%")
            print(f"     跨日持仓:     均{res_new.avg_hold_days}天, 最长{res_new.max_hold_days}天")
    else:
        print_result_header(f"参数: 买入-3% / 止盈-6% / 止损-5% ({mode_label_text})")
        user_result = run_single_backtest(df, buy_pct=0.03, tp_pct=0.06, sl_pct=0.05)
        print_result(user_result)

        print_result_header(f"参数: 买入-3% / 止盈-4% / 止损-5% ({mode_label_text})")
        user_result2 = run_single_backtest(df, buy_pct=0.03, tp_pct=0.04, sl_pct=0.05)
        print_result(user_result2)

    # 3. 运行参数优化
    if args.quick:
        buy_pcts = [0.03]
        tp_pcts = [0.02, 0.03, 0.04, 0.05, 0.06, 0.07, 0.08]
        sl_pcts = [0.02, 0.03, 0.04, 0.05, 0.06]
    else:
        buy_pcts = [0.01, 0.02, 0.03, 0.04, 0.05]
        tp_pcts = [0.02, 0.03, 0.04, 0.05, 0.06, 0.07, 0.08, 0.10]
        sl_pcts = [0.01, 0.02, 0.03, 0.04, 0.05, 0.06]

    logger.info(f"\n买入%参数: {[f'{p*100:.0f}%' for p in buy_pcts]}")
    logger.info(f"止盈%参数: {[f'{p*100:.0f}%' for p in tp_pcts]}")
    logger.info(f"止损%参数: {[f'{p*100:.0f}%' for p in sl_pcts]}")

    print_result_header(f"参数优化 - {mode_label_text}")
    opt = run_optimization(df, buy_pcts, tp_pcts, sl_pcts, hold_across_days=args.hold_mode)

    # 4. 打印优化结果
    print_optimization_summary(opt)

    if opt.best_by_return:
        print_result_header("最佳组合详情（按净收益率）")
        print_result(opt.best_by_return, "最佳")

    if opt.best_by_sharpe and opt.best_by_sharpe != opt.best_by_return:
        print_result_header("最佳组合详情（按夏普比率）")
        print_result(opt.best_by_sharpe, "最佳夏普")

    # 5. 导出 CSV
    if args.export_csv and opt.best_by_return:
        export_trades_to_csv(opt.best_by_return.trade_records, args.export_csv, mode_label_text)

    # 6. 生成 HTML 报告
    output_path = Path(args.output) if args.output else OUTPUT_DIR / "tqqq_backtest_report.html"
    logger.info("\n生成 HTML 报告 ...")
    generate_html_report(opt, df, output_path, mode_label=mode_label_text)

    print()
    print("=" * 72)
    print(f"  ✅ 回测完成！({mode_label_text})")
    print(f"  📄 HTML 报告: {output_path}")
    if args.export_csv:
        print(f"  📊 CSV 明细: {args.export_csv}")
    print("=" * 72)


if __name__ == "__main__":
    main()
