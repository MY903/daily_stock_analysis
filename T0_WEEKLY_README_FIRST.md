# 🎉 T+0 选股池周报自动化 - 部署完成！

## ✅ 已完成的工作

### 1. 核心功能开发

✅ **选股策略脚本** (`scripts/t0_stock_screener.py`)
- 基于多维度指标筛选适合 T+0 交易的股票
- 支持飞书机器人推送通知
- 导出完整选股结果到 CSV 文件

✅ **周度定时调度器** (`scripts/t0_weekly_scheduler.py`)
- 每周一上午 9:00 自动运行（可自定义）
- 优雅退出处理
- 异常捕获和日志记录

✅ **部署脚本** (2 个)
- `setup-t0-weekly-service.sh`: systemd 服务一键部署
- `deploy-to-synology.sh`: 群晖 NAS 专用部署工具

### 2. 配置文件

✅ **systemd 服务模板** (`docker/t0-weekly-screener.service`)
- 开机自启
- 自动重启
- 标准化日志管理

### 3. 完整文档

✅ **技术文档** (4 份)
- `t0-weekly-screener-config.md`: 完整配置指南
- `T0_WEEKLY_QUICK_REFERENCE.md`: 快速参考卡片
- `T0_WEEKLY_DEPLOYMENT_CHECKLIST.md`: 部署检查清单
- `T0_WEEKLY_SUMMARY.md`: 总结文档

✅ **README 更新**
- 新增"T+0 选股池"功能特性说明

---

## 🚀 在群晖 NAS 上部署（3 种方式）

### 方式一：使用部署脚本（最简单）

```bash
cd /home/dministrator/workspaces/stock_analysis/daily_stock_analysis

# 运行群晖部署脚本
./scripts/deploy-to-synology.sh
```

然后按照菜单提示选择：
- 选项 1: 直接部署（使用系统 Python）
- 选项 2: Docker 部署（推荐）
- 选项 3: 仅测试运行

### 方式二：手动配置任务计划（传统方式）

#### Step 1: 安装 Python

在群晖套件中心安装 **Python 3.8+**

#### Step 2: 安装依赖

```bash
ssh 登录群晖
sudo -i

# 安装依赖
pip3 install schedule pandas numpy requests python-dotenv
```

#### Step 3: 配置环境变量

编辑 `~/.bash_profile`：

```bash
export FEISHU_WEBHOOK_URL="https://open.feishu.cn/open-apis/bot/v2/hook/xxx"
export TUSHARE_TOKEN="your_token"
```

使配置生效：
```bash
source ~/.bash_profile
```

#### Step 4: 创建任务计划

1. 打开 **控制面板 → 任务计划**
2. 点击 **新增 → 排定的工作 → 用户定义的脚本**
3. 填写：
   - **名称**: T+0 选股池周报
   - **用户**: dministrator
   - **运行频率**: 每周
   - **星期**: 星期一
   - **时间**: 09:00
4. 在 **用户定义的脚本** 中输入：

```bash
#!/bin/bash
cd /volume1/homes/dministrator/workspaces/stock_analysis/daily_stock_analysis
source ~/.bash_profile 2>/dev/null || true
export PATH=/usr/local/bin:/usr/bin:/bin
python3 scripts/t0_stock_screener.py --notify >> logs/t0_screener.log 2>&1
```

5. 点击 **确定** 保存

#### Step 5: 验证

右键任务 → **运行**，然后查看日志

### 方式三：Docker 部署（最推荐）

#### Step 1: 打开 Container Manager

应用程序 → Container Manager → 项目 → 新增

#### Step 2: 创建容器

- **来源**: 从映像开始创建容器
- **镜像**: `python:3.10-slim`
- **容器名称**: `t0-weekly-screener`

#### Step 3: 设置

**基本设置**:
- 启用：自动重新启动
- 执行指令：
```bash
sh -c '
  pip install schedule pandas numpy requests python-dotenv &&
  cd /app &&
  python3 -m scripts.t0_weekly_scheduler --weekday monday --time 09:00
'
```

**存储空间**:
- 本地文件夹：`/volume1/homes/dministrator/workspaces/stock_analysis/daily_stock_analysis`
- 装载路径：`/app`

**环境变量**:
```
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/xxx
TUSHARE_TOKEN=your_token_here
```

**网络**:
- 使用与 DSM 相同的网络

#### Step 4: 启动

点击 **完成** 启动容器

---

## 📋 配置检查清单

部署前确保已配置：

