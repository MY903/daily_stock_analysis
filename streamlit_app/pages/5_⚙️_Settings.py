"""
⚙️ 系统设置
===========

交易模式切换 · 策略注册表 · 环境变量 · 管线一键操作
"""

import asyncio
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

# ── 项目根路径 ──────────────────────────────────────────────────────
_root = Path(__file__).resolve().parent.parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

# ── 页面标题 ────────────────────────────────────────────────────────
st.title("⚙️ 系统设置")
st.markdown(
    '<p class="subtitle">模式切换 · 策略注册表 · 环境变量 · 管线操作</p>',
    unsafe_allow_html=True,
)

# ═══════════════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════════════


def _run_async(coro):
    """在单独的 event loop 中安全执行异步协程

    Streamlit 的 Tornado 后端可能存在活跃 loop，因此不使用 asyncio.run()，
    而是创建全新的 loop 来避免冲突。
    """
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ═══════════════════════════════════════════════════════════════════
# 1. 交易模式切换
# ═══════════════════════════════════════════════════════════════════

st.markdown("### 🎯 交易模式")
st.markdown(
    '<p class="subtitle">切换运行环境将影响所有交易行为的执行方式</p>',
    unsafe_allow_html=True,
)

try:
    from config.settings import settings

    current_mode = settings.TRADING_MODE.value
except Exception as e:
    st.error(f"❌ 读取配置失败: {e}")
    st.stop()

MODE_LABELS: dict[str, tuple[str, str, str]] = {
    "SANDBOX": ("🟢", "模拟环境", "纯模拟测试，不产生真实订单"),
    "PAPER": ("🟡", "纸交验证", "模拟下单，验证完整流程"),
    "PROD": ("🔴", "实盘交易", "真实生产环境，实际下单交易"),
}

cols = st.columns(3)
for idx, (mode, (icon, label, desc)) in enumerate(MODE_LABELS.items()):
    with cols[idx]:
        with st.container(border=True):
            st.markdown(
                f'<div style="text-align:center;font-size:2rem;line-height:1.2;">{icon}</div>',
                unsafe_allow_html=True,
            )
            st.markdown(
                f'<div style="text-align:center;font-weight:700;font-size:1.1rem;'
                f'color:#F1F5F9;">{label}</div>',
                unsafe_allow_html=True,
            )
            st.caption(desc)

            is_current = mode == current_mode
            if is_current:
                st.markdown(
                    f'<div style="text-align:center;margin-top:0.5rem;">'
                    f'<span class="status-tag status-{mode.lower()}">✓ 当前模式</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
            else:
                if st.button(
                    f"切换到 {label}",
                    key=f"mode_switch_{mode}",
                    use_container_width=True,
                ):
                    st.warning(
                        f"⚠️ 切换到 **{label}** 需要手动修改配置文件。\n\n"
                        f"1. 打开项目根目录下的 `.env` 文件\n"
                        f"2. 将 `TIGER_ENV={current_mode}` 改为 `TIGER_ENV={mode}`\n"
                        f"3. 保存文件后**重新启动** Streamlit 应用\n\n"
                        f"当前: `{current_mode}` → 目标: `{mode}`"
                    )

# ═══════════════════════════════════════════════════════════════════
# 2. 已注册策略
# ═══════════════════════════════════════════════════════════════════

st.divider()
st.markdown("### 📋 已注册策略")
st.markdown(
    '<p class="subtitle">StrategyRegistry 中所有已注册的策略类</p>',
    unsafe_allow_html=True,
)

try:
    from src.trading.strategy.registry import StrategyRegistry

    strategies = StrategyRegistry.list_strategies()
except Exception as e:
    st.error(f"❌ 读取策略注册表失败: {e}")
    strategies = []

if strategies:
    st.markdown(f"共 **{len(strategies)}** 个已注册策略")
    for sname in strategies:
        with st.container(border=True):
            c1, c2, c3 = st.columns([3, 2, 1])
            c1.markdown(f"**{sname}**")
            try:
                cls = StrategyRegistry.get(sname)
                c2.markdown(
                    f'<code style="color:#94A3B8;font-size:0.85rem;">{cls.__name__}</code>',
                    unsafe_allow_html=True,
                )
            except KeyError:
                c2.markdown(
                    '<span style="color:#EF4444;font-size:0.85rem;">⚠️ 状态未知</span>',
                    unsafe_allow_html=True,
                )
            # 视觉启用开关（仅展示，无后端持久化）
            c3.markdown(
                '<div style="text-align:right;color:#22C55E;">🟢 已启用</div>',
                unsafe_allow_html=True,
            )
else:
    st.info("暂未注册任何策略。使用 `@StrategyRegistry.register` 装饰器注册策略类。")

# ═══════════════════════════════════════════════════════════════════
# 3. 环境变量
# ═══════════════════════════════════════════════════════════════════

st.divider()
st.markdown("### 🔑 环境变量")
st.markdown(
    '<p class="subtitle">当前运行时配置 —— 含密钥的字段已自动掩码</p>',
    unsafe_allow_html=True,
)

SECRET_KEYWORDS = ["PRIVATE_KEY", "SECRET", "TOKEN", "PASSWORD"]


def _mask_value(field_name: str, raw_value) -> str:
    """对敏感字段进行掩码处理"""
    if raw_value is None:
        return "（空）"
    val = str(raw_value)
    if not val:
        return "（空）"
    upper_name = field_name.upper()
    if any(kw in upper_name for kw in SECRET_KEYWORDS):
        if len(val) > 8:
            return val[:4] + "••••" + val[-4:]
        return "••••••••"
    return val


try:
    rows: list[dict[str, str]] = []
    for fname, finfo in settings.model_fields.items():
        raw = getattr(settings, fname)
        default = finfo.default
        default_str = str(default) if default is not None else "—"
        masked = _mask_value(fname, raw)
        rows.append({"参数名": fname, "当前值": masked, "默认值": default_str})

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)

    st.caption(
        "💡 通过编辑项目根目录的 `.env` 文件修改配置，重启后生效。"
        " 掩码规则: 字段名含 PRIVATE_KEY / SECRET / TOKEN / PASSWORD 的自动掩码。"
    )
