# T+0 选股池周度任务配置说明

## 📋 功能概述

该脚本用于每周自动运行 T+0 选股筛选器，并通过飞书机器人推送选股结果。

**默认执行时间**：每周一上午 9:00（可自定义）

---

## 🔧 配置步骤

### 1. 环境准备

确保已安装必要的依赖：

```bash
pip install schedule pandas numpy requests python-dotenv
```

### 2. 配置飞书 Webhook

在 `.env` 文件中配置飞书机器人 Webhook URL：

```bash
# .env 文件
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

**如何获取飞书 Webhook URL**：
1. 打开飞书群聊 → 右上角设置 → 添加机器人 → 自定义机器人
2. 复制 Webhook 地址
3. 粘贴到 `.env` 文件中

### 3. 配置 Tushare Token

确保 `.env` 文件中已配置 Tushare API Token：

```bash
TUSHARE_TOKEN=your_tushare_token_here
```

**如何获取 Tushare Token**：
1. 访问 https://tushare.pro
2. 注册账号并获取个人 Token
3. 需要 2000 积分才能使用日线行情数据（可通过签到或捐赠获得）

---

## 🚀 运行方式

### 方式一：直接运行（测试用）

```bash
# 立即执行一次选股任务（带飞书通知）
python scripts/t0_stock_screener.py --notify

# 仅运行选股任务（不发送通知）
python scripts/t0_stock_screener.py
```

### 方式二：作为后台服务运行（推荐）

使用 systemd 在服务器上持续运行定时任务：

#### 1. 创建 systemd 服务文件

```bash
sudo nano /etc/systemd/system/t0-weekly-screener.service
```

内容如下（根据实际情况修改路径）：

```ini
[Unit]
Description=T+0 Stock Screener Weekly Scheduler
After=network.target

[Service]
Type=simple
User=your_username
Group=your_username
WorkingDirectory=/home/dministrator/workspaces/stock_analysis/daily_stock_analysis
Environment="PATH=/usr/bin:/usr/local/bin"
ExecStart=/usr/bin/python3 -m scripts.t0_weekly_scheduler --weekday monday --time 09:00
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=t0-weekly-screener

[Install]
WantedBy=multi-user.target
```

**注意修改项**：
- `User`: 你的用户名（运行 `whoami` 查看）
- `WorkingDirectory`: 项目根目录的绝对路径
- `ExecStart`: Python 解释器的绝对路径（运行 `which python3` 查看）

#### 2. 启动服务

```bash
# 重新加载 systemd 配置
sudo systemctl daemon-reload

# 启用服务（开机自启）
sudo systemctl enable t0-weekly-screener

# 启动服务
sudo systemctl start t0-weekly-screener

# 查看服务状态
sudo systemctl status t0-weekly-screener

# 查看日志
sudo journalctl -u t0-weekly-screener -f

# 停止服务
sudo systemctl stop t0-weekly-screener

# 禁用服务
sudo systemctl disable t0-weekly-screener
```

### 方式三：使用 Crontab（替代方案）

如果不想让程序一直运行，可以使用 crontab 每周触发一次：

```bash
crontab -e
```

添加以下行（每周一 9:00 执行）：

```bash
# T+0 选股池周度任务（每周一 9:00）
0 9 * * 1 cd /home/dministrator/workspaces/stock_analysis/daily_stock_analysis && \
    /usr/bin/python3 scripts/t0_stock_screener.py --notify >> logs/t0_screener.log 2>&1
```

**Cron 时间格式参考**：
```
分 时 日 月 周  命令
|  |  |  |  |
|  |  |  |  +---- 星期 (0-7, 0 和 7 都代表周日)
|  |  |  +------- 月份 (1-12)
|  |  +---------- 日期 (1-31)
|  +------------- 小时 (0-23)
+---------------- 分钟 (0-59)
```

**常用时间配置**：
- 每周一 9:00: `0 9 * * 1`
- 每周五 18:00: `0 18 * * 5`
- 每天 9:30: `30 9 * * *`
- 每月 1 号 9:00: `0 9 1 * *`

---

## ⚙️ 调度参数配置

### 修改执行时间

编辑 systemd 服务文件或 crontab，修改 `--weekday` 和 `--time` 参数：

```bash
# 可用的 weekday 值：
monday      # 周一
tuesday     # 周二
wednesday   # 周三
thursday    # 周四
friday      # 周五
saturday    # 周六
sunday      # 周日

