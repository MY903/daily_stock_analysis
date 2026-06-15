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
    st.rerun(60)
