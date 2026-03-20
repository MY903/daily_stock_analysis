# T+0 选股池周度任务 - 快速参考卡片

## 🚀 快速开始（3 步完成配置）

### Step 1: 配置环境变量

编辑 `.env` 文件，确保已配置：

```bash
# 飞书机器人 Webhook（必填，用于推送通知）
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx

# Tushare Token（必填，用于获取股票数据）
TUSHARE_TOKEN=your_tushare_token_here
```

### Step 2: 安装依赖

```bash
cd /home/dministrator/workspaces/stock_analysis/daily_stock_analysis
pip install schedule pandas numpy requests python-dotenv
```

### Step 3: 部署服务

```bash
# 安装 systemd 服务（每周一 9:00 自动运行）
sudo ./scripts/setup-t0-weekly-service.sh install

# 查看服务状态
sudo ./scripts/setup-t0-weekly-service.sh status
```

---

## 📋 常用管理命令

```bash
# 查看服务状态
sudo systemctl status t0-weekly-screener

# 查看实时日志
sudo journalctl -u t0-weekly-screener -f

# 手动触发一次（带飞书通知）
python scripts/t0_stock_screener.py --notify

# 停止服务
sudo systemctl stop t0-weekly-screener

# 重启服务
sudo systemctl restart t0-weekly-screener

# 卸载服务
sudo ./scripts/setup-t0-weekly-service.sh uninstall
```

---

## ⏰ 修改执行时间

### 方式 A: 修改 systemd 服务

编辑服务文件：
```bash
sudo nano /etc/systemd/system/t0-weekly-screener.service
```

修改 `ExecStart` 行：
```ini
# 改为每周五 15:30 运行
ExecStart=/usr/bin/python3 -m scripts.t0_weekly_scheduler --weekday friday --time 15:30
```

重新加载并重启：
```bash
sudo systemctl daemon-reload
sudo systemctl restart t0-weekly-screener
```

### 方式 B: 使用 Crontab（替代方案）

```bash
crontab -e
```

添加一行（例如每周一 9:00）：
```bash
0 9 * * 1 cd /home/dministrator/workspaces/stock_analysis/daily_stock_analysis && \
    /usr/bin/python3 scripts/t0_stock_screener.py --notify >> logs/t0_screener.log 2>&1
```

---

## 🔧 自定义筛选条件

编辑 `scripts/t0_stock_screener.py` 文件：

```python
# 振幅范围（默认 2.5% ~ 4.0%）
AMP_LOW = 2.5        # 降低可筛选更活跃的股票
AMP_HIGH = 4.0       # 提高可放宽上限

# 年涨幅限制（默认 ≤ 20%）
YEAR_RETURN_MAX = 20.0  # 提高可选入更多底部股票

# 股价范围（默认 5 ~ 30 元）
PRICE_MIN = 5.0
PRICE_MAX = 30.0

# 流动性要求
MIN_AVG_TURNOVER = 50.0  # 降低可纳入更小盘股票
MIN_AVG_VOLUME = 8_000_000

# 振幅稳定性（默认 ≤ 0.6）
AMP_CV_MAX = 0.6  # 提高可筛选更稳定的股票

# 距离新高（默认 ≥ 10%）
MIN_DISTANCE_FROM_HIGH = 10.0  # 提高确保更靠近底部
```

修改后测试运行：
```bash
python scripts/t0_stock_screener.py --notify
```

---

## 📊 输出示例

### 飞书消息预览

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

...

---
📄 **完整清单已保存至**: data/t0_stock_pool.csv
💡 **提示**: 以上股票仅供研究参考，不构成投资建议
```

### CSV 文件位置

```
/home/dministrator/workspaces/stock_analysis/daily_stock_analysis/data/t0_stock_pool.csv
```

包含字段：
- ts_code: 股票代码
- name: 股票名称
- industry: 所属行业
- latest_price: 最新股价
- avg_amplitude: 平均振幅
- amp_cv: 振幅变异系数
- year_return: 年收益率
- distance_from_high: 距离新高百分比
- avg_turnover_wan: 日均成交额（万元）
- avg_volume: 日均成交量

---

## 🐛 故障排查

### 问题 1: 服务未运行

```bash
# 检查状态
sudo systemctl status t0-weekly-screener

