"""Tests for DecisionSignal→QuantWeasel bridge."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.trading.signal_bridge import (
    DecisionSignalBridge,
    BridgeConfig,
    BridgeResult,
)


@pytest.fixture
def mock_bridge_config() -> BridgeConfig:
    """Minimal bridge config for testing."""
    return BridgeConfig(
        enabled=True,
        poll_interval_sec=10,
        min_confidence=0.5,
        max_age_sec=86400,
    )


@pytest.fixture
def mock_active_signals():
    """Sample active DecisionSignals for bridge testing."""
    return [
        {
            "id": 1,
            "stock_code": "TQQQ",
            "action": "buy",
            "reason": "Technical breakout",
            "confidence": 0.85,
            "price_target": 85.0,
            "source_type": "analysis",
            "created_at": "2026-06-20T08:00:00+00:00",
            "status": "active",
        },
        {
            "id": 2,
            "stock_code": "AAPL",
            "action": "sell",
            "reason": "RSI overbought",
            "confidence": 0.72,
            "price_target": 180.0,
            "source_type": "agent",
            "created_at": "2026-06-19T10:00:00+00:00",
            "status": "active",
        },
        {
            "id": 3,
            "stock_code": "TSLA",
            "action": "buy",
            "reason": "Momentum signal",
            "confidence": 0.35,  # Below threshold
            "price_target": 250.0,
            "source_type": "analysis",
            "created_at": "2026-06-20T06:00:00+00:00",
            "status": "active",
        },
    ]


class TestDecisionSignalBridge:
    """Test suite for DecisionSignalBridge."""

    def test_bridge_config_defaults(self):
        """BridgeConfig should have sensible defaults."""
        config = BridgeConfig()
        assert config.enabled is True
        assert config.poll_interval_sec > 0
        assert config.min_confidence == 0.5
        assert "analysis" in config.allowed_source_types
        assert "buy" in config.allowed_actions

    @patch("src.trading.signal_bridge.DecisionSignalService")
    @patch("src.trading.signal_bridge.QuantWeaselPipeline")
    def test_run_once_no_signals(self, mock_pipeline_cls, mock_svc_cls):
        """Should handle empty signal list gracefully."""
        mock_svc = MagicMock()
        mock_svc.list_signals.return_value = {"items": [], "total": 0}
        bridge = DecisionSignalBridge(
            signal_service=mock_svc,
            config=BridgeConfig(enabled=True),
        )
        import asyncio
        result = asyncio.run(bridge.run_once())
        assert result.polled == 0
        assert result.accepted == 0
        assert result.rejected == 0

    @patch("src.trading.signal_bridge.DecisionSignalService")
    @patch("src.trading.signal_bridge.QuantWeaselPipeline")
    def test_bridge_disabled(self, mock_pipeline_cls, mock_svc_cls):
        """Should no-op when disabled."""
        bridge = DecisionSignalBridge(config=BridgeConfig(enabled=False))
        import asyncio
        result = asyncio.run(bridge.run_once())
        assert result.polled == 0
        assert result.accepted == 0

    @patch("src.trading.signal_bridge.DecisionSignalService")
    @patch("src.trading.signal_bridge.QuantWeaselPipeline")
    def test_get_status(self, mock_pipeline_cls, mock_svc_cls):
        """get_status should return current bridge state."""
        bridge = DecisionSignalBridge(config=BridgeConfig(enabled=True, poll_interval_sec=60))
        status = bridge.get_status()
        assert status["enabled"] is True
        assert status["running"] is False
        assert status["poll_interval_sec"] == 60
        assert status["last_run"] is None

    def test_bridge_config_customization(self):
        """Should allow custom bridge configuration."""
        config = BridgeConfig(
            enabled=True,
            poll_interval_sec=120,
            min_confidence=0.7,
            allowed_source_types={"manual", "analysis"},
            allowed_actions={"buy", "sell"},
        )
        assert config.min_confidence == 0.7
        assert config.poll_interval_sec == 120
        assert "manual" in config.allowed_source_types
        assert "alert" not in config.allowed_source_types

    def test_bridge_result_accumulation(self):
        """BridgeResult should correctly accumulate stats."""
        result = BridgeResult()
        assert result.polled == 0
        assert result.accepted == 0
        assert result.rejected == 0
        assert result.errors == 0

        result.polled = 10
        result.accepted = 3
        result.rejected = 5
        result.errors = 2
        assert result.polled == 10
        assert result.accepted == 3
        assert result.rejected == 5
        assert result.errors == 2
