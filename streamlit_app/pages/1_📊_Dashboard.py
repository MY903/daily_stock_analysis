"""
📊 系统仪表盘
=============

系统状态总览：运行模式、Tiger 连接状态、风控摘要、注册策略。
"""

import asyncio
import sys
from pathlib import Path

import streamlit as st

# ── 项目根路径 ──────────────────────────────────────────────────────
_root = Path(__file__).resolve().parent.parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

# ── 页面标题 ────────────────────────────────────────────────────────
st.title("📊 系统仪表盘")
st.markdown('<p class="subtitle">QuantWeasel AI 交易系统运行状态总览</p>', unsafe_allow_html=True)

# ── 缓存：Tiger 连接测试 ───────────────────────────────────────────

@st.cache_data(ttl=30, show_spinner="正在连接 Tiger API…")
def check_tiger_status():
    """测试 Tiger API 连接并获取账户摘要"""
    try:
        from src.trading.config import load_config
        from src.trading.tiger_client import TigerClient

        config = load_config()
        client = TigerClient(config)
        client.connect()
        summary = client.get_account_summary()
        market_status = client.get_market_status()
        client.disconnect()
        return {
            "ok": True,
            "summary": summary,
            "market_status": market_status,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── 缓存：账户资产 + 市场状态（自动加载） ─────────────────────────

@st.cache_data(ttl=30, show_spinner="正在加载账户数据…")
def _load_account_data():
    """自动加载 Tiger 账户资产与市场状态"""
    try:
        from src.trading.config import load_config
        from src.trading.tiger_client import TigerClient

        config = load_config()
        client = TigerClient(config)
        client.connect()
        summary = client.get_account_summary()
        market_status = client.get_market_status()
        client.disconnect()
        return {"ok": True, "summary": summary, "market_status": market_status}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ══════════════════════════════════════════════════════════════════════
# 🚀 快速上手 — 工作流引导
# ══════════════════════════════════════════════════════════════════════

with st.container(border=True):
    st.markdown("### 🚀 快速上手")
    st.markdown(
        '<p style="color:#94A3B8;font-size:0.85rem;margin:-8px 0 16px 0;">'
        "按顺序完成以下 5 步开始交易</p>",
        unsafe_allow_html=True,
    )

    # ── 状态检测 ──────────────────────────────────────────────────
    _qs_ad = _load_account_data()
    _tiger_ok = _qs_ad.get("ok", False)

    try:
        from config.settings import settings as _s

        _qs_mode = _s.TRADING_MODE.value
    except Exception:
        _qs_mode = "UNKNOWN"

    try:
        from src.trading.audit_logger import AuditLogger

        _qs_pending = AuditLogger().get_pending_signals()
        _qs_pending_n = len(_qs_pending)
    except Exception:
        _qs_pending_n = 0

    try:
        from src.trading.trade_recorder import TradeRecorder

        _qs_tr = TradeRecorder(data_dir=str(_root / "data"))
        _qs_trades = _qs_tr.get_today_trades()
        _qs_trade_n = len(_qs_trades)
    except Exception:
        _qs_trade_n = 0

    # ── 当前活跃步骤 ──────────────────────────────────────────────
    if not _tiger_ok:
        _qs_active = 0
    elif _qs_trade_n == 0 and _qs_pending_n == 0:
        _qs_active = 2
    elif _qs_pending_n > 0:
        _qs_active = 3
    elif _qs_trade_n > 0:
        _qs_active = 4
    else:
        _qs_active = 1

    # ── 步骤数据 ──────────────────────────────────────────────────
    _qs_icons = ["🔌", "⚙️", "📈", "✅", "📊"]
    _qs_titles = ["连接账户", "选择模式", "发送信号", "确认执行", "查看结果"]
    _qs_descs = [
        "连接 Tiger API 交易接口",
        "确认交易环境与运行模式",
        "创建并发送交易信号到系统",
        "审核风控结果，确认或拒绝",
        "查看持仓、盈亏与交易记录",
    ]

    # ── 渲染五列卡片 ──────────────────────────────────────────────
    _qs_cols = st.columns(5)
    for _i, _col in enumerate(_qs_cols):
        with _col:
            # ── 步骤视觉状态 ──────────────────────────────────────
            if _i < _qs_active:
                _badge = "✅"
                _border_cls = "completed"
                _head_color = "#22C55E"
            elif _i == _qs_active:
                _badge = "👉"
                _border_cls = "current"
                _head_color = "#60A5FA"
            else:
                _badge = "⬜"
                _border_cls = "future"
                _head_color = "#475569"

            with st.container(border=True):
                st.markdown(
                    f"<div style='text-align:center;font-size:1.5rem;line-height:1.3;'>{_badge}</div>",
                    unsafe_allow_html=True,
                )
                st.markdown(
                    f"<div style='text-align:center;color:{_head_color};"
                    f"font-size:0.7rem;font-weight:600;letter-spacing:0.5px;"
                    f"text-transform:uppercase;'>步骤 {_i + 1}</div>",
                    unsafe_allow_html=True,
                )
                st.markdown(
                    f"<div style='text-align:center;font-weight:600;color:#F1F5F9;"
                    f"font-size:0.9rem;margin:3px 0 2px 0;'>"
                    f"{_qs_icons[_i]} {_qs_titles[_i]}</div>",
                    unsafe_allow_html=True,
                )
                st.markdown(
                    f"<div style='text-align:center;color:#64748B;font-size:0.7rem;"
                    f"margin-bottom:8px;'>{_qs_descs[_i]}</div>",
                    unsafe_allow_html=True,
                )

                # ═══ 步骤 1: 连接账户 ═══
                if _i == 0:
                    if _tiger_ok:
                        st.markdown(
                            "<div style='text-align:center;color:#22C55E;font-size:0.75rem;"
                            "font-weight:500;'>✅ API 已连接</div>",
                            unsafe_allow_html=True,
                        )
                    else:
                        st.markdown(
                            "<div style='text-align:center;color:#FBBF24;font-size:0.75rem;"
                            "font-weight:500;'>🔌 需要连接</div>",
                            unsafe_allow_html=True,
                        )
                        if st.button(
                            "🔌 测试连接",
                            key="qs_connect_tiger",
                            use_container_width=True,
                        ):
                            _r = check_tiger_status()
                            if _r["ok"]:
                                st.success("✅ 连接成功")
                                st.rerun()
                            else:
                                st.error(f"❌ {_r.get('error', '未知错误')}")

                # ═══ 步骤 2: 选择模式 ═══
                elif _i == 1:
                    _mode_labels = {
                        "SANDBOX": "🟢 模拟环境",
                        "PAPER": "🟡 纸交验证",
                        "PROD": "🔴 实盘交易",
                    }
                    _qs_ml = _mode_labels.get(_qs_mode, _qs_mode)
                    st.markdown(
                        f"<div style='text-align:center;color:#E2E8F0;font-size:0.8rem;"
                        f"font-weight:500;'>{_qs_ml}</div>",
                        unsafe_allow_html=True,
                    )
                    if _qs_mode == "SANDBOX":
                        st.markdown(
                            "<div style='text-align:center;color:#FBBF24;font-size:0.7rem;"
                            "margin-top:2px;'>💡 模拟模式可切换</div>",
                            unsafe_allow_html=True,
                        )

                # ═══ 步骤 3: 发送信号 ═══
                elif _i == 2:
                    if _qs_trade_n > 0 or _qs_pending_n > 0:
                        st.markdown(
                            f"<div style='text-align:center;color:#22C55E;font-size:0.75rem;"
                            f"font-weight:500;'>✅ 已发送 {_qs_trade_n + _qs_pending_n} 个信号</div>",
                            unsafe_allow_html=True,
                        )
                    else:
                        st.markdown(
                            "<div style='text-align:center;color:#94A3B8;font-size:0.75rem;'>"
                            "尚未发送信号</div>",
                            unsafe_allow_html=True,
                        )
                    st.page_link(
                        "pages/2_📈_Trading.py",
                        label="📈 发信号",
                        use_container_width=True,
                    )

                # ═══ 步骤 4: 确认执行 ═══
                elif _i == 3:
                    if _qs_pending_n > 0:
                        st.markdown(
                            f"<div style='text-align:center;color:#FBBF24;font-size:0.75rem;"
                            f"font-weight:500;'>⏳ {_qs_pending_n} 个待确认</div>",
                            unsafe_allow_html=True,
                        )
                        st.page_link(
                            "pages/2_📈_Trading.py",
                            label="📋 去确认",
                            use_container_width=True,
                        )
                    else:
                        st.markdown(
                            "<div style='text-align:center;color:#22C55E;font-size:0.75rem;"
                            "font-weight:500;'>✅ 无待确认信号</div>",
                            unsafe_allow_html=True,
                        )
                        st.markdown(
                            "<div style='text-align:center;color:#64748B;font-size:0.7rem;'>"
                            "信号自动经风控检查后执行</div>",
                            unsafe_allow_html=True,
                        )

                # ═══ 步骤 5: 查看结果 ═══
                elif _i == 4:
                    if _qs_trade_n > 0:
                        st.markdown(
                            f"<div style='text-align:center;color:#22C55E;font-size:0.75rem;"
                            f"font-weight:500;'>📈 今日 {_qs_trade_n} 笔交易</div>",
                            unsafe_allow_html=True,
                        )
                    else:
                        st.markdown(
                            "<div style='text-align:center;color:#94A3B8;font-size:0.75rem;'>"
                            "暂无交易记录</div>",
                            unsafe_allow_html=True,
                        )
                    st.page_link(
                        "pages/2_📈_Trading.py",
                        label="📊 查看详情",
                        use_container_width=True,
                    )


# ── 第一行：运行模式 + Tiger 状态 ──────────────────────────────────
col1, col2 = st.columns(2)

with col1:
    with st.container(border=True):
        st.markdown("### ⚙️ 运行模式")

        try:
            from config.settings import settings

            mode = settings.TRADING_MODE.value
            cls = f"status-{mode.lower()}"
            label_map = {
                "SANDBOX": "🟢 模拟环境（SANDBOX）",
                "PAPER": "🟡 纸交验证（PAPER）",
                "PROD": "🔴 实盘交易（PROD）",
            }
            st.markdown(
                f'<div class="status-tag {cls}" style="font-size:1rem;padding:6px 20px;">'
                f'{label_map.get(mode, mode)}</div>',
                unsafe_allow_html=True,
            )
            st.markdown(
                f'<div style="margin-top:12px;color:#94A3B8;font-size:0.9rem;">'
                f'TIGER_ENV = <code style="color:#F1F5F9;">{settings.TIGER_ENV}</code></div>',
                unsafe_allow_html=True,
            )
        except ImportError as e:
            st.error(f"导入 settings 失败: {e}")
        except Exception as e:
            st.error(f"读取配置失败: {e}")

with col2:
    with st.container(border=True):
        st.markdown("### 🔌 Tiger API 连接")

        if st.button("🔄 测试 Tiger 连接", use_container_width=True, type="primary"):
            result = check_tiger_status()
            if result["ok"]:
                st.success("✅ 连接成功")
                summary = result["summary"]
                cols = st.columns(3)
                cols[0].metric("净资产", f"${summary.get('net_value', 0):,.2f}")
                cols[1].metric("现金", f"${summary.get('cash', 0):,.2f}")
                cols[2].metric("购买力", f"${summary.get('buying_power', 0):,.2f}")
                if result.get("market_status"):
                    st.info(f"📡 市场状态: {result['market_status']}")
            else:
                st.error(f"❌ 连接失败: {result.get('error', '未知错误')}")
        else:
            st.info("👆 点击按钮测试 Tiger API 连接")
            st.caption("连接成功后自动显示账户摘要")

# ══════════════════════════════════════════════════════════════════════
# 新增：账户资产 + 市场状态
# ══════════════════════════════════════════════════════════════════════

with st.container(border=True):
    rr1, rr2 = st.columns([6, 1])
    with rr1:
        st.markdown("### 💰 账户资产")
    with rr2:
        if st.button("🔄", key="refresh_assets", help="刷新账户数据"):
            st.cache_data.clear()
            st.rerun()

    _ad = _load_account_data()
    if _ad["ok"]:
        _s = _ad["summary"]
        ca1, ca2, ca3, ca4 = st.columns(4)
        ca1.metric("净资产", f"${_s.get('net_value', 0):,.2f}")
        ca2.metric("现金", f"${_s.get('cash', 0):,.2f}")
        ca3.metric("购买力", f"${_s.get('buying_power', 0):,.2f}")

        # 市场状态
        _status = _ad.get("market_status", "UNKNOWN")
        _icons = {"盘中": "🟢", "盘前": "🟡", "盘后": "🟠", "已收盘": "🔴"}
        _labels = {"盘中": "交易中", "盘前": "盘前", "盘后": "盘后", "已收盘": "已休市"}
        _icon = _icons.get(_status, "⚪")
        _label = _labels.get(_status, _status)
        ca4.markdown(
            f"""
            <div style="background:#0F172A;border:1px solid #1E293B;border-radius:10px;padding:1rem 1.25rem;">
                <div style="color:#94A3B8;font-size:0.85rem;font-weight:500;">📡 市场状态</div>
                <div style="display:flex;align-items:center;gap:8px;margin-top:6px;">
                    <span style="font-size:1.5rem;">{_icon}</span>
                    <span style="color:#F1F5F9;font-size:1.1rem;font-weight:600;">{_label}</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.warning(f"⚠️ 账户数据暂不可用: {_ad.get('error', '未知错误')}")
        st.caption("点击 🔄 按钮重试")

# ── 第三行：今日盈亏 + 待处理信号 + 交易统计 ──────────────────────

with st.container(border=True):
    st.markdown("### 📈 今日交易概览")
    td1, td2, td3 = st.columns(3)

    # 今日盈亏
    with td1:
        try:
            from src.trading.trade_recorder import TradeRecorder
            _tr = TradeRecorder(data_dir=str(_root / "data"))
            _pnl = _tr.get_today_pnl()
            _trades = _tr.get_today_trades()
            td1.metric("今日盈亏", f"${_pnl:+,.2f}", delta=_pnl)
            td1.caption(f"今日交易: {len(_trades)} 笔")
        except Exception as _e:
            td1.error("盈亏数据暂不可用")

    # 待处理信号
    with td2:
        try:
            from src.trading.audit_logger import AuditLogger
            _al = AuditLogger()
            _pending = _al.get_pending_signals()
            td2.metric("待处理信号", str(len(_pending)))
            if len(_pending) > 0:
                td2.page_link("pages/2_📈_Trading.py", label="前往交易页 →", icon="📈")
            else:
                td2.caption("暂无待处理信号")
        except Exception as _e:
            td2.error("信号数据暂不可用")

    # 交易统计
    with td3:
        try:
            _stats = AuditLogger().get_daily_stats()
            td3.metric("今日信号", str(_stats.get("total", 0)))
            td3.caption(
                f"✅ 成功: {_stats.get('executed', 0)}  ·  "
                f"❌ 失败: {_stats.get('failed', 0)}  ·  "
                f"⏳ 待处理: {_stats.get('pending', 0)}"
            )
        except Exception as _e:
            td3.error("统计数据暂不可用")

# ── 第四行：快速导航 ──────────────────────────────────────────────

st.markdown("### 🧭 快速导航")
n1, n2, n3, _ns = st.columns([2, 2, 2, 6])
with n1:
    st.page_link("pages/2_📈_Trading.py", label="📈 发信号", use_container_width=True)
with n2:
    st.page_link("pages/2_📈_Trading.py", label="💼 看持仓", use_container_width=True)
with n3:
    st.page_link("pages/3_🛡️_RiskConfig.py", label="🛡️ 风控", use_container_width=True)

# ── 第二行：风控参数摘要 ──────────────────────────────────────────

st.markdown("### 🛡️ 风控参数摘要")

try:
    from config.settings import settings as s

    risk_params = {
        "单标的最大仓位": f"{s.RISK_MAX_POSITION_PCT}%",
        "每日最大亏损": f"{s.RISK_MAX_DAILY_LOSS_PCT}%",
        "单笔最大订单价值": f"${s.RISK_MAX_ORDER_VALUE:,.0f}",
        "每分钟最大下单数": str(s.RISK_MAX_ORDERS_PER_MIN),
        "每日最大订单数": str(s.RISK_MAX_DAILY_ORDERS),
        "信号有效期": f"{s.RISK_SIGNAL_TTL_MINUTES} 分钟",
    }

    cols = st.columns(len(risk_params))
    for i, (label, value) in enumerate(risk_params.items()):
        cols[i].metric(label, value)

except ImportError as e:
    st.error(f"导入 settings 失败: {e}")
except Exception as e:
    st.error(f"读取风控参数失败: {e}")

# ── 第三行：注册策略列表 ──────────────────────────────────────────

st.markdown("### 📋 已注册策略")

try:
    from src.trading.strategy.registry import StrategyRegistry
    from src.trading.config import load_config

    strategies = StrategyRegistry.list_strategies()
    config = load_config()

    if strategies:
        for name in strategies:
            with st.container(border=True):
                c1, c2, c3 = st.columns([2, 3, 3])
                c1.markdown(f"**{name}**")
                c2.markdown(f"标的: `{config.trading.symbol}`")
                entry = config.trading.entry
                tp = config.trading.take_profit
                sl = config.trading.stop_loss
                c3.markdown(
                    f"触发价: ${entry.trigger_price} · "
                    f"止盈: {tp.percentage*100:.0f}% · "
                    f"止损: {sl.percentage*100:.0f}%"
                )
    else:
        st.info("暂未注册任何策略")

except ImportError as e:
    st.error(f"导入策略模块失败: {e}")
except Exception as e:
    st.error(f"查询策略失败: {e}")

# ── 底部：Auto-refresh ─────────────────────────────────────────────
st.divider()
auto_refresh = st.checkbox("🔄 自动刷新（每 30 秒）", value=False)
if auto_refresh:
    st.rerun(wait_seconds=60)