# 如果失败，查看日志
sudo journalctl -u t0-weekly-screener -n 50
```

常见错误：
- Python 路径错误 → 修改 `which python3`
- 工作目录错误 → 修改为项目绝对路径
- 依赖缺失 → 运行 `pip install schedule pandas numpy requests python-dotenv`

### 问题 2: 飞书通知未收到

检查步骤：
```bash
# 1. 检查 .env 配置
grep FEISHU_WEBHOOK_URL .env

# 2. 测试运行
python scripts/t0_stock_screener.py --notify

# 3. 查看日志中的发送状态
sudo journalctl -u t0-weekly-screener | grep -i feishu
```

### 问题 3: Tushare 数据获取失败

```bash
# 1. 检查 Token
grep TUSHARE_TOKEN .env

# 2. 验证 Token 有效性（需要 2000 积分）
# 访问 https://tushare.pro/user/token

# 3. 测试查询
python -c "import requests; r = requests.post('http://api.tushare.pro', json={'api_name': 'daily', 'token': 'YOUR_TOKEN', 'params': {'ts_code': '000001.SZ', 'trade_date': '20260120'}}); print(r.text)"
```

### 问题 4: 选股结果为空

可能原因：
1. 筛选条件过严 → 调整参数（见"自定义筛选条件"）
2. 市场整体波动率低 → 正常现象，等待下周
3. 数据源问题 → 检查 Tushare 积分是否足够

调试方法：
```bash
# 查看详细日志
python scripts/t0_stock_screener.py --notify 2>&1 | tee /tmp/screener.log

# 查看各阶段筛选结果
grep "\[Filter\]" /tmp/screener.log
```

---

## 📅 推荐执行时间

| 时间 | Cron 表达式 | 说明 |
|------|------------|------|
| 周一 9:00 | `0 9 * * 1` | 周一开盘前，适合周末复盘选股 ✅ |
| 周一 12:00 | `0 12 * * 1` | 周一中午休市，有充足时间分析 |
| 周五 15:30 | `30 15 * * 5` | 周五收盘后，适合周末持仓分析 |
| 周六 10:00 | `0 10 * * 6` | 周六上午，周末充分研究时间 |
| 周日 20:00 | `0 20 * * 0` | 周日晚间，为下周一做准备 ✅ |

**推荐**: 周一 9:00 或 周日 20:00

---

## 🔗 相关资源

- **完整文档**: [docs/t0-weekly-screener-config.md](docs/t0-weekly-screener-config.md)
- **选股策略说明**: [scripts/t0_stock_screener.py](scripts/t0_stock_screener.py)
- **调度器源码**: [scripts/t0_weekly_scheduler.py](scripts/t0_weekly_scheduler.py)
- **部署脚本**: [scripts/setup-t0-weekly-service.sh](scripts/setup-t0-weekly-service.sh)

---

## 💡 最佳实践

1. **首次部署建议**: 先用 crontab 测试一周，确认稳定后再用 systemd
2. **监控提醒**: 可以配置额外通知渠道（邮件、PushPlus 等），确保任务正常运行
3. **定期回顾**: 每月检查一次选股效果，必要时调整筛选参数
4. **备份配置**: 将 `.env` 文件和自定义配置备份到安全位置
5. **日志轮转**: 定期清理旧日志，避免磁盘占用过大

```bash
# 示例：日志轮转配置（/etc/logrotate.d/t0-weekly-screener）
/var/log/syslog {
    weekly
    rotate 4
    compress
    delaycompress
    missingok
    notifempty
}
```

---

**最后更新**: 2026-01-20  
**维护者**: dministrator
