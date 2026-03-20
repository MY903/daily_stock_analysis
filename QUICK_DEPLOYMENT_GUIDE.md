# 🚀 T+0 选股池周报 - 立即部署指南

## ⚡ 快速部署（复制粘贴到 NAS 执行）

### Step 1: SSH 登录 NAS

打开终端，执行：

```bash
ssh my.sun@192.168.3.70
```

输入密码：`MegaMingyang2023`

---

### Step 2: 查找容器 ID

在 NAS 上执行：

```bash
sudo /usr/bin/docker ps -a | grep -i stock
```

如果找不到，查看所有容器：

```bash
sudo /usr/bin/docker ps -a
```

**记下容器 ID**（例如：`abc123def456`）

---

### Step 3: 进入容器

```bash
sudo /usr/bin/docker exec -it <CONTAINER_ID> /bin/bash
```

将 `<CONTAINER_ID>` 替换为实际的容器 ID

---

### Step 4: 在容器内执行所有命令

**复制以下所有内容**，在容器内一次性执行：

```bash
# 切换到应用目录
cd /app

# 1. 安装 Python 依赖
echo "🔧 安装 Python 依赖..."
pip3 install schedule pandas numpy requests python-dotenv

# 2. 验证依赖
echo "✅ 验证依赖安装..."
python3 -c "import schedule, pandas, numpy, requests; print('✓ 依赖安装成功')"

# 3. 检查 .env 配置
echo ""
echo "📋 检查环境配置..."
if [ -f ".env" ]; then
    echo "✓ .env 文件存在"
    if grep -q "FEISHU_WEBHOOK_URL=" .env && [ -n "$(grep FEISHU_WEBHOOK_URL .env | cut -d'=' -f2)" ]; then
        echo "✓ FEISHU_WEBHOOK_URL 已配置"
    else
        echo "⚠️  FEISHU_WEBHOOK_URL 未配置"
    fi
    if grep -q "TUSHARE_TOKEN=" .env && [ -n "$(grep TUSHARE_TOKEN .env | cut -d'=' -f2)" ]; then
        echo "✓ TUSHARE_TOKEN 已配置"
    else
        echo "⚠️  TUSHARE_TOKEN 未配置"
    fi
else
    echo "⚠️  .env 文件不存在"
fi

# 4. 测试运行选股任务（可选，需要 1-2 分钟）
echo ""
echo "🧪 是否现在测试运行选股任务？(y/N)"
read -p "> " answer

if [ "$answer" = "y" ] || [ "$answer" = "Y" ]; then
    echo "开始测试..."
    python3 scripts/t0_stock_screener.py --notify
    echo ""
    echo "✅ 测试完成！请检查飞书消息"
    echo "CSV 文件位置：data/t0_stock_pool.csv"
else
    echo "跳过测试运行"
fi

# 5. 设置 crontab 定时任务（每周一 9:00）
echo ""
echo "⏰ 设置定时任务..."
(crontab -l 2>/dev/null | grep -v 't0_stock_screener'; echo '0 9 * * 1 cd /app && python3 scripts/t0_stock_screener.py --notify >> logs/t0_screener.log 2>&1') | crontab -

# 6. 验证 crontab
echo "验证 crontab 配置..."
crontab -l | grep t0

echo ""
echo "=========================================="
echo "✅ 部署完成！"
echo "=========================================="
echo ""
echo "下次执行时间：下周一 上午 9:00"
echo ""
echo "管理命令："
echo "  手动运行：python3 scripts/t0_stock_screener.py --notify"
echo "  查看日志：tail -f logs/t0_screener.log"
echo "  编辑定时：crontab -e"
echo "  查看定时：crontab -l"
echo ""
echo "🎉 恭喜！T+0 选股池周报已配置完成！"
```

---

## 📋 执行过程示例

