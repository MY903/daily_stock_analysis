# -*- coding: utf-8 -*-
"""
Mock-based integration tests for QuantWeaselPipeline.

Tests the full SIGNAL → RISK_CHECK → LARK_CARD → CONFIRM → EXECUTE flow
with mocked TigerClient and LarkInteractiveBot, but real AuditLogger and RiskManager.

Test scenarios:
1. Pipeline creation with all components wired
2. generate_and_push_signal() creates Signal, logs to audit
3. process_confirmed_signal() calls ExecutionEngine.execute() (sandbox → dry-run)
4. Signal is rejected by risk check (order value too high)
5. Dedup guard prevents double execution
6. Sandbox mode returns dry-run-order
"""

import os
import sys
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock, AsyncMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.trading.pipeline import QuantWeaselPipeline
from src.trading.signal import Signal, SignalStatus, SignalAction, SignalSource
from src.trading.audit_logger import AuditLogger
from src.trading.risk_manager import RiskManager
from src.trading.execution import ExecutionEngine
from src.trading.card_handler import SignalConfirmHandler
from src.trading.signal_expiry import DedupGuard
from src.trading.config import load_config
from config.settings import settings


# ==================== Fixtures ====================


@pytest.fixture
def mock_tiger():
    """Mock TigerClient to avoid any real API calls."""
    with patch("src.trading.pipeline.TigerClient") as mock_cls:
        instance = mock_cls.return_value
        instance.is_connected = False
        instance.connect.return_value = None
        instance.get_account_summary.return_value = {
            "net_value": 1_000_000.0,
            "cash": 500_000.0,
            "buying_power": 800_000.0,
        }
        instance.place_limit_buy.return_value = 12345
        instance.place_limit_sell.return_value = 12346
        yield instance


@pytest.fixture
def mock_lark():
    """Mock LarkInteractiveBot to avoid real Lark pushes."""
    with patch("src.trading.pipeline.LarkInteractiveBot") as mock_cls:
        instance = mock_cls.return_value
        instance.push_card = AsyncMock(return_value=True)
        instance.on_confirm = MagicMock()
        instance.on_reject = MagicMock()
        yield instance


@pytest.fixture
def audit_db_path(tmp_path):
    """Return a temp file path for the audit log database."""
    return str(tmp_path / "test_audit_log.db")


@pytest.fixture
def loss_db_path(tmp_path):
    """Return a temp file path for the daily loss database."""
    return str(tmp_path / "test_daily_loss.db")


@pytest.fixture
def pipeline(mock_tiger, mock_lark, audit_db_path, loss_db_path):
    """Build QuantWeaselPipeline with real internals but mocked external services.

    - TigerClient: mocked (prevents real API connections)
    - LarkInteractiveBot: mocked (prevents real Lark pushes)
    - AuditLogger: real (SQLite in temp file)
    - RiskManager: real (SQLite in temp file, equity set for determinism)
    - DedupGuard: real
    - ExecutionEngine: real (uses mocked TigerClient, real RiskManager)
    """
    audit_logger = AuditLogger(db_path=audit_db_path)
    risk_manager = RiskManager(loss_db_path=loss_db_path)
    risk_manager._total_equity = 1_000_000.0  # deterministic total equity

    # Build pipeline via __new__ to bypass __init__ (which creates real TigerClient etc.)
    pl = QuantWeaselPipeline.__new__(QuantWeaselPipeline)
    pl._config = load_config()
    pl._bot = mock_lark
    pl._audit_logger = audit_logger
    pl._risk_manager = risk_manager
    pl._tiger_client = mock_tiger
    pl._signal_generator = MagicMock()  # not exercised by tested methods

    # Real card handler with mocked bot
    pl._card_handler = SignalConfirmHandler(mock_lark, audit_logger)
    pl._card_handler.on_execution(
        lambda signal: pl.process_confirmed_signal(signal.signal_id)
    )

    # Real execution engine with mocked tiger, real risk/audit
    pl._execution_engine = ExecutionEngine(
        mock_tiger, risk_manager, audit_logger, lark_bot=mock_lark,
    )

    # Scheduler / expiry — minimal mock, not exercised by tested methods
    pl._pre_market = MagicMock()
    pl._intraday = MagicMock()
    pl._scheduler = MagicMock()
    pl._expiry_manager = MagicMock()

    pl._dedup_guard = DedupGuard()
    pl._running = False

    return pl


