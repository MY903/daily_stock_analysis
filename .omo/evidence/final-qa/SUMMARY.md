# Final Verification Wave F3 — Actual Manual QA

**Date**: 2026-06-15 17:04 UTC+8  
**Executor**: Sisyphus-Junior  
**Project**: QuantWeasel (Daily Stock Analysis)  

---

## Scenario Results

### Scenario 1: 信号创建和 CLI 解析 ✅ PASS
- **1a**: Signal model creation — `Signal(symbol='TQQQ', action=SignalAction.BUY, quantity=100, confidence=0.85)`  
  → All fields verified: symbol, action, quantity, confidence, source, signal_id, status(PENDING), created_at
- **1b**: CLI argument parsing via `QuantWeaselPipeline.build_parser()`  
  → `--mode premarket` defaults `dry_run=True` ✓  
  → `--mode manual --symbol AAPL --action SELL --quantity 50` correct ✓

### Scenario 2: Pipeline 构建和生命周期 ✅ PASS
- Pipeline created successfully ✓
- `is_running` = False initially ✓
- `start()` sets `is_running` = True ✓
- `stop()` sets `is_running` = False ✓  
- Internal: ExpiryManager started, SignalScheduler (APScheduler) started, shutdown handlers registered

### Scenario 3: 信号生成与推送 ✅ PASS
- `generate_and_push_signal('TQQQ', 'BUY', quantity=100, confidence=0.85)` → signal created with UUID ✓
- Signal pushed via `LarkCardBuilder.signal_confirm_card()` → `LarkInteractiveBot.push_card()` returns True ✓
- `process_confirmed_signal()` → ExecutionEngine in dry-run mode → `{'success': True, 'order_id': 'dry-run-order-000', ...}` ✓

### Scenario 4: 重复确认防护 ✅ PASS
- First confirmation: `success: True`, order executed ✓
- Second confirmation intercepted by `DedupGuard.confirm_once()` → `success: False`, `message: "信号已被确认（防重复执行）"` ✓
- Message contains "重复" as expected ✓

### Scenario 5: 边缘情况 — 大盘模式 ✅ PASS
- `run_pre_market()` → returned `int` (0 signals, no OHLCV data) ✓
- `run_intraday()` → returned `int` (0 signals, outside market hours) ✓
- Both return integer type as expected ✓

### Scenario 6: 主入口脚本 ✅ PASS
- `python quant_weasel_main.py --help` → correct CLI usage output with all 4 modes ✓
- `python quant_weasel_main.py --mode premarket --dry-run` → runs successfully, prints completion ✓

---

## Summary

```
Scenarios 6/6 pass | Integration 6/6 | Edge Cases 0 tested | VERDICT ALL PASS
```

