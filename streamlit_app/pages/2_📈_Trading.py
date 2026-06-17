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

# ══════════════════════════════════════════════════════════════════════
# 新增功能：待确认信号 · 活跃订单 · 信号历史
# ══════════════════════════════════════════════════════════════════════

# ── 待确认信号 ──────────────────────────────────────────────────────

st.markdown("### ⏳ 待确认信号")
st.markdown('<p class="subtitle">已推送至飞书、等待人工确认的交易信号</p>', unsafe_allow_html=True)

try:
    from src.trading.audit_logger import AuditLogger
    from src.trading.signal import Signal, ConfirmResult, ConfirmAction

    al = AuditLogger()
    pending = al.get_pending_signals()

    if pending:
        # 解析 signal_json 提取完整字段
        parsed = []
        for row in pending:
            try:
                sig = Signal.model_validate_json(row["signal_json"])
                parsed.append({
                    "signal_id": row["signal_id"],
                    "created_at": row["created_at"],
                    "symbol": sig.symbol,
                    "action": sig.action.value,
                    "quantity": sig.quantity,
                    "price_target": sig.price_target,
                    "confidence": sig.confidence,
                    "rationale": sig.rationale,
                })
            except Exception:
                # 降级：直接从表字段读取
                parsed.append({
                    "signal_id": row["signal_id"],
                    "created_at": row["created_at"],
                    "symbol": row["symbol"],
                    "action": row["action"],
                    "quantity": None,
                    "price_target": None,
                    "confidence": None,
                    "rationale": "",
                })

        # ── 表头 ──
        hdr = st.columns([1.5, 0.9, 0.8, 0.8, 1, 1, 3, 1.1, 1.1])
        hdr[0].markdown("**创建时间**")
        hdr[1].markdown("**标的**")
        hdr[2].markdown("**方向**")
        hdr[3].markdown("**数量**")
        hdr[4].markdown("**目标价**")
        hdr[5].markdown("**信心**")
        hdr[6].markdown("**理由**")
        hdr[7].markdown("**确认**")
        hdr[8].markdown("**拒绝**")

        st.divider()

        # ── 数据行 ──
        for item in parsed:
            cols = st.columns([1.5, 0.9, 0.8, 0.8, 1, 1, 3, 1.1, 1.1])

            cols[0].text(item["created_at"][:16] if item.get("created_at") else "—")

            cols[1].text(item["symbol"] or "—")

            a = item["action"]
            if a == "BUY":
                cols[2].markdown('**:green[BUY]**', unsafe_allow_html=True)
            elif a == "SELL":
                cols[2].markdown('**:red[SELL]**', unsafe_allow_html=True)
            else:
                cols[2].markdown('**:gray[HOLD]**', unsafe_allow_html=True)

            cols[3].text(str(item["quantity"]) if item.get("quantity") else "—")
            cols[4].text(f"{item['price_target']:.2f}" if item.get("price_target") else "—")
            cols[5].text(f"{item['confidence']:.2f}" if item.get("confidence") is not None else "—")

            rationale = item.get("rationale") or ""
            cols[6].text(rationale[:50] + "…" if len(rationale) > 50 else rationale)

            confirm_key = f"confirm_{item['signal_id']}"
            reject_key = f"reject_{item['signal_id']}"

            if cols[7].button("✅", key=confirm_key, help="确认执行此信号"):
                with st.spinner("⏳ 正在处理确认信号…"):
                    try:
                        from src.trading.pipeline import QuantWeaselPipeline
                        pipeline = QuantWeaselPipeline()
                        result = asyncio.run(pipeline.process_confirmed_signal(item["signal_id"]))
                        if result.get("success"):
                            st.success("✅ 信号已确认并执行！")
                        else:
                            st.warning(f"⚠️ {result.get('message', '处理完成但返回未知状态')}")
                    except Exception as e:
                        st.error(f"❌ 确认处理失败: {e}")
                st.rerun()

            if cols[8].button("❌", key=reject_key, help="拒绝此信号"):
                try:
                    confirm_result = ConfirmResult(
                        signal_id=item["signal_id"],
                        action=ConfirmAction.REJECT,
                        user_id="streamlit_user",
                    )
                    al.log_confirmed(item["signal_id"], confirm_result)
                    st.success("✅ 信号已拒绝")
                except Exception as e:
                    st.error(f"❌ 拒绝失败: {e}")
                st.rerun()
    else:
        st.info("📭 暂无待确认信号")

