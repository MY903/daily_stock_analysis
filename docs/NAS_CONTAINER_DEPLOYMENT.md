# 在 Synology NAS 容器内部署 T+0 选股周报任务

## 📋 前提条件

- ✅ 群晖 NAS (192.168.3.70) 已运行 stock_analysis 容器
- ✅ 容器内已安装 Python 环境
- ✅ `.env` 文件已配置必要的 API Key

---

## 🚀 快速部署步骤

### 方式一：手动进入容器配置（推荐）

#### Step 1: SSH 登录 NAS

```bash
ssh my.sun@192.168.3.70
# 密码：MegaMingyang2023
```

#### Step 2: 进入容器

找到 stock_analysis 容器 ID：
```bash
sudo /usr/bin/docker ps | grep stock
```

进入容器：
```bash
sudo /usr/bin/docker exec -it <container_id> /bin/bash
```

或者直接进入（如果只有一个容器）：
```bash
sudo /usr/bin/docker exec -it $(sudo /usr/bin/docker ps -q --filter "ancestor=stock_analysis") /bin/bash
```

#### Step 3: 安装依赖

在容器内执行：
```bash
# 进入应用目录
cd /app || cd /volume1/docker/stock_analysis

# 安装必要的 Python 包
pip3 install schedule pandas numpy requests python-dotenv
```

#### Step 4: 测试运行

```bash
# 测试选股任务（带飞书通知）
python3 scripts/t0_stock_screener.py --notify
```

预期输出：
- ✅ 终端显示选股过程日志
- ✅ 飞书收到选股报告
- ✅ `data/t0_stock_pool.csv` 文件生成

#### Step 5: 设置定时任务

**选项 A: 使用 crontab（推荐）**

```bash
# 编辑 crontab
crontab -e
```

添加一行（每周一 9:00 执行）：
```bash
0 9 * * 1 cd /app && python3 scripts/t0_stock_screener.py --notify >> logs/t0_screener.log 2>&1
```

保存退出后验证：
```bash
crontab -l
```

**选项 B: 使用后台进程**

```bash
# 启动周度调度器（后台运行）
nohup python3 -m scripts.t0_weekly_scheduler --weekday monday --time 09:00 > logs/t0_scheduler.log 2>&1 &

# 查看进程
ps aux | grep t0_weekly
```

---

### 方式二：使用部署脚本

#### 复制脚本到 NAS

在本地执行：
```bash
cd /home/dministrator/workspaces/stock_analysis/daily_stock_analysis

# 复制脚本到 NAS
scp scripts/setup-weekly-on-nas.sh my.sun@192.168.3.70:/volume1/docker/stock_analysis/scripts/
```

#### SSH 登录并执行

```bash
ssh my.sun@192.168.3.70
```

进入容器：
```bash
sudo /usr/bin/docker exec -it $(sudo /usr/bin/docker ps -q --filter "name=stock") /bin/bash
```

执行部署脚本：
```bash
cd /app/scripts
chmod +x setup-weekly-on-nas.sh
./setup-weekly-on-nas.sh
```

---

## 🔧 配置检查

### 1. 检查 .env 文件

确保容器内的 `/app/.env` 包含：

```bash
# 飞书 Webhook（必需）
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx

# Tushare Token（必需，需要 2000 积分）
TUSHARE_TOKEN=your_tushare_token_here

# 可选：调试模式
DEBUG=true
```

### 2. 验证数据目录

确保容器内可以访问数据目录：
```bash
ls -la /app/data/
```

应该能看到：
- `t0_stock_pool.csv` - 选股结果文件
- 其他数据文件

### 3. 检查日志目录

```bash
ls -la /app/logs/
```

确保有写入权限用于保存日志。

---

## 📊 验证部署

### 立即测试一次

```bash
cd /app
python3 scripts/t0_stock_screener.py --notify
```

检查点：
- [ ] 脚本正常运行无报错
- [ ] 飞书收到选股报告
- [ ] CSV 文件生成在 `data/t0_stock_pool.csv`

### 查看定时任务

```bash
# 查看 crontab
crontab -l

# 查看 cron 服务状态
service cron status
```

### 查看日志

```bash
# 实时查看 scheduler 日志
tail -f logs/t0_scheduler.log

# 查看选股任务日志
tail -f logs/t0_screener.log

# 查看最近的 cron 日志
grep CRON /var/log/syslog | tail -20
```

