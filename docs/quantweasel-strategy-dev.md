# QuantWeasel 策略开发指南

## 概述

QuantWeasel 支持多种策略类型：基于技术指标的规则策略、AI/LLM 信号策略，以及决策信号（DecisionSignal）联动策略。本文档说明如何开发和注册新策略。

## 策略架构

所有策略继承 `BaseStrategy` 基类（`src/trading/strategy/base.py`），通过 `StrategyRegistry` 注册表管理。

### BaseStrategy 核心方法

| 方法 | 用途 | 返回值 |
|------|------|--------|
| `evaluate(quote, state, prices)` | 评估实时行情，返回 Signal 列表 | `list[Signal]` |
| `should_enter(market_data)` | 判断是否开仓 | `bool` |
| `should_exit(position)` | 判断是否平仓 | `bool` |
| `name` | 策略唯一名称（属性） | `str` |
| `symbol` | 策略关联的标的（属性） | `str` |

## 创建新策略

### 步骤 1: 创建策略文件

在 `src/trading/strategy/` 下创建 `<策略名称>.py`：

```python
from src.trading.strategy.base import BaseStrategy, Signal
from src.trading.strategy.registry import StrategyRegistry

@StrategyRegistry.register("my_custom_strategy")
class MyCustomStrategy(BaseStrategy):
    """自定义策略示例"""

    @property
    def name(self) -> str:
        return "my_custom_strategy"

    def evaluate(self, quote, state, prices=None):
        signals = []
        if self._check_condition(quote):
            signals.append(Signal(
                action="buy",
                reason="条件满足",
                price=quote.get("latest_price", 0),
            ))
        return signals

    def should_enter(self, market_data):
        return self._check_condition(market_data)

    def should_exit(self, position):
        return False

    def _check_condition(self, data):
        return True
```

### 步骤 2: 注册策略

使用 `@StrategyRegistry.register` 装饰器注册策略。系统会自动发现已注册的策略。

### 步骤 3: 配置策略参数

在 `config/trading.yaml` 中添加策略配置：

```yaml
strategies:
  my_custom_strategy:
    enabled: true
    symbols:
      - TQQQ
    params:
      lookback_period: 20
      threshold: 0.05
```

## 技术信号策略

`TechnicalSignalSource`（`src/trading/signal_generator.py`）提供基于内置技术指标的信号生成，支持：
- **SMA 均线**: `_compute_sma()` 简单移动平均
- **RSI**: `_compute_rsi()` 相对强弱指标
- **成交量突破**: `_compute_volume_breakout_ratio()` 量比计算

## AI 信号策略

`AISignalSource` 通过 LLM 分析新闻、公告和基本面数据生成交易信号。信号格式：

```json
{
  "signals": [{
    "action": "buy",
    "reason": "突破 MA20 且放量",
    "confidence": 0.85,
    "price_target": 85.0,
    "stop_loss": 78.0
  }]
}
```

AI 信号解析由 `parse_llm_response()` 处理，包含置信度过滤和格式校验。

## 信号聚合

`SignalAggregator` 负责合并多个策略生成的信号：
1. **去重**: 同标的同方向信号合并
2. **排序**: 按置信度降序
3. **权重**: AI 信号优先级 > 技术信号
4. **过滤**: 低置信度信号丢弃（< 0.3）

## 决策信号联动

QuantWeasel 策略可以直接消费 `DecisionSignal`（来自 `src/services/decision_signal_service.py`）：

```python
from src.services.decision_signal_service import DecisionSignalService

class SignalDrivenStrategy(BaseStrategy):
    def __init__(self, config):
        super().__init__(config)
        self._signal_service = DecisionSignalService()

    def evaluate(self, quote, state, prices=None):
        signals = []
        decision_signals = self._signal_service.list_signals(
            stock_code=self.symbol, statuses={"active"}
        )
        for ds in decision_signals:
            if ds.action in ("buy", "strong_buy"):
                signals.append(Signal(
                    action="buy",
                    reason=f"DecisionSignal: {ds.reason}",
                    confidence=ds.confidence or 0.7,
                ))
        return signals
```

详见 [决策信号→交易桥接](quantweasel-architecture.md)。

## 策略测试

```bash
# 独立测试策略
python -c "from src.trading.strategy.registry import StrategyRegistry; print(StrategyRegistry.list_strategies())"

# 回测验证
python -m pytest tests/test_trading_strategy_*.py -v
```

## 最佳实践

1. **幂等性**: 策略的 `evaluate()` 不应有副作用
2. **性能**: 策略应快速执行；复杂计算放在预处理阶段
3. **日志**: 策略关键决策点记录结构化日志，便于审计回溯
4. **失效保护**: 数据缺失时返回空信号列表，不抛异常
5. **配置外部化**: 所有可调参数通过 YAML 配置暴露，不硬编码
