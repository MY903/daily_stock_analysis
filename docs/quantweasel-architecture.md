# QuantWeasel 交易系统架构

## 概述

QuantWeasel 是 DSA 的量化交易子系统，提供从信号生成、风控审核到订单执行的全链路交易能力。支持 Tiger Brokers OpenAPI 对接，覆盖模拟盘、纸交易和实盘三种运行模式。

## 技术栈

| 组件 | 实现 |
|------|------|
| 行情驱动 | Tiger WebSocket / REST API |
| 策略引擎 | `BaseStrategy` 策略注册表 + `SignalGenerator` 信号聚合器 |
| 风控 | `RiskManager` 多维度检查（仓位/亏损/频次/价格等） |
| 执行 | `ExecutionEngine` 信号确认→下单→审计→通知闭环 |
| 审计 | `AuditLogger` 结构化日志，支持查询和回放 |
| 通知 | 飞书卡片 + `src/notifications/` 多渠道 |
| 调度 | `SignalScheduler` APScheduler 驱动（盘前/盘中） |

## 核心流水线

```
SignalGenerator        RiskManager         ExecutionEngine
  技术信号 ───→     仓位限制检查       ──→   TigerClient 下单
  AI 信号  ───→     日亏损检查        ──→   AuditLogger 记录
  聚合排序  ───→     异常价格检查      ──→   飞书卡片回调
                     冷却/频次检查            TradeRecorder
```

## 模块映射

| 文件/目录 | 职责 |
|-----------|------|
| `src/trading/pipeline.py` | `QuantWeaselPipeline` 统一入口，编排全流程 |
| `src/trading/signal.py` | 信号数据模型（`Signal`, `SignalStatus`, `SignalAction`） |
| `src/trading/signal_generator.py` | 技术指标 + AI 信号生成器、信号聚合器 |
| `src/trading/signal_scheduler.py` | APScheduler 定时任务调度 |
| `src/trading/strategy/` | 策略注册表、BaseStrategy 基类、内置策略 |
| `src/trading/risk_manager.py` | 多维度风控检查引擎 |
| `src/trading/execution.py` | `ExecutionEngine` 交易执行 |
| `src/trading/order_manager.py` | 订单状态跟踪和管理 |
| `src/trading/tiger_client.py` | Tiger Brokers OpenAPI 客户端封装 |
| `src/trading/monitor.py` | 持仓实时监控 |
| `src/trading/notifier.py` | 飞书/通知推送 |
| `src/trading/config.py` | 配置数据类（TigerConfig、EntryConfig 等） |
| `src/trading/state_machine.py` | 交易状态机（用于旧版 TradingBot） |
| `src/trading/audit_logger.py` | 结构化审计日志 |
| `src/trading/audit.py` | 审计数据模型 |
| `src/trading/trade_recorder.py` | 成交记录持久化 |
| `src/trading/loss_persistence.py` | 日亏损持久化 |
| `src/trading/card_handler.py` | 飞书卡片交互回调处理 |
| `src/trading/bot.py` | 旧版 TradingBot（已废弃） |

## 运行模式

| 模式 | `TRADING_MODE` 取值 | 行为 |
|------|----------------------|------|
| SANDBOX | `SANDBOX` | 纯模拟，不下真实订单；风控完整执行，结果记录在审计日志 |
| PAPER | `PAPER` | 纸交易，调用 Tiger 模拟环境 + 飞书通知；用于信号质量验证 |
| PROD | `PROD` | 实盘，风控检查后等待 Lark 双确认 |

## 调度体系

由 `SignalScheduler` 统一管理：
1. **盘前调度**（`PreMarketScheduler`）：开盘前生成技术指标信号
2. **盘中调度**（`IntradayScheduler`）：盘中每分钟轮询价格触发
3. **依赖**: APScheduler，未安装时自动降级为 no-op

## 数据流

```
行情/Tiger API → SignalGenerator (技术+AI)
                      ↓
              SignalAggregator (去重+排序+权重)
                      ↓
              RiskManager (8 维度检查)
                      ↓
              Lark Card 推送 → 用户确认
                      ↓
              ExecutionEngine (下单+审计+记录)
```

## 入口

- **主入口**: `trading_server.py`（独立 FastAPI 服务，端口 8001）
- **QuantWeasel 入口**: `trading_main.py`（CLI，已废弃，推荐直接调用 `QuantWeaselPipeline`）
- **Web 整合**: `api/v1/endpoints/trading.py` 挂载到主 FastAPI `/api/v1/trading/`
- **Streamlit 看板**: `streamlit_app/` 6 页仪表盘

## 故障排查

1. **风控拒绝**：检查 `RiskManager` 日志，确认仓位/亏损/频次限制
2. **连接失败**：检查 Tiger 凭证路径和环境变量 `TIGER_ENV`
3. **信号未触发**：检查 `SignalScheduler` 是否在运行，`APScheduler` 是否安装
4. **Web 不显示交易页面**：确认 `api/v1/endpoints/trading.py` 已挂载到主路由

## 相关文档

- [策略开发指南](quantweasel-strategy-dev.md)
- [风控配置说明](quantweasel-risk.md)
- [部署与配置](quantweasel-deploy.md)
- [旧版 TQQQ Bot 部署](trading-bot-setup.md)