# time 格式：HH:MM (24 小时制)
# 示例：
# 09:00  -> 上午 9 点
# 14:30  -> 下午 2 点 30 分
# 20:00  -> 晚上 8 点
```

**常见时间参考（北京时间）**：

| 时间 | 描述 | weekday | time |
|------|------|---------|------|
| 周一 9:00 | 周一开盘前 | monday | 09:00 |
| 周一 12:00 | 周一中午休市 | monday | 12:00 |
| 周五 15:30 | 周五收盘后 | friday | 15:30 |
| 周六 10:00 | 周六上午 | saturday | 10:00 |
| 周日 20:00 | 周日晚间 | sunday | 20:00 |

---

## 📊 输出结果

### 1. 飞书消息示例

飞书机器人会推送如下格式的周报：

```
## 📊 T+0 选股池周报
**生成时间**: 2026-01-20 09:00

### 📈 筛选统计
- **入选股票数量**: 25 只
- **平均振幅**: 3.15%
- **平均股价**: 12.50 元
- **平均年化收益**: 5.23%
- **覆盖行业数**: 18 个

### 🎯 筛选条件
- 振幅范围：2.5% ~ 4.0%
- 年涨幅限制：≤ 20%
- 股价范围：5 ~ 30 元
- 最小日均量：≥ 800 万股
- 最小日均成交额：≥ 50 百万

### 🏆 优选标的（Top 15）

**某某股份 (000123)**
- 行业：制造业
- 股价：15.20 元
- 平均振幅：3.25%
- 年收益：8.50%
- 振幅稳定性：0.450

...（更多股票）

---
📄 **完整清单已保存至**: data/t0_stock_pool.csv
💡 **提示**: 以上股票仅供研究参考，不构成投资建议
```

### 2. CSV 文件

完整选股结果保存在 `data/t0_stock_pool.csv`，包含所有通过筛选的股票详细数据。

---

## 🔍 故障排查

### 查看日志

**systemd 方式**：
```bash
# 查看最近 100 行日志
sudo journalctl -u t0-weekly-screener -n 100

# 实时跟踪日志
sudo journalctl -u t0-weekly-screener -f

# 查看今天的日志
sudo journalctl -u t0-weekly-screener --since today
```

**Crontab 方式**：
```bash
# 查看日志文件
tail -f logs/t0_screener.log
```

### 常见问题

**Q1: 飞书通知未收到？**
- 检查 `.env` 中的 `FEISHU_WEBHOOK_URL` 是否正确
- 确认飞书机器人已在群聊中启用
- 查看日志中是否有 "Feishu notification sent successfully" 信息

**Q2: Tushare 数据获取失败？**
- 检查 `TUSHARE_TOKEN` 是否有效
- 确认积分是否足够（需要 2000 积分）
- 查看日志中的具体错误信息

**Q3: 选股结果为空？**
- 可能是筛选条件过于严格，可以调整参数：
  - `AMP_LOW` / `AMP_HIGH`: 振幅范围
  - `YEAR_RETURN_MAX`: 年涨幅限制
  - `PRICE_MIN` / `PRICE_MAX`: 股价范围
  - `MIN_AVG_VOLUME`: 最小成交量

**Q4: 服务无法启动？**
- 检查 Python 路径是否正确：`which python3`
- 检查工作目录是否存在
- 查看 systemd 状态：`systemctl status t0-weekly-screener`

---

## 🛠️ 高级配置

### 修改筛选参数

编辑 `scripts/t0_stock_screener.py` 文件中的常量：

```python
# 振幅 filter
AMP_LOW = 2.5        # 最低振幅
AMP_HIGH = 4.0       # 最高振幅
AMP_LOOKBACK_DAYS = 30  # 回看天数

# 收益 filter
YEAR_RETURN_MAX = 20.0  # 最大年收益率

# 流动性 filter
MIN_AVG_TURNOVER = 50.0  # 最小日均成交额（百万）
MIN_AVG_VOLUME = 8_000_000  # 最小日均成交量（股）

# 价格 filter
PRICE_MIN = 5.0
PRICE_MAX = 30.0

# 振幅稳定性
AMP_CV_MAX = 0.6  # 最大变异系数

# 距离新高
MIN_DISTANCE_FROM_HIGH = 10.0  # 最小距离新高百分比
```

### 自定义通知内容

修改 `_send_feishu_notification()` 函数中的报告模板，可以自定义：
- 显示字段
- 股票数量（默认 Top 15）
- 格式样式

---

## 📝 注意事项

1. **数据源依赖**：需要有效的 Tushare Pro 账号（2000 积分）
2. **网络要求**：确保服务器能访问 Tushare API 和飞书 Webhook
3. **资源占用**：后台服务会持续运行，占用少量内存（约 50MB）
4. **磁盘空间**：确保日志目录有足够空间（建议定期清理旧日志）
5. **合规声明**：选股结果仅供研究参考，不构成投资建议

---

## 🔗 相关文档

- [完整使用指南](docs/full-guide.md)
- [飞书机器人配置](docs/bot-command.md)
- [定时任务配置](docs/full-guide.md#定时任务配置)

---

**最后更新**: 2026-01-20