except Exception as e:
    st.warning(f"加载待确认信号失败: {e}")

# ── 活跃订单 ────────────────────────────────────────────────────────

st.markdown("### 📋 活跃订单")
st.markdown('<p class="subtitle">Tiger 交易端当前未成交或部分成交的订单</p>', unsafe_allow_html=True)

try:
    from src.trading.config import load_config
    from src.trading.tiger_client import TigerClient

    config = load_config()
    tc = TigerClient(config)

    with st.spinner("⏳ 连接 Tiger API 获取活跃订单…"):
        tc.connect()
        orders = tc.get_active_orders()

    if orders:
        # 统一转为 dict 并摘录关键字段
        display_rows = []
        for o in orders:
            if not isinstance(o, dict):
                o = {k: v for k, v in vars(o).items() if not k.startswith("_")} if hasattr(o, '__dict__') else {}
            display_rows.append({
                "order_id": o.get("id", o.get("order_id", "—")),
                "symbol": o.get("symbol", "—"),
                "action": o.get("action", "—"),
                "quantity": o.get("quantity", o.get("total_quantity", "—")),
                "filled": o.get("filled", o.get("filled_quantity", 0)),
                "price": o.get("limit_price", o.get("price", "—")),
                "status": o.get("status", "—"),
            })

        # 表头
        hdr2 = st.columns([1, 1.5, 1, 1, 1, 1.2, 1.5, 1])
        hdr2[0].markdown("**订单 ID**")
        hdr2[1].markdown("**标的**")
        hdr2[2].markdown("**方向**")
        hdr2[3].markdown("**数量**")
        hdr2[4].markdown("**已成交**")
        hdr2[5].markdown("**价格**")
        hdr2[6].markdown("**状态**")
        hdr2[7].markdown("**取消**")

        st.divider()

        for o in display_rows:
            cols2 = st.columns([1, 1.5, 1, 1, 1, 1.2, 1.5, 1])
            cols2[0].text(str(o["order_id"]))
            cols2[1].text(o["symbol"])
            a2 = o["action"]
            if a2 == "BUY":
                cols2[2].markdown('**:green[BUY]**', unsafe_allow_html=True)
            elif a2 == "SELL":
                cols2[2].markdown('**:red[SELL]**', unsafe_allow_html=True)
            else:
                cols2[2].text(str(a2))
            cols2[3].text(str(o["quantity"]))
            cols2[4].text(str(o["filled"]))
            cols2[5].text(str(o["price"]))

            status_str = str(o["status"])
            if "illed" in status_str or "Filled" in status_str:
                cols2[6].markdown(f'**:green[{status_str}]**', unsafe_allow_html=True)
            elif "Submit" in status_str or "Initial" in status_str:
                cols2[6].markdown(f'**:orange[{status_str}]**', unsafe_allow_html=True)
            else:
                cols2[6].text(status_str)

            cancel_key = f"cancel_{o['order_id']}"
            if cols2[7].button("🗑️", key=cancel_key, help="取消此订单"):
                with st.spinner("⏳ 正在取消订单…"):
                    try:
                        success = tc.cancel_order(int(o["order_id"]))
                        if success:
                            st.success(f"✅ 订单 {o['order_id']} 已取消")
                        else:
                            st.error(f"❌ 取消订单 {o['order_id']} 失败")
                    except Exception as e:
                        st.error(f"❌ 取消失败: {e}")
                st.rerun()

    else:
        st.info("📭 暂无活跃订单")

    tc.disconnect()

except Exception as e:
    st.warning(f"加载活跃订单失败: {e}")

# ── 信号历史 ────────────────────────────────────────────────────────

st.markdown("### 📜 信号历史")
st.markdown('<p class="subtitle">所有交易信号的完整生命周期记录</p>', unsafe_allow_html=True)

