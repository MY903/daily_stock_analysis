"""
DecisionSignal → QuantWeasel signal bridge.

This module connects the analysis/decision layer (DecisionSignalService) with the
trading execution layer (QuantWeaselPipeline). It:

1. Periodically polls active DecisionSignals
2. Validates signals against risk and trading rules
3. Pushes validated signals into QuantWeaselPipeline for execution
4. Provides a Web API for manual signal triggering

Usage:
    bridge = DecisionSignalBridge()
    await bridge.run_once()  # One-shot poll + push
    await bridge.run_loop(interval=60)  # Continuous loop

API integration (via existing FastAPI endpoints):
    POST /api/v1/trading/signal-bridge/trigger  # Manual trigger
    GET  /api/v1/trading/signal-bridge/status   # Bridge status
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from src.services.decision_signal_service import DecisionSignalService
from src.trading.pipeline import QuantWeaselPipeline
from src.trading.signal import Signal, SignalSource, SignalAction, SignalStatus
from src.trading.risk_manager import RiskManager, RiskVerdict

logger = logging.getLogger(__name__)

# Signal source types that can be auto-bridged to trading
BRIDGEABLE_SOURCE_TYPES: Set[str] = {"analysis", "agent", "manual"}

# Actions that can trigger a trading signal
TRADING_ACTIONS: Set[str] = {"buy", "strong_buy", "sell", "strong_sell"}


@dataclass
class BridgeConfig:
    """Bridge configuration."""

    enabled: bool = True
    poll_interval_sec: int = 300  # 5 minutes
    min_confidence: float = 0.5
    max_age_sec: int = 43200  # 12 hours
    allowed_source_types: Set[str] = field(
        default_factory=lambda: BRIDGEABLE_SOURCE_TYPES
    )
    allowed_actions: Set[str] = field(
        default_factory=lambda: TRADING_ACTIONS
    )


@dataclass
class BridgeResult:
    """Result of a bridge run."""

    polled: int = 0  # Number of signals polled
    accepted: int = 0  # Signals accepted into pipeline
    rejected: int = 0  # Signals rejected by validation
    errors: int = 0  # Errors during processing
    details: List[Dict[str, Any]] = field(default_factory=list)


class DecisionSignalBridge:
    """Bridge between DecisionSignalService and QuantWeaselPipeline.

    This is the core connector that enables the full flow:
    Analysis → DecisionSignal → Bridge → QuantWeasel → Execution
    """

    def __init__(
        self,
        signal_service: Optional[DecisionSignalService] = None,
        pipeline: Optional[QuantWeaselPipeline] = None,
        risk_manager: Optional[RiskManager] = None,
        config: Optional[BridgeConfig] = None,
    ) -> None:
        """Initialize the bridge.

        Args:
            signal_service: DecisionSignalService instance (created if None).
            pipeline: QuantWeaselPipeline instance (created if None).
            risk_manager: RiskManager instance (created if None).
            config: Bridge configuration (defaults used if None).
        """
        self._signal_service = signal_service or DecisionSignalService()
        self._pipeline = pipeline or QuantWeaselPipeline()
        self._risk_manager = risk_manager or RiskManager()
        self._config = config or BridgeConfig()
        self._running = False
        self._last_run: Optional[datetime] = None
        self._last_result: Optional[BridgeResult] = None

    @property
    def is_running(self) -> bool:
        """Whether the bridge loop is running."""
        return self._running

    @property
    def last_run(self) -> Optional[datetime]:
        """Timestamp of the last bridge run."""
        return self._last_run

    @property
    def last_result(self) -> Optional[BridgeResult]:
        """Result of the last bridge run."""
        return self._last_result

    async def run_once(self) -> BridgeResult:
        """One-shot poll and push cycle.

        Queries active DecisionSignals, validates them, and pushes
        accepted signals into the QuantWeasel pipeline.

        Returns:
            BridgeResult with processing statistics.
        """
        result = BridgeResult()

        if not self._config.enabled:
            logger.info("DecisionSignalBridge is disabled")
            return result

        try:
            # Poll active signals across bridgeable sources
            active_signals = self._poll_active_signals()
            result.polled = len(active_signals)

            for ds in active_signals:
                try:
                    accepted = await self._process_signal(ds)
                    if accepted:
                        result.accepted += 1
                    else:
                        result.rejected += 1
                except Exception as e:
                    logger.exception(
                        "DecisionSignalBridge: error processing signal %s: %s",
                        ds.get("id"), e
                    )
                    result.errors += 1
                    result.details.append({
                        "signal_id": ds.get("id"),
                        "status": "error",
                        "error": str(e),
                    })

        except Exception as e:
            logger.exception("DecisionSignalBridge.run_once: %s", e)
            result.errors += 1

        self._last_run = datetime.now(timezone.utc)
        self._last_result = result

        logger.info(
            "DecisionSignalBridge: polled=%d accepted=%d rejected=%d errors=%d",
            result.polled, result.accepted, result.rejected, result.errors
        )
        return result

    async def run_loop(self, interval_sec: Optional[int] = None) -> None:
        """Continuously poll and push signals in a loop.

        Args:
            interval_sec: Polling interval in seconds (defaults to config).
        """
        if self._running:
            logger.warning("DecisionSignalBridge is already running")
            return

        self._running = True
        interval = interval_sec or self._config.poll_interval_sec

        try:
            while self._running:
                await self.run_once()
                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            logger.info("DecisionSignalBridge loop cancelled")
        finally:
            self._running = False

    def stop(self) -> None:
        """Stop the bridge loop."""
        self._running = False
        logger.info("DecisionSignalBridge: stop requested")

    def _poll_active_signals(self) -> List[Dict[str, Any]]:
        """Query DecisionSignalService for active bridgeable signals.

        Returns:
            List of DecisionSignal dicts.
        """
        all_items: List[Dict[str, Any]] = []
        page = 1

        while True:
            try:
                result = self._signal_service.list_signals(
                    status="active",
                    page=page,
                    page_size=50,
                )
            except Exception as e:
                logger.warning(
                    "DecisionSignalBridge: poll error (page %d): %s", page, e
                )
                break

            items: List[Dict[str, Any]] = result.get("items", [])
            all_items.extend(items)

            total = result.get("total", 0)
            if len(all_items) >= total:
                break
            page += 1

        # Filter by allowed source types
        filtered = [
            s for s in all_items
            if s.get("source_type") in self._config.allowed_source_types
            and s.get("action") in self._config.allowed_actions
        ]

        logger.debug(
            "DecisionSignalBridge: polled %d active, %d bridgeable",
            len(all_items), len(filtered)
        )
        return filtered

    async def _process_signal(
        self, ds: Dict[str, Any]
    ) -> bool:
        """Validate and push a single DecisionSignal to the pipeline.

        Args:
            ds: DecisionSignal dict.

        Returns:
            True if accepted, False if rejected.
        """
        # 1. Confidence filter
        confidence = ds.get("confidence")
        if confidence is not None:
            try:
                if float(confidence) < self._config.min_confidence:
                    logger.debug(
                        "Bridge reject: signal %s confidence %.2f < %.2f",
                        ds.get("id"), float(confidence),
                        self._config.min_confidence
                    )
                    return False
            except (TypeError, ValueError):
                pass

        # 2. Age check
        created_at = ds.get("created_at")
        if created_at and self._config.max_age_sec > 0:
            try:
                if isinstance(created_at, str):
                    created_dt = datetime.fromisoformat(
                        created_at.replace("Z", "+00:00")
                    )
                elif isinstance(created_at, datetime):
                    created_dt = created_at
                else:
                    created_dt = None
                if created_dt:
                    age = (datetime.now(timezone.utc) - created_dt).total_seconds()
                    if age > self._config.max_age_sec:
                        logger.debug(
                            "Bridge reject: signal %s age %.0fs > %.0fs",
                            ds.get("id"), age, self._config.max_age_sec
                        )
                        return False
            except (ValueError, TypeError):
                pass

        # 3. Determine stock code and action
        stock_code = ds.get("stock_code") or ds.get("symbol")
        if not stock_code:
            return False

        action = ds.get("action", "")
        if action not in self._config.allowed_actions:
            return False

        # 4. Check risk limits
        price = float(ds.get("price_target") or 0)
        risk_check = self._risk_manager.check_position_limit(
            stock_code, 1, price
        )
        if risk_check.verdict == RiskVerdict.REJECT:
            logger.info(
                "Bridge reject: signal %s rejected by risk: %s",
                ds.get("id"), risk_check.reason
            )
            return False

        # 5. Push to QuantWeasel pipeline
        try:
            await self._pipeline.generate_and_push_signal(
                symbol=stock_code,
                action=action,
                reason=str(ds.get("reason", "")),
                price=price,
                source=SignalSource.AI,
            )

            logger.info(
                "Bridge accepted: signal %s -> %s %s",
                ds.get("id"), stock_code, action
            )
            return True
        except Exception as e:
            logger.error(
                "Bridge pipeline error for signal %s: %s",
                ds.get("id"), e
            )
            return False

    def get_status(self) -> Dict[str, Any]:
        """Get bridge status for diagnostics.

        Returns:
            Status dict.
        """
        return {
            "enabled": self._config.enabled,
            "running": self._running,
            "poll_interval_sec": self._config.poll_interval_sec,
            "min_confidence": self._config.min_confidence,
            "max_age_sec": self._config.max_age_sec,
            "allowed_source_types": sorted(self._config.allowed_source_types),
            "allowed_actions": sorted(self._config.allowed_actions),
            "last_run": self._last_run.isoformat() if self._last_run else None,
            "last_result": {
                "polled": self._last_result.polled if self._last_result else 0,
                "accepted": self._last_result.accepted if self._last_result else 0,
                "rejected": self._last_result.rejected if self._last_result else 0,
                "errors": self._last_result.errors if self._last_result else 0,
            } if self._last_result else None,
        }
