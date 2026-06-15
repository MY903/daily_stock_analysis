"""
QuantWeasel AI 量化交易系统 — Streamlit 入口
=============================================

多页面导航入口，所有子页面通过 st.navigation 加载。
"""

import sys
from pathlib import Path

import streamlit as st

# ── 项目根目录加入 sys.path ──────────────────────────────────────────
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

# ── 页面配置 ─────────────────────────────────────────────────────────
st.set_page_config(
    page_title="QuantWeasel AI 交易系统",
    page_icon="🐍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── 全局 CSS（暗色金融主题） ────────────────────────────────────────
st.markdown("""
<style>
    /* ── 全局重置 ── */
    .stApp {
        background: #0B1120;
    }
    .stApp > header {
        background: transparent;
    }

    /* ── 卡片容器 ── */
    div[data-testid="stVerticalBlockBorderer"] > div,
    .card {
        background: #0F172A;
        border: 1px solid #1E293B;
        border-radius: 12px;
        padding: 1.25rem;
        margin-bottom: 1rem;
    }

    /* ── 指标卡片 ── */
    div[data-testid="metric-container"] {
        background: #0F172A;
        border: 1px solid #1E293B;
        border-radius: 10px;
        padding: 1rem 1.25rem;
        box-shadow: 0 1px 3px rgba(0,0,0,0.3);
    }
    div[data-testid="metric-container"] > label {
        color: #94A3B8 !important;
        font-size: 0.85rem !important;
        font-weight: 500 !important;
    }
    div[data-testid="metric-container"] > div[data-testid="metric-value"] {
        color: #F1F5F9 !important;
        font-size: 1.75rem !important;
        font-weight: 700 !important;
    }

    /* ── 侧边栏 ── */
    section[data-testid="stSidebar"] {
        background: #0B1120;
        border-right: 1px solid #1E293B;
        min-width: 260px;
    }
    section[data-testid="stSidebar"] .stTitle {
        color: #F1F5F9;
    }
    section[data-testid="stSidebar"] .stCaption {
        color: #64748B;
    }

    /* ── 按钮 ── */
    .stButton > button {
        background: #1E293B;
        border: 1px solid #334155;
        border-radius: 8px;
        color: #F1F5F9;
        font-weight: 600;
        transition: all 0.2s;
    }
    .stButton > button:hover {
        background: #334155;
        border-color: #475569;
    }
    .stButton > button[kind="primary"] {
        background: #059669;
        border-color: #059669;
        color: white;
    }
    .stButton > button[kind="primary"]:hover {
        background: #047857;
        border-color: #047857;
    }

    /* ── 状态标签 ── */
    .status-tag {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 2px 14px;
        border-radius: 20px;
        font-size: 0.85rem;
        font-weight: 600;
        letter-spacing: 0.3px;
    }
    .status-sandbox {
        background: rgba(34,197,94,0.12);
        color: #22C55E;
        border: 1px solid rgba(34,197,94,0.25);
    }
    .status-paper {
        background: rgba(245,158,11,0.12);
        color: #F59E0B;
        border: 1px solid rgba(245,158,11,0.25);
    }
    .status-prod {
        background: rgba(239,68,68,0.12);
        color: #EF4444;
        border: 1px solid rgba(239,68,68,0.25);
    }

    /* ── 标题排版 ── */
    h1, h2, h3 {
        color: #F1F5F9 !important;
        font-weight: 600 !important;
    }
    h1 {
        font-size: 1.6rem !important;
        letter-spacing: -0.3px;
    }
    h2 {
        font-size: 1.25rem !important;
        border-bottom: 1px solid #1E293B;
        padding-bottom: 0.5rem;
        margin-bottom: 1rem;
    }
    .subtitle {
        color: #64748B;
        font-size: 0.9rem;
        margin-top: -0.5rem;
        margin-bottom: 1.25rem;
    }

    /* ── 分割线 ── */
    hr {
        border-color: #1E293B !important;
        margin: 0.75rem 0 !important;
    }

    /* ── 代码／日志区域 ── */
    .log-container {
        background: #020617;
        border: 1px solid #1E293B;
        border-radius: 8px;
        padding: 1rem;
        font-family: 'JetBrains Mono', 'Fira Code', monospace;
        font-size: 0.8rem;
        line-height: 1.5;
        max-height: 600px;
        overflow-y: auto;
        white-space: pre-wrap;
        word-break: break-all;
        color: #CBD5E1;
    }
    .log-info  { color: #38BDF8; }
    .log-warn  { color: #FBBF24; }
    .log-error { color: #F87171; }
    .log-debug { color: #A78BFA; }

    /* ── Form 卡片 ── */
    div[data-testid="stForm"] {
        background: #0F172A;
        border: 1px solid #1E293B;
        border-radius: 12px;
        padding: 1.5rem;
    }
    div[data-testid="stForm"] > div {
        gap: 0.75rem;
    }

    /* ── 信息／警告／错误框 ── */
    .stAlert {
        border-radius: 8px !important;
        border-left-width: 4px !important;
    }

    /* ── 表格 ── */
    div[data-testid="stDataFrame"] {
        border: 1px solid #1E293B;
        border-radius: 8px;
        overflow: hidden;
    }
    div[data-testid="stDataFrame"] th {
        background: #0F172A !important;
        color: #94A3B8 !important;
        font-size: 0.8rem !important;
        font-weight: 600 !important;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        padding: 0.75rem 1rem !important;
        border-bottom: 1px solid #1E293B !important;
    }
    div[data-testid="stDataFrame"] td {
        background: transparent !important;
        color: #E2E8F0 !important;
        padding: 0.6rem 1rem !important;
        border-bottom: 1px solid rgba(30,41,59,0.5) !important;
    }

    /* ── 选择器 ── */
    div[data-baseweb="select"] > div {
        background: #1E293B !important;
        border-color: #334155 !important;
        border-radius: 6px !important;
    }
    div[data-baseweb="input"] > div {
        background: #1E293B !important;
        border-color: #334155 !important;
        border-radius: 6px !important;
    }
    div[data-baseweb="input"] input {
        color: #F1F5F9 !important;
    }
    div[data-baseweb="textarea"] textarea {
        background: #1E293B !important;
        border-color: #334155 !important;
        border-radius: 6px !important;
        color: #F1F5F9 !important;
    }

    /* ── Slider ── */
    div[data-testid="stSlider"] > div {
        padding-top: 0.5rem;
    }
    div[data-testid="stSlider"] div[role="slider"] {
        background-color: #059669 !important;
    }
</style>
""", unsafe_allow_html=True)

# ── 侧边栏 ───────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div style="display:flex;align-items:center;gap:12px;margin-bottom:4px;">
        <span style="font-size:2rem;">🐍</span>
        <div>
            <div style="font-size:1.3rem;font-weight:700;color:#F1F5F9;">QuantWeasel</div>
            <div style="font-size:0.8rem;color:#64748B;">AI 量化交易系统</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.divider()

    # 尝试导入并显示当前模式
    try:
        from config.settings import settings
        mode = settings.TRADING_MODE.value
        cls = f"status-{mode.lower()}"
        label = {"SANDBOX": "🟢 模拟环境", "PAPER": "🟡 纸交环境", "PROD": "🔴 实盘环境"}
        st.markdown(
            f'<div style="padding:0 0 1rem 0;">'
            f'<div class="status-tag {cls}">{label.get(mode, mode)}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
    except Exception:
        pass

    st.caption("v1.0.0 · Streamlit UI")

# ── 多页面导航 ──────────────────────────────────────────────────────
pages = [
    st.Page("pages/1_📊_Dashboard.py", title="仪表盘", icon="📊"),
    st.Page("pages/2_📈_Trading.py", title="交易", icon="📈"),
    st.Page("pages/3_🛡️_RiskConfig.py", title="风控配置", icon="🛡️"),
    st.Page("pages/4_📋_Strategy.py", title="策略管理", icon="📋"),
    st.Page("pages/5_📝_Logs.py", title="运行日志", icon="📝"),
]

pg = st.navigation(pages, position="sidebar")
pg.run()
