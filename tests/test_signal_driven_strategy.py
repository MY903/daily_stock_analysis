"""Tests for DecisionSignal-driven trading strategy."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.trading.config import AppConfig, TradingConfig, TigerConfig, EntryConfig, TakeProfitConfig, StopLossConfig, MACrossoverConfig
from src.trading.strategy.signal_driven import SignalDrivenStrategy
from src.trading.signal import Signal


@pytest.fixture
def mock_config() -> AppConfig:
    """Create a minimal mock config."""
    tc = TradingConfig(
        symbol="TQQQ",
        symbols=["TQQQ"],
        auto_trade=False,
        entry=EntryConfig(),
        take_profit=TakeProfitConfig(),
        stop_loss=StopLossConfig(),
        ma=MACrossoverConfig(),
    )
    return AppConfig(
        tiger=TigerConfig(),
        trading=tc,
    )


@pytest.fixture
def strategy(mock_config) -> SignalDrivenStrategy:
    """Create a default SignalDrivenStrategy for testing."""
    return SignalDrivenStrategy(mock_config)


@pytest.fixture
def mock_decision_signal():
    """Sample DecisionSignal dict."""
    return {
        "id": 42,
        "stock_code": "TQQQ",
        "action": "buy",
        "reason": "Strong momentum with volume breakout",
        "confidence": 0.85,
        "price_target": 85.0,
        "source_type": "analysis",
        "created_at": "2026-06-20T08:00:00+00:00",
        "status": "active",
    }


class TestSignalDrivenStrategy:
    """Test suite for SignalDrivenStrategy."""

    def test_name(self, strategy):
        """Strategy name should be 'signal_driven'."""
        assert strategy.name == "signal_driven"

    def test_symbol(self, strategy):
        """Symbol should come from config."""
        assert strategy.symbol == "TQQQ"

    def test_evaluate_no_signals(self, strategy):
        """Should return empty list when no signals exist."""
        with patch.object(
            strategy._signal_service, "list_signals",
            return_value={"items": [], "total": 0},
        ):
            result = strategy.evaluate({"latest_price": 80.0}, "idle")
            assert result == []

    @patch("src.trading.strategy.signal_driven.DecisionSignalService")
    def test_evaluate_with_signals(self, mock_svc_cls, strategy, mock_decision_signal):
        """Should convert active DecisionSignals to trading Signals."""
        mock_svc = MagicMock()
        mock_svc.list_signals.return_value = {
            "items": [mock_decision_signal],
            "total": 1,
        }
        strategy._signal_service = mock_svc

        result = strategy.evaluate({"latest_price": 80.0}, "idle")
        assert len(result) == 1
        assert isinstance(result[0], Signal)
        assert result[0].action == "buy"
        assert "Strong momentum" in result[0].reason
        assert result[0].price == 85.0
        assert result[0].confidence == 0.85

    @patch("src.trading.strategy.signal_driven.DecisionSignalService")
    def test_confidence_filter(self, mock_svc_cls, strategy, mock_decision_signal):
        """Should filter signals below min_confidence."""
        mock_decision_signal["confidence"] = 0.3
        mock_svc = MagicMock()
        mock_svc.list_signals.return_value = {
            "items": [mock_decision_signal],
            "total": 1,
        }
        strategy._signal_service = mock_svc

        result = strategy.evaluate({"latest_price": 80.0}, "idle")
        assert len(result) == 0

    @patch("src.trading.strategy.signal_driven.DecisionSignalService")
    def test_action_mapping(self, mock_svc_cls, strategy, mock_decision_signal):
        """Buy/strong_buy maps to buy action, sell/strong_sell maps to sell."""
        mock_svc = MagicMock()
        mock_decision_signal["confidence"] = 0.9

        mock_decision_signal["action"] = "strong_buy"
        mock_svc.list_signals.return_value = {"items": [mock_decision_signal], "total": 1}
        strategy._signal_service = mock_svc
        result = strategy.evaluate({"latest_price": 80.0}, "idle")
        assert result[0].action == "buy"

        mock_decision_signal["action"] = "sell"
        mock_svc.list_signals.return_value = {"items": [mock_decision_signal], "total": 1}
        result = strategy.evaluate({"latest_price": 80.0}, "idle")
        assert result[0].action == "sell"

    @patch("src.trading.strategy.signal_driven.DecisionSignalService")
    def test_should_enter(self, mock_svc_cls, strategy, mock_decision_signal):
        """should_enter returns True when buy signal exists."""
        mock_svc = MagicMock()
        mock_svc.list_signals.return_value = {"items": [mock_decision_signal], "total": 1}
        strategy._signal_service = mock_svc
        assert strategy.should_enter({"latest_price": 80.0}) is True

    @patch("src.trading.strategy.signal_driven.DecisionSignalService")
    def test_should_enter_no_signal(self, mock_svc_cls, strategy):
        """should_enter returns False when no buy signal."""
        mock_svc = MagicMock()
        mock_svc.list_signals.return_value = {"items": [], "total": 0}
        strategy._signal_service = mock_svc
        assert strategy.should_enter({"latest_price": 80.0}) is False

    def test_service_error_handling(self, strategy):
        """Should handle DecisionSignalService errors gracefully."""
        with patch.object(
            strategy._signal_service, "list_signals",
            side_effect=Exception("Service unavailable"),
        ):
            result = strategy.evaluate({"latest_price": 80.0}, "idle")
            assert result == []
