# T+0 选股池自动周报 - 部署检查清单

## ✅ 部署前检查

### 1. 环境准备

- [ ] Python 3.10+ 已安装
- [ ] 项目代码已克隆到本地
- [ ] 已进入项目目录：`cd /path/to/daily_stock_analysis`

### 2. 依赖安装

```bash
# 安装核心依赖
pip install schedule pandas numpy requests python-dotenv

# 验证安装
python -c "import schedule, pandas, numpy, requests; print('✅ 依赖安装成功')"
```

- [ ] 上述命令无报错

### 3. 环境变量配置

编辑 `.env` 文件，确保包含以下配置：

```bash
# === 必需配置 ===

# 飞书机器人 Webhook（用于推送选股结果）
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx

# Tushare Token（获取股票数据，需要 2000 积分）
TUSHARE_TOKEN=your_tushare_token_here

# === 可选配置 ===

# 调试模式（可选，建议开启便于排查问题）
DEBUG=true
```

**配置验证**：
```bash
# 检查 .env 文件是否包含必要配置
grep FEISHU_WEBHOOK_URL .env
grep TUSHARE_TOKEN .env
```

- [ ] `FEISHU_WEBHOOK_URL` 已配置且有效
- [ ] `TUSHARE_TOKEN` 已配置且有效（访问 https://tushare.pro/user/token 验证）

---

## 🚀 快速部署（3 步完成）

### Step 1: 测试运行（验证配置）

```bash
# 手动运行一次选股任务（带飞书通知）
python scripts/t0_stock_screener.py --notify
```

**预期结果**：
- ✅ 终端显示选股过程日志
- ✅ 飞书群收到机器人推送的选股报告
- ✅ `data/t0_stock_pool.csv` 文件生成

**如果失败**：
- 查看错误日志，确认是数据源问题还是通知问题
- 检查 `.env` 配置是否正确
- 确认 Tushare 积分足够（需要 2000 积分）

### Step 2: 部署 systemd 服务（推荐）

```bash
# 安装并启动 systemd 服务（每周一 9:00 自动运行）
sudo ./scripts/setup-t0-weekly-service.sh install

# 查看服务状态
sudo ./scripts/setup-t0-weekly-service.sh status
```

**预期输出**：
```
[INFO] 服务安装完成！
● t0-weekly-screener.service - T+0 Stock Screener Weekly Scheduler
     Loaded: loaded (/etc/systemd/system/t0-weekly-screener.service; enabled)
     Active: active (running) since ...
```

- [ ] 服务状态为 `active (running)`
- [ ] 下次执行时间正确（下周一 9:00）

### Step 3: 验证服务

```bash
# 查看实时日志
sudo journalctl -u t0-weekly-screener -f

# 等待或手动触发
# （或者等到下周一早上 9 点查看自动执行结果）
```

---

## 🔧 自定义配置（可选）

### 修改执行时间

**默认**: 每周一上午 9:00

**修改为其他时间**（例如每周五 15:30）：

```bash
# 1. 编辑 systemd 服务文件
sudo nano /etc/systemd/system/t0-weekly-screener.service

# 2. 修改 ExecStart 行
ExecStart=/usr/bin/python3 -m scripts.t0_weekly_scheduler --weekday friday --time 15:30

# 3. 重新加载并重启
sudo systemctl daemon-reload
sudo systemctl restart t0-weekly-screener
```

**常用时间参考**：

| 时间 | 参数 | 说明 |
|------|------|------|
| 周一 9:00 | `--weekday monday --time 09:00` | 周一开盘前选股 ✅ |
| 周一 12:00 | `--weekday monday --time 12:00` | 周一中午休市分析 |
| 周五 15:30 | `--weekday friday --time 15:30` | 周五收盘后复盘 ✅ |
| 周六 10:00 | `--weekday saturday --time 10:00` | 周末充分研究 |
| 周日 20:00 | `--weekday sunday --time 20:00` | 为下周做准备 ✅ |

### 修改筛选条件

编辑 `scripts/t0_stock_screener.py`，调整以下参数：