# ==================== Helper ====================


async def _create_signal(pipeline, symbol="TQQQ", action="BUY",
                         quantity=35, confidence=0.85, rationale="test",
                         price_target=None) -> Signal:
    """Create a Signal and log it into the pipeline's audit logger + push card.

    This mirrors `generate_and_push_signal` but allows setting price_target
    (which the pipeline method doesn't expose).
    """
    signal = Signal(
        symbol=symbol,
        action=SignalAction(action.upper()),
        quantity=quantity,
        price_target=price_target,
        confidence=confidence,
        rationale=rationale,
        source=SignalSource.AI,
    )
    pipeline._audit_logger.log_created(signal)
    await pipeline._card_handler.push_signal_card(signal)
    return signal


# ==================== Tests ====================


class TestPipelineConstruction:
    """Verify the pipeline fixture wires all components correctly."""

    def test_pipeline_has_all_components(self, pipeline):
        """All key components should be present and properly typed."""
        assert pipeline._config is not None
        assert pipeline._audit_logger is not None
        assert isinstance(pipeline._audit_logger, AuditLogger)
        assert pipeline._risk_manager is not None
        assert isinstance(pipeline._risk_manager, RiskManager)
        assert pipeline._card_handler is not None
        assert isinstance(pipeline._card_handler, SignalConfirmHandler)
        assert pipeline._execution_engine is not None
        assert isinstance(pipeline._execution_engine, ExecutionEngine)
        assert pipeline._dedup_guard is not None
        assert isinstance(pipeline._dedup_guard, DedupGuard)

    def test_pipeline_is_not_running_initially(self, pipeline):
        """Pipeline should not be marked as running until start() is called."""
        assert pipeline.is_running is False


class TestGenerateAndPushSignal:
    """Tests for QuantWeaselPipeline.generate_and_push_signal()."""

    @pytest.mark.asyncio
    async def test_generates_signal_with_correct_fields(self, pipeline):
        """Signal should be created with all provided fields."""
        signal = await pipeline.generate_and_push_signal(
            "TQQQ", "BUY", quantity=35, confidence=0.85, rationale="test signal",
        )
        assert signal is not None
        assert signal.symbol == "TQQQ"
        assert signal.action == SignalAction.BUY
        assert signal.quantity == 35
        assert signal.confidence == 0.85
        assert signal.rationale == "test signal"
        # SANDBOX auto-executes, so status is EXECUTED
        assert signal.status == SignalStatus.EXECUTED

    @pytest.mark.asyncio
    async def test_logs_to_audit(self, pipeline):
        """After generation, the audit database should contain the signal."""
        signal = await pipeline.generate_and_push_signal(
            "TQQQ", "BUY", quantity=35, confidence=0.85, rationale="audit test",
        )
        history = pipeline._audit_logger.get_signal_history(signal.signal_id)
        assert history is not None
        assert history["signal_id"] == signal.signal_id
        assert history["symbol"] == "TQQQ"
        assert history["action"] == "BUY"
        # SANDBOX auto-executes, so audit status is EXECUTED
        assert history["status"] == SignalStatus.EXECUTED.value

    @pytest.mark.asyncio
    async def test_pushes_lark_card(self, pipeline):
        """LarkInteractiveBot.push_card should be called when generating a signal."""
        await pipeline.generate_and_push_signal(
            "TQQQ", "BUY", quantity=35, confidence=0.85, rationale="card test",
        )
        pipeline._bot.push_card.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_generate_hold_action(self, pipeline):
        """HOLD action should also generate a valid signal."""
        signal = await pipeline.generate_and_push_signal(
            "TQQQ", "HOLD", quantity=0, confidence=0.5, rationale="hold test",
        )
        assert signal is not None
        assert signal.action == SignalAction.HOLD
        # SANDBOX auto-executes HOLD as success
        assert signal.status == SignalStatus.EXECUTED


