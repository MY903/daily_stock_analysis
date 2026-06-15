"""
📋 策略管理
===========

查看已注册的交易策略及其配置参数。
"""

import sys
from pathlib import Path

import streamlit as st

# ── 项目根路径 ──────────────────────────────────────────────────────
_root = Path(__file__).resolve().parent.parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

st.title("📋 策略管理")
st.markdown('<p class="subtitle">查看已注册的交易策略及实时配置参数</p>', unsafe_allow_html=True)

# ── 加载策略注册表 ──────────────────────────────────────────────────
try:
    from src.trading.strategy.registry import StrategyRegistry
    from src.trading.config import load_config
except ImportError as e:
    st.error(f"❌ 导入策略模块失败: {e}")
    st.stop()

# ── 列出所有策略 ────────────────────────────────────────────────────

strategies = StrategyRegistry.list_strategies()
config = load_config()

if not strategies:
    st.warning("⚠️ 当前未注册任何策略")
    st.info("请在代码中使用 `@StrategyRegistry.register` 注册策略类")
    st.stop()

st.markdown(f"**共 {len(strategies)} 个已注册策略**")

# ── 为每个策略展示详情卡片 ──────────────────────────────────────────
for name in strategies:
    with st.container(border=True):
        # 头部
        c1, c2 = st.columns([3, 1])
        c1.markdown(f"### 🎯 {name}")

        try:
            cls = StrategyRegistry.get(name)
            c2.markdown(
                f'<div style="text-align:right;color:#64748B;font-size:0.85rem;">'
                f'<span style="color:#22C55E;">●</span> 已注册 · '
                f'<code style="color:#94A3B8;">{cls.__name__}</code>'
                f'</div>',
                unsafe_allow_html=True,
            )
        except KeyError:
            c2.markdown(
                '<div style="text-align:right;color:#EF4444;">⚠️ 状态未知</div>',
                unsafe_allow_html=True,
            )

        # ── TQQQ-Swing 特殊处理：展示详细策略参数 ──────────────
        if name == "TQQQ-Swing":
            trading = config.trading

            st.markdown("---")
            st.markdown("**策略参数**")

            col1, col2, col3 = st.columns(3)

            with col1:
                st.markdown("##### 买入配置 (Entry)")
                entry = trading.entry
                st.metric("触发价格", f"${entry.trigger_price}")
                st.metric("触发百分比", f"{entry.trigger_percentage*100:.0f}%")
                st.metric("买入数量", f"{entry.quantity} 股")
                st.metric("订单类型", entry.order_type)
                st.metric("有效期限", entry.time_in_force)

            with col2:
                st.markdown("##### 止盈配置 (Take Profit)")
                tp = trading.take_profit
                st.metric("止盈百分比", f"{tp.percentage*100:.0f}%")
                st.metric("订单类型", tp.order_type)
                st.metric("有效期限", tp.time_in_force)

            with col3:
                st.markdown("##### 止损配置 (Stop Loss)")
                sl = trading.stop_loss
                st.metric("止损百分比", f"{sl.percentage*100:.0f}%")
                st.metric("订单类型", sl.order_type)
                st.metric("限价偏移", f"{sl.limit_offset*100:.1f}%")
                st.metric("有效期限", sl.time_in_force)

            # 当前运行环境
            st.markdown("---")
            from config.settings import settings

            auto_trade = "✅ 开启" if settings.TRADING_AUTO_TRADE else "❌ 关闭"
            st.markdown(
                f"**自动交易**: {auto_trade} &nbsp;·&nbsp; "
                f"**交易标的**: `{trading.symbol}` &nbsp;·&nbsp; "
                f"**市场**: `{trading.market}`"
            )

        elif name:
            # 通用策略展示
            st.markdown("---")
            st.markdown(f"**标的**: `{config.trading.symbol}`")

            import pandas as pd
            try:
                df = pd.DataFrame([
                    {"参数": "自动交易", "值": "✅ 开启" if config.trading.auto_trade else "❌ 关闭"},
                    {"参数": "交易标的", "值": config.trading.symbol},
                    {"参数": "市场", "值": config.trading.market},
                ])
                st.dataframe(df, use_container_width=True, hide_index=True)
            except Exception:
                pass

# ── 底部信息 ────────────────────────────────────────────────────────
st.divider()
st.caption(
    "策略通过 `@StrategyRegistry.register` 装饰器注册，"
    "配置文件路径: `config/trading.yaml`"
)
