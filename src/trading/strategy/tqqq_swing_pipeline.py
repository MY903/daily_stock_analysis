"""TQQQSwingStrategy → QuantWeaselPipeline bridge runner.

Bridges the legacy ``TQQQSwingStrategy.evaluate()`` output into the new
``QuantWeaselPipeline.generate_and_push_signal()`` via ``SignalAdapter.legacy_to_new()``.

Usage:
    runner = TQQQSwingRunner(config, strategy_instance, pipeline_instance)
    result = await runner.run_once(quote, state, context)
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from src.trading.config import AppConfig
from src.trading.pipeline import QuantWeaselPipeline
from src.trading.signal import Signal
from src.trading.strategy.signal_adapter import legacy_to_new
from src.trading.strategy.tqqq_swing import TQQQSwingStrategy

logger = logging.getLogger(__name__)


class TQQQSwingRunner:
    """Bridge runner that connects the legacy TQQQSwingStrategy to the new QuantWeaselPipeline.

    The runner's ``run_once()`` method:
    1. Calls the legacy strategy's ``evaluate()``
    2. Converts the legacy ``Signal`` to a new Pydantic ``Signal`` via ``legacy_to_new()``
    3. Passes the result to ``pipeline.generate_and_push_signal()``
    """

    def __init__(
        self,
        config: AppConfig,
        strategy: TQQQSwingStrategy,
        pipeline: QuantWeaselPipeline,
    ) -> None:
        """Initialize the runner.

        Args:
            config: Application configuration (read from trading.yaml).
            strategy: An instance of TQQQSwingStrategy.
            pipeline: An instance of QuantWeaselPipeline.
        """
        self._config = config
        self._strategy = strategy
        self._pipeline = pipeline

    @property
    def strategy(self) -> TQQQSwingStrategy:
        """The wrapped TQQQSwingStrategy instance."""
        return self._strategy

    @property
    def pipeline(self) -> QuantWeaselPipeline:
        """The wrapped QuantWeaselPipeline instance."""
        return self._pipeline

    async def run_once(
        self,
        quote: Dict[str, Any],
        state: str,
        context: Dict[str, Any],
    ) -> Optional[Signal]:
        """Run one evaluation cycle: evaluate → adapt → push.

        Args:
            quote: Latest market data dict.
            state: Current state machine state (e.g. "IDLE", "HOLDING").
            context: State context dict (includes e.g. ``fill_price``).

        Returns:
            The new Pydantic ``Signal`` if a signal was generated and pushed,
            or ``None`` if no signal was produced.
        """
        # 1. Legacy evaluation
        legacy_signal = self._strategy.evaluate(quote, state, context)
        if legacy_signal is None:
            logger.debug("TQQQSwingStrategy.evaluate() returned None — no signal")
            return None

        logger.debug(
            "Legacy signal: action=%s price=%s reason=%s",
            legacy_signal.action,
            legacy_signal.price,
            legacy_signal.reason,
        )

        # 2. Convert legacy → new Pydantic Signal
        symbol = self._strategy.symbol
        new_signal = legacy_to_new(legacy_signal, symbol=symbol)

        logger.debug(
            "Converted to new Signal: action=%s symbol=%s",
            new_signal.action.value,
            new_signal.symbol,
        )

        # 3. Push through pipeline
        result = await self._pipeline.generate_and_push_signal(
            symbol=new_signal.symbol,
            action=new_signal.action.value,
            confidence=new_signal.confidence,
            rationale=new_signal.rationale,
        )

        if result is None:
            logger.error("Pipeline failed to push signal for %s %s", symbol, new_signal.action.value)
            return None

        logger.info(
            "Signal pushed via pipeline: %s %s (ID: %s)",
            result.symbol,
            result.action.value,
            result.signal_id,
        )
        return result
