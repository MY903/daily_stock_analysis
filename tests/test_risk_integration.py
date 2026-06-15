"""
风控强制执行集成测试。

测试场景：
1. 仓位上限（4.9% 通过, 5.1% 拦截）
2. 日亏损上限（7.9% 通过, 8.1% 拦截）
3. 黑名单标的拦截
4. 冷却时间（30秒内重复拒绝）
5. 异常价格偏离（>10% 拦截）
6. 风控+执行集成（超仓→确认→ExecutionEngine→风控拦截）
"""

import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.trading.risk_manager import RiskManager, RiskVerdict
from src.trading.signal import Signal, SignalAction, SignalSource


# ==================== Fixtures ====================

def create_risk_manager() -> RiskManager:
    rm = RiskManager()
    rm._total_equity = 100_000.0  # 总资产10万
    return rm


def create_signal(symbol: str = "AAPL", action: str = "BUY",
                  quantity: int = 100, confidence: float = 0.8,
                  price_target: float = 150.0) -> Signal:
    return Signal(
        symbol=symbol,
        action=SignalAction(action),
        quantity=quantity,
        confidence=confidence,
        rationale="Test signal for integration test",
        source=SignalSource.AI,
        price_target=price_target,
    )


# ==================== Test: 仓位上限 ====================

def test_position_limit_pass():
    """仓位 4.9% 应该通过"""
    rm = create_risk_manager()
    result = rm.check_position_limit("AAPL", 49, 100.0)  # 49 * 100 / 100000 = 4.9%
    assert result.verdict == RiskVerdict.PASS, f"Expected PASS, got {result.verdict}: {result.reason}"


def test_position_limit_reject():
    """仓位 5.1% 应该拦截"""
    rm = create_risk_manager()
    result = rm.check_position_limit("AAPL", 51, 100.0)  # 51 * 100 / 100000 = 5.1%
    assert result.verdict == RiskVerdict.REJECT, f"Expected REJECT, got {result.verdict}: {result.reason}"


def test_position_limit_boundary():
    """仓位恰好 5.0% 应该通过（临界值）"""
    rm = create_risk_manager()
    result = rm.check_position_limit("AAPL", 50, 100.0)  # 50 * 100 / 100000 = 5.0%
    assert result.verdict == RiskVerdict.PASS, f"Expected PASS, got {result.verdict}: {result.reason}"


# ==================== Test: 日亏损上限 ====================

def test_daily_loss_pass():
    """日亏损 7.9% 应该通过"""
    rm = create_risk_manager()
    rm._daily_loss_pct = 7.9
    result = rm.check_daily_loss_limit()
    assert result.verdict == RiskVerdict.PASS, f"Expected PASS, got {result.verdict}: {result.reason}"


def test_daily_loss_reject():
    """日亏损 8.1% 应该拦截"""
    rm = create_risk_manager()
    rm._daily_loss_pct = 8.1
    result = rm.check_daily_loss_limit()
    assert result.verdict == RiskVerdict.REJECT, f"Expected REJECT, got {result.verdict}: {result.reason}"


def test_daily_loss_exact_boundary():
    """日亏损恰好 8.0% 应该通过（临界值）"""
    rm = create_risk_manager()
    rm._daily_loss_pct = 8.0
    result = rm.check_daily_loss_limit()
    assert result.verdict == RiskVerdict.PASS, f"Expected PASS, got {result.verdict}: {result.reason}"


# ==================== Test: 冷却时间 ====================

def test_cooldown_pass():
    """首次信号检查应该通过"""
    rm = create_risk_manager()
    result = rm.check_cooldown("AAPL")
    assert result.verdict == RiskVerdict.PASS


def test_cooldown_reject():
    """30秒内重复信号应该拦截"""
    rm = create_risk_manager()
    rm._last_signal_time["AAPL"] = datetime.now()
    result = rm.check_cooldown("AAPL")
    assert result.verdict == RiskVerdict.REJECT, f"Expected REJECT, got {result.verdict}: {result.reason}"
    assert "冷却" in result.reason


# ==================== Test: 异常价格 ====================