class TestProcessConfirmedSignal:
    """Tests for QuantWeaselPipeline.process_confirmed_signal()."""

    @pytest.mark.asyncio
    async def test_sandbox_returns_dry_run_order(self, pipeline):
        """In SANDBOX mode, execution should return a dry-run order ID."""
        signal = await pipeline.generate_and_push_signal(
            "TQQQ", "BUY", quantity=35, confidence=0.85, rationale="sandbox exec",
        )
        result = await pipeline.process_confirmed_signal(signal.signal_id)

        assert result["success"] is True
        assert "dry-run-order" in result.get("order_id", "")
        assert result["risk_blocked"] is False

    @pytest.mark.asyncio
    async def test_execution_logged_in_audit(self, pipeline):
        """After successful execution, the audit log should reflect EXECUTED status."""
        signal = await pipeline.generate_and_push_signal(
            "TQQQ", "BUY", quantity=35, confidence=0.85, rationale="audit exec",
        )
        await pipeline.process_confirmed_signal(signal.signal_id)

        history = pipeline._audit_logger.get_signal_history(signal.signal_id)
        assert history is not None
        assert history["status"] == SignalStatus.EXECUTED.value
        assert history["execution_result"] is not None

    @pytest.mark.asyncio
    async def test_hold_action_skips_execution(self, pipeline):
        """HOLD signal should return success without a real order."""
        signal = await pipeline.generate_and_push_signal(
            "TQQQ", "HOLD", quantity=0, confidence=0.5, rationale="hold exec",
        )
        result = await pipeline.process_confirmed_signal(signal.signal_id)

        assert result["success"] is True
        assert result["message"] == "HOLD - 无需下单"
        assert result["order_id"] == "hold"

    @pytest.mark.asyncio
    async def test_signal_not_found_returns_error(self, pipeline):
        """Processing a non-existent signal ID should return an error."""
        result = await pipeline.process_confirmed_signal("nonexistent-id")

        assert result["success"] is False
        assert "不存在" in result.get("message", "")


class TestRiskRejection:
    """Test that risk rules correctly block oversized orders."""

    @pytest.mark.asyncio
    async def test_oversized_order_blocked_by_risk(self, pipeline):
        """Order value exceeding RISK_MAX_ORDER_VALUE should be blocked.

        We switch to PAPER mode so ExecutionEngine runs risk checks.
        quantity=100 * price_target=200 = $20,000 > $10,000 (default limit).
        """
        original_env = settings.TIGER_ENV
        settings.TIGER_ENV = "PAPER"
        try:
            signal = await _create_signal(
                pipeline, symbol="TQQQ", action="BUY",
                quantity=100, confidence=0.8, rationale="large order",
                price_target=200.0,
            )

            result = await pipeline.process_confirmed_signal(signal.signal_id)

            assert result["success"] is False
            assert result["risk_blocked"] is True
            assert "风控拦截" in result["message"] or "价值超限" in result["message"]
        finally:
            settings.TIGER_ENV = original_env

    @pytest.mark.asyncio
    async def test_small_order_passes_risk_check(self, pipeline):
        """A small legitimate order should pass risk checks.

        quantity=10 * price_target=200 = $2,000 < $10,000 → passes.
        """
        original_env = settings.TIGER_ENV
        settings.TIGER_ENV = "PAPER"
        try:
            signal = await _create_signal(
                pipeline, symbol="TQQQ", action="BUY",
                quantity=10, confidence=0.8, rationale="small order",
                price_target=200.0,
            )

            result = await pipeline.process_confirmed_signal(signal.signal_id)

            assert result["success"] is True
            assert result["risk_blocked"] is False
        finally:
            settings.TIGER_ENV = original_env


class TestDedupGuard:
    """Test that double confirmation is prevented."""

    @pytest.mark.asyncio
    async def test_double_confirm_returns_already_confirmed(self, pipeline):
        """Second call to process_confirmed_signal with same ID should be blocked."""
        signal = await pipeline.generate_and_push_signal(
            "TQQQ", "BUY", quantity=35, confidence=0.85, rationale="dedup test",
        )

        # First confirmation → should succeed
        first = await pipeline.process_confirmed_signal(signal.signal_id)
        assert first["success"] is True

        # Second confirmation → should be blocked by dedup
        second = await pipeline.process_confirmed_signal(signal.signal_id)
        assert second["success"] is False
        assert "already confirmed" in second.get("message", "").lower() or \
               "防重复" in second.get("message", "")

    @pytest.mark.asyncio
    async def test_different_signals_not_blocked(self, pipeline):
        """Two different signals should each be confirmable once."""
        s1 = await pipeline.generate_and_push_signal(
            "TQQQ", "BUY", quantity=35, confidence=0.85, rationale="first",
        )
        s2 = await pipeline.generate_and_push_signal(
            "AAPL", "BUY", quantity=20, confidence=0.75, rationale="second",
        )

        r1 = await pipeline.process_confirmed_signal(s1.signal_id)
        assert r1["success"] is True

        r2 = await pipeline.process_confirmed_signal(s2.signal_id)
        assert r2["success"] is True


