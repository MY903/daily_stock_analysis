"""Legacy → New Signal adapter.

Bridges the old 4-field ``Signal`` (strategy/base.py) to the new Pydantic
``Signal`` model (signal.py) and back.

Usage:
    adapter = SignalAdapter()
    new_sig = adapter.legacy_to_new(legacy_sig, symbol="AAPL")
    roundtripped = adapter.new_to_legacy(new_sig)
"""

from __future__ import annotations

from typing import Any, Dict

from src.trading.signal import Signal, SignalAction, SignalSource, SignalStatus
from src.trading.strategy.base import Signal as LegacySignal

# ── action string → SignalAction ──────────────────────────────────────────

_ACTION_MAP: Dict[str, SignalAction] = {
    "buy": SignalAction.BUY,
    "take_profit": SignalAction.SELL,
    "stop_loss": SignalAction.SELL,
    "hold": SignalAction.HOLD,
}

_REVERSE_ACTION_MAP: Dict[SignalAction, str] = {
    SignalAction.BUY: "buy",
    SignalAction.SELL: "take_profit",
    SignalAction.HOLD: "hold",
}


# ── public functions ──────────────────────────────────────────────────────


def legacy_to_new(
    legacy_signal: LegacySignal,
    symbol: str,
    **overrides: Any,
) -> Signal:
    """Convert a legacy 4-field Signal to the new Pydantic Signal.

    Parameters
    ----------
    legacy_signal : LegacySignal
        The legacy signal with fields ``action``, ``reason``, ``price``,
        ``trigger_price``.
    symbol : str
        Trading symbol (required by new Signal model).
    **overrides :
        Any additional field value to override on the new Signal
        (e.g. ``confidence=0.9``, ``source=SignalSource.AI``).

    Returns
    -------
    Signal
        Fully populated new Pydantic Signal instance.

    Raises
    ------
    ValueError
        If ``legacy_signal.action`` is not a recognised action string.

    Mapping
    -------
    ==================  ==========================  =========================
    Legacy field        New Signal field            Notes
    ==================  ==========================  =========================
    ``action``          ``action``                  ``"buy"`` → BUY,
                                                    ``"take_profit"`` /
                                                    ``"stop_loss"`` → SELL,
                                                    ``"hold"`` → HOLD
    ``reason``          ``rationale``               —
    ``price``           ``price_target``            —
    ``trigger_price``   (not mapped)                —
    ==================  ==========================  =========================

    Defaults
    --------
    - ``signal_id``: auto-generated UUID.
    - ``confidence``: ``0.7``.
    - ``source``: ``SignalSource.RULE``.
    - ``status``: ``SignalStatus.PENDING``.
    - ``created_at``: current UTC time.
    - ``expires_at``: 30 minutes after ``created_at``.
    """
    action = legacy_signal.action.lower().strip()
    if action not in _ACTION_MAP:
        valid = ", ".join(_ACTION_MAP)
        raise ValueError(
            f"Unknown legacy action '{legacy_signal.action}'. "
            f"Expected one of: {valid}"
        )

    # Start with defaults
    params: Dict[str, Any] = {
        "symbol": symbol,
        "action": _ACTION_MAP[action],
        "price_target": legacy_signal.price if legacy_signal.price != 0.0 else None,
        "rationale": legacy_signal.reason,
        "confidence": 0.7,
        "source": SignalSource.RULE,
        "status": SignalStatus.PENDING,
    }

    # Apply overrides (user-supplied values win)
    params.update(overrides)

    return Signal(**params)


def new_to_legacy(new_signal: Signal) -> LegacySignal:
    """Convert a new Pydantic Signal back to the legacy 4-field Signal.

    Parameters
    ----------
    new_signal : Signal
        The new Pydantic Signal instance.

    Returns
    -------
    LegacySignal
        Equivalent legacy signal.

    Mapping
    -------
    ==================  ==========================
    New Signal field    Legacy field
    ==================  ==========================
    ``action``          ``action`` (BUY→``"buy"``,
                        SELL→``"take_profit"``,
                        HOLD→``"hold"``)
    ``rationale``       ``reason``
    ``price_target``    ``price`` (``0.0`` if
                        ``None``)
    (not mapped)        ``trigger_price`` → ``0.0``
    ==================  ==========================
    """
    action_str = _REVERSE_ACTION_MAP.get(new_signal.action, "hold")
    price = new_signal.price_target if new_signal.price_target is not None else 0.0
    return LegacySignal(
        action=action_str,
        reason=new_signal.rationale,
        price=price,
        trigger_price=0.0,
    )