---

## ⚙️ 自定义配置

### 修改执行时间

编辑 crontab：
```bash
crontab -e
```

常用时间配置：
```bash
# 每周一 9:00
0 9 * * 1 python3 scripts/t0_stock_screener.py --notify

# 每周五 15:30
30 15 * * 5 python3 scripts/t0_stock_screener.py --notify

# 每周日 20:00
0 20 * * 0 python3 scripts/t0_stock_screener.py --notify
```

### 调整筛选参数

编辑 `/app/scripts/t0_stock_screener.py`：

```python
# 振幅范围（默认 2.5% ~ 4.0%）
AMP_LOW = 2.0        # 降低可选更活跃股票
AMP_HIGH = 5.0       # 提高可放宽上限

# 年涨幅限制（默认 ≤ 20%）
YEAR_RETURN_MAX = 30.0  # 提高可选更多底部股

# 股价范围（默认 5 ~ 30 元）
PRICE_MIN = 3.0
PRICE_MAX = 50.0
```

---

## 🐛 故障排查

### 问题 1: Python 包未安装

**错误**: `ModuleNotFoundError: No module named 'schedule'`

**解决**:
```bash
pip3 install schedule pandas numpy requests python-dotenv
```

### 问题 2: 飞书通知失败

**检查**:
```bash
# 查看 .env 配置
cat /app/.env | grep FEISHU

# 测试 Webhook
curl -X POST "YOUR_WEBHOOK_URL" \
  -H "Content-Type: application/json" \
  -d '{"msg_type":"text","content":{"text":"test"}}'
```

### 问题 3: Tushare 数据获取失败

**错误**: `RuntimeError: 积分不够，需要 2000 积分`

**解决**:
1. 访问 https://tushare.pro
2. 登录账号查看积分
3. 通过签到或捐赠获得 2000 积分
4. 更新 `/app/.env` 中的 TUSHARE_TOKEN

### 问题 4: crontab 未执行

**检查**:
```bash
# 确认 cron 服务运行
service cron status

# 启动 cron 服务
service cron start
```

**查看 cron 日志**:
```bash
grep CRON /var/log/syslog | tail -50
```

---

## 📝 日常管理

### 手动触发选股

```bash
cd /app
python3 scripts/t0_stock_screener.py --notify
```

### 查看选股结果

```bash
# 查看最新 CSV 文件
cat data/t0_stock_pool.csv

# 统计选股数量
wc -l data/t0_stock_pool.csv
```

### 停止任务

```bash
# 如果使用 crontab，删除对应行
crontab -e
# 删除：0 9 * * 1 ...

# 如果使用后台进程，杀死进程
ps aux | grep t0_weekly
kill <pid>
```

### 更新代码

```bash
cd /app
git pull origin main
pip3 install -r requirements.txt
```

---

## 💡 最佳实践

### 1. 日志轮转

创建 `/etc/logrotate.d/t0-screener`:
```
/app/logs/t0_screener.log {
    weekly
    rotate 4
    compress
    delaycompress
    missingok
    notifempty
}
```

### 2. 监控提醒

可以配置额外的通知渠道，确保任务正常运行：

```bash
# 在 .env 中添加
PUSHPLUS_TOKEN=your_pushplus_token
EMAIL_SENDER=your@email.com
```

### 3. 健康检查

定期检查：
- [ ] 飞书消息是否准时收到
- [ ] CSV 文件是否每周更新
- [ ] 日志中无明显错误

---

## 🔗 相关文档

- **完整配置指南**: [docs/t0-weekly-screener-config.md](docs/t0-weekly-screener-config.md)
- **快速参考**: [docs/T0_WEEKLY_QUICK_REFERENCE.md](docs/T0_WEEKLY_QUICK_REFERENCE.md)
- **部署检查清单**: [docs/T0_WEEKLY_DEPLOYMENT_CHECKLIST.md](docs/T0_WEEKLY_DEPLOYMENT_CHECKLIST.md)

---

## 🎉 完成！

部署成功后，系统将：
- ✅ 每周一上午 9:00 自动运行选股任务
- ✅ 通过飞书机器人推送选股结果
- ✅ 保存完整数据到 CSV 文件
- ✅ 自动记录运行日志

**祝投资顺利！** 📈💰

---

**更新时间**: 2026-01-20  
**适用版本**: v1.0.0