class TestExpiredSignal:
    """Test that expired signals are rejected at execution time."""

    @pytest.mark.asyncio
    async def test_expired_signal_is_blocked(self, pipeline):
        """A signal past its expiry time should be rejected."""
        signal = await pipeline.generate_and_push_signal(
            "TQQQ", "BUY", quantity=35, confidence=0.85, rationale="expiry test",
        )
        # Force the signal to be expired
        signal.expires_at = datetime.now() - timedelta(minutes=1)

        # Update audit log so the rebuilt signal is also expired
        history = pipeline._audit_logger.get_signal_history(signal.signal_id)
        # Restore signal from JSON, modify, and re-save
        stored = Signal.model_validate_json(history["signal_json"])
        stored.expires_at = signal.expires_at
        # We need to update the DB. Since AuditLogger doesn't expose update,
        # we directly manipulate the DB connection.
        import sqlite3
        conn = sqlite3.connect(pipeline._audit_logger._db_path)
        conn.execute(
            "UPDATE signal_audit SET signal_json=? WHERE signal_id=?",
            (stored.model_dump_json(), signal.signal_id),
        )
        conn.commit()
        conn.close()

        result = await pipeline.process_confirmed_signal(signal.signal_id)

        assert result["success"] is False
        assert result.get("risk_blocked") is True
        assert "过期" in result.get("message", "")


class TestSandboxMode:
    """Tests specific to SANDBOX (default) trading mode."""

    @pytest.mark.asyncio
    async def test_sandbox_generates_dry_run_order_id(self, pipeline):
        """Verify the dry-run order ID format."""
        signal = await pipeline.generate_and_push_signal(
            "TQQQ", "BUY", quantity=35, confidence=0.85, rationale="sandbox format",
        )
        result = await pipeline.process_confirmed_signal(signal.signal_id)

        assert result["order_id"].startswith("dry-run-order-")

    @pytest.mark.asyncio
    async def test_sandbox_does_not_call_tiger_api(self, pipeline):
        """In SANDBOX mode, TigerClient methods should NOT be called."""
        signal = await pipeline.generate_and_push_signal(
            "TQQQ", "BUY", quantity=35, confidence=0.85, rationale="no tiger call",
        )
        await pipeline.process_confirmed_signal(signal.signal_id)

        # SANDBOX mode uses _sandbox_execute which never calls tiger methods
        pipeline._tiger_client.connect.assert_not_called()
        pipeline._tiger_client.place_limit_buy.assert_not_called()


class TestEndToEndFlow:
    """Full end-to-end flow: SIGNAL → CARD → CONFIRM → EXECUTE."""

    @pytest.mark.asyncio
    async def test_full_pipeline_flow(self, pipeline):
        """Complete happy path through the entire pipeline."""
        # Step 1: Generate signal (SANDBOX auto-executes)
        signal = await pipeline.generate_and_push_signal(
            "TQQQ", "BUY", quantity=35, confidence=0.85, rationale="e2e test",
        )
        # SANDBOX auto-executes, so status is EXECUTED immediately
        assert signal.status == SignalStatus.EXECUTED

        # Step 2: Verify audit logged creation + execution
        history = pipeline._audit_logger.get_signal_history(signal.signal_id)
        assert history is not None
        assert history["status"] == SignalStatus.EXECUTED.value

        # Step 3: Process confirmation → triggers execution
        result = await pipeline.process_confirmed_signal(signal.signal_id)
        assert result["success"] is True
        assert "dry-run-order" in result.get("order_id", "")

        # Step 4: Verify audit updated to EXECUTED
        history = pipeline._audit_logger.get_signal_history(signal.signal_id)
        assert history["status"] == SignalStatus.EXECUTED.value
        assert history["executed_at"] is not None


class TestCleanShutdown:
    """Pipeline lifecycle tests."""

    def test_start_and_stop(self, pipeline):
        """start() and stop() should toggle the running flag."""
        pipeline.start()
        assert pipeline.is_running is True

        pipeline.stop()
        assert pipeline.is_running is False


# ==================== Run standalone ====================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
