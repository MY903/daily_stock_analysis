# TQQQ 自动化波段交易机器人 — 产品需求文档（PRD）

> **用途**：将此文档直接复制给 AI Coding 工具（Cursor / Claude Code / Trae / Windsurf 等），作为开发需求的唯一输入源。
> **作者**：用户委托 QoderWork 整理
> **日期**：2026-05-13
> **版本**：v1.0

---

## 一、项目概述

开发一个基于 **Tiger Brokers（老虎证券）OpenAPI** 的自动化交易机器人，专用于标的 **TQQQ（纳斯达克100三倍做多ETF）** 的隔夜波段交易。

机器人核心目标：
- **自动监控** TQQQ 实时价格
- **自动检测** 买入/止盈/止损信号
- **推送通知** 到飞书/钉钉/企业微信机器人
- **可选自动下单**（支持"提醒模式"与"自动交易模式"一键切换）
- **无人值守运行**，支持断线重连与异常恢复

**用户现状**：
- 券商：Tiger Trade（老虎证券）综合账户
- 本金：约 $3,825 USD（3万港币已换汇）
- 标的：TQQQ（当前价约 $76.75）
- T+0 无限制，但优先做隔夜波段（买入后持仓过夜，第二天或第三天触发卖出）

---

## 二、核心功能需求

### 2.1 实时行情监控

- 使用 **Tiger OpenAPI PushClient（WebSocket）** 订阅 TQQQ 实时行情
- 订阅字段：`latestPrice`, `bidPrice`, `askPrice`, `volume`, `latestTime`
- 推送频率：行情变动即推送（无需轮询）
- 盘前/盘后数据也需要接收（TQQQ 盘前盘后流动性足够）
- **断线重连**：PushClient 断开后自动重连，重连后自动重新订阅

### 2.2 交易状态机

机器人内部维护一个状态机，状态如下：

| 状态 | 含义 | 行为 |
|---|---|---|
| `IDLE` | 空仓，等待买入触发 | 监控价格是否 ≤ 买入触发价 |
| `BUY_PENDING` | 买入限价单已提交，等待成交 | 监控订单状态 |
| `HOLDING` | 持仓中，等待止盈或止损 | 同时监控止盈价和止损价 |
| `SELL_PENDING` | 卖出限价单已提交，等待成交 | 监控订单状态 |
| `COOLDOWN` | 卖出完成，进入冷静期 | 默认冷静 300 秒（5分钟），防止频繁交易，然后自动回到 `IDLE` |

状态转换图：
```
IDLE → (价格触及买入价) → BUY_PENDING → (成交) → HOLDING
HOLDING → (价格触及止盈价) → SELL_PENDING → (成交) → COOLDOWN → IDLE
HOLDING → (价格触及止损价) → SELL_PENDING → (成交) → COOLDOWN → IDLE
```

### 2.3 买入信号检测

- 触发条件：`最新价 ≤ 配置中的买入触发价`（limit_price）
- 买入方式：**限价单（LMT）**
- 买入数量：配置中的固定股数（如 35 股或 51 股）
- 有效期：`GTC`（撤销前有效，最长90天）
- 仅在美股交易时段（含盘前盘后）允许触发买入
- **防重复下单**：状态不为 `IDLE` 时，禁止再次提交买入单

### 2.4 止盈信号检测

- 触发条件：`最新价 ≥ 配置中的止盈触发价`（take_profit_price）
- 卖出方式：**限价单（LMT）**
- 卖出数量：全部持仓（与买入数量一致）
- 有效期：`GTC`
- 仅在持仓状态 `HOLDING` 时检测

### 2.5 止损信号检测

- 触发条件：`最新价 ≤ 配置中的止损触发价`（stop_loss_price）
- 卖出方式：**止损单（STP）或止损限价单（STP_LMT）**
  - 优先使用 `STP_LMT`，止损触发价 = 配置的止损价，限价 = 止损价 × 0.995（确保成交）
- 卖出数量：全部持仓
- 有效期：`GTC`
- 仅在持仓状态 `HOLDING` 时检测
- **同时挂止盈和止损**：买入成交后，机器人需要同时挂出止盈限价单和止损单。如果其中一个成交，另一个必须自动撤销（或系统会自动因无持仓而失败，需验证并处理）

