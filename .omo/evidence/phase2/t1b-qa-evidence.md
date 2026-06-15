# T1b — RiskManager Safety Upgrades: QA Evidence

## Summary
- **Task**: Add 4 new risk rules + SQLite persistence for daily loss
- **Date**: 2026-06-15
- **TDD**: ✓ Tests written first, then implementation

## What Changed

### New Files
- `src/trading/loss_persistence.py` — `DailyLossStore` class with SQLite (data/daily_loss.db)
- `tests/test_risk_safety_upgrades.py` — 21 new tests across 4 rules + persistence + integration

### Modified Files
- `config/settings.py` — Added 3 new settings:
  - `RISK_MAX_ORDER_VALUE = 10000.0`
  - `RISK_MAX_ORDERS_PER_MIN = 3`
  - `RISK_MAX_DAILY_ORDERS = 20`
- `src/trading/risk_manager.py` — Added:
  - `check_order_value_limit(symbol, quantity, price)`
  - `check_order_frequency(symbol)`
  - `check_daily_order_count()`
  - `check_circuit_breaker()`
  - DailyLossStore integration in `__init__`, `update_daily_loss()`, `reset_daily()`
  - Order frequency/daily count tracking in `is_allowed()`
  - Updated docstring + `check_all()` with all new rules

## Test Results

### Risk Tests: 37/37 PASSED (16 old + 21 new)

**Existing tests** (16, all green):
- `test_risk_integration.py` — position_limit, daily_loss_limit, cooldown, abnormal_price, signal_expiry, check_all, daily_reset

**New tests** (21, all green):

| Class | Test | What it verifies |
|-------|------|-----------------|
| `TestOrderValueLimit` | `test_value_limit_pass` | $9,500 < $10,000 → PASS |
| `TestOrderValueLimit` | `test_value_limit_reject` | $10,500 > $10,000 → REJECT |
| `TestOrderValueLimit` | `test_value_limit_boundary` | $10,000 exactly → PASS (≤) |
| `TestOrderFrequency` | `test_frequency_pass` | 1/min ≤ 3/min → PASS |
| `TestOrderFrequency` | `test_frequency_reject` | 4/min > 3/min → REJECT |
| `TestOrderFrequency` | `test_frequency_old_timestamps_ignored` | Old timestamps (>60s) excluded |
| `TestOrderFrequency` | `test_frequency_no_history` | First order → PASS |
| `TestDailyOrderCount` | `test_daily_count_pass` | 19 < 20 → PASS |
| `TestDailyOrderCount` | `test_daily_count_reject` | 21 > 20 → REJECT |
| `TestDailyOrderCount` | `test_daily_count_boundary` | 20 exactly → PASS (≤) |
| `TestCircuitBreaker` | `test_circuit_breaker_pass` | 4.9% < 5% → PASS |
| `TestCircuitBreaker` | `test_circuit_breaker_reject` | 5.1% ≥ 5% → REJECT |
| `TestCircuitBreaker` | `test_circuit_breaker_exact_boundary` | 5.0% ≥ 5% → REJECT (hard stop) |
| `TestDailyLossStore` | `test_load_empty` | Empty DB → 0.0 |
| `TestDailyLossStore` | `test_append_and_load` | Single loss persist + load |
| `TestDailyLossStore` | `test_append_multiple_and_sum` | Multi-symbol aggregation |
| `TestDailyLossStore` | `test_reset_daily` | Reset clears today's records |
| `TestDailyLossStore` | `test_yesterday_loss_not_counted` | Date isolation |
| `TestIntegration` | `test_check_all_includes_new_rules` | All 4 new rules in check_all |
| `TestIntegration` | `test_risk_manager_restores_loss_from_store` | Cross-restart recovery |
| `TestIntegration` | `test_update_daily_loss_persists` | update_daily_loss writes SQLite |

### Other Tests: No regressions
- `test_config_env_compat.py` — 18/18 passed
- `test_stock_code_bse.py` — 16/16 passed

## SQLite Verification
- `DailyLossStore` successfully creates `data/daily_loss.db`
- `append_loss()` → `load_today_loss()` round-trip verified
- `reset_daily()` clears today's records
- Date isolation: yesterday's losses not counted today
- Connection lifecycle: fresh connection per call (thread-safe)

## Risk: None
- All changes additive (new methods, new settings)
- Existing tests untouched, all pass
- No modification to existing API/signatures
