# -*- coding: utf-8 -*-
"""
TQQQ 条件单策略 - 交易股数优化
===============================

测试不同交易股数对手续费占比和净收益的影响。

核心发现：
- 35股时，每笔最低收费占主导（$0.99 + $1.00 + $0.99/边）
- 加大股数可摊薄单笔费率占比
- 但过大股数也会增加单次亏损金额

Usage:
    python scripts/tqqq_quantity_optimize.py
"""

import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import numpy as np

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# 复用主脚本的数据获取和手续费计算
from scripts.tqqq_condition_order_backtest import (  # noqa: E402
    fetch_tqqq_data,
    run_single_backtest,
    BacktestResult,
    TRADE_QUANTITY,
    calc_trade_fees,
    calc_round_trip_fees,
    OUTPUT_DIR,
)


@dataclass
class QuantityResult:
    quantity: int
    result: BacktestResult
    fee_per_roundtrip: float
    fee_pct_of_trade: float  # 手续费占交易额百分比
    capital_per_trade: float  # 每笔投入资金


def run_quantity_analysis(
    df=None,
    years=5,
    quantities: Optional[List[int]] = None,
    param_combos: Optional[List[tuple]] = None,
):
    """分析不同交易量对不同参数组合的影响。"""
    if df is None:
        df = fetch_tqqq_data(years=years)

    if quantities is None:
        quantities = [35, 50, 100, 150, 200, 300, 500]

    if param_combos is None:
        # 用 Top 5 最优参数 + 用户提到的 2 个参数
        param_combos = [
            (0.05, 0.05, 0.04),   # Top 1: 买5%/止盈5%/止损4%
            (0.04, 0.04, 0.03),   # Top 2: 买4%/止盈4%/止损3%
            (0.05, 0.05, 0.03),   # Top 3: 买5%/止盈5%/止损3%
            (0.03, 0.03, 0.02),   # User's tight
            (0.03, 0.04, 0.05),   # User's alt (4% TP)
            (0.03, 0.06, 0.05),   # User's original
        ]

    all_results = []

    for bp, tp, sl in param_combos:
        label = f"买{bp*100:.0f}%/止盈{tp*100:.0f}%/止损{sl*100:.0f}%"
        print()
        print(f"{'='*72}")
        print(f"  参数: {label}")
        print(f"{'='*72}")

        for qty in quantities:
            # 临时修改全局 TRADE_QUANTITY
            import scripts.tqqq_condition_order_backtest as bt_mod
            bt_mod.TRADE_QUANTITY = qty

            res = run_single_backtest(df, bp, tp, sl)

            # 计算费用明细
            sample_price = df["open"].median()
            buy_price = sample_price * (1 - bp)
            sell_price = buy_price * (1 + tp)
            round_trip_fee = calc_round_trip_fees(buy_price, sell_price, qty)
            capital = buy_price * qty
            fee_pct = round_trip_fee / (capital + buy_price * qty * 0) * 100

            all_results.append({
                "quantity": qty,
                "buy_pct": bp,
                "tp_pct": tp,
                "sl_pct": sl,
                "param_label": label,
                "gross_return": res.total_return_pct,
                "net_return": res.net_total_return_pct,
                "gross_annualized": res.annualized_return_pct,
                "net_annualized": res.net_annualized_return_pct,
                "win_rate": res.win_rate_pct,
                "sharpe": res.sharpe_ratio,
                "max_dd": res.max_drawdown_pct,
                "trigger_count": res.buy_triggered_days,
                "total_fees": res.total_fees_usd,
                "round_trip_fee": round_trip_fee,
                "fee_pct": fee_pct,
                "capital_per_trade": capital,
            })

            print(f"  Qty={qty:>4}股 | 本金${capital:<7.0f} | 每笔费${round_trip_fee:<5.2f} | "
                  f"毛收益:{res.total_return_pct:>+9.2f}% → 净收益:{res.net_total_return_pct:>+9.2f}% | "
                  f"净年化:{res.net_annualized_return_pct:>+6.2f}% | 夏普:{res.sharpe_ratio:.2f}")

        # 复原
        bt_mod.TRADE_QUANTITY = 35

    return all_results


