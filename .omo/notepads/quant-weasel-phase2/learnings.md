# Quant Weasel Phase 2 — Learnings

## T0: Tiger Credential Smoke Test (2026-06-15)

- script created: `scripts/tiger_smoke.py`
- credential loading from `config.settings` (pydantic BaseSettings via .env) works correctly
- `TigerClient.connect()` sets PAPER mode correctly via `TigerConfig(environment="PAPER")`
- Tiger OpenAPI SDK v3.5.8 initializes successfully
- Token is **expired** (`code=2400, msg=user token expired invalid`)
- Script handles failure gracefully: logs error, exits with code 1
- Script successfully verifies the complete credential loading + SDK init pipeline
- **Action needed**: Refresh `TIGER_TOKEN` in `.env` from Tiger Brokers OpenAPI console before re-testing
- Script must be run from project root: `python scripts/tiger_smoke.py` (auto-adds project root to sys.path)

## T1a: Unify env config (2026-06-15)

- Added `TradingMode` enum (SANDBOX/PAPER/PROD) to `config/settings.py` as single authoritative environment source
- `settings.TRADING_MODE` property derived from `settings.TIGER_ENV`
- Clean `is_sandbox` (SANDBOX only), `is_paper` (PAPER only), `is_prod` (PROD only) properties
- Old `is_sandbox` previously returned True for both SANDBOX and PAPER; now SANDBOX-only, execution.py updated to use `settings.is_prod` for Phase 1 safety lock
- `TigerConfig.environment` in `src/trading/config.py` is now a property reading from `settings.TIGER_ENV`; mapping: SANDBOX/PAPER→"PAPER", PROD→"LIVE"
- `TRADING_TIGER_ENV` env var in config.py env_map removed (superceded by `settings.TIGER_ENV`)
- `QUANT_DRY_RUN` and `TRADING_AUTO_TRADE` fields preserved for backward compat with updated descriptions linking to TRADING_MODE
- Evidence saved to `.omo/evidence/phase2/t1a-sandbox.txt` and `t1a-prod.txt`
- All 3 changed files pass `python -m py_compile` and LSP diagnostics