### 2.6 通知系统（Webhook 推送）

当以下事件发生时，通过 **Webhook** 推送到飞书/钉钉/企业微信机器人：

| 事件 | 通知内容模板（示例） |
|---|---|
| 机器人启动 | 🟢 TQQQ 交易机器人已启动<br>标的: TQQQ<br>买入触发: $74.61<br>止盈: $77.59<br>止损: $72.20<br>模式: 自动交易/仅提醒 |
| 买入信号触发 | 📥 买入信号触发<br>触发价格: $74.61<br>当前价格: $74.55<br>买入股数: 35<br>预估金额: $2,610<br>模式: 自动下单/仅提醒 |
| 买入成交 | ✅ 买入成交<br>成交价格: $74.61<br>成交股数: 35<br>成交金额: $2,611.35<br>已挂止盈: $77.59 (+4.0%)<br>已挂止损: $72.20 (-3.2%) |
| 止盈触发 | 🎯 止盈触发<br>触发价格: $77.59<br>当前价格: $77.65 |
| 止盈成交 | ✅ 止盈成交<br>成交价格: $77.59<br>成交股数: 35<br>盈利: $104.30 (+4.0%)<br>本次收益率: +4.0% |
| 止损触发 | 🛑 止损触发<br>触发价格: $72.20<br>当前价格: $72.15 |
| 止损成交 | ⚠️ 止损成交<br>成交价格: $72.18<br>成交股数: 35<br>亏损: -$85.05 (-3.2%)<br>本次收益率: -3.2% |
| 订单异常 | ❌ 订单异常<br>订单ID: xxx<br>状态: REJECTED / CANCELLED<br>原因: xxx |
| API 断线 | 🔴 API 连接断开，正在重连... |
| API 恢复 | 🟢 API 已重连，已恢复订阅 |
| 每日收盘总结 | 📊 今日交易总结<br>交易次数: 1<br>盈亏: +$104.30<br>当前状态: IDLE/HOLDING |

**Webhook 格式**：
- 使用通用 HTTP POST，Content-Type: `application/json`
- 消息体结构：`{"msg_type": "text", "content": {"text": "..."}}`（兼容飞书）
- 同时支持钉钉和企业微信的格式切换（通过配置）

### 2.7 两种交易模式（配置切换）

通过配置文件 `config.yaml` 中的 `auto_trade: true/false` 切换：

**模式 A：自动交易模式（auto_trade: true）**
- 买入信号触发 → 自动提交买入限价单
- 买入成交 → 自动挂止盈和止损
- 止盈/止损触发 → 自动提交卖出单
- 全程无需人工干预

**模式 B：监控提醒模式（auto_trade: false）**
- 买入信号触发 → 只推送 Webhook 提醒，不自动下单
- 用户收到提醒后，手动在 Tiger Trade APP 中下单
- 买入成交后，机器人仍然自动挂止盈和止损（如果用户希望）
- 或者止盈/止损也仅提醒，不下单

> **安全默认**：首次运行默认 `auto_trade: false`，必须由用户手动改为 `true` 才开启自动下单。

### 2.8 订单状态轮询与同步

由于 WebSocket Push 的订单变动推送可能延迟或丢失，机器人需要：
- 每 30 秒通过 REST API 查询当前活跃订单列表
- 比对本地状态与远程状态，不一致时以远程为准并更新状态机
- 查询当前持仓，确认是否真实持仓

### 2.9 日志与数据记录

- 日志级别：INFO / WARN / ERROR / DEBUG
- 日志输出：同时输出到控制台和文件
- 日志文件：`logs/tqqq_bot_YYYY-MM-DD.log`，按天滚动，保留最近 30 天
- 交易记录：每次成交写入 `data/trades.csv`，字段包括：
  - `trade_id`, `symbol`, `action` (BUY/SELL), `order_type` (TP/SL/ENTRY), `price`, `quantity`, `timestamp`, `pnl`, `mode`
- 每日生成简报：`data/daily_report_YYYY-MM-DD.json`

---

## 三、交易策略配置

