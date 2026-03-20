# T+0 选股池周报自动化 - 完成总结

## 📦 已创建的文件

### 1. 核心脚本

| 文件 | 说明 | 用途 |
|------|------|------|
| [`scripts/t0_stock_screener.py`](../scripts/t0_stock_screener.py) | 选股筛选器（已更新） | 执行选股策略，支持飞书通知 |
| [`scripts/t0_weekly_scheduler.py`](../scripts/t0_weekly_scheduler.py) | 周度定时调度器 | 每周自动运行选股任务 |
| [`scripts/setup-t0-weekly-service.sh`](../scripts/setup-t0-weekly-service.sh) | 部署脚本 | 一键安装 systemd 服务 |

### 2. 配置文件

| 文件 | 说明 |
|------|------|
| [`docker/t0-weekly-screener.service`](../docker/t0-weekly-screener.service) | systemd 服务模板（需修改用户名和路径） |

### 3. 文档

| 文件 | 说明 | 适用场景 |
|------|------|----------|
| [`docs/t0-weekly-screener-config.md`](../docs/t0-weekly-screener-config.md) | 完整配置指南 | 详细部署和配置说明 |
| [`docs/T0_WEEKLY_QUICK_REFERENCE.md`](../docs/T0_WEEKLY_QUICK_REFERENCE.md) | 快速参考卡片 | 日常使用速查 |
| [`docs/T0_WEEKLY_DEPLOYMENT_CHECKLIST.md`](../docs/T0_WEEKLY_DEPLOYMENT_CHECKLIST.md) | 部署检查清单 | 按步骤验证部署 |
| `T0_WEEKLY_SUMMARY.md` (本文件) | 完成总结 | 了解整体方案 |

### 4. README 更新

| 文件 | 变更 |
|------|------|
| [`README.md`](../README.md) | 新增"T+0 选股池"功能特性说明 |

---

## 🎯 功能概述

### 实现了什么？

✅ **自动化选股**：每周一上午 9:00 自动运行 T+0 选股策略  
✅ **飞书推送**：选股结果自动推送到飞书群聊  
✅ **CSV 导出**：完整选股数据保存到 `data/t0_stock_pool.csv`  
✅ **灵活配置**：支持自定义执行时间、筛选参数  
✅ **优雅部署**：提供 systemd 服务和 crontab 两种部署方式  
✅ **完善文档**：从部署到维护的全流程文档

### 选股策略逻辑

基于以下维度筛选适合 T+0 交易的股票：

