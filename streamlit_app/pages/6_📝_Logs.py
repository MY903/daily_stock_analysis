"""
📝 运行日志
===========

实时查看日志文件内容，支持自动刷新和级别过滤。
"""

import sys
from pathlib import Path
from datetime import datetime

import streamlit as st

# ── 项目根路径 ──────────────────────────────────────────────────────
_root = Path(__file__).resolve().parent.parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

st.title("📝 运行日志")
st.markdown('<p class="subtitle">实时查看系统运行日志</p>', unsafe_allow_html=True)

# ── 初始化 Session State ────────────────────────────────────────────
if "log_auto_refresh" not in st.session_state:
    st.session_state.log_auto_refresh = False
if "log_level_filter" not in st.session_state:
    st.session_state.log_level_filter = "ALL"

# ── 查找日志文件 ────────────────────────────────────────────────────
log_dir = _root / "logs"
log_files = sorted(log_dir.glob("*.log")) if log_dir.exists() else []

if not log_files:
    st.warning("⚠️ 未找到日志文件")
    st.info(f"日志目录: {log_dir}")
    st.stop()

# ── 控制栏 ──────────────────────────────────────────────────────────
col1, col2, col3, col4 = st.columns([3, 2, 1, 2])

with col1:
    # 按修改时间排序，选最新的
    log_files_sorted = sorted(log_files, key=lambda p: p.stat().st_mtime, reverse=True)
    file_options = {f.name: p for p in log_files_sorted}
    selected_name = st.selectbox(
        "选择日志文件",
        options=list(file_options.keys()),
        index=0,
    )
    selected_file = file_options[selected_name]

with col2:
    level_filter = st.selectbox(
        "级别过滤",
        options=["ALL", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        index=0,
        key="log_level_filter",
    )

with col3:
    max_lines = st.number_input("行数", min_value=50, max_value=2000, value=200, step=50)

with col4:
    st.write("")  # spacer
    st.write("")  # spacer
    auto_refresh = st.toggle("🔄 自动刷新", value=st.session_state.log_auto_refresh,
                              key="log_auto_refresh")

# ── 文件信息 ────────────────────────────────────────────────────────
file_size = selected_file.stat().st_size
file_mtime = datetime.fromtimestamp(selected_file.stat().st_mtime)
st.caption(
    f"📄 `{selected_file.name}` · "
    f"大小: {file_size/1024:.1f} KB · "
    f"修改时间: {file_mtime.strftime('%Y-%m-%d %H:%M:%S')}"
)

# ── 读取并过滤日志 ──────────────────────────────────────────────────

def read_logs(file_path: Path, n_lines: int, level: str) -> str:
    """读取日志文件最后 N 行，按级别过滤"""
    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return f"[错误] 无法读取日志文件: {file_path}"

    lines = content.splitlines()
    tail = lines[-n_lines:] if len(lines) > n_lines else lines

    if level != "ALL":
        level_upper = level.upper()
        tail = [ln for ln in tail if level_upper in ln.upper()]

    return "\n".join(tail)


log_text = read_logs(selected_file, max_lines, level_filter)

# ── 渲染日志 ────────────────────────────────────────────────────────
if log_text.strip():
    # 简单的 ANSI / 颜色处理：按日志级别着色
    html_lines = []
    for line in log_text.split("\n"):
        if "ERROR" in line or "CRITICAL" in line:
            cls = "log-error"
        elif "WARNING" in line or "WARN" in line:
            cls = "log-warn"
        elif "DEBUG" in line:
            cls = "log-debug"
        else:
            cls = "log-info"
        # Escape HTML
        escaped = (
            line.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
        html_lines.append(f'<span class="{cls}">{escaped}</span>')

    html_content = "\n".join(html_lines)

    # 使用 st.markdown 渲染着色日志
    st.markdown(
        f'<div class="log-container">{html_content}</div>',
        unsafe_allow_html=True,
    )

    # 显示行数统计
    total_lines = len(log_text.split("\n"))
    st.caption(f"显示 {total_lines} 行")

else:
    st.info(f"未找到匹配级别 `{level_filter}` 的日志行")

# ── 操作按钮 ────────────────────────────────────────────────────────
col_a, col_b, col_c = st.columns([1, 1, 3])

with col_a:
    if st.button("🔄 刷新", use_container_width=True):
        st.rerun()

with col_b:
    if st.button("📋 复制全部", use_container_width=True):
        st.code(log_text, language="text")
        st.info("已显示为代码块（浏览器中可手动复制）")

# ── 自动刷新逻辑 ────────────────────────────────────────────────────
if auto_refresh:
    st.caption("⏳ 自动刷新中（每 10 秒）…")
    st.rerun(wait_seconds=10)
