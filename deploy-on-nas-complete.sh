#!/bin/bash
# T+0 Weekly Screener - Complete Deployment Script for Synology NAS
# 复制到 NAS 后直接执行此脚本

set -e

echo "=========================================="
echo "🚀 T+0 选股池周报 - 自动化部署"
echo "=========================================="
echo ""

# 检查是否在正确的目录
if [ ! -d "/volume1/docker/stock_analysis" ]; then
    echo "❌ 错误：未找到项目目录 /volume1/docker/stock_analysis"
    exit 1
fi

cd /volume1/docker/stock_analysis

echo "✅ 工作目录：$(pwd)"
echo ""

# 步骤 1: 查找容器
echo "📦 Step 1: 查找 stock_analysis 容器..."
CONTAINER_ID=$(sudo /usr/bin/docker ps -q --filter "name=stock" 2>/dev/null || echo "")

if [ -z "$CONTAINER_ID" ]; then
    echo "尝试搜索其他容器名称..."
    CONTAINER_ID=$(sudo /usr/bin/docker ps -q 2>/dev/null | head -1)
fi

if [ -z "$CONTAINER_ID" ]; then
    echo "❌ 未找到 Docker 容器"
    echo "请确认容器已启动："
    echo "  sudo /usr/bin/docker ps -a"
    exit 1
fi

echo "✓ 找到容器：$CONTAINER_ID"
echo ""

# 步骤 2: 在容器内安装依赖并测试
echo "🔧 Step 2: 在容器内安装依赖和测试..."

sudo /usr/bin/docker exec "$CONTAINER_ID" /bin/bash -c "
    cd /app || cd /volume1/docker/stock_analysis
    
    echo '安装 Python 依赖...'
    pip3 install schedule pandas numpy requests python-dotenv -q
    
    echo '验证依赖安装...'
    python3 -c 'import schedule, pandas, numpy, requests; print(\"✓ 依赖安装成功\")'
"

echo ""
echo "🧪 Step 3: 测试运行选股任务..."

# 检查 .env 文件
if [ ! -f ".env" ]; then
    echo "⚠️  警告：.env 文件不存在"
    echo "请先配置 FEISHU_WEBHOOK_URL 和 TUSHARE_TOKEN"
else
    echo "✓ .env 文件存在"
    
    if ! grep -q "FEISHU_WEBHOOK_URL=" .env || [ -z "$(grep FEISHU_WEBHOOK_URL .env | cut -d'=' -f2)" ]; then
        echo "⚠️  警告：FEISHU_WEBHOOK_URL 未配置或未设置"
    else
        echo "✓ FEISHU_WEBHOOK_URL 已配置"
    fi
    
    if ! grep -q "TUSHARE_TOKEN=" .env || [ -z "$(grep TUSHARE_TOKEN .env | cut -d'=' -f2)" ]; then
        echo "⚠️  警告：TUSHARE_TOKEN 未配置或未设置"
    else
        echo "✓ TUSHARE_TOKEN 已配置"
    fi
fi

echo ""
echo "是否现在测试运行选股任务？（这可能需要 1-2 分钟）"
read -p "输入 y 继续，其他键跳过：[y/N] " answer

if [ "$answer" = "y" ] || [ "$answer" = "Y" ]; then
    sudo /usr/bin/docker exec -it "$CONTAINER_ID" /bin/bash -c "
        cd /app
        python3 scripts/t0_stock_screener.py --notify
    "
fi

echo ""
echo "⏰ Step 4: 设置定时任务（每周一 9:00）..."

# 创建 crontab 命令
CRON_CMD="0 9 * * 1 cd /app && python3 scripts/t0_stock_screener.py --notify >> logs/t0_screener.log 2>&1"

# 进入容器设置 crontab
sudo /usr/bin/docker exec "$CONTAINER_ID" /bin/bash -c "
    # 备份现有 crontab
    crontab -l > /tmp/cron_backup.txt 2>/dev/null || true
    
    # 添加新的定时任务
    (crontab -l 2>/dev/null | grep -v 't0_stock_screener'; echo '$CRON_CMD') | crontab -
    
    echo '验证 crontab...'
    crontab -l | grep t0
"

echo ""
echo "=========================================="
echo "✅ 部署完成！"
echo "=========================================="
echo ""
echo "容器 ID: $CONTAINER_ID"
echo "下次执行时间：下周一 上午 9:00"
echo ""
echo "管理命令："
echo "  手动运行：docker exec -it $CONTAINER_ID python3 scripts/t0_stock_screener.py --notify"
echo "  查看日志：docker exec -it $CONTAINER_ID tail -f logs/t0_screener.log"
echo "  编辑定时：docker exec -it $CONTAINER_ID crontab -e"
echo "  查看定时：docker exec -it $CONTAINER_ID crontab -l"
echo ""
echo "🎉 恭喜！T+0 选股池周报已配置完成！"