1. **财务健康**：排除 ST/*ST/PT 股票，排除上市不满 1 年
2. **振幅适中**：近 30 日平均振幅 2.5%~4.0%（T+0 黄金区间）
3. **位置低位**：距离一年新高≥10%，年涨幅≤20%（底部标的）
4. **流动性好**：日均成交≥800 万股，日均成交额≥5000 万元
5. **振幅稳定**：振幅变异系数≤0.6（规律性强）
6. **价格适中**：股价 5~30 元（适合 5-20 万资金）

---

## 🚀 快速开始（3 步完成）

### Step 1: 配置环境变量

编辑 `.env` 文件：

```bash
# 飞书机器人 Webhook
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx

# Tushare Token（需要 2000 积分）
TUSHARE_TOKEN=your_tushare_token_here
```

### Step 2: 测试运行

```bash
cd /home/dministrator/workspaces/stock_analysis/daily_stock_analysis

# 手动测试一次（带飞书通知）
python scripts/t0_stock_screener.py --notify
```

**预期**：
- ✅ 终端显示选股过程
- ✅ 飞书收到选股报告
- ✅ `data/t0_stock_pool.csv` 生成

### Step 3: 部署自动任务

```bash
# 安装 systemd 服务（每周一 9:00 自动运行）
sudo ./scripts/setup-t0-weekly-service.sh install

# 查看状态
sudo ./scripts/setup-t0-weekly-service.sh status
```

**完成！** 🎉

---

## ⚙️ 配置选项

### 修改执行时间

**默认**: 每周一 9:00

**改为其他时间**（例如每周五 15:30）：

```bash
sudo nano /etc/systemd/system/t0-weekly-screener.service
```

修改 `ExecStart` 行：
```ini
ExecStart=/usr/bin/python3 -m scripts.t0_weekly_scheduler --weekday friday --time 15:30
```

重新加载：
```bash
sudo systemctl daemon-reload
sudo systemctl restart t0-weekly-screener
```

**常用时间**：
- 周一 9:00: `--weekday monday --time 09:00` ✅
- 周五 15:30: `--weekday friday --time 15:30` ✅
- 周六 10:00: `--weekday saturday --time 10:00`
- 周日 20:00: `--weekday sunday --time 20:00` ✅

### 修改筛选参数

编辑 `scripts/t0_stock_screener.py`：

```python
# 振幅范围（默认 2.5% ~ 4.0%）
AMP_LOW = 2.0        # 降低可选更活跃股票
AMP_HIGH = 5.0       # 提高可放宽上限

# 年涨幅限制（默认 ≤ 20%）
YEAR_RETURN_MAX = 30.0  # 提高可选更多底部股

# 股价范围（默认 5 ~ 30 元）
PRICE_MIN = 3.0
PRICE_MAX = 50.0

# 流动性要求
MIN_AVG_TURNOVER = 30.0  # 降低可纳入更小盘股
MIN_AVG_VOLUME = 5_000_000
```

---

## 📊 输出示例

### 飞书消息格式

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

### CSV 字段说明

| 字段 | 说明 |
|------|------|
| ts_code | 股票代码（如 000123.SZ） |
| name | 股票名称 |
| industry | 所属行业 |
| latest_price | 最新股价（元） |
| avg_amplitude | 平均振幅（%） |
| amp_cv | 振幅变异系数（稳定性） |
| year_return | 年收益率（%） |
| distance_from_high | 距离一年新高（%） |
| avg_turnover_wan | 日均成交额（万元） |
| avg_volume | 日均成交量（股） |

---

## 🔧 管理命令

### systemd 服务管理

```bash
# 查看状态
sudo systemctl status t0-weekly-screener

# 查看日志
sudo journalctl -u t0-weekly-screener -f

# 停止服务
sudo systemctl stop t0-weekly-screener

# 重启服务
sudo systemctl restart t0-weekly-screener

# 禁用服务（开机不自启）
sudo systemctl disable t0-weekly-screener

# 启用服务
sudo systemctl enable t0-weekly-screener

# 卸载服务
sudo ./scripts/setup-t0-weekly-service.sh uninstall
```

### 手动触发

```bash
# 不带通知
python scripts/t0_stock_screener.py

# 带飞书通知
python scripts/t0_stock_screener.py --notify
```

---

## 🐛 常见问题

### Q1: 飞书通知未收到？

**检查**：
1. `.env` 中 `FEISHU_WEBHOOK_URL` 是否正确
2. 飞书机器人是否在群内启用
3. 网络是否通畅

**测试**：
```bash
python scripts/t0_stock_screener.py --notify
```

### Q2: Tushare 数据获取失败？

**原因**：积分不足（需要 2000 积分）

**解决**：
1. 访问 https://tushare.pro
2. 签到或捐赠获得积分
3. 验证 Token：https://tushare.pro/user/token

### Q3: 选股结果为空？

**原因**：
1. 市场整体波动率低（正常）
2. 筛选条件过严

**解决**：放宽筛选参数（见"修改筛选参数"部分）

### Q4: 服务无法启动？

**检查**：
```bash
# 查看详细错误
sudo systemctl status t0-weekly-screener

# 检查 Python 路径
which python3

# 检查依赖
pip list | grep -E "schedule|pandas|numpy|requests"
```

---

## 📚 文档索引

### 新手入门

1. **[部署检查清单](T0_WEEKLY_DEPLOYMENT_CHECKLIST.md)** - 按步骤完成部署
2. **[快速参考](T0_WEEKLY_QUICK_REFERENCE.md)** - 日常使用速查

### 深入配置

3. **[完整配置指南](t0-weekly-screener-config.md)** - 详细的技术文档
4. **[源码注释](../scripts/t0_stock_screener.py)** - 选股策略实现细节

### 故障排查

- 常见问题解答：见各文档的"故障排查"章节
- 日志查看：`sudo journalctl -u t0-weekly-screener -f`

---

## 💡 最佳实践

### 1. 首次部署建议

- 先用 crontab 测试一周，确认稳定后再用 systemd
- 或先用 `python scripts/t0_stock_screener.py --notify` 手动测试几次

### 2. 监控与告警

可以配置额外通知渠道（邮件、PushPlus），确保服务正常运行：

```bash
# 在 .env 中添加
PUSHPLUS_TOKEN=your_pushplus_token
```

### 3. 定期回顾

- 每月检查一次选股效果
- 根据实际表现调整筛选参数
- 关注 Tushare 积分余额（避免欠费）

### 4. 备份配置

```bash
# 备份 .env 文件
cp .env .env.backup.$(date +%Y%m%d)

# 备份自定义参数
cp scripts/t0_stock_screener.py scripts/t0_stock_screener.py.custom
```

### 5. 日志管理

```bash
# 定期清理旧日志
sudo journalctl --vacuum-time=4weeks

# 或限制日志大小
sudo journalctl --vacuum-size=100M
```

---

## 🎯 下一步建议

### 1. 回测验证

使用生成的选股池进行历史回测：

```bash
# 参考回测脚本
python scripts/t0_backtest.py
```

### 2. 实盘跟踪

建立模拟组合，跟踪选股表现：
- 记录每周选股结果
- 跟踪下一周的实际涨幅
- 统计胜率和盈亏比

### 3. 策略优化

根据回测和实盘结果，优化筛选参数：
- 调整振幅范围
- 优化流动性要求
- 增加新的筛选维度（如量比、换手率等）

### 4. 整合其他功能

结合项目的其他功能，形成完整体系：
- AI 决策仪表盘：对选股池中的股票进行 AI 分析
- 大盘复盘：结合市场环境判断是否适合 T+0
- 实时监控：设置价格异动提醒

---

## 📋 技术架构

### 组件关系

```
┌─────────────────────────────────────┐
│  t0_weekly_scheduler.py             │
│  - 定时调度器 (schedule 库)          │
│  - 每周一 9:00 触发                  │
│  - 优雅退出处理                      │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│  t0_stock_screener.py               │
│  - 选股策略执行                     │
│  - 数据获取 (Tushare)               │
│  - 指标计算与筛选                   │
│  - 生成 CSV 文件                     │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│  NotificationService                │
│  - 生成 Markdown 报告               │
│  - 调用飞书 Webhook API             │
│  - 发送消息到飞书群                 │
└─────────────────────────────────────┘
```

### 依赖库

```python
# 核心依赖
schedule      # 定时任务调度
pandas        # 数据处理
numpy         # 数值计算
requests      # HTTP 请求
python-dotenv # 环境变量管理
```

### 数据流

```
Tushare API → 日线数据 → 指标计算 → 筛选过滤 → CSV + 飞书推送
```

---

## 🔐 安全与合规

### 数据安全

- ✅ 所有数据存储在本地
- ✅ 不上传任何敏感信息
- ✅ 仅查询公开的股票数据

### 合规声明

⚠️ **重要提示**：
- 选股结果仅供研究参考
- 不构成任何投资建议
- 实盘交易需谨慎，做好风险控制
- 过往表现不代表未来收益

### API 使用限制

- **Tushare**: 免费用户 80 次/分钟，注意积分消耗
- **飞书 Webhook**: 无明显限制，但建议合理频率

---

## 🤝 贡献与反馈

### 发现问题？

欢迎提交 Issue：
- 描述问题现象
- 提供错误日志
- 说明复现步骤

### 改进建议？

欢迎 Pull Request：
- 代码优化
- 文档改进
- 新功能建议

### 联系方式

- GitHub: [daily_stock_analysis](https://github.com/ZhuLinsen/daily_stock_analysis)
- 项目讨论区：Issues / Discussions

---

## 📄 许可证

本项目采用 MIT 许可证，详见 [LICENSE](../LICENSE) 文件。

---

## 🎉 结语

恭喜你完成了 T+0 选股池周报自动化的部署！

现在，你拥有了一个：
- ✅ **全自动**：每周自动运行，无需手动干预
- ✅ **智能化**：基于多维度指标科学选股
- ✅ **可视化**：飞书消息清晰展示结果
- ✅ **可扩展**：支持自定义参数和策略

**祝投资顺利，收益长虹！** 📈💰

---

**创建时间**: 2026-01-20  
**版本**: v1.0.0  
**维护者**: dministrator