所有策略参数通过 `config.yaml` 配置，支持热重载（修改后自动生效，无需重启）。

```yaml
# ==================== 账户配置 ====================
tiger:
  # 方式1：配置文件路径（推荐，从老虎开发者后台下载）
  config_path: "./tiger_openapi_config.properties"
  # 方式2：直接填写（不推荐，仅测试用）
  # tiger_id: "your_tiger_id"
  # account: "your_account"
  # private_key_path: "./private_key.pem"
  
  # 账户类型：PAPER（模拟）/ LIVE（实盘）
  # 强烈建议先用 PAPER 测试至少一周
  env: "PAPER"

# ==================== 标的配置 ====================
trading:
  symbol: "TQQQ"
  market: "US"
  
  # 买入配置
  entry:
    trigger_price: 74.61        # 买入触发价（限价）
    quantity: 35                # 买入股数（建议首次不超过总资金的2/3）
    order_type: "LMT"           # 限价单
    time_in_force: "GTC"        # 撤销前有效
    
  # 止盈配置
  take_profit:
    trigger_price: 77.59        # 止盈触发价 = 74.61 * 1.04
    order_type: "LMT"           # 限价单
    time_in_force: "GTC"
    
  # 止损配置（建议 -3% 到 -3.5%，不要太大）
  stop_loss:
    trigger_price: 72.20        # 止损触发价 = 74.61 * 0.968
    order_type: "STP_LMT"       # 止损限价单
    limit_price_offset: 0.005   # 止损限价 = 触发价 * (1 - 0.005)，确保成交
    time_in_force: "GTC"

# ==================== 机器人行为配置 ====================
bot:
  # 交易模式
  auto_trade: false             # false = 仅提醒，true = 自动下单
  
  # 冷静期（秒）：卖出后等待多久才允许下一次买入
  cooldown_seconds: 300
  
  # 交易时段限制
  trading_hours:
    allow_pre_market: true      # 允许盘前交易
    allow_post_market: true     # 允许盘后交易
    # 如果设为 false，则只在常规时段 (9:30-16:00 ET) 交易

# ==================== 通知配置 ====================
notification:
  enabled: true
  # 飞书机器人 Webhook URL
  webhook_url: "https://open.feishu.cn/open-apis/bot/v2/hook/xxxxxxxx"
  # 消息格式：feishu / dingtalk / wecom
  platform: "feishu"

# ==================== 日志配置 ====================
logging:
  level: "INFO"
  log_dir: "./logs"
  data_dir: "./data"
```

**参数计算逻辑（代码中需实现）**：
- 止盈价 = 买入触发价 × (1 + 止盈比例)
- 止损价 = 买入触发价 × (1 - 止损比例)
- 建议默认参数（用户可覆盖）：
  - 买入跌幅：-2.8%（从当前市价回落）
  - 止盈涨幅：+4.0%
  - 止损跌幅：-3.2%

---

## 四、技术架构

### 4.1 技术栈

- **语言**：Python 3.10+
- **核心依赖**：
  - `tigeropen>=3.4.8`（老虎官方SDK）
  - `pyyaml`（配置解析）
  - `requests`（Webhook 通知）
  - `schedule`（定时任务：日志滚动、每日报告、状态同步）
- **可选依赖**：
  - `loguru`（更友好的日志，推荐）
  - `pandas`（交易数据分析）
  - `rich`（控制台美化输出）

### 4.2 代码目录结构

```
tqqq-trading-bot/
├── main.py                   # 入口文件
├── config.yaml               # 用户配置文件（需手动填写）
├── requirements.txt          # Python 依赖
├── README.md                 # 使用说明
│
├── tiger_openapi_config.properties  # 老虎 API 配置文件（从开发者后台下载）
├── private_key.pem           # RSA 私钥（从开发者后台下载）
│
├── src/
│   ├── __init__.py
│   ├── bot.py                # 核心机器人逻辑（状态机）
│   ├── config_loader.py      # 配置加载与热重载
│   ├── tiger_client.py       # 老虎 API 封装（QuoteClient + TradeClient + PushClient）
│   ├── order_manager.py      # 订单管理（下单、撤单、查单、持仓查询）
│   ├── strategy.py           # 交易策略逻辑（信号检测）
│   ├── state_machine.py      # 状态机实现
│   ├── notifier.py           # Webhook 通知模块
│   ├── logger.py             # 日志配置
│   └── trade_recorder.py     # 交易记录与 CSV 持久化
│
├── logs/                     # 日志目录（运行时生成）
├── data/                     # 数据目录（trades.csv, daily_report.json）
└── tests/                    # 单元测试（可选）
    └── test_strategy.py
```