```python
# 振幅范围（默认 2.5% ~ 4.0%）
AMP_LOW = 2.5        # 降低可选更活跃股票
AMP_HIGH = 4.0       # 提高可放宽上限

# 年涨幅限制（默认 ≤ 20%）
YEAR_RETURN_MAX = 20.0  # 提高可选更多底部股票

# 股价范围（默认 5 ~ 30 元）
PRICE_MIN = 5.0
PRICE_MAX = 30.0

# 流动性要求
MIN_AVG_TURNOVER = 50.0  # 降低可纳入更小盘股
MIN_AVG_VOLUME = 8_000_000

# 振幅稳定性（默认 ≤ 0.6）
AMP_CV_MAX = 0.6  # 提高可筛选更稳定

# 距离新高（默认 ≥ 10%）
MIN_DISTANCE_FROM_HIGH = 10.0  # 提高可确保更靠近底部
```

**修改后测试**：
```bash
python scripts/t0_stock_screener.py --notify
```

### 使用 Crontab 替代 systemd

如果不想让程序持续运行，可以使用 crontab：

```bash
# 编辑 crontab
crontab -e

# 添加一行（每周一 9:00 执行）
0 9 * * 1 cd /home/dministrator/workspaces/stock_analysis/daily_stock_analysis && \
    /usr/bin/python3 scripts/t0_stock_screener.py --notify >> logs/t0_screener.log 2>&1
```

**优点**：
- 系统资源占用更少
- 配置简单直观
- 易于管理

**缺点**：
- 无法实时查看运行状态
- 日志需要自己管理

---

## 📊 验证结果

### 1. 检查飞书消息

打开飞书群聊，查看机器人推送的消息，应包含：

```
## 📊 T+0 选股池周报
**生成时间**: 2026-01-20 09:00

### 📈 筛选统计
- **入选股票数量**: XX 只
- **平均振幅**: X.XX%
- **平均股价**: XX.XX 元
- **平均年化收益**: X.XX%
- **覆盖行业数**: XX 个

### 🏆 优选标的（Top 15）
...
```

- [ ] 飞书消息格式正确
- [ ] 股票信息完整（至少 1 只）
- [ ] 数据统计准确

### 2. 检查 CSV 文件

```bash
# 查看文件是否存在
ls -lh data/t0_stock_pool.csv

# 查看内容（前 10 行）
head -n 10 data/t0_stock_pool.csv
```

**CSV 字段**：
- ts_code: 股票代码
- name: 股票名称
- industry: 所属行业
- latest_price: 最新股价
- avg_amplitude: 平均振幅
- amp_cv: 振幅稳定性
- year_return: 年收益率
- distance_from_high: 距离新高
- avg_turnover_wan: 日均成交额（万元）

- [ ] CSV 文件存在且有数据
- [ ] 字段完整，数据格式正确

### 3. 检查服务状态

```bash
# 查看 systemd 服务状态
sudo systemctl status t0-weekly-screener

# 查看最近一次执行日志
sudo journalctl -u t0-weekly-screener -n 50
```

**预期输出**：
```
● t0-weekly-screener.service - T+0 Stock Screener Weekly Scheduler
     Loaded: loaded (/etc/systemd/system/t0-weekly-screener.service; enabled)
     Active: active (running)
     Last log: ...
```

- [ ] 服务状态为 `active (running)`
- [ ] 日志中无 ERROR 级别错误
- [ ] 显示"定时任务执行完成"

---

## 🐛 常见问题排查

### 问题 1: 飞书通知未收到

**排查步骤**：

```bash
# 1. 检查 Webhook URL
grep FEISHU_WEBHOOK_URL .env

# 2. 测试 Webhook 是否有效
curl -X POST https://open.feishu.cn/open-apis/bot/v2/hook/xxx \
  -H "Content-Type: application/json" \
  -d '{"msg_type":"text","content":{"text":"测试消息"}}'

# 3. 手动运行选股任务
python scripts/t0_stock_screener.py --notify
```

**可能原因**：
- ❌ Webhook URL 配置错误 → 重新复制完整的 URL
- ❌ 飞书机器人被禁用 → 在飞书群启用机器人
- ❌ 网络问题 → 检查服务器能否访问外网