- [ ] **Python 3.10+** 已安装
- [ ] **依赖库** 已安装：`schedule`, `pandas`, `numpy`, `requests`, `python-dotenv`
- [ ] **.env 文件** 存在且包含：
  - [ ] `FEISHU_WEBHOOK_URL`（飞书机器人 Webhook）
  - [ ] `TUSHARE_TOKEN`（Tushare API Token，需要 2000 积分）
- [ ] **测试运行** 成功：`python scripts/t0_stock_screener.py --notify`
- [ ] **飞书消息** 已收到
- [ ] **CSV 文件** 已生成：`data/t0_stock_pool.csv`

---

## ⚙️ 自定义配置

### 修改执行时间

**默认**: 每周一 9:00

**改为其他时间**：

#### systemd 方式
```bash
sudo nano /etc/systemd/system/t0-weekly-screener.service
```

修改 `ExecStart`:
```ini
# 改为每周五 15:30
ExecStart=/usr/bin/python3 -m scripts.t0_weekly_scheduler --weekday friday --time 15:30
```

重新加载：
```bash
sudo systemctl daemon-reload
sudo systemctl restart t0-weekly-screener
```

#### 任务计划方式
直接在群晖任务计划中双击任务，修改时间和频率

#### Docker 方式
修改执行指令中的参数：
```bash
python3 -m scripts.t0_weekly_scheduler --weekday friday --time 15:30
```

### 常用时间参考

| 时间 | weekday | time | 说明 |
|------|---------|------|------|
| 周一 9:00 | monday | 09:00 | 周一开盘前选股 ✅ |
| 周一 12:00 | monday | 12:00 | 周一中午分析 |
| 周五 15:30 | friday | 15:30 | 周五收盘后复盘 ✅ |
| 周六 10:00 | saturday | 10:00 | 周末研究 |
| 周日 20:00 | sunday | 20:00 | 为下周准备 ✅ |

### 修改筛选条件

编辑 `scripts/t0_stock_screener.py`，调整以下参数：

```python
# === 振幅范围（默认 2.5% ~ 4.0%）===
AMP_LOW = 2.5        # 降低可选更活跃股票
AMP_HIGH = 4.0       # 提高可放宽上限

# === 年涨幅限制（默认 ≤ 20%）===
YEAR_RETURN_MAX = 20.0  # 提高可选更多底部股

# === 股价范围（默认 5 ~ 30 元）===
PRICE_MIN = 5.0
PRICE_MAX = 30.0

# === 流动性要求 ===
MIN_AVG_TURNOVER = 50.0  # 降低可纳入更小盘股
MIN_AVG_VOLUME = 8_000_000

# === 振幅稳定性（默认 ≤ 0.6）===
AMP_CV_MAX = 0.6  # 提高可筛选更稳定

# === 距离新高（默认 ≥ 10%）===
MIN_DISTANCE_FROM_HIGH = 10.0  # 提高可确保更靠近底部
```

修改后测试：
```bash
python scripts/t0_stock_screener.py --notify
```

---

## 📊 输出效果

### 飞书消息示例

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

### CSV 文件内容

位置：`/home/dministrator/workspaces/stock_analysis/daily_stock_analysis/data/t0_stock_pool.csv`

包含字段：
- ts_code: 股票代码
- name: 股票名称
- industry: 所属行业
- latest_price: 最新股价
- avg_amplitude: 平均振幅
- amp_cv: 振幅稳定性
- year_return: 年收益率
- distance_from_high: 距离新高
- avg_turnover_wan: 日均成交额（万元）
- avg_volume: 日均成交量

---

## 🔧 日常管理

### 查看日志

#### systemd 方式
```bash
# 实时日志
sudo journalctl -u t0-weekly-screener -f

# 最近 100 行
sudo journalctl -u t0-weekly-screener -n 100

# 今天的日志
sudo journalctl -u t0-weekly-screener --since today
```

#### 任务计划方式
群晖任务计划 → 右键任务 → 日志

#### Docker 方式
Container Manager → 容器 → t0-weekly-screener → 日志

### 服务管理

#### systemd 方式
```bash
# 查看状态
sudo systemctl status t0-weekly-screener

# 停止
sudo systemctl stop t0-weekly-screener

# 重启
sudo systemctl restart t0-weekly-screener

# 禁用（开机不自启）
sudo systemctl disable t0-weekly-screener

# 启用
sudo systemctl enable t0-weekly-screener

# 卸载
sudo ./scripts/setup-t0-weekly-service.sh uninstall
```

### 手动触发