### 4.3 核心类设计

```python
class TQQQTradingBot:
    """核心机器人"""
    def __init__(self, config: dict):
        self.state = BotState.IDLE
        self.tiger = TigerAPIClient(config["tiger"])
        self.strategy = TradingStrategy(config["trading"])
        self.order_mgr = OrderManager(self.tiger)
        self.notifier = Notifier(config["notification"])
        self.recorder = TradeRecorder(config["logging"]["data_dir"])
        
    def on_price_update(self, quote: dict):
        """WebSocket 价格更新回调"""
        price = quote["latest_price"]
        self.check_signals(price)
        
    def check_signals(self, price: float):
        """检测买卖信号"""
        if self.state == BotState.IDLE:
            if price <= self.strategy.entry_price:
                self.handle_buy_signal(price)
        elif self.state == BotState.HOLDING:
            if price >= self.strategy.take_profit_price:
                self.handle_sell_signal(price, reason="TAKE_PROFIT")
            elif price <= self.strategy.stop_loss_price:
                self.handle_sell_signal(price, reason="STOP_LOSS")
                
    def handle_buy_signal(self, price: float):
        """处理买入信号"""
        self.notifier.send(f"📥 买入信号触发: {price}")
        if self.config["bot"]["auto_trade"]:
            order = self.order_mgr.place_buy_order(...)
            self.state = BotState.BUY_PENDING
        
    def handle_sell_signal(self, price: float, reason: str):
        """处理卖出信号"""
        self.notifier.send(f"{'🎯' if reason=='TAKE_PROFIT' else '🛑'} 卖出信号触发: {price}")
        if self.config["bot"]["auto_trade"]:
            order = self.order_mgr.place_sell_order(reason=reason, ...)
            self.state = BotState.SELL_PENDING
```

---

## 五、部署方案推荐

### 方案 1：本地 Windows 电脑（最简单，零成本）

**适用**：有闲置电脑/笔记本可以晚上不关机。

**步骤**：
1. 安装 Python 3.10+
2. `pip install -r requirements.txt`
3. 填写 `config.yaml` 和老虎 API 配置文件
4. 运行 `python main.py`
5. 用 Windows 任务计划程序或 `pythonw` 后台运行

**缺点**：电脑必须24小时开机，断网/断电会中断。

### 方案 2：云服务器 VPS（最稳定，推荐）

**适用**：没有闲置电脑，或希望稳定运行。

**推荐配置**：
- 阿里云/腾讯云/华为云 **轻量应用服务器**
- 配置：1核2G 或 2核2G（足够）
- 系统：Ubuntu 22.04 LTS
- 费用：约 100-200 元/年（新用户首年通常 99 元）
- 带宽：3Mbps 足够

**部署步骤**：
1. 购买服务器，选择 Ubuntu 22.04
2. SSH 登录服务器
3. 安装 Python、pip、git
4. `git clone` 项目代码
5. `pip install -r requirements.txt`
6. 用 `systemd` 或 `supervisor` 配置后台服务
7. 用 `nohup` 或 `screen` 临时运行调试

