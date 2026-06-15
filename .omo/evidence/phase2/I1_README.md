# I1: L3 Card Callback → T2 ExecutionEngine → Result Pushback — Full End-to-End Wire

## Changes Made

### 1. `src/trading/card_handler.py`
- Added `Awaitable` to typing imports
- Changed `on_execution()` type hint from `Callable[[Signal], None]` to `Callable[[Signal], Awaitable[None]]` — supports async execution handlers
- Changed `handle_card_action()` line 189: `self._execution_handler(signal)` → `await self._execution_handler(signal)` — proper coroutine await for async handlers

### 2. `src/trading/pipeline.py`
- `__init__`: Added `self._card_handler.on_execution(lambda signal: self.process_confirmed_signal(signal.signal_id))` — wires L3 card confirm callback to pipeline execution
- `process_confirmed_signal()`: Added signal expiry check before `execution_engine.execute()` — if `signal.is_expired()`, pushes `signal_expired_card` and returns early

### 3. `src/trading/signal_expiry.py`
- `start()`: Added `asyncio.create_task(self._expiry_loop())` — previously only set `_running = True` without actually starting the expiry loop

## End-to-End Flow

```
SignalConfirmHandler._on_confirm(signal_id)
  → handle_card_action(signal_id, "confirm")
    → await execution_handler(signal)                    [card_handler.py:189]
      → QuantWeaselPipeline.process_confirmed_signal(signal_id)  [pipeline.py:51]
        → DedupGuard.confirm_once(signal_id)              [防重复执行]
        → AuditLogger.get_signal_history(signal_id)       [重建Signal]
        → signal.is_expired() → push_signal_expired()     [信号过期卡片]
        → ExecutionEngine.execute(signal)                 [TRADING_MODE路由]
          → success → push_execution_result()             [执行结果卡片]
          → risk_blocked → push_risk_intercept()          [风控拦截卡片]
```

## Test Results: 7/7 PASSED

1. ✅ Pipeline instantiation + on_execution wired
2. ✅ Dedup/nonexistent guard
3. ✅ Expired signal detection
4. ✅ Success flow → push_execution_result
5. ✅ Risk intercept flow → push_risk_intercept
6. ✅ Expired signal → push_signal_expired
7. ✅ DedupGuard double-execution prevention

## Files Changed
- `src/trading/card_handler.py` — 3 lines changed
- `src/trading/pipeline.py` — 6 lines changed
- `src/trading/signal_expiry.py` — 1 line changed
