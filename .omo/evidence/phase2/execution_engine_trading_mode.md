# Phase 2 - ExecutionEngine Multi-Tier TradingMode

## Summary
Replaced Phase 1 hard lock (`if settings.is_prod` → fail) and `QUANT_DRY_RUN` check with TRADING_MODE-based routing in `ExecutionEngine.execute()`.

## Changes
- **`execute()`**: Routes by `settings.TRADING_MODE` enum (SANDBOX/PAPER/PROD)
- **`_sandbox_execute()`**: Preserves Phase 1 dry-run behavior — log, audit, return simulated order ID
- **`_paper_execute()`**: Full risk check → TigerClient connect → place_limit_buy/sell → Lark notification via `LarkInteractiveBot.push_card()`
- **`_prod_execute()`**: Risk check → return `{"awaiting_confirmation": True}` (L3 will wire double-confirm)
- **`_send_lark_notification()`**: Helper that builds card via `LarkCardBuilder.execution_result_card()` and pushes via `asyncio.run(bot.push_card(...))`
- **Removed**: `settings.is_prod` hard lock, `settings.QUANT_DRY_RUN` reference
- **Added**: `LarkInteractiveBot` as optional constructor param (defaults to fresh instance)

## Routing Logic
```
execute(signal, ref_price)
  ├── SANDBOX → _sandbox_execute()  → dry-run-order-{timestamp}
  ├── PAPER   → _paper_execute()    → risk → TigerClient → Lark notification
  └── PROD    → _prod_execute()     → risk → pending-confirmation (awaiting L3)
```

## Verification
- `python -m py_compile src/trading/execution.py` — PASS
- LSP diagnostics — 0 errors, 0 warnings
- No remaining `QUANT_DRY_RUN` references in execution.py
