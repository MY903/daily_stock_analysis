"""
单元测试：动态权重算法
- 权重计算、归一化、幂等回填（无 LLM 依赖）
"""
import os
import sqlite3
import sys

import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.services.performance_tracker import PerformanceTracker
from src.agents.consensus_engine import RayDalioAggregator


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def temp_tracker(tmp_path):
    """每个测试独享一个临时数据库，测试结束后自动清理。"""
    db_path = str(tmp_path / "test_performance.db")
    tracker = PerformanceTracker(db_path=db_path)
    yield tracker
    # tmp_path 由 pytest 自动回收，无需手动删除


# ---------------------------------------------------------------------------
# 单元测试：权重计算逻辑
# ---------------------------------------------------------------------------

def test_new_expert_gets_baseline_weight(temp_tracker):
    """没有历史记录的专家应获得基准权重（归一化后约 0.2，即等权）。"""
    weights = temp_tracker.get_analyst_weights()
    # 5 位专家全无历史，归一化后每人应接近 0.2
    for w in weights.values():
        assert abs(w - 0.2) < 1e-4, f"新专家初始权重应约为 0.2，实际: {w}"


def test_accurate_expert_gets_higher_weight(temp_tracker):
    """胜率高的专家归一化后权重应大于胜率低的专家。"""
    # 塔勒布：5 场全对 (bearish, 跌 5%)
    for _ in range(5):
        rid = temp_tracker.record_prediction("nassim_taleb", "MOCK", "bearish", 90)
        temp_tracker.backfill_result(rid, -0.05)

    # 巴菲特：5 场全错 (bullish, 跌 5%)
    for _ in range(5):
        rid = temp_tracker.record_prediction("warren_buffett", "MOCK", "bullish", 90)
        temp_tracker.backfill_result(rid, -0.05)

    weights = temp_tracker.get_analyst_weights()
    assert weights["nassim_taleb"] > weights["warren_buffett"], (
        f"塔勒布（全对）权重 {weights['nassim_taleb']} 应大于巴菲特（全错）{weights['warren_buffett']}"
    )


def test_weights_sum_to_one(temp_tracker):
    """归一化后所有专家权重之和应为 1.0（允许浮点误差）。"""
    # 给部分专家添加战绩
    for _ in range(3):
        rid = temp_tracker.record_prediction("nassim_taleb", "MOCK", "bearish", 80)
        temp_tracker.backfill_result(rid, -0.03)

    weights = temp_tracker.get_analyst_weights()
    total = sum(weights.values())
    assert abs(total - 1.0) < 1e-3, f"权重之和应为 1.0，实际: {total}"


def test_backfill_is_idempotent(temp_tracker):
    """同一条记录多次回填，结果应保持不变（幂等性）。"""
    rid = temp_tracker.record_prediction("warren_buffett", "MOCK", "bullish", 90)

    temp_tracker.backfill_result(rid, 0.05)  # 第一次：涨 5% -> 正确
    temp_tracker.backfill_result(rid, -0.10)  # 第二次：应被忽略

    with sqlite3.connect(temp_tracker.db_path) as conn:
        row = conn.execute(
            "SELECT actual_return_5d, is_correct FROM track_record WHERE id = ?", (rid,)
        ).fetchone()
    assert row[0] == pytest.approx(0.05), "二次回填不应覆盖已结算的 actual_return"
    assert row[1] == 1, "结果应维持第一次结算的正确性"


def test_neutral_signal_correct_when_small_move(temp_tracker):
    """neutral 信号在涨跌幅 < 2% 时判定为正确。"""
    rid = temp_tracker.record_prediction("li_lu", "MOCK", "neutral", 50)
    temp_tracker.backfill_result(rid, 0.01)  # 涨 1% < 2%
    with sqlite3.connect(temp_tracker.db_path) as conn:
        row = conn.execute("SELECT is_correct FROM track_record WHERE id = ?", (rid,)).fetchone()
    assert row[0] == 1


def test_neutral_signal_wrong_when_large_move(temp_tracker):
    """neutral 信号在涨幅 > 2% 时判定为错误。"""
    rid = temp_tracker.record_prediction("li_lu", "MOCK", "neutral", 50)
    temp_tracker.backfill_result(rid, 0.05)  # 涨 5% > 2%
    with sqlite3.connect(temp_tracker.db_path) as conn:
        row = conn.execute("SELECT is_correct FROM track_record WHERE id = ?", (rid,)).fetchone()
    assert row[0] == 0


def test_lookback_days_filters_old_records(temp_tracker):
    """lookback_days 参数应正确过滤过期战绩。"""
    # 直接插入一条旧日期记录（模拟 60 天前）
    with sqlite3.connect(temp_tracker.db_path) as conn:
        conn.execute("""
            INSERT INTO track_record (analyst_id, ticker, prediction_date, signal, confidence,
                                      actual_return_5d, is_correct, created_at)
            VALUES ('warren_buffett', 'MOCK', '2020-01-01', 'bullish', 90, 0.05, 1,
                    datetime('now', '-60 days'))
        """)
        conn.commit()

    # lookback_days=7 时不应看到 60 天前的记录
    weights_7d = temp_tracker.get_analyst_weights(lookback_days=7)
    # 巴菲特在 7 天内无战绩，应取基准值（等权，约 0.2）
    assert abs(weights_7d["warren_buffett"] - 0.2) < 1e-4, (
        f"lookback_days=7 时巴菲特应为基准权重，实际: {weights_7d['warren_buffett']}"
    )

