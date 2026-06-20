# QuantWeasel 风控配置说明

## 概述

`RiskManager`（`src/trading/risk_manager.py`）是 QuantWeasel 交易系统的核心风控模块，在每笔订单执行前进行多维度检查。所有配置通过环境变量和 `TRADING_MODE` 控制。

## 风控检查维度

| 检查项 | 方法 | 说明 | 阻断等级 |
|--------|------|------|---------|
| 仓位限制 | `check_position_limit()` | 单标的仓位百分比上限 | 硬阻断 |
| 日亏损限制 | `check_daily_loss_limit()` | 单日累计亏损上限 | 硬阻断 |
| 最大持仓数 | `check_max_positions()` | 同时持仓标的上限 | 硬阻断 |
| 信号过期 | `check_signal_expiry()` | 信号生成时间有效性 | 硬阻断 |
| 异常价格 | `check_abnormal_price()` | 价格偏离参考价过大 | 硬阻断 |
| 冷却期 | `check_cooldown()` | 同标的两次交易最小间隔 | 硬阻断 |
| 订单金额限制 | `check_order_value_limit()` | 单笔订单金额上限 | 硬阻断 |
| 订单频率限制 | `check_order_frequency()` | 单位时间内交易次数限制 | 硬阻断 |

## 风险等级

每个检查返回 `RiskCheckResult`，包含 `verdict`（通过/警告/拒绝）和原因描述。

```python
class RiskVerdict(Enum):
    PASS = "pass"         # 检查通过
    WARN = "warn"         # 警告（可执行，但需记录）
    REJECT = "reject"     # 拒绝（不执行）
```

## 配置方式

### 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `TRADING_MODE` | 运行模式（SANDBOX/PAPER/PROD） | `SANDBOX` |
| `TIGER_ENV` | Tiger 环境（SANDBOX/PROD） | `SANDBOX` |
| `MAX_POSITION_PCT` | 单标的最大仓位百分比 | `0.2` |
| `MAX_DAILY_LOSS_PCT` | 单日最大亏损百分比 | `0.03` |
| `MAX_POSITIONS` | 最大同时持仓数 | `5` |
| `MIN_TRADE_INTERVAL` | 同标的最小交易间隔（秒） | `86400` |
| `MAX_ORDER_FREQUENCY` | 每小时最大交易次数 | `3` |

### 运行时配置

风控参数可通过 `api/v1/endpoints/trading.py` 的 API 动态调整：

```bash
# 查看当前风控状态
curl http://localhost:8000/api/v1/trading/risk/status

# 查看风控规则
curl http://localhost:8000/api/v1/trading/risk/rules

# 更新风控参数
curl -X POST http://localhost:8000/api/v1/trading/risk/rules \
  -H "Content-Type: application/json" \
  -d '{"max_position_pct": 0.15}'
```

## 日亏损管理

`RiskManager` 通过 `update_daily_loss()` 和 `loss_persistence.py` 实现日亏损的持久化管理：

1. 日亏损存储在 `data/daily_loss.db`
2. 每日自动重置（通过 `reset_daily()`）
3. 超过 `MAX_DAILY_LOSS_PCT` 时，当日所有新订单被拒绝
4. 已持仓不受影响（保护已有仓位）

## 冷却期机制

为防止频繁交易，系统维护每个标的的冷却状态：

- `check_cooldown()` 检查同标的交易间隔是否满足 `MIN_TRADE_INTERVAL`
- 冷却期内该标的的新信号自动跳过
- 冷却期从上次订单执行时间开始计算

## 异常价格检测

```python
def check_abnormal_price(self, symbol: str, price: float, ref_price: float) -> RiskCheckResult:
    """检查价格是否异常：
    - 价格偏离参考价超过 50% 拒绝
    - 价格为零或负数拒绝
    """
```

参考价格为最近收盘价或移动平均价。

## 模拟模式（SANDBOX）

在 SANDBOX 模式下：
- 所有风控检查完整执行
- 检查结果写入审计日志
- 不实际下单
- 飞书卡片标注为「模拟」

## 审计日志

所有风控检查记录通过 `AuditLogger` 持久化，包含：

| 字段 | 示例 |
|------|------|
| timestamp | `2026-06-20T09:30:00Z` |
| symbol | `TQQQ` |
| check_type | `position_limit` |
| verdict | `reject` |
| detail | `仓位超限: 当前 25%, 上限 20%` |

## 故障排查

1. **订单总被风控拒绝**：检查 `MAX_POSITION_PCT` / `MAX_DAILY_LOSS_PCT` 是否过严
2. **信号一直显示冷却中**：检查 `MIN_TRADE_INTERVAL` 配置和 `daily_loss.db`
3. **SANDBOX 模式不下单**：确认 `TRADING_MODE` 不为 `PROD`
4. **审计日志不记录**：检查 `logs/` 目录可写性和日志级别