except Exception as e:
    st.error(f"❌ 读取环境变量失败: {e}")

# ═══════════════════════════════════════════════════════════════════
# 4. 管线操作
# ═══════════════════════════════════════════════════════════════════

st.divider()
st.markdown("### 🚀 管线操作")
st.markdown(
    '<p class="subtitle">一键触发交易管道任务</p>',
    unsafe_allow_html=True,
)

pcol1, pcol2 = st.columns(2)

with pcol1:
    if st.button(
        "🌅 运行盘前信号生成（Pre-Market）",
        key="run_premarket",
        use_container_width=True,
        type="primary",
    ):
        try:
            from src.trading.pipeline import QuantWeaselPipeline

            with st.spinner("正在执行盘前管线……"):
                pipeline = QuantWeaselPipeline()
                count = _run_async(pipeline.run_pre_market())
            st.success(f"✅ 盘前信号生成完成！共生成 **{count}** 条信号")
        except Exception as e:
            st.error(f"❌ 盘前管线执行失败: {e}")

with pcol2:
    if st.button(
        "☀️ 运行盘中信号生成（Intraday）",
        key="run_intraday",
        use_container_width=True,
        type="primary",
    ):
        try:
            from src.trading.pipeline import QuantWeaselPipeline

            with st.spinner("正在执行盘中管线……"):
                pipeline = QuantWeaselPipeline()
                count = _run_async(pipeline.run_intraday())
            if count > 0:
                st.success(f"✅ 盘中信号生成完成！共生成 **{count}** 条信号")
            else:
                st.info("盘中管线执行完成，当前无新信号生成（可能非交易时间）")
        except Exception as e:
            st.error(f"❌ 盘中管线执行失败: {e}")

# ═══════════════════════════════════════════════════════════════════
# 5. 系统信息
# ═══════════════════════════════════════════════════════════════════

st.divider()
st.markdown("### ℹ️ 系统信息")

# ── 版本号 ──────────────────────────────────────────────────────────
try:
    import tomllib  # Python ≥3.11

    _pyproject = _root / "pyproject.toml"
    if _pyproject.exists():
        with _pyproject.open("rb") as f:
            _proj_data = tomllib.load(f)
        _version = _proj_data.get("project", {}).get("version", "0.0.0")
    else:
        _version = "0.0.0 (no pyproject.toml)"
except Exception:
    _version = "0.1.0 (dev)"

# ── 数据目录 ─────────────────────────────────────────────────────────
_data_dir = _root / "data"
if _data_dir.exists():
    _data_size_bytes = sum(
        f.stat().st_size for f in _data_dir.rglob("*") if f.is_file()
    )
    _data_size_mb = _data_size_bytes / 1024 / 1024
else:
    _data_size_mb = 0.0

# ── 系统运行时间 ──────────────────────────────────────────────────────
try:
    with open("/proc/uptime") as _f:
        _uptime_sec = float(_f.read().split()[0])
    _uptime_days = int(_uptime_sec // 86400)
    _uptime_hours = int((_uptime_sec % 86400) // 3600)
    _uptime_str = f"{_uptime_days}d {_uptime_hours}h"
except Exception:
    _uptime_str = "N/A"

with st.container(border=True):
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("系统版本", _version)
    c2.metric("Python 版本", f"{sys.version_info.major}.{sys.version_info.minor}")
    c3.metric("Streamlit 版本", st.__version__)
    c4.metric("系统运行时间", _uptime_str)

    st.markdown(
        f'<div style="color:#64748B;font-size:0.85rem;margin-top:0.5rem;">'
        f'数据目录: <code>{_data_dir}</code> · '
        f'数据大小: <strong>{_data_size_mb:.1f} MB</strong> · '
        f'运行模式: <code>{settings.TIGER_ENV}</code> · '
        f'自动交易: {"✅ 开启" if settings.TRADING_AUTO_TRADE else "❌ 关闭"} · '
        f'Dry-Run: {"✅ 是" if settings.QUANT_DRY_RUN else "❌ 否"}'
        f'</div>',
        unsafe_allow_html=True,
    )

# ═══════════════════════════════════════════════════════════════════
# 底部
# ═══════════════════════════════════════════════════════════════════

st.divider()
st.caption(
    "QuantWeasel AI 交易系统 · 配置文件: `.env` + `config/trading.yaml` · "
    "配置变更需重启 Streamlit 应用后生效"
)
