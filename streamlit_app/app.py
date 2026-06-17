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

# ── 全局 CSS（暗色金融主题 · 高对比度优化） ────────────────────────
st.markdown("""
<style>
    /* ══════════════════════════════════════════════════════════════════
       设计系统：暗色金融主题
       背景 #111827 | 卡片 #1F2937 | 边框 #374151
       主色 #F8FAFC   | 次要 #D1D5DB | 弱化 #9CA3AF
       ══════════════════════════════════════════════════════════════════ */

    /* ── 全局重置 ── */
    .stApp {
        background: #111827;
    }
    .stApp > header {
        background: transparent;
    }

    /* ── 正文基础 ── */
    p, li, .stMarkdown, .stText, .element-container {
        color: #D1D5DB;
    }

    /* ── 卡片容器 ── */
    div[data-testid="stVerticalBlockBorderer"] > div,
    .card {
        background: #1F2937;
        border: 1px solid #374151;
        border-radius: 12px;
        padding: 1.5rem;
        margin-bottom: 1rem;
        transition: border-color 0.2s ease;
    }
    div[data-testid="stVerticalBlockBorderer"] > div:hover,
    .card:hover {
        border-color: #4B5563;
    }

    /* ── 指标卡片 ── */
    div[data-testid="metric-container"] {
        background: #1F2937;
        border: 1px solid #374151;
        border-radius: 10px;
        padding: 1rem 1.25rem;
        box-shadow: 0 1px 3px rgba(0,0,0,0.3);
        transition: border-color 0.2s ease;
    }
    div[data-testid="metric-container"]:hover {
        border-color: #4B5563;
    }
    div[data-testid="metric-container"] > label {
        color: #D1D5DB !important;
        font-size: 0.85rem !important;
        font-weight: 500 !important;
        letter-spacing: 0.02em;
    }
    div[data-testid="metric-container"] > div[data-testid="metric-value"] {
        color: #F8FAFC !important;
        font-size: 1.8rem !important;
        font-weight: 700 !important;
        line-height: 1.2;
        letter-spacing: -0.02em;
    }

    /* ── 侧边栏 ── */
    section[data-testid="stSidebar"] {
        background: #111827;
        border-right: 1px solid #374151;
        min-width: 260px;
    }
    section[data-testid="stSidebar"] .stTitle {
        color: #F8FAFC;
    }
    section[data-testid="stSidebar"] .stCaption {
        color: #9CA3AF;
    }

    /* ── 按钮 ── */
    .stButton > button {
        background: #374151;
        border: 1px solid #4B5563;
        border-radius: 8px;
        color: #F8FAFC;
        font-weight: 600;
        transition: all 0.2s ease;
        cursor: pointer;
    }
    .stButton > button:hover {
        background: #4B5563;
        border-color: #6B7280;
        transform: translateY(-1px);
        box-shadow: 0 4px 12px rgba(0,0,0,0.3);
    }
    .stButton > button:active {
        transform: translateY(0);
    }
    .stButton > button[kind="primary"] {
        background: #059669;
        border-color: #059669;
        color: white;
    }
    .stButton > button[kind="primary"]:hover {
        background: #047857;
        border-color: #047857;
        transform: translateY(-1px);
        box-shadow: 0 4px 12px rgba(5,150,105,0.3);
    }

    /* ── 链接按钮（page_link） ── */
    .stLinkButton button {
        color: #60A5FA !important;
        font-weight: 500 !important;
        transition: color 0.2s ease;
    }
    .stLinkButton button:hover {
        color: #93C5FD !important;
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
        background: rgba(34,197,94,0.15);
        color: #4ADE80;
        border: 1px solid rgba(34,197,94,0.30);
    }
    .status-paper {
        background: rgba(251,191,36,0.15);
        color: #FBBF24;
        border: 1px solid rgba(251,191,36,0.30);
    }
    .status-prod {
        background: rgba(248,113,113,0.15);
        color: #F87171;
        border: 1px solid rgba(248,113,113,0.30);
    }

    /* ── 标题排版 ── */
    h1, h2, h3 {
        color: #F8FAFC !important;
        font-weight: 600 !important;
        letter-spacing: -0.02em;
    }
    h1 {
        font-size: 1.6rem !important;
        letter-spacing: -0.03em;
    }
    h2 {
        font-size: 1.25rem !important;
        border-bottom: 1px solid #374151;
        padding-bottom: 0.5rem;
        margin-bottom: 1rem;
    }
    h3 {
        font-size: 1.1rem !important;
    }
    .subtitle {
        color: #9CA3AF;
        font-size: 0.9rem;
        margin-top: -0.5rem;
        margin-bottom: 1.25rem;
    }

    /* ── Caption ── */
    .stCaption {
        color: #9CA3AF !important;
    }

    /* ── 分割线 ── */
    hr {
        border-color: #374151 !important;
        margin: 0.75rem 0 !important;
    }

    /* ── 代码／日志区域 ── */
    .log-container {
        background: #0F172A;
        border: 1px solid #374151;
        border-radius: 8px;
        padding: 1rem;
        font-family: 'JetBrains Mono', 'Fira Code', monospace;
        font-size: 0.8rem;
        line-height: 1.5;
        max-height: 600px;
        overflow-y: auto;
        white-space: pre-wrap;
        word-break: break-all;
        color: #E5E7EB;
    }
    .log-info  { color: #38BDF8; }
    .log-warn  { color: #FBBF24; }
    .log-error { color: #F87171; }
    .log-debug { color: #A78BFA; }

    /* ── Form 卡片 ── */
    div[data-testid="stForm"] {
        background: #1F2937;
        border: 1px solid #374151;
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
    .stAlert p {
        color: inherit !important;
    }

    /* ── 表格 ── */
    div[data-testid="stDataFrame"] {
        border: 1px solid #374151;
        border-radius: 8px;
        overflow: hidden;
    }
    div[data-testid="stDataFrame"] th {
        background: #1F2937 !important;
        color: #D1D5DB !important;
        font-size: 0.8rem !important;
        font-weight: 600 !important;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        padding: 0.75rem 1rem !important;
        border-bottom: 1px solid #374151 !important;
    }
    div[data-testid="stDataFrame"] td {
        background: transparent !important;
        color: #F3F4F6 !important;
        padding: 0.6rem 1rem !important;
        border-bottom: 1px solid rgba(55,65,81,0.5) !important;
    }

    /* ── 选择器 / 输入框 ── */
    div[data-baseweb="select"] > div {
        background: #374151 !important;
        border-color: #4B5563 !important;
        border-radius: 6px !important;
    }
    div[data-baseweb="input"] > div {
        background: #374151 !important;
        border-color: #4B5563 !important;
        border-radius: 6px !important;
    }
    div[data-baseweb="input"] input {
        color: #F8FAFC !important;
    }
    div[data-baseweb="input"] input::placeholder {
        color: #9CA3AF !important;
    }
    div[data-baseweb="textarea"] textarea {
        background: #374151 !important;
        border-color: #4B5563 !important;
        border-radius: 6px !important;
        color: #F8FAFC !important;
    }
    div[data-baseweb="textarea"] textarea::placeholder {
        color: #9CA3AF !important;
    }

    /* ── Select dropdown menu ── */
    div[data-baseweb="menu"] {
        background: #1F2937 !important;
        border: 1px solid #374151 !important;
    }
    div[data-baseweb="menu"] li {
        color: #D1D5DB !important;
        background: transparent !important;
    }
    div[data-baseweb="menu"] li:hover {
        background: #374151 !important;
    }

    /* ── Slider ── */
    div[data-testid="stSlider"] > div {
        padding-top: 0.5rem;
    }
    div[data-testid="stSlider"] div[role="slider"] {
        background-color: #059669 !important;
    }

    /* ── Tabs ── */
    .stTabs [data-baseweb="tab-list"] {
        gap: 2px;
        background: #1F2937;
        border-radius: 8px;
        padding: 4px;
    }
    .stTabs [data-baseweb="tab"] {
        color: #D1D5DB !important;
        border-radius: 6px;
        padding: 0.5rem 1rem;
        font-weight: 500;
    }
    .stTabs [data-baseweb="tab"][aria-selected="true"] {
        background: #374151 !important;
        color: #F8FAFC !important;
    }

    /* ── Checkbox / Radio ── */
    .stCheckbox label {
        color: #D1D5DB !important;
    }
    div[data-testid="stRadio"] label {
        color: #D1D5DB !important;
    }

    /* ── Code inline ── */
    code {
        color: #F8FAFC !important;
        background: #374151 !important;
        border-radius: 4px;
        padding: 1px 4px;
        font-size: 0.85em;
    }

    /* ── Success / Info / Warning / Error message text ── */
    .stSuccess p, .stInfo p, .stWarning p, .stError p {
        color: inherit !important;
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
    st.Page("pages/2_📈_Trading.py", title="交易中心", icon="📈"),
    st.Page("pages/3_🛡️_RiskConfig.py", title="风控配置", icon="🛡️"),
    st.Page("pages/4_📋_Strategy.py", title="策略管理", icon="📋"),
    st.Page("pages/5_⚙️_Settings.py", title="系统设置", icon="⚙️"),
    st.Page("pages/6_📝_Logs.py", title="运行日志", icon="📝"),
]

pg = st.navigation(pages, position="sidebar")
pg.run()
