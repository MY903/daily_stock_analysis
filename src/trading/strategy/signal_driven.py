"""DecisionSignal-driven trading strategy.

Consumes DecisionSignal (from src/services/decision_signal_service.py) as trading
signals and bridges them into the QuantWeasel pipeline. Supports configurable
signal sources, minimum confidence thresholds, and action-to-order mapping.

Usage:
    strategy = SignalDrivenStrategy(config)
    signals = strategy.evaluate(quote, state, prices)
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from src.trading.config import AppConfig
from src.trading.strategy.base import BaseStrategy, Signal
from src.trading.strategy.registry import StrategyRegistry
from src.services.decision_signal_service import DecisionSignalService

logger = logging.getLogger(__name__)

# Default action mapping: how DecisionSignal actions map to trading Signal actions
DEFAULT_ACTION_MAP: Dict[str, str] = {
    "strong_buy": "buy",
    "buy": "buy",
    "hold": "hold",
    "sell": "sell",
    "strong_sell": "sell",
}

# Minimum confidence to accept a DecisionSignal as a trading signal
DEFAULT_MIN_CONFIDENCE: float = 0.5

# Maximum age in seconds for a DecisionSignal to be accepted
DEFAULT_MAX_AGE_SEC: int = 86400  # 24 hours


@StrategyRegistry.register
class SignalDrivenStrategy(BaseStrategy):
    """Trading strategy driven by persisted DecisionSignals.

    This strategy queries the DecisionSignalService for active signals on the
    configured symbol and converts validated signals into QuantWeasel trading
    signals. It acts as a bridge between the analysis/decision layer and the
    execution layer.
    """

    name: str = "signal_driven"

    def __init__(self, config: AppConfig) -> None:
        """Initialize the strategy with a DecisionSignalService instance.

        Args:
            config: Application configuration, must have trading.symbol set.
        """
        super().__init__(config)
        self._signal_service = DecisionSignalService()
        self._action_map: Dict[str, str] = DEFAULT_ACTION_MAP.copy()
        self._min_confidence: float = DEFAULT_MIN_CONFIDENCE
        self._max_age_sec: int = DEFAULT_MAX_AGE_SEC

        # Override from config if provided
        strategy_cfg = self._get_strategy_config()
        if strategy_cfg:
            custom_map = strategy_cfg.get("action_map", {})
            if isinstance(custom_map, dict):
                self._action_map.update(custom_map)
            self._min_confidence = float(
                strategy_cfg.get("min_confidence", self._min_confidence)
            )
            self._max_age_sec = int(
                strategy_cfg.get("max_age_sec", self._max_age_sec)
            )

    def _get_strategy_config(self) -> Optional[Dict[str, Any]]:
        """Extract strategy-specific config from AppConfig."""
        # AppConfig uses dataclass, strategy params live in a dict key
        raw = getattr(self._config, "strategies", None)
        if isinstance(raw, dict):
            return raw.get("signal_driven", {})
        return None

    @property
    def symbol(self) -> str:
        """Return the configured trading symbol."""
        return self._config.trading.symbol

    def evaluate(
        self,
        quote: Dict[str, Any],
        state: str,
        prices: Optional[List[float]] = None,
    ) -> List[Signal]:
        """Query DecisionSignalService and convert active signals to trading signals.

        Args:
            quote: Current market quote dictionary.
            state: Current strategy state (idle/entered/exited).
            prices: Optional historical price list (unused).

        Returns:
            List of trading Signal objects.
        """
        if not self.symbol:
            return []

        try:
            result = self._signal_service.list_signals(
                stock_code=self.symbol,
                status="active",
                page=1,
                page_size=50,
            )
        except Exception as e:
            logger.warning(
                "SignalDrivenStrategy[%s]: failed to query DecisionSignalService: %s",
                self.symbol, e
            )
            return []

        items: List[Dict[str, Any]] = result.get("items", [])
        if not items:
            return []

        signals: List[Signal] = []
        for ds in items:
            signal = self._convert(ds, quote)
            if signal is not None:
                signals.append(signal)

        return signals

    def _convert(
        self,
        decision_signal: Dict[str, Any],
        quote: Dict[str, Any],
    ) -> Optional[Signal]:
        """Convert a single DecisionSignal dict to a trading Signal.

        Args:
            decision_signal: Raw dict from DecisionSignalService.
            quote: Current quote for price context.

        Returns:
            Signal or None if validation fails.
        """
        raw_action: Optional[str] = decision_signal.get("action")
        if not raw_action:
            return None

        mapped_action = self._action_map.get(raw_action)
        if mapped_action is None:
            return None

        # Confidence filter
        confidence = decision_signal.get("confidence")
        if confidence is not None:
            try:
                if float(confidence) < self._min_confidence:
                    return None
            except (TypeError, ValueError):
                pass

        # Age check
        created_at = decision_signal.get("created_at")
        if created_at and self._max_age_sec > 0:
            from datetime import datetime, timezone
            try:
                if isinstance(created_at, str):
                    created_dt = datetime.fromisoformat(
                        created_at.replace("Z", "+00:00")
                    )
                else:
                    created_dt = created_at
                if isinstance(created_dt, datetime):
                    age = (datetime.now(timezone.utc) - created_dt).total_seconds()
                    if age > self._max_age_sec:
                        logger.debug(
                            "SignalDrivenStrategy[%s]: signal %s expired by age %.0fs",
                            self.symbol, decision_signal.get("id"), age
                        )
                        return None
            except (ValueError, TypeError):
                pass

        # Determine price from signal or quote
        price = 0.0
        price_target = decision_signal.get("price_target")
        if price_target is not None:
            try:
                price = float(price_target)
            except (TypeError, ValueError):
                price = float(quote.get("latest_price", 0))
        else:
            price = float(quote.get("latest_price", 0))

        # Build reason string
        reason_parts: List[str] = []
        reason = decision_signal.get("reason") or decision_signal.get("summary")
        if reason:
            reason_parts.append(str(reason)[:200])
        source = decision_signal.get("source_type") or decision_signal.get("trigger_source")
        if source:
            reason_parts.append(f"(source: {source})")
        signal_id = decision_signal.get("id")
        if signal_id:
            reason_parts.append(f"(signal_id: {signal_id})")

        return Signal(
            action=mapped_action,
            reason=" | ".join(reason_parts) if reason_parts else f"DecisionSignal: {raw_action}",
            price=price,
            confidence=float(confidence) if confidence else 0.7,
        )

    def should_enter(self, market_data: Dict[str, Any]) -> bool:
        """Check if any active buy signal exists for the configured symbol.

        Args:
            market_data: Current market data dict.

        Returns:
            True if there's an active buy/strong_buy signal.
        """
        signals = self.evaluate(market_data, "idle")
        return any(s.action in ("buy", "strong_buy") for s in signals)

    def should_exit(self, position: Any) -> bool:
        """Check if any active sell signal exists for the configured symbol.

        Args:
            position: Current position info.

        Returns:
            True if there's an active sell/strong_sell signal.
        """
        signals = self.evaluate({}, "entered")
        return any(s.action in ("sell", "strong_sell") for s in signals)