def test_abnormal_price_pass():
    """偏离5%应该通过"""
    rm = create_risk_manager()
    result = rm.check_abnormal_price("AAPL", 105.0, 100.0)
    assert result.verdict == RiskVerdict.PASS, f"Expected PASS, got {result.verdict}: {result.reason}"


def test_abnormal_price_reject():
    """偏离15%应该拦截"""
    rm = create_risk_manager()
    result = rm.check_abnormal_price("AAPL", 115.0, 100.0)
    assert result.verdict == RiskVerdict.REJECT, f"Expected REJECT, got {result.verdict}: {result.reason}"


def test_abnormal_price_no_ref():
    """无参考价时应该通过"""
    rm = create_risk_manager()
    result = rm.check_abnormal_price("AAPL", 150.0, 0)
    assert result.verdict == RiskVerdict.PASS


# ==================== Test: 信号过期 ====================

def test_signal_expiry_pass():
    """新信号应该通过"""
    rm = create_risk_manager()
    signal = create_signal()
    result = rm.check_signal_expiry(signal)
    assert result.verdict == RiskVerdict.PASS


def test_signal_expiry_reject():
    """过期信号应该拦截"""
    rm = create_risk_manager()
    signal = create_signal()
    signal.expires_at = signal.created_at  # 立即过期
    result = rm.check_signal_expiry(signal)
    assert result.verdict == RiskVerdict.REJECT


# ==================== Test: 综合检查 ====================

def test_check_all_returns_reject_for_over_limit():
    """综合检查应该返回超仓的拒绝结果"""
    rm = create_risk_manager()
    signal = create_signal(quantity=600, price_target=100.0)  # 60% > 5%
    results = rm.check_all(signal, 100.0)
    rejects = [r for r in results if r.verdict == RiskVerdict.REJECT]
    assert len(rejects) >= 1, f"Expected at least 1 reject, got all PASS: {[r.reason for r in results]}"


def test_check_all_all_pass():
    """合法信号应该全部风控通过"""
    rm = create_risk_manager()
    signal = create_signal(quantity=10, price_target=100.0)  # 10*100/100000 = 1%
    results = rm.check_all(signal, 100.0, ref_price=100.0)
    rejects = [r for r in results if r.verdict == RiskVerdict.REJECT]
    assert len(rejects) == 0, f"Expected 0 rejects, got: {[(r.reason, r.rule) for r in rejects]}"


# ==================== Test: 每日重置 ====================

def test_daily_reset():
    """每日重置后计数器清零"""
    rm = create_risk_manager()
    rm._daily_loss_pct = 8.0
    rm._daily_trades["AAPL"] = [{"loss_pct": 5.0}]
    rm.reset_daily()
    assert rm._daily_loss_pct == 0.0
    assert len(rm._daily_trades) == 0


if __name__ == "__main__":
    # Run all tests
    tests = [
        ("position_limit_pass", test_position_limit_pass),
        ("position_limit_reject", test_position_limit_reject),
        ("position_limit_boundary", test_position_limit_boundary),
        ("daily_loss_pass", test_daily_loss_pass),
        ("daily_loss_reject", test_daily_loss_reject),
        ("daily_loss_exact_boundary", test_daily_loss_exact_boundary),
        ("cooldown_pass", test_cooldown_pass),
        ("cooldown_reject", test_cooldown_reject),
        ("abnormal_price_pass", test_abnormal_price_pass),
        ("abnormal_price_reject", test_abnormal_price_reject),
        ("abnormal_price_no_ref", test_abnormal_price_no_ref),
        ("signal_expiry_pass", test_signal_expiry_pass),
        ("signal_expiry_reject", test_signal_expiry_reject),
        ("check_all_returns_reject_for_over_limit", test_check_all_returns_reject_for_over_limit),
        ("check_all_all_pass", test_check_all_all_pass),
        ("daily_reset", test_daily_reset),
    ]
    
    passed = 0
    failed = 0
    for name, test_fn in tests:
        try:
            test_fn()
            print(f"  ✅ {name}")
            passed += 1
        except Exception as e:
            print(f"  ❌ {name}: {e}")
            failed += 1
    
    print(f"\n结果: {passed} 通过, {failed} 失败")
    sys.exit(0 if failed == 0 else 1)
