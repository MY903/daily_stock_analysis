"""
📈 手动交易
===========

发送交易信号到 QuantWeasel 管道，查看最近信号历史。
"""

import asyncio
import sys
from pathlib import Path

import streamlit as st

# ── 项目根路径 ──────────────────────────────────────────────────────
_root = Path(__file__).resolve().parent.parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

st.title("📈 手动交易")
st.markdown('<p class="subtitle">构造并推送交易信号到 QuantWeasel 管道</p>', unsafe_allow_html=True)

# ── 信号表单 ────────────────────────────────────────────────────────

with st.form("signal_form", clear_on_submit=False):
    st.markdown("### ✏️ 新建交易信号")

    col1, col2 = st.columns(2)

    with col1:
        symbol = st.text_input("交易标的", value="TQQQ", help="股票代码，如 TQQQ、SOXL")
        action = st.radio(
            "交易方向",
            options=["BUY", "SELL", "HOLD"],
            horizontal=True,
            index=0,
            help="BUY=买入, SELL=卖出, HOLD=持仓观望",
        )

    with col2:
        quantity = st.number_input(
            "数量（股）",
            min_value=1,
            max_value=10000,
            value=35,
            step=5,
            help="买入/卖出股数",
        )
        confidence = st.slider(
            "信心指数",
            min_value=0.0,
            max_value=1.0,
            value=0.85,
            step=0.05,
            help="0.0 = 最低信心, 1.0 = 最高信心",
        )

    rationale = st.text_area(
        "交易理由",
        value="",
        placeholder="输入此交易信号的逻辑依据…",
        height=100,
    )

    submitted = st.form_submit_button("🚀 发送信号", use_container_width=True, type="primary")

# ── 处理表单提交 ────────────────────────────────────────────────────

if submitted:
    with st.spinner("⏳ 正在生成并推送交易信号…"):
        try:
            from src.trading.pipeline import QuantWeaselPipeline
            from src.trading.signal import SignalAction

            async def _send():
                pipeline = QuantWeaselPipeline()
                result = await pipeline.generate_and_push_signal(
                    symbol=symbol,
                    action=action,
                    quantity=quantity,
                    confidence=confidence,
                    rationale=rationale or f"手动触发 {symbol} {action}",
                )
                return result

            result = asyncio.run(_send())

            if result:
                st.success(f"✅ 信号已成功推送！")
                st.json({
                    "signal_id": result.signal_id,
                    "symbol": result.symbol,
                    "action": result.action.value,
                    "quantity": result.quantity,
                    "confidence": result.confidence,
                    "rationale": result.rationale,
                    "status": result.status.value,
                    "created_at": str(result.created_at),
                })
            else:
                st.error("❌ 信号推送失败（返回空），请检查日志")

        except Exception as e:
            st.error(f"❌ 发送信号时出错: {e}")
            st.exception(e)

# ── 最近信号历史 ────────────────────────────────────────────────────

st.markdown("### 📜 最近信号记录")

try:
    import sqlite3
    from datetime import datetime

    db_path = _root / "data" / "audit_log.db"

    if db_path.exists():
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            "SELECT signal_id, symbol, action, status, created_at, pushed_at, executed_at "
            "FROM signal_audit ORDER BY created_at DESC LIMIT 20"
        )
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()

        if rows:
            import pandas as pd
            df = pd.DataFrame(rows)

            # 美化显示
            def _fmt(v):
                if v is None:
                    return "—"
                try:
                    dt = datetime.fromisoformat(v) if isinstance(v, str) else v
                    return dt.strftime("%m-%d %H:%M")
                except Exception:
                    return str(v)[:16]

            df["created_at"] = df["created_at"].apply(_fmt)
            df["pushed_at"] = df["pushed_at"].apply(_fmt)
            df["executed_at"] = df["executed_at"].apply(_fmt)

            df = df.rename(columns={
                "signal_id": "信号 ID",
                "symbol": "标的",
                "action": "方向",
                "status": "状态",
                "created_at": "创建时间",
                "pushed_at": "推送时间",
                "executed_at": "执行时间",
            })
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("暂无信号记录")
    else:
        st.info("审计日志数据库尚未创建（首次发送信号后将自动生成）")

except ImportError:
    st.info("pandas 未安装，信号历史表格不可用（pip install pandas）")
except Exception as e:
    st.warning(f"加载信号历史失败: {e}")

# ── 运行模式提示 ────────────────────────────────────────────────────
st.divider()
try:
    from config.settings import settings
    mode = settings.TRADING_MODE.value
    if mode == "SANDBOX":
        st.info("🟢 当前为 **模拟环境（SANDBOX）**，信号将记录但不产生真实订单")
    elif mode == "PAPER":
        st.warning("🟡 当前为 **纸交环境（PAPER）**，信号将发送飞书通知并模拟下单")
    else:
        st.error("🔴 当前为 **实盘环境（PROD）**，请谨慎操作")
except Exception:
    pass
