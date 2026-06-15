"""
风控安全升级测试：4项新规则 + SQLite 持久化。

测试范围：
1. check_order_value_limit — 单笔订单价值上限（≤ $10,000）
2. check_order_frequency — 同标的下单频率（≤ 3次/分钟）
3. check_daily_order_count — 每日总订单数（≤ 20）
4. check_circuit_breaker — 日亏损熔断（≥ RISK_MAX_DAILY_LOSS_PCT 时拦截所有交易）
5. DailyLossStore — SQLite 持久化读写
6. 综合集成 — check_all() 包含新规则
"""

import sys
import os
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from src.trading.risk_manager import RiskManager, RiskVerdict
from src.trading.signal import Signal, SignalAction, SignalSource
from src.trading.loss_persistence import DailyLossStore
from config.settings import settings


# ==================== Fixtures ====================

@pytest.fixture
def rm():
    """创建一个干净的 RiskManager 实例"""
    manager = RiskManager()
    manager._total_equity = 100_000.0
    return manager


def make_signal(symbol: str = "AAPL", action: str = "BUY",
                quantity: int = 100, confidence: float = 0.8,
                price_target: float = 150.0) -> Signal:
    return Signal(
        symbol=symbol,
        action=SignalAction(action),
        quantity=quantity,
        confidence=confidence,
        rationale="Test signal for safety upgrade test",
        source=SignalSource.AI,
        price_target=price_target,
    )


@pytest.fixture(autouse=True)
def reset_settings_defaults():
    """确保测试使用默认值，不受 .env 影响"""
    prev_value = settings.RISK_MAX_ORDER_VALUE
    prev_freq = settings.RISK_MAX_ORDERS_PER_MIN
    prev_daily = settings.RISK_MAX_DAILY_ORDERS
    prev_loss = settings.RISK_MAX_DAILY_LOSS_PCT
    # 显式设置测试默认值
    settings.RISK_MAX_ORDER_VALUE = 10000.0
    settings.RISK_MAX_ORDERS_PER_MIN = 3
    settings.RISK_MAX_DAILY_ORDERS = 20
    settings.RISK_MAX_DAILY_LOSS_PCT = 5.0
    yield
    # 恢复
    settings.RISK_MAX_ORDER_VALUE = prev_value
    settings.RISK_MAX_ORDERS_PER_MIN = prev_freq
    settings.RISK_MAX_DAILY_ORDERS = prev_daily
    settings.RISK_MAX_DAILY_LOSS_PCT = prev_loss


# ==================== 1. check_order_value_limit ====================

class TestOrderValueLimit:

    def test_value_limit_pass(self, rm):
        """单笔 9,500 元（< 10,000）应该通过"""
        result = rm.check_order_value_limit("AAPL", 95, 100.0)  # 95 * 100 = 9500
        assert result.verdict == RiskVerdict.PASS, f"Expected PASS, got {result.verdict}: {result.reason}"

    def test_value_limit_reject(self, rm):
        """单笔 10,500 元（> 10,000）应该拦截"""
        result = rm.check_order_value_limit("AAPL", 105, 100.0)  # 105 * 100 = 10500
        assert result.verdict == RiskVerdict.REJECT, f"Expected REJECT, got {result.verdict}: {result.reason}"
        assert "order_value" in result.rule

    def test_value_limit_boundary(self, rm):
        """单笔恰好 10,000 元（≤）应该通过"""
        result = rm.check_order_value_limit("AAPL", 100, 100.0)  # 100 * 100 = 10000
        assert result.verdict == RiskVerdict.PASS, f"Expected PASS, got {result.verdict}: {result.reason}"


# ==================== 2. check_order_frequency ====================