```bash
# SSH 登录
my.sun@192.168.3.70's password: ********

# 查找容器
$ sudo /usr/bin/docker ps -a | grep -i stock
abc123def456   stock_analysis   "/bin/bash"   2 days ago   Up 2 days   stock_analysis

# 进入容器
$ sudo /usr/bin/docker exec -it abc123def456 /bin/bash

# 在容器内执行上述所有命令...

# 预期输出：
🔧 安装 Python 依赖...
Collecting schedule
Installing collected packages: schedule, pandas, numpy, requests, python-dotenv
Successfully installed pandas-2.x.x numpy-2.x.x requests-2.x.x python-dotenv-11.x.x schedule-1.x.x

✅ 验证依赖安装...
✓ 依赖安装成功

📋 检查环境配置...
✓ .env 文件存在
✓ FEISHU_WEBHOOK_URL 已配置
✓ TUSHARE_TOKEN 已配置

🧪 是否现在测试运行选股任务？(y/N)
> y

开始测试...
[选股过程日志...]
✅ Feishu notification sent successfully
✅ 测试完成！请检查飞书消息

⏰ 设置定时任务...
验证 crontab 配置...
0 9 * * 1 cd /app && python3 scripts/t0_stock_screener.py --notify >> logs/t0_screener.log 2>&1

==========================================
✅ 部署完成！
==========================================

下次执行时间：下周一 上午 9:00
```

---

## ✅ 验收检查

### 1. 检查飞书消息

打开飞书群聊，应该收到测试推送的消息：

```
## 📊 T+0 选股池周报
**生成时间**: 2026-01-20 XX:XX

### 📈 筛选统计
- **入选股票数量**: XX 只
- **平均振幅**: X.XX%
...
```

### 2. 检查 CSV 文件

在容器内执行：

```bash
ls -lh data/t0_stock_pool.csv
cat data/t0_stock_pool.csv | head -5
```

应该能看到选股结果数据。

### 3. 检查 crontab

```bash
crontab -l
```

应该显示：

```bash
0 9 * * 1 cd /app && python3 scripts/t0_stock_screener.py --notify >> logs/t0_screener.log 2>&1
```

---

## 🔧 故障排查

### 问题 1: 找不到容器

**解决**:
```bash
# 查看所有容器（包括已停止的）
sudo /usr/bin/docker ps -a

# 如果容器已停止，启动它
sudo /usr/bin/docker start <container_id>
```

### 问题 2: pip3 安装失败

**错误**: `pip3: command not found`

**解决**:
```bash
# 在容器内尝试使用 python3 -m pip
python3 -m pip install schedule pandas numpy requests python-dotenv
```

### 问题 3: 飞书通知失败

**检查**:
```bash
# 查看 .env 配置
cat .env | grep FEISHU

# 如果为空或未配置，编辑 .env
vi .env
# 添加：FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/xxx
```

### 问题 4: Tushare 积分不足

**错误**: `RuntimeError: 积分不够，需要 2000 积分`

**解决**:
1. 访问 https://tushare.pro
2. 登录账号查看积分
3. 通过签到或捐赠获得 2000 积分
4. 更新 `.env` 中的 TUSHARE_TOKEN

---

## 📞 需要帮助？

如果遇到任何问题，可以：

1. 查看详细文档：`docs/NAS_CONTAINER_DEPLOYMENT.md`
2. 查看日志：`tail -f logs/t0_screener.log`
3. 手动运行测试：`python3 scripts/t0_stock_screener.py --notify`

---

## 🎯 下一步

部署完成后：

1. ✅ 检查飞书是否收到测试消息
2. ✅ 查看 `data/t0_stock_pool.csv` 是否生成
3. ✅ 等待下周一验证自动执行
4. ✅ 定期查看日志确保正常运行

---

**祝部署顺利！** 🎉

如有问题，参考完整文档：
- [NAS 容器部署指南](docs/NAS_CONTAINER_DEPLOYMENT.md)
- [快速参考卡片](docs/T0_WEEKLY_QUICK_REFERENCE.md)
- [完整总结](DEPLOYMENT_COMPLETE_SUMMARY.md)