```bash
# 带飞书通知
python scripts/t0_stock_screener.py --notify

# 不带通知
python scripts/t0_stock_screener.py
```

---

## 🐛 常见问题

### Q1: 飞书通知未收到？

**检查步骤**：

1. 验证 Webhook URL
```bash
grep FEISHU_WEBHOOK_URL .env
```

2. 测试 Webhook
```bash
curl -X POST "YOUR_WEBHOOK_URL" \
  -H "Content-Type: application/json" \
  -d '{"msg_type":"text","content":{"text":"测试"}}'
```

3. 手动运行选股
```bash
python scripts/t0_stock_screener.py --notify
```

**可能原因**：
- ❌ Webhook URL 错误 → 重新复制完整 URL
- ❌ 飞书机器人被禁用 → 在飞书群启用
- ❌ 网络问题 → 检查服务器外网访问

### Q2: Tushare 数据获取失败？

**错误**：`RuntimeError: 积分不够，需要 2000 积分`

**解决**：
1. 访问 https://tushare.pro
2. 登录账号
3. 通过签到或捐赠获得 2000 积分
4. 验证 Token：https://tushare.pro/user/token

### Q3: 选股结果为空？

**原因**：
1. 市场波动率低（正常）
2. 筛选条件过严

**解决**：放宽筛选参数（见"修改筛选条件"部分）

### Q4: 服务无法启动？

**检查**：
```bash
# 查看详细错误
sudo systemctl status t0-weekly-screener

# 检查 Python 路径
which python3

# 检查依赖
pip3 list | grep -E "schedule|pandas|numpy|requests"
```

---

## 📚 文档索引

### 新手入门
1. **[部署检查清单](docs/T0_WEEKLY_DEPLOYMENT_CHECKLIST.md)** - 按步骤完成部署
2. **[快速参考](docs/T0_WEEKLY_QUICK_REFERENCE.md)** - 日常使用速查

### 深入配置
3. **[完整配置指南](docs/t0-weekly-screener-config.md)** - 详细技术文档
4. **[总结文档](T0_WEEKLY_SUMMARY.md)** - 了解整体方案

### 源码
- **选股策略**: [scripts/t0_stock_screener.py](scripts/t0_stock_screener.py)
- **调度器**: [scripts/t0_weekly_scheduler.py](scripts/t0_weekly_scheduler.py)
- **部署脚本**: [scripts/setup-t0-weekly-service.sh](scripts/setup-t0-weekly-service.sh)

---

## 💡 下一步建议

### 1. 回测验证
```bash
# 使用历史数据验证选股策略
python scripts/t0_backtest.py
```

### 2. 实盘跟踪
- 建立模拟组合
- 记录每周选股表现
- 统计胜率和盈亏比

### 3. 策略优化
根据实际效果调整：
- 振幅范围
- 流动性要求
- 增加新指标（量比、换手率等）

### 4. 整合 AI 分析
对选股池中的股票进行 AI 深度分析：
```bash
# 使用 AI 决策仪表盘
python main.py --stocks <股票代码>
```

---

## 🎯 验收标准

部署完成后应满足：

- [ ] 服务持续运行（`systemctl status` 显示 active）
- [ ] 每周自动执行一次
- [ ] 飞书准时收到选股报告
- [ ] CSV 文件每周更新
- [ ] 无明显错误或警告

---

## 📞 获取帮助

### 遇到问题？

1. **查看文档**: 上方列出的 4 份详细文档
2. **查看日志**: `sudo journalctl -u t0-weekly-screener -f`
3. **测试运行**: `python scripts/t0_stock_screener.py --notify`
4. **提交 Issue**: GitHub 项目 Issues

### 联系方式

- GitHub: [daily_stock_analysis](https://github.com/ZhuLinsen/daily_stock_analysis)
- 讨论区：Issues / Discussions

---

## ✨ 功能亮点

✅ **全自动**: 每周自动运行，无需手动干预  
✅ **智能化**: 多维度科学选股  
✅ **可视化**: 飞书消息清晰展示  
✅ **可扩展**: 支持自定义参数  
✅ **零成本**: 无需服务器，利用现有 NAS  
✅ **易部署**: 提供多种部署方式和脚本  

---

## 🎉 恭喜完成！

现在你拥有了一个专业的 T+0 选股系统，每周自动为你筛选优质标的！

**祝投资顺利，收益长虹！** 📈💰

---

**版本**: v1.0.0  
**创建时间**: 2026-01-20  
**适用系统**: Linux / Synology DSM 7.x  
**Python 版本**: 3.10+