**systemd 服务文件示例**（代码中需提供）：
```ini
[Unit]
Description=TQQQ Trading Bot
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/tqqq-trading-bot
ExecStart=/usr/bin/python3 /home/ubuntu/tqqq-trading-bot/main.py
Restart=always
RestartSec=10
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

### 方案 3：Docker 部署（可选，进阶）

提供 `Dockerfile` 和 `docker-compose.yml`，方便迁移和复现环境。

---

## 六、安全与风控约束（强制要求）

以下约束必须在代码中硬编码或强制校验，不可通过配置绕过：

1. **默认模拟账户**：首次运行必须检测 `env: PAPER`，如果用户配置了 `LIVE` 且 `auto_trade: true`，必须在启动时弹出警告并要求用户输入确认码（如键入 "CONFIRM_LIVE"）才能继续。

2. **最大亏损限制**：单次交易亏损不得超过本金的 5%。如果止损比例配置导致潜在亏损 > 5%，启动时报错拒绝运行。

3. **防重复下单**：同一信号在 60 秒内只触发一次，防止网络抖动或价格抖动导致重复提交订单。

4. **持仓校验**：提交卖出单前，必须通过 REST API 查询当前真实持仓，确认有足量持仓才允许下单。

5. **自动撤销失效单**：启动时检查所有历史 GTC 订单，如果有与当前策略不相关的残留订单，自动撤销（避免手动在 APP 里下单后机器人状态混乱）。

6. **通知必达**：如果 Webhook 推送失败（HTTP 非 200），必须记录到日志并每 60 秒重试，最多重试 5 次。

7. **只读模式可切换**：`TIGERMCP_READONLY` 环境变量或配置项为 `true` 时，禁止调用任何下单/撤单 API。

---

## 七、老虎 API 前置准备（用户需先行完成）

代码开发完成后，用户需要自行完成以下步骤才能运行：

1. **开通老虎 API 权限**
   - 访问 https://developer.itigerup.com/profile
   - 使用老虎账户登录
   - 激活 OpenAPI 权限
   - 下载配置文件 `tiger_openapi_config.properties` 和 RSA 私钥

2. **获取 Webhook URL**
   - 飞书：在飞书群设置中添加自定义机器人，复制 Webhook URL
   - 钉钉/企业微信：类似操作

3. **修改配置**
   - 将下载的配置文件放入项目根目录
   - 复制 `config.example.yaml` 为 `config.yaml`
   - 填写 Webhook URL、策略参数、账户类型（先填 PAPER）

4. **测试运行**
   - 先以 `auto_trade: false` 运行一天，观察通知是否正常触发
   - 确认无误后，再切换为 `auto_trade: true` 和 `env: LIVE`

---

## 八、验收标准

AI Coding 工具交付的代码需满足以下最低标准：

- [ ] 能通过 `pip install -r requirements.txt` 一键安装依赖
- [ ] 能通过 `python main.py` 一键启动
- [ ] 启动时正确加载 `config.yaml` 和老虎 API 配置
- [ ] WebSocket 连接成功并持续接收 TQQQ 实时报价
- [ ] 状态机正确运转：IDLE → BUY_PENDING → HOLDING → SELL_PENDING → COOLDOWN → IDLE
- [ ] 买入/止盈/止损信号触发时，正确推送 Webhook 消息
- [ ] `auto_trade: false` 时只推送提醒，不下单
- [ ] `auto_trade: true` 时能正确提交限价单/止损限价单
- [ ] 买入成交后，能正确挂出止盈和止损两个子单
- [ ] 断线后能自动重连并恢复订阅
- [ ] 所有交易记录正确写入 `data/trades.csv`
- [ ] 日志文件正确按天滚动
- [ ] 提供 `README.md` 说明如何配置和运行
- [ ] 提供 systemd 服务文件和 Docker 支持（可选但推荐）

---

## 九、给 AI Coding 工具的额外提示

1. **优先使用模拟账户（PAPER）开发和测试**，所有默认配置必须指向模拟账户。
2. **错误处理要完善**：老虎 API 可能返回各种异常（连接超时、订单被拒、持仓不足等），每个 API 调用都必须有 try-except 包裹并记录到日志。
3. **不要过度工程化**：用户本金只有 $3,800，代码应该简洁、易读、易维护，不要引入复杂的机器学习或高频交易逻辑。
4. **配置即代码**：所有可调整参数都放到 `config.yaml`，不要在 Python 代码里写死数字。
5. **日志要友好**：控制台输出用中文，包含当前状态、最新价、距离触发价还有百分之几等关键信息，方便用户一眼看懂机器人在干什么。

---

*此 PRD 由 QoderWork 根据用户实际需求整理生成，可直接复制给任意 AI Coding 工具使用。*
