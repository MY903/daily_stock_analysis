# QuantWeasel 部署与配置

## 概述

QuantWeasel 支持多种部署方式：独立服务、嵌入主 API 服务、Streamlit 看板和 GitHub Actions 定时任务。

## 前置条件

1. **Tiger 开放平台账号**: https://www.tigerbrokers.com/openapi/
2. **Tiger API 配置文件**: `tiger_openapi_config.properties`
3. **TIGER_ENV 环境变量**: `SANDBOX`（模拟）或 `PROD`（实盘）
4. **飞书 Webhook URL**（可选，用于交易通知）

## 配置

### 环境变量

| 变量 | 说明 | 必填 | 默认值 |
|------|------|------|--------|
| `TRADING_MODE` | 运行模式: SANDBOX/PAPER/PROD | 否 | `SANDBOX` |
| `TIGER_ENV` | Tiger 环境: SANDBOX/PROD | 否 | `SANDBOX` |
| `TIGER_CONFIG_PATH` | Tiger 凭证文件路径 | 否 | `tiger_openapi_config.properties` |
| `FEISHU_WEBHOOK_URL` | 飞书通知 Webhook | 否 | - |
| `ENABLE_TRADING` | 是否启用交易 API | 否 | `false` |

### 配置文件

创建 `config/trading.yaml`：

```yaml
tiger:
  config_path: "tiger_openapi_config.properties"

trading:
  auto_trade: false
  default_quantity: 35
  max_positions: 5

risk:
  max_position_pct: 0.2
  max_daily_loss_pct: 0.03
  min_trade_interval: 86400

strategies:
  tqqq_swing:
    enabled: true
    symbols:
      - TQQQ
  ma_crossover:
    enabled: true
    symbols:
      - TQQQ
      - QQQ
      - SPY
```

## 部署方式

### 方式 1: 独立服务

```bash
# 启动独立交易服务（端口 8001）
python trading_server.py

# 指定配置
python trading_server.py --config config/trading.yaml

# 试运行
python trading_server.py --dry-run
```

### 方式 2: 嵌入主 API 服务

在 `.env` 中设置 `ENABLE_TRADING=true`，交易路由自动挂载到 `/api/v1/trading/`：

```bash
python main.py --serve
# 或
uvicorn server:app --host 0.0.0.0 --port 8000
```

### 方式 3: Streamlit 看板

```bash
cd streamlit_app
streamlit run app.py --server.port 8501
```

Streamlit 看板提供 6 个页面：Dashboard / Trading / RiskConfig / Strategy / Settings / Logs。

### 方式 4: 命令行

```bash
# 生成盘前信号
python -c "
from src.trading.pipeline import QuantWeaselPipeline
import asyncio
asyncio.run(QuantWeaselPipeline().run_pre_market())
"

# 检查状态
python trading_main.py --status
```

## Docker 部署

建议使用主服务的 Docker 镜像，通过环境变量启用交易模块：

```yaml
# docker-compose.yml
version: "3.8"
services:
  dsa:
    image: zhulinsen/daily_stock_analysis:latest
    ports:
      - "8000:8000"
    environment:
      - ENABLE_TRADING=true
      - TRADING_MODE=SANDBOX
      - TIGER_ENV=SANDBOX
    volumes:
      - ./tiger_openapi_config.properties:/app/tiger_openapi_config.properties
      - ./config/trading.yaml:/app/config/trading.yaml
```

## 生产环境检查清单

- [ ] Tiger API 凭证配置正确（SANDBOX 测试通过）
- [ ] `TRADING_MODE` 和 `TIGER_ENV` 环境变量设置正确
- [ ] 风控参数（仓位/亏损/频次）按风险偏好调整
- [ ] 飞书 Webhook 通知测试通过
- [ ] 运行时策略 YAML 不为空
- [ ] `daily_loss.db` 和 `logs/` 目录可写
- [ ] 首次在 SANDBOX 模式运行至少一个交易日验证
- [ ] 确认 ENABLE_TRADING 与主服务路由不冲突

## 升级与回滚

### 升级步骤

1. 停止交易服务
2. 拉取最新代码
3. 检查 `CHANGELOG.md` 中 QuantWeasel 相关变更
4. 运行迁移脚本（如有）
5. 在 SANDBOX 模式启动验证
6. 切换到 PROD 模式

### 回滚

```bash
# 回滚代码
git revert HEAD~1

# 恢复配置备份
cp config/trading.yaml.bak config/trading.yaml

# 基于备份重启
python trading_server.py
```
