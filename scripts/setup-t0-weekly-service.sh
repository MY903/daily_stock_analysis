#!/bin/bash

# T+0 选股池周度任务部署脚本
# 用于在 Synology NAS 或其他 Linux 服务器上快速配置 systemd 服务

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 日志函数
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 检查是否以 root 运行
check_root() {
    if [ "$EUID" -ne 0 ]; then
        log_error "请使用 sudo 运行此脚本"
        exit 1
    fi
}

# 获取当前用户
get_current_user() {
    if [ -n "$SUDO_USER" ]; then
        echo "$SUDO_USER"
    else
        whoami
    fi
}

# 获取 Python 路径
get_python_path() {
    if command -v python3 &> /dev/null; then
        which python3
    else
        log_error "未找到 Python3，请先安装"
        exit 1
    fi
}

# 获取项目根目录
get_project_root() {
    cd "$(dirname "$0")/.."
    pwd
}

# 检查依赖
check_dependencies() {
    log_info "检查依赖..."
    
    local deps=("python3" "pip3")
    for dep in "${deps[@]}"; do
        if ! command -v "$dep" &> /dev/null; then
            log_error "未找到 $dep，请先安装"
            exit 1
        fi
    done
    
    # 检查 Python 依赖
    log_info "检查 Python 依赖..."
    python3 -c "import schedule" 2>/dev/null || {
        log_warn "schedule 库未安装，正在安装..."
        pip3 install schedule
    }
    
    python3 -c "import pandas" 2>/dev/null || {
        log_warn "pandas 库未安装，正在安装..."
        pip3 install pandas numpy requests python-dotenv
    }
    
    log_info "依赖检查完成"
}

# 安装 systemd 服务
install_service() {
    local user=$(get_current_user)
    local project_root=$(get_project_root)
    local python_path=$(get_python_path)
    local service_file="$project_root/docker/t0-weekly-screener.service"
    local dest_service_file="/etc/systemd/system/t0-weekly-screener.service"
    
    log_info "配置参数:"
    echo "  - 用户：$user"
    echo "  - 项目根目录：$project_root"
    echo "  - Python 路径：$python_path"
    echo "  - 服务文件：$service_file"
    
    # 检查服务文件是否存在
    if [ ! -f "$service_file" ]; then
        log_error "服务文件不存在：$service_file"
        exit 1
    fi
    
    # 更新服务文件中的路径
    log_info "更新服务文件..."
    cp "$service_file" "/tmp/t0-weekly-screener.service"
    
    # 替换用户名
    sed -i "s/^User=.*/User=$user/" "/tmp/t0-weekly-screener.service"
    sed -i "s/^Group=.*/Group=$user/" "/tmp/t0-weekly-screener.service"
    
    # 替换工作目录
    sed -i "s|^WorkingDirectory=.*|WorkingDirectory=$project_root|" "/tmp/t0-weekly-screener.service"
    
    # 替换 Python 路径
    sed -i "s|^ExecStart=.*|ExecStart=$python_path -m scripts.t0_weekly_scheduler --weekday monday --time 09:00|" "/tmp/t0-weekly-screener.service"
    
    # 复制到 systemd 目录
    log_info "安装服务到 systemd..."
    cp "/tmp/t0-weekly-screener.service" "$dest_service_file"
    
    # 重新加载 systemd
    log_info "重新加载 systemd 配置..."
    systemctl daemon-reload
    
    # 启用服务
    log_info "启用服务（开机自启）..."
    systemctl enable t0-weekly-screener
    
    # 启动服务
    log_info "启动服务..."
    systemctl start t0-weekly-screener
    
    # 显示状态
    echo ""
    log_info "服务安装完成！"
    show_status
}

# 显示服务状态
show_status() {
    echo ""
    log_info "服务状态:"
    systemctl status t0-weekly-screener --no-pager | head -20
    
    echo ""
    log_info "查看日志:"
    echo "  sudo journalctl -u t0-weekly-screener -f"
    
    echo ""
    log_info "管理命令:"
    echo "  停止服务：sudo systemctl stop t0-weekly-screener"
    echo "  重启服务：sudo systemctl restart t0-weekly-screener"
    echo "  禁用服务：sudo systemctl disable t0-weekly-screener"
    echo "  卸载服务：sudo rm /etc/systemd/system/t0-weekly-screener.service && sudo systemctl daemon-reload"
}

# 测试运行
test_run() {
    local project_root=$(get_project_root)
    
    log_info "测试运行选股任务（不带通知）..."
    cd "$project_root"
    python3 scripts/t0_stock_screener.py
    
    echo ""
    log_info "测试完成！检查结果文件:"
    ls -lh "$project_root/data/t0_stock_pool.csv"
}

# 测试通知
test_notification() {
    local project_root=$(get_project_root)
    
    log_info "测试运行选股任务（带飞书通知）..."
    cd "$project_root"
    python3 scripts/t0_stock_screener.py --notify
    
    echo ""
    log_info "测试完成！请检查飞书消息"
}

# 显示帮助
show_help() {
    echo "T+0 选股池周度任务部署脚本"
    echo ""
    echo "用法：$0 [选项]"
    echo ""
    echo "选项:"
    echo "  install     安装并启动 systemd 服务"
    echo "  status      显示服务状态"
    echo "  start       启动服务"
    echo "  stop        停止服务"
    echo "  restart     重启服务"
    echo "  test        测试运行选股任务（不带通知）"
    echo "  test-notify 测试运行选股任务（带飞书通知）"
    echo "  uninstall   卸载服务"
    echo "  help        显示此帮助信息"
    echo ""
    echo "示例:"
    echo "  sudo $0 install      # 安装服务"
    echo "  sudo $0 status       # 查看状态"
    echo "  sudo $0 test         # 测试运行"
    echo "  sudo $0 test-notify  # 测试通知"
    echo ""
}

# 主函数
main() {
    case "${1:-help}" in
        install)
            check_root
            check_dependencies
            install_service
            ;;
        status)
            show_status
            ;;
        start)
            check_root
            log_info "启动服务..."
            systemctl start t0-weekly-screener
            show_status
            ;;
        stop)
            check_root
            log_info "停止服务..."
            systemctl stop t0-weekly-screener
            ;;
        restart)
            check_root
            log_info "重启服务..."
            systemctl restart t0-weekly-screener
            show_status
            ;;
        test)
            test_run
            ;;
        test-notify)
            test_notification
            ;;
        uninstall)
            check_root
            log_warn "卸载服务将删除 systemd 服务文件..."
            read -p "确定继续吗？(y/N): " confirm
            if [ "$confirm" = "y" ] || [ "$confirm" = "Y" ]; then
                systemctl stop t0-weekly-screener || true
                systemctl disable t0-weekly-screener || true
                rm -f /etc/systemd/system/t0-weekly-screener.service
                systemctl daemon-reload
                log_info "服务已卸载"
            else
                log_info "取消卸载"
            fi
            ;;
        help|--help|-h)
            show_help
            ;;
        *)
            log_error "未知选项：$1"
            show_help
            exit 1
            ;;
    esac
}

main "$@"