class TestOrderFrequency:

    def test_frequency_pass(self, rm):
        """1 次/分钟（≤ 3）应该通过"""
        rm._order_timestamps["AAPL"] = [datetime.now() - timedelta(seconds=10)]
        result = rm.check_order_frequency("AAPL")
        assert result.verdict == RiskVerdict.PASS, f"Expected PASS, got {result.verdict}: {result.reason}"

    def test_frequency_reject(self, rm):
        """4 次/分钟（> 3）应该拦截"""
        now = datetime.now()
        rm._order_timestamps["AAPL"] = [
            now - timedelta(seconds=50),
            now - timedelta(seconds=40),
            now - timedelta(seconds=30),
            now - timedelta(seconds=10),
        ]
        result = rm.check_order_frequency("AAPL")
        assert result.verdict == RiskVerdict.REJECT, f"Expected REJECT, got {result.verdict}: {result.reason}"
        assert "order_frequency" in result.rule

    def test_frequency_old_timestamps_ignored(self, rm):
        """超过 60 秒的旧时间戳应该被忽略"""
        now = datetime.now()
        rm._order_timestamps["AAPL"] = [
            now - timedelta(seconds=120),  # 超过 1 分钟
            now - timedelta(seconds=90),   # 超过 1 分钟
            now - timedelta(seconds=30),   # 有效的
        ]
        result = rm.check_order_frequency("AAPL")
        assert result.verdict == RiskVerdict.PASS, f"Expected PASS, got {result.verdict}: {result.reason}"

    def test_frequency_no_history(self, rm):
        """首次下单应该通过"""
        result = rm.check_order_frequency("AAPL")
        assert result.verdict == RiskVerdict.PASS


# ==================== 3. check_daily_order_count ====================

class TestDailyOrderCount:

    def test_daily_count_pass(self, rm):
        """19 笔（< 20）应该通过"""
        rm._daily_order_count = 19
        result = rm.check_daily_order_count()
        assert result.verdict == RiskVerdict.PASS, f"Expected PASS, got {result.verdict}: {result.reason}"

    def test_daily_count_reject(self, rm):
        """21 笔（> 20）应该拦截"""
        rm._daily_order_count = 21
        result = rm.check_daily_order_count()
        assert result.verdict == RiskVerdict.REJECT, f"Expected REJECT, got {result.verdict}: {result.reason}"
        assert "daily_order_count" in result.rule

    def test_daily_count_boundary(self, rm):
        """恰好 20 笔（≤）应该通过"""
        rm._daily_order_count = 20
        result = rm.check_daily_order_count()
        assert result.verdict == RiskVerdict.PASS, f"Expected PASS, got {result.verdict}: {result.reason}"


# ==================== 4. check_circuit_breaker ====================

class TestCircuitBreaker:

    def test_circuit_breaker_pass(self, rm):
        """日亏损 4.9%（< 5%）应该通过"""
        rm._daily_loss_pct = 4.9
        result = rm.check_circuit_breaker()
        assert result.verdict == RiskVerdict.PASS, f"Expected PASS, got {result.verdict}: {result.reason}"

    def test_circuit_breaker_reject(self, rm):
        """日亏损 5.1%（≥ 5%）应该熔断拦截"""
        rm._daily_loss_pct = 5.1
        result = rm.check_circuit_breaker()
        assert result.verdict == RiskVerdict.REJECT, f"Expected REJECT, got {result.verdict}: {result.reason}"
        assert "circuit_breaker" in result.rule

    def test_circuit_breaker_exact_boundary(self, rm):
        """日亏损恰好 5.0%（≥）应该熔断拦截"""
        rm._daily_loss_pct = 5.0
        result = rm.check_circuit_breaker()
        assert result.verdict == RiskVerdict.REJECT, f"Expected REJECT at boundary, got {result.verdict}"


# ==================== 5. DailyLossStore ====================

class TestDailyLossStore:

    @pytest.fixture(autouse=True)
    def temp_db(self, tmp_path):
        """使用临时目录的 SQLite 数据库，避免污染真实数据"""
        db_path = tmp_path / "test_daily_loss.db"
        store = DailyLossStore(str(db_path))
        yield store
        # 清理
        if os.path.exists(str(db_path)):
            os.remove(str(db_path))

    def test_load_empty(self, temp_db):
        """空数据库应该返回 0.0"""
        loss = temp_db.load_today_loss()
        assert loss == 0.0, f"Expected 0.0, got {loss}"

    def test_append_and_load(self, temp_db):
        """添加一笔亏损后应该能够正确加载"""
        temp_db.append_loss("AAPL", 2.5, datetime.now())
        loss = temp_db.load_today_loss()
        assert loss == 2.5, f"Expected 2.5, got {loss}"

    def test_append_multiple_and_sum(self, temp_db):
        """多笔亏损应该汇总"""
        temp_db.append_loss("AAPL", 1.0, datetime.now())
        temp_db.append_loss("GOOG", 2.0, datetime.now())
        temp_db.append_loss("MSFT", 1.5, datetime.now())
        loss = temp_db.load_today_loss()
        assert loss == 4.5, f"Expected 4.5, got {loss}"

    def test_reset_daily(self, temp_db):
        """重置后今日亏损应该归零"""
        temp_db.append_loss("AAPL", 5.0, datetime.now())
        temp_db.reset_daily()
        loss = temp_db.load_today_loss()
        assert loss == 0.0, f"Expected 0.0 after reset, got {loss}"

    def test_yesterday_loss_not_counted(self, temp_db):
        """昨天的记录不应该计入今日亏损"""
        yesterday = datetime.now() - timedelta(days=1)
        temp_db.append_loss("AAPL", 10.0, yesterday)
        loss = temp_db.load_today_loss()
        assert loss == 0.0, f"Expected 0.0 (yesterday's loss), got {loss}"