### 问题 2: Tushare 数据获取失败

**错误示例**：
```
RuntimeError: 积分不够，需要 2000 积分
```

**解决方案**：
1. 访问 https://tushare.pro
2. 登录账号，查看当前积分
3. 通过签到或捐赠获得 2000 积分
4. 更新 `.env` 中的 `TUSHARE_TOKEN`

**验证 Token**：
```bash
python -c "
import requests
resp = requests.post('http://api.tushare.pro', json={
    'api_name': 'daily',
    'token': 'YOUR_TOKEN',
    'params': {'ts_code': '000001.SZ', 'trade_date': '20260120'}
})
print(resp.json())
"
```

### 问题 3: 选股结果为空

**可能原因**：
1. 市场整体波动率低（正常现象）
2. 筛选条件过于严格
3. 数据质量问题

**解决方案**：
```python
# 放宽筛选条件（编辑 t0_stock_screener.py）
AMP_LOW = 2.0        # 降低下限
AMP_HIGH = 5.0       # 提高上限
YEAR_RETURN_MAX = 30.0  # 提高年收益限制
PRICE_MIN = 3.0      # 降低最低价
PRICE_MAX = 50.0     # 提高最高价
```

### 问题 4: systemd 服务无法启动

**排查步骤**：

```bash
# 1. 查看详细错误
sudo systemctl status t0-weekly-screener

# 2. 检查 Python 路径
which python3

# 3. 检查工作目录
pwd

# 4. 检查依赖
pip list | grep -E "schedule|pandas|numpy|requests"
```

**常见错误**：
- ❌ Python 路径错误 → 修改服务文件中的 `ExecStart`
- ❌ 工作目录不存在 → 确认 `WorkingDirectory` 正确
- ❌ 依赖缺失 → 运行 `pip install schedule pandas numpy requests python-dotenv`

---

## 📝 维护与监控

### 日常监控

```bash
# 每周查看一次执行日志
sudo journalctl -u t0-weekly-screener --since "Monday" --until "Tuesday"

# 实时监控（调试时使用）
sudo journalctl -u t0-weekly-screener -f
```

### 日志清理

```bash
# 清理旧日志（保留最近 4 周）
sudo journalctl --vacuum-time=4weeks

# 或者限制日志大小
sudo journalctl --vacuum-size=100M
```

### 服务管理

```bash
# 临时禁用服务（不卸载）
sudo systemctl disable t0-weekly-screener
sudo systemctl stop t0-weekly-screener

# 重新启用
sudo systemctl enable t0-weekly-screener
sudo systemctl start t0-weekly-screener

# 完全卸载
sudo ./scripts/setup-t0-weekly-service.sh uninstall
```

---

## 🎯 验收标准

部署完成后，应满足以下标准：

- [ ] 服务持续运行（`systemctl status` 显示 active）
- [ ] 每周自动执行一次（查看历史日志确认）
- [ ] 飞书准时收到选股报告
- [ ] CSV 文件每周更新
- [ ] 无明显错误或警告日志

---

## 📚 相关文档

- **完整配置指南**: [docs/t0-weekly-screener-config.md](docs/t0-weekly-screener-config.md)
- **快速参考**: [docs/T0_WEEKLY_QUICK_REFERENCE.md](docs/T0_WEEKLY_QUICK_REFERENCE.md)
- **选股策略源码**: [scripts/t0_stock_screener.py](scripts/t0_stock_screener.py)
- **调度器源码**: [scripts/t0_weekly_scheduler.py](scripts/t0_weekly_scheduler.py)

---

## 💡 下一步建议

1. **回测验证**: 使用生成的选股池进行历史回测，验证策略有效性
2. **参数优化**: 根据实际效果调整筛选参数，找到最优配置
3. **实盘跟踪**: 建立模拟组合，跟踪选股表现
4. **策略扩展**: 结合 AI 分析、大盘复盘等功能，形成完整交易体系

---

**部署时间**: 约 10 分钟  
**难度等级**: ⭐⭐☆☆☆（初级）  
**最后更新**: 2026-01-20
