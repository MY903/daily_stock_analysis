#!/bin/bash

# T+0 选股池周报 - Synology NAS 部署脚本
# 专为群晖 DSM 系统设计，支持 Container Manager 或直接部署

set -e

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# 检查是否已安装 Python3
check_python() {
    if ! command -v python3 &> /dev/null; then
        log_error "未找到 Python3"
        echo ""
        echo "请在群晖套件中心安装 Python 3.x"
        echo "或者使用 Docker 方式部署（推荐）"
        exit 1
    fi
    
    log_info "Python 版本：$(python3 --version)"
}

# 检查依赖
check_dependencies() {
    log_info "检查 Python 依赖..."
    
    local deps=("schedule" "pandas" "numpy" "requests" "dotenv")
    for dep in "${deps[@]}"; do
        if ! python3 -c "import $dep" 2>/dev/null; then
            log_warn "$dep 未安装，正在安装..."
            pip3 install $dep
        fi
    done
    
    log_info "依赖检查完成"
}

# 检查 .env 配置
check_env() {
    log_info "检查 .env 配置..."
    
    if [ ! -f ".env" ]; then
        log_error ".env 文件不存在"
        exit 1
    fi
    
    # 检查必需配置
    if ! grep -q "^FEISHU_WEBHOOK_URL=" .env; then
        log_error ".env 中缺少 FEISHU_WEBHOOK_URL 配置"
        exit 1
    fi
    
    if ! grep -q "^TUSHARE_TOKEN=" .env; then
        log_error ".env 中缺少 TUSHARE_TOKEN 配置"
        exit 1
    fi
    
    log_info ".env 配置检查通过"
}

# 测试运行
test_run() {
    log_info "测试运行选股任务..."
    python3 scripts/t0_stock_screener.py --notify
    
    if [ -f "data/t0_stock_pool.csv" ]; then
        log_info "CSV 文件生成成功"
        ls -lh data/t0_stock_pool.csv
    else
        log_warn "CSV 文件未生成"
    fi
}

# 创建启动脚本
create_startup_script() {
    cat > /usr/local/bin/t0-weekly-screener << 'EOF'
#!/bin/bash
cd /volume1/homes/dministrator/workspaces/stock_analysis/daily_stock_analysis
export PATH=/usr/local/bin:/usr/bin:/bin
python3 -m scripts.t0_weekly_scheduler --weekday monday --time 09:00
EOF
    
    chmod +x /usr/local/bin/t0-weekly-screener
    log_info "启动脚本已创建：/usr/local/bin/t0-weekly-screener"
}

# 配置任务计划
setup_task_scheduler() {
    log_warn "群晖 DSM 7.x 任务计划配置步骤："
    echo ""
    echo "1. 打开 控制面板 → 任务计划"
    echo "2. 点击 新增 → 排定的工作 → 用户定义的脚本"
    echo "3. 填写以下信息："
    echo "   - 名称：T+0 选股池周报"
    echo "   - 用户：dministrator (或 root)"
    echo "   - 运行频率：每周"
    echo "   - 星期：星期一"
    echo "   - 时间：09:00"
    echo ""
    echo "4. 在『用户定义的脚本』中输入："
    echo ""
    echo "   #!/bin/bash"
    echo "   cd /volume1/homes/dministrator/workspaces/stock_analysis/daily_stock_analysis"
    echo "   source ~/.bash_profile 2>/dev/null || true"
    echo "   export PATH=/usr/local/bin:/usr/bin:/bin"
    echo "   python3 scripts/t0_stock_screener.py --notify >> logs/t0_screener.log 2>&1"
    echo ""
    echo "5. 点击 确定 保存"
    echo ""
    log_info "完成后可以通过 日志 查看执行记录"
}

# Docker 部署方式（推荐）
docker_deployment() {
    log_info "Docker 部署方式（推荐）"
    echo ""
    echo "群晖 Container Manager (Docker) 部署步骤："
    echo ""
    echo "1. 打开 Container Manager"
    echo "2. 进入 项目 → 新增"
    echo "3. 选择『从映像开始创建容器」"
    echo "4. 搜索并下载镜像：python:3.10-slim"
    echo ""
    echo "5. 设置容器配置："
    echo "   - 容器名称：t0-weekly-screener"
    echo "   - 启用：自动重新启动"
    echo "   - 执行指令："
    echo ""
    echo "     sh -c '"
    echo "       pip install schedule pandas numpy requests python-dotenv &&"
    echo "       cd /app &&"
    echo "       python3 -m scripts.t0_weekly_scheduler --weekday monday --time 09:00"
    echo "     '"
    echo ""
    echo "6. 设置存储空间："
    echo "   - 本地文件夹：/volume1/homes/dministrator/workspaces/stock_analysis/daily_stock_analysis"
    echo "   - 装载路径：/app"
    echo ""
    echo "7. 设置环境变量（可选）："
    echo "   - FEISHU_WEBHOOK_URL=..."
    echo "   - TUSHARE_TOKEN=..."
    echo ""
    echo "8. 点击 完成 启动容器"
    echo ""
    log_info "Docker 方式优势：环境隔离、易于管理、不影响系统 Python"
}

# 主菜单
show_menu() {
    echo ""
    echo "=========================================="
    echo "  T+0 选股池周报 - 群晖 NAS 部署工具"
    echo "=========================================="
    echo ""
    echo "请选择部署方式："
    echo ""
    echo "1. 直接部署（使用系统 Python）"
    echo "2. Docker 部署（推荐，环境隔离）"
    echo "3. 仅测试运行"
    echo "4. 查看帮助"
    echo "5. 退出"
    echo ""
    read -p "请输入选项 [1-5]: " choice
    
    case $choice in
        1)
            check_python
            check_dependencies
            check_env
            test_run
            create_startup_script
            setup_task_scheduler
            ;;
        2)
            docker_deployment
            ;;
        3)
            check_python
            check_env
            test_run
            ;;
        4)
            echo ""
            echo "详细文档："
            echo "  - docs/t0-weekly-screener-config.md"
            echo "  - docs/T0_WEEKLY_QUICK_REFERENCE.md"
            echo "  - docs/T0_WEEKLY_DEPLOYMENT_CHECKLIST.md"
            echo ""
            ;;
        5)
            log_info "退出部署"
            exit 0
            ;;
        *)
            log_error "无效选项"
            show_menu
            ;;
    esac
}

# 主程序
main() {
    echo ""
    log_info "欢迎使用 T+0 选股池周报部署工具"
    echo ""
    
    # 检查是否在正确的目录
    if [ ! -f "scripts/t0_stock_screener.py" ]; then
        log_error "请在项目根目录运行此脚本"
        exit 1
    fi
    
    show_menu
}

main "$@"