# ==================== 6. 集成测试 ====================

class TestIntegration:

    def test_check_all_includes_new_rules(self, rm):
        """check_all() 应该包含全部新规则（通过结果数量 + 触发拒绝来验证）"""
        signal = make_signal(quantity=1, price_target=50.0)
        results = rm.check_all(signal, 50.0, ref_price=50.0)
        # 旧版 check_all 返回 7 个结果；新增 3 个规则后应为 10 个
        #   (signal_expiry, cooldown, position_limit, order_value_limit,
        #    daily_loss_limit, max_positions, order_frequency,
        #    daily_order_count, circuit_breaker, abnormal_price)
        assert len(results) == 10, f"Expected 10 checks, got {len(results)}"

        # 使用触发拒绝来验证各规则名称出现在结果中
        # 1) order_value_limit: 大额订单应触发
        big_signal = make_signal(quantity=200, price_target=100.0)
        rm._total_equity = 1_000_000.0  # 提高 equity 避免 position_limit 先拒绝
        results2 = rm.check_all(big_signal, 100.0)
        reject_rules = {r.rule for r in results2 if r.verdict == RiskVerdict.REJECT}
        assert "order_value_limit" in reject_rules, f"order_value_limit not triggered: {reject_rules}"

        # 2) order_frequency: 高频率触发
        rm2 = RiskManager()
        rm2._order_timestamps["AAPL"] = [datetime.now()] * 4
        results3 = rm2.check_all(make_signal(quantity=1, price_target=50.0), 50.0)
        reject_rules3 = {r.rule for r in results3 if r.verdict == RiskVerdict.REJECT}
        assert "order_frequency" in reject_rules3, f"order_frequency not triggered: {reject_rules3}"

        # 3) daily_order_count: 超量触发
        rm3 = RiskManager()
        rm3._daily_order_count = 21
        results4 = rm3.check_all(make_signal(quantity=1, price_target=50.0), 50.0)
        reject_rules4 = {r.rule for r in results4 if r.verdict == RiskVerdict.REJECT}
        assert "daily_order_count" in reject_rules4, f"daily_order_count not triggered: {reject_rules4}"

        # 4) circuit_breaker: 亏损触发
        rm4 = RiskManager()
        rm4._daily_loss_pct = 5.0
        results5 = rm4.check_all(make_signal(quantity=1, price_target=50.0), 50.0)
        reject_rules5 = {r.rule for r in results5 if r.verdict == RiskVerdict.REJECT}
        assert "circuit_breaker" in reject_rules5, f"circuit_breaker not triggered: {reject_rules5}"

    def test_risk_manager_restores_loss_from_store(self, tmp_path):
        """RiskManager 初始化时应该从 DailyLossStore 恢复亏损"""
        db_path = tmp_path / "restore_test.db"
        # 预先写入亏损
        store = DailyLossStore(str(db_path))
        store.append_loss("AAPL", 3.0, datetime.now())
        store.append_loss("GOOG", 1.5, datetime.now())
        store = None  # 关闭连接

        # 创建 RiskManager，使用同一个数据库文件
        manager = RiskManager(loss_db_path=str(db_path))
        assert manager._daily_loss_pct == 4.5, f"Expected 4.5 restored, got {manager._daily_loss_pct}"

    def test_update_daily_loss_persists(self, rm, tmp_path):
        """update_daily_loss() 应该同时写入 SQLite"""
        db_path = tmp_path / "persist_test.db"
        rm._loss_store = DailyLossStore(str(db_path))
        rm.update_daily_loss("AAPL", 2.5)
        loaded = rm._loss_store.load_today_loss()
        assert loaded == 2.5, f"Expected 2.5 persisted, got {loaded}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
