# TQQQ 自动交易机器人部署指南

## 概述

基于 Tiger Brokers OpenAPI 的 TQQQ 短线摆动交易机器人，支持：
- 实时行情监控（WebSocket）
- 状态机驱动的买入/止盈/止损策略
- 飞书 Webhook 通知
- 模拟盘/实盘环境切换
- Docker 部署到群晖 NAS

## 前置条件

1. **Tiger 开放平台账号**：https://developer.itigerup.com/
2. **Tiger OpenAPI 配置文件**：`tiger_openapi_config.properties`（包含 tiger_id、account、private_key）
3. **飞书机器人 Webhook URL**（用于通知）
4. **Docker 环境**（群晖 NAS 或其他 Linux 主机）

## 快速开始

### 1. 准备配置文件

```bash
# 复制配置模板
cp config/trading.yaml.example config/trading.yaml

# 编辑配置（填入实际参数）
vi config/trading.yaml
```

关键配置项：
- `tiger.config_path`：Tiger API 配置文件路径
- `tiger.environment`：`PAPER`（模拟盘）或 `LIVE`（实盘）
- `trading.auto_trade`：`false`（仅通知）或 `true`（自动交易）
- `trading.entry.trigger_price`：买入触发价
- `notification.webhook_url`：飞书 Webhook URL

### 2. 放置 Tiger 凭证

将 `tiger_openapi_config.properties` 放在项目根目录（或 `config/` 下），内容格式：

```properties
tiger_id=20159275
account=66002790
private_key_pk8=MIIEvgIB...（PKCS#8 格式私钥）
license=TBHK
```

### 3. 本地试运行

```bash
# 安装依赖
pip install -r requirements.txt

# 试运行（验证 API 连接）
python trading_main.py --dry-run

# 查看当前状态
python trading_main.py --status

# 正式启动
python trading_main.py
```

### 4. Docker 部署（推荐）

```bash
# 在项目根目录执行
docker-compose -f docker/docker-compose.yml up -d trading-bot

# 查看日志
docker logs -f tqqq-trading-bot

# 停止
docker-compose -f docker/docker-compose.yml stop trading-bot
```

## 群晖 NAS 部署

### 方式一：Docker Compose（推荐）

1. SSH 登录群晖
2. 将代码拉取到 NAS（如 `/volume1/docker/daily_stock_analysis/`）
3. 准备 `config/trading.yaml` 和 `tiger_openapi_config.properties`
4. 执行：

```bash
cd /volume1/docker/daily_stock_analysis
docker-compose -f docker/docker-compose.yml up -d trading-bot
```

### 方式二：Container Manager 图形界面

1. 打开群晖 Container Manager
2. 注册表 → 搜索并下载 `python:3.10-slim`
3. 使用 `docker/Dockerfile.trading` 构建自定义镜像
4. 创建容器，挂载 `config/`、`logs/`、`data/` 目录

## 运行模式

### Alert-Only 模式（默认）

```yaml
trading:
  auto_trade: false
```

机器人监控行情并在信号触发时发送飞书通知，不自动下单。适合初期验证策略。

### 自动交易模式

```yaml
trading:
  auto_trade: true
```

机器人自动下单。切换到实盘时启动会要求输入确认码。

## 状态机

```
IDLE → BUY_PENDING → HOLDING → SELL_PENDING → COOLDOWN → IDLE
```

- **IDLE**：空仓等待买入信号
- **BUY_PENDING**：买入单已提交，等待成交
- **HOLDING**：持仓中，监控止盈/止损
- **SELL_PENDING**：卖出单已提交，等待成交
- **COOLDOWN**：冷却期（默认 300 秒）

状态持久化到 `data/trading_state.json`，进程重启后自动恢复。

## 安全机制

1. 默认模拟盘环境
2. 默认 alert-only 模式
3. 实盘 + 自动交易需输入确认码
4. 防重复下单（同信号 60 秒冷却）
5. 卖出前校验实际持仓
6. 启动时清理过期 GTC 挂单
7. WebSocket 断线自动重连

## 文件说明

```
src/trading/
├── __init__.py
├── bot.py              # TradingBot 主类
├── config.py           # 配置加载
├── tiger_client.py     # Tiger API 封装
├── state_machine.py    # 状态机
├── order_manager.py    # 订单管理
├── monitor.py          # WebSocket 行情监控
├── notifier.py         # 飞书通知
├── trade_recorder.py   # 交易记录（CSV）
└── strategy/
    ├── base.py         # 策略基类
    └── tqqq_swing.py   # TQQQ 摆动策略
```

## 日志与数据

- 日志：`logs/tqqq_bot_YYYY-MM-DD.log`
- 交易记录：`data/trades.csv`
- 状态文件：`data/trading_state.json`
- 每日报告：`data/daily_report_YYYY-MM-DD.json`

## 常见问题

### Token 过期

Tiger Token 有有效期（通常 30 天），过期后需要在开放平台刷新：
https://developer.itigerup.com/profile

### WebSocket 频繁断线

检查网络稳定性，机器人内置自动重连机制（最多 50 次尝试）。

### 如何切换到实盘

1. 修改 `config/trading.yaml`：`tiger.environment: "LIVE"`
2. 修改 `tiger_openapi_config.properties` 中的 `env: PROD`
3. 设置 `trading.auto_trade: true`
4. 启动时输入确认码 `CONFIRM`
