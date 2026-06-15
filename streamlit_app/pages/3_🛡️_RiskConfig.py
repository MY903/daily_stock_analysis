"""
🛡️ 风控参数配置
================

只读展示当前运行时风控参数。修改需编辑 .env 文件后重启。
"""

import sys
from pathlib import Path

import streamlit as st

# ── 项目根路径 ──────────────────────────────────────────────────────
_root = Path(__file__).resolve().parent.parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

st.title("🛡️ 风控参数")
st.markdown('<p class="subtitle">当前运行时风险控制参数（只读）</p>', unsafe_allow_html=True)

# ── 加载设置 ────────────────────────────────────────────────────────
try:
    from config.settings import settings
except ImportError as e:
    st.error(f"❌ 导入 settings 模块失败: {e}")
    st.info("请确认项目根目录已包含 config/settings.py 且 .env 文件存在")
    st.stop()
except Exception as e:
    st.error(f"❌ 加载配置失败: {e}")
    st.stop()

# ── 风险参数分组 ────────────────────────────────────────────────────

st.markdown("### 📊 参数总览")

with st.container(border=True):
    c1, c2, c3 = st.columns(3)
    c1.metric("单标的最大仓位", f"{settings.RISK_MAX_POSITION_PCT}%", help="单个标的占总投资组合的最大百分比")
    c2.metric("每日最大亏损", f"{settings.RISK_MAX_DAILY_LOSS_PCT}%", help="当日累计最大可接受亏损百分比")
    c3.metric("信号有效期", f"{settings.RISK_SIGNAL_TTL_MINUTES} 分钟", help="交易信号生成后的有效时长")

with st.container(border=True):
    c1, c2, c3 = st.columns(3)
    c1.metric("单笔最大订单价值", f"${settings.RISK_MAX_ORDER_VALUE:,.0f}",
              help=" quantity × price 不得超过此值")
    c2.metric("每分钟最大下单数", str(settings.RISK_MAX_ORDERS_PER_MIN),
              help="同一标的每分钟最多下单次数")
    c3.metric("每日最大订单数", str(settings.RISK_MAX_DAILY_ORDERS),
              help="全局每日总订单数上限")

# ── 详细表格 ────────────────────────────────────────────────────────

st.markdown("### 📋 参数明细")

params_detail = [
    ("RISK_MAX_POSITION_PCT", f"{settings.RISK_MAX_POSITION_PCT}%", "单标的最高仓位占比"),
    ("RISK_MAX_DAILY_LOSS_PCT", f"{settings.RISK_MAX_DAILY_LOSS_PCT}%", "单日最大亏损占比"),
    ("RISK_MAX_ORDER_VALUE", f"${settings.RISK_MAX_ORDER_VALUE:,.0f}", "单笔订单最大价值（美元）"),
    ("RISK_MAX_ORDERS_PER_MIN", str(settings.RISK_MAX_ORDERS_PER_MIN), "同一标的每分钟最大下单次数"),
    ("RISK_MAX_DAILY_ORDERS", str(settings.RISK_MAX_DAILY_ORDERS), "每日最大总订单数"),
    ("RISK_SIGNAL_TTL_MINUTES", f"{settings.RISK_SIGNAL_TTL_MINUTES} 分钟", "交易信号有效时长，超时自动失效"),
    ("QUANT_DRY_RUN", str(settings.QUANT_DRY_RUN), "是否为 Dry-Run 模式（模拟交易不下真实订单）"),
    ("LOG_LEVEL", settings.LOG_LEVEL, "日志级别"),
]

import pandas as pd
df = pd.DataFrame(params_detail, columns=["参数名", "当前值", "说明"])
st.dataframe(df, use_container_width=True, hide_index=True)

# ── 如何修改 ────────────────────────────────────────────────────────

st.markdown("### ✏️ 如何修改")

with st.container(border=True):
    st.warning("⚠️ 这些参数为运行时只读设置，无法通过 UI 修改。")

    st.markdown("""
**修改步骤：**

1. 打开项目根目录下的 `.env` 文件
2. 找到对应的参数行进行修改，例如：
   ```ini
   RISK_MAX_POSITION_PCT=10.0
   RISK_MAX_DAILY_LOSS_PCT=5.0
   RISK_SIGNAL_TTL_MINUTES=15
   ```
3. 保存文件后**重新启动** Streamlit 应用使新值生效

> 💡 **提示**: 如果 `.env` 中未配置某参数，将使用 `config/settings.py` 中的默认值。
""")

# ── 当前环境信息 ────────────────────────────────────────────────────
st.divider()
st.markdown(f"""
<div style="color:#64748B;font-size:0.85rem;">
    当前环境: <code>{settings.TIGER_ENV}</code> ·
    交易模式: <code>{settings.TRADING_MODE.value}</code> ·
    自动交易: <code>{'开启' if settings.TRADING_AUTO_TRADE else '关闭'}</code> ·
    Dry-Run: <code>{'是' if settings.QUANT_DRY_RUN else '否'}</code>
</div>
""", unsafe_allow_html=True)