def print_summary(all_results):
    """打印汇总对比。"""
    print()
    print()
    print("=" * 72)
    print("  不同交易量下最佳净收益对比")
    print("=" * 72)

    # 按参数组合分组
    param_groups = {}
    for r in all_results:
        key = r["param_label"]
        if key not in param_groups:
            param_groups[key] = []
        param_groups[key].append(r)

    print(f"\n{'参数组合':<28} {'量':>5} {'本金':>8} {'每笔费':>7} {'毛收益%':>10} {'净收益%':>10} {'净年化%':>8} {'夏普':>6}")
    print(f"  {'-'*80}")

    for label, results in param_groups.items():
        for r in results:
            color = "🟢" if r["net_return"] > 0 else "🔴"
            print(f"{color} {label:<26} {r['quantity']:>5} ${r['capital_per_trade']:<6.0f} ${r['round_trip_fee']:<5.2f} "
                  f"{r['gross_return']:>+9.2f}% {r['net_return']:>+9.2f}% "
                  f"{r['net_annualized']:>+7.2f}% {r['sharpe']:>5.2f}")

    # 找出每个组合的最佳交易量
    print()
    print("=" * 72)
    print("  每个参数组合的最佳交易量")
    print("=" * 72)
    for label, results in param_groups.items():
        valid = [r for r in results if r["net_return"] > 0]
        if valid:
            best = max(valid, key=lambda r: r["net_return"])
            print(f"  🏆 {label}: {best['quantity']}股 → 净收益{best['net_return']:+.2f}% 净年化{best['net_annualized']:+.2f}% 夏普{best['sharpe']:.2f}")
        else:
            print(f"  ❌ {label}: 所有量级均为负收益")

    # 最佳跨参数跨量级组合
    all_valid = [r for r in all_results if r["net_return"] > 0]
    if all_valid:
        overall_best = max(all_valid, key=lambda r: r["net_return"])
        print()
        print(f"\n  🌟 跨量级全局最优:")
        print(f"     参数: {overall_best['param_label']}")
        print(f"     交易量: {overall_best['quantity']}股")
        print(f"     本金/笔: ${overall_best['capital_per_trade']:.0f}")
        print(f"     每笔手续费: ${overall_best['round_trip_fee']:.2f}")
        print(f"     毛收益: {overall_best['gross_return']:+.2f}%")
        print(f"     净收益: {overall_best['net_return']:+.2f}%")
        print(f"     净年化: {overall_best['net_annualized']:+.2f}%")
        print(f"     夏普: {overall_best['sharpe']:.2f}")
        print(f"     总手续费: ${overall_best['total_fees']:.0f}")
        print(f"     触发次数: {overall_best['trigger_count']}")


def main():
    df = fetch_tqqq_data(years=5)

    # 更宽泛的量级范围
    quantities = [35, 50, 75, 100, 150, 200, 300, 500]

    # 更多参数组合
    param_combos = [
        (0.05, 0.05, 0.04),   # Top 1
        (0.04, 0.04, 0.03),   # Top 2
        (0.05, 0.05, 0.03),   # Top 3
        (0.04, 0.04, 0.02),   # Top 4
        (0.03, 0.03, 0.02),   # 用户窄带
        (0.03, 0.04, 0.05),   # 用户备选
        (0.05, 0.04, 0.03),   # Top 8
        (0.03, 0.04, 0.02),
        (0.05, 0.04, 0.02),
    ]

    results = run_quantity_analysis(
        df=df,
        years=5,
        quantities=quantities,
        param_combos=param_combos,
    )

    print_summary(results)


if __name__ == "__main__":
    main()