try:
    from src.trading.audit_logger import AuditLogger
    from src.trading.signal import Signal

    al = AuditLogger()

    # ── 状态筛选 ──
    status_options = ["全部", "PENDING", "CONFIRMED", "EXECUTED", "REJECTED", "FAILED", "EXPIRED"]
    col_filter, col_page_info, _ = st.columns([2, 2, 4])

    with col_filter:
        selected_status = st.selectbox(
            "按状态筛选",
            options=status_options,
            index=0,
            key="history_status_filter",
        )
    filter_status = None if selected_status == "全部" else selected_status

    # 筛选变化时重置到第一页
    if "history_filter_prev" not in st.session_state:
        st.session_state.history_filter_prev = selected_status
    if selected_status != st.session_state.history_filter_prev:
        st.session_state.history_filter_prev = selected_status
        st.session_state.history_page = 0

    # ── 分页 ──
    PAGE_SIZE = 50
    if "history_page" not in st.session_state:
        st.session_state.history_page = 0

    offset = st.session_state.history_page * PAGE_SIZE

    # 多取一条以判断是否有下一页
    all_signals = al.get_all_signals(limit=PAGE_SIZE + 1, offset=offset, status=filter_status)
    has_next = len(all_signals) > PAGE_SIZE
    all_signals = all_signals[:PAGE_SIZE]

    if all_signals:
        # 解析数据
        history_rows = []
        for row in all_signals:
            try:
                sig = Signal.model_validate_json(row["signal_json"])
                history_rows.append({
                    "created_at": row["created_at"][:16] if row.get("created_at") else "—",
                    "symbol": sig.symbol,
                    "action": sig.action.value,
                    "quantity": sig.quantity if sig.quantity else "—",
                    "price": f"{sig.price_target:.2f}" if sig.price_target else "—",
                    "confidence": f"{sig.confidence:.2f}",
                    "rationale": (sig.rationale[:30] + "…") if sig.rationale and len(sig.rationale) > 30 else (sig.rationale or ""),
                    "status": row["status"],
                    "signal_id": row["signal_id"][:8],
                })
            except Exception:
                history_rows.append({
                    "created_at": row.get("created_at", "—")[:16] if row.get("created_at") else "—",
                    "symbol": row.get("symbol", "—"),
                    "action": row.get("action", "—"),
                    "quantity": "—",
                    "price": "—",
                    "confidence": "—",
                    "rationale": "",
                    "status": row.get("status", "—"),
                    "signal_id": row.get("signal_id", "—")[:8],
                })

        # 状态着色
        def fmt_status(status):
            badge_map = {
                "PENDING": "🟡 PENDING",
                "CONFIRMED": "🔵 CONFIRMED",
                "EXECUTED": "🟢 EXECUTED",
                "REJECTED": "🔴 REJECTED",
                "FAILED": "🔴 FAILED",
                "EXPIRED": "⚪ EXPIRED",
            }
            return badge_map.get(status, status)

        for row in history_rows:
            row["status"] = fmt_status(row["status"])

        import pandas as pd
        df = pd.DataFrame(history_rows)

        st.dataframe(
            df,
            column_config={
                "created_at": st.column_config.TextColumn("创建时间", width="small"),
                "symbol": st.column_config.TextColumn("标的", width="small"),
                "action": st.column_config.TextColumn("方向", width="small"),
                "quantity": st.column_config.TextColumn("数量", width="small"),
                "price": st.column_config.TextColumn("目标价", width="small"),
                "confidence": st.column_config.TextColumn("信心", width="small"),
                "rationale": st.column_config.TextColumn("理由", width="medium"),
                "status": st.column_config.TextColumn("状态", width="small"),
                "signal_id": st.column_config.TextColumn("信号 ID", width="small"),
            },
            use_container_width=True,
            hide_index=True,
        )

        # ── 分页控件 ──
        prev_col, info_col, next_col = st.columns([1, 3, 1])
        with prev_col:
            if st.session_state.history_page > 0:
                if st.button("◀ 上一页", use_container_width=True):
                    st.session_state.history_page -= 1
                    st.rerun()
        with info_col:
            st.markdown(
                f"<p style='text-align:center;margin-top:4px'>第 {st.session_state.history_page + 1} 页</p>",
                unsafe_allow_html=True,
            )
        with next_col:
            if has_next:
                if st.button("下一页 ▶", use_container_width=True):
                    st.session_state.history_page += 1
                    st.rerun()
    else:
        st.info("📭 暂无信号记录")

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
