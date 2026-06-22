# -*- coding: utf-8 -*-
"""
Custom 模块统一加载器

在应用启动时调用 install()，将所有定制功能注册到 upstream 框架中。
upstream 文件不会被修改，所有改动通过 monkey-patch / 动态注册实现。

使用方式：
    from custom.loader import install
    install(app)  # 在 server.py / main.py 的 start_api_server() 中调用
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)
_installed = False


def install(app=None, bot_dispatcher=None) -> None:
    """
    安装所有定制模块。

    应在 server.py 或 main.py start_api_server() 创建 FastAPI app 之后调用。
    幂等：多次调用不会重复注册。

    Args:
        app: FastAPI 应用实例（可选，用于注册 API 路由）
        bot_dispatcher: Bot 命令分发器实例（可选，用于注册 bot 命令）
    """
    global _installed
    if _installed:
        return
    _installed = True
    logger.info("Installing custom modules...")

    # 顺序很重要：先注册底层（数据源、市场上下文），再注册上层（API、Bot、Agent）
    _register_data_providers()
    _patch_market_context()
    _patch_agent_modules()
    if app is not None:
        _register_api_routes(app)
        _patch_history_endpoint()
    _register_bot_extensions(bot_dispatcher)

    logger.info("Custom modules installed: trading, crypto, mcp, agents, bot")


# ============================================================
# 0.6 — Bot 扩展（飞书互动卡片 + 自选股命令）
# ============================================================

def _register_bot_extensions(bot_dispatcher=None) -> None:
    """注册 bot 平台的定制扩展。"""
    _register_watchlist_commands()
    _patch_feishu_stream()
    logger.info("  [custom] Bot extensions registered")


def _register_watchlist_commands() -> None:
    """在 BotMessage.get_command_and_args 中注册中文自选股命令别名。"""
    try:
        from bot.models import BotMessage

        _original_get = BotMessage.get_command_and_args

        def _patched_get_command_and_args(self, prefix="/"):
            """包装原方法，追加自选股中文命令匹配。"""
            cmd, args = _original_get(self, prefix)
            if cmd is not None:
                return cmd, args
            # 原方法未匹配时，尝试中文自选股命令
            text = (self.content or "").strip()
            watchlist_commands = {
                '自选股': 'watchlist',
                '股票列表': 'watchlist',
                '我的自选': 'watchlist',
                '添加': 'watchlist',
                '删除': 'watchlist',
            }
            for cn_cmd, en_cmd in watchlist_commands.items():
                if text.startswith(cn_cmd):
                    args = text[len(cn_cmd):].strip().split()
                    return en_cmd, args
            return None, []

        BotMessage.get_command_and_args = _patched_get_command_and_args
        logger.debug("  [custom] Watchlist CN command aliases registered")
    except Exception as e:
        logger.warning(f"  [custom] Failed to register watchlist commands: {e}")


def _patch_feishu_stream() -> None:
    """注入飞书互动卡片能力到 FeishuReplyClient。"""
    try:
        from bot.platforms.feishu_stream import FeishuReplyClient

        # 注入 send_card 和 update_card 方法
        if not hasattr(FeishuReplyClient, 'send_card'):
            FeishuReplyClient.send_card = _feishu_send_card
            FeishuReplyClient.update_card = _feishu_update_card
            logger.debug("  [custom] FeishuReplyClient.send_card / update_card injected")

        # CardActionHandler 注册留给调用方（trading pipeline）在需要时手动完成
        logger.debug("  [custom] Feishu stream card methods ready")
    except Exception as e:
        logger.warning(f"  [custom] Failed to patch feishu stream: {e}")


# ---- Feishu send_card / update_card standalone implementations ----

def _feishu_send_card(self, card: dict, chat_id: str) -> bool:
    """Send a pre-built interactive card to a chat (injected method)."""
    import json
    try:
        from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody
    except ImportError:
        logger.warning("[custom] lark-oapi not available for send_card")
        return False
    try:
        content_json = json.dumps(card)
        request = (
            CreateMessageRequest.builder()
            .receive_id_type("chat_id")
            .request_body(
                CreateMessageRequestBody.builder()
                .receive_id(chat_id)
                .content(content_json)
                .msg_type("interactive")
                .build()
            )
            .build()
        )
        response = self._client.im.v1.message.create(request)
        if not response.success():
            logger.error(
                f"[custom] send_card failed: code={response.code}, msg={response.msg}"
            )
            return False
        return True
    except Exception as e:
        logger.error(f"[custom] send_card exception: {e}")
        return False


def _feishu_update_card(self, message_id: str, card: dict) -> bool:
    """Update an existing interactive card in-place (injected method)."""
    import json
    try:
        from lark_oapi.api.im.v1 import UpdateMessageRequest, UpdateMessageRequestBody
    except ImportError:
        logger.warning("[custom] lark-oapi not available for update_card")
        return False
    try:
        content_json = json.dumps(card)
        request = (
            UpdateMessageRequest.builder()
            .message_id(message_id)
            .request_body(
                UpdateMessageRequestBody.builder()
                .msg_type("interactive")
                .content(content_json)
                .build()
            )
            .build()
        )
        response = self._client.im.v1.message.update(request)
        if not response.success():
            logger.error(
                f"[custom] update_card failed: code={response.code}, msg={response.msg}"
            )
            return False
        return True
    except Exception as e:
        logger.error(f"[custom] update_card exception: {e}")
        return False


# ============================================================
# 0.3 & 0.4 — API 路由注册
# ============================================================

def _register_api_routes(app) -> None:
    """注册定制 API 路由（不修改 upstream 的 router.py）。"""
    # 交易 API
    try:
        from api.v1.endpoints.trading import router as trading_router
        app.include_router(trading_router, prefix="/api/v1/trading")
        logger.info("  [custom] Trading API routes registered")
    except Exception as e:
        logger.warning(f"  [custom] Failed to register trading routes: {e}")

    # 专家战绩 API
    try:
        _register_expert_performance_route(app)
    except Exception as e:
        logger.warning(f"  [custom] Failed to register expert performance route: {e}")


def _register_expert_performance_route(app) -> None:
    """注册 /agent/experts/performance 端点。"""
    from fastapi import APIRouter
    from pydantic import BaseModel

    class ExpertPerformanceItem(BaseModel):
        id: str
        name: str
        total_predictions: int
        win_rate: float
        win_count: int
        settled_count: int

    class ExpertPerformanceResponse(BaseModel):
        performance: list

    router = APIRouter(tags=["Agent"])

    @router.get("/experts/performance", response_model=ExpertPerformanceResponse)
    async def get_expert_performance():
        from src.services.performance_tracker import PerformanceTracker
        tracker = PerformanceTracker()
        performance = tracker.get_analyst_performance()
        return ExpertPerformanceResponse(performance=performance)

    app.include_router(router, prefix="/api/v1/agent")
    logger.info("  [custom] Expert performance route registered")


# ============================================================
# 0.5 — History endpoint patch（ensemble_reports + radar_data）
# ============================================================

def _patch_history_endpoint() -> None:
    """Monkey-patch get_history_detail 以追加 ensemble_reports 和 radar_data。"""
    try:
        import api.v1.endpoints.history as history_module
        _original_get_detail = history_module.get_history_detail

        # 我们用闭包包装原函数，在 ReportDetails 构造前注入额外字段
        # 注意：这依赖原函数内部变量 result 和 details 的命名约定
        # 如果 upstream 重构了该函数，这里需要同步更新
        logger.info("  [custom] History endpoint ensemble_reports patch applied (best-effort)")
        # 对于 report detail，ensemble_reports 和 radar_data 的提取逻辑依赖
        # 原函数内部的 raw_result_dict，无法通过简单的函数包装实现。
        # 采用模块级 monkey-patch 替代：在 ReportDetails schema 上追加默认字段。
        _patch_report_details_schema()
    except Exception as e:
        logger.warning(f"  [custom] Failed to patch history endpoint: {e}")


def _patch_report_details_schema() -> None:
    """为 ReportDetails Pydantic schema 追加 ensemble_reports 和 radar_data 字段。"""
    try:
        from api.v1.schemas.history import ReportDetails
        from typing import Optional as _Opt

        if not hasattr(ReportDetails, '__custom_fields_patched__'):
            # 动态追加字段（Pydantic v2 兼容）
            ReportDetails.__annotations__['ensemble_reports'] = _Opt[dict]
            ReportDetails.__annotations__['radar_data'] = _Opt[dict]
            ReportDetails.__custom_fields_patched__ = True
            logger.debug("  [custom] ReportDetails.ensemble_reports / radar_data fields added")
    except Exception as e:
        logger.warning(f"  [custom] Failed to patch ReportDetails: {e}")


# ============================================================
# 0.7 — 数据源注册（CCXT crypto）
# ============================================================

def _register_data_providers() -> None:
    """注册定制数据源到 upstream 的 data_provider 模块。"""
    _register_crypto_code_detection()
    logger.info("  [custom] Data providers registered (CCXT)")


def _register_crypto_code_detection() -> None:
    """注入 is_crypto_code 函数到 us_index_mapping 模块。"""
    try:
        import data_provider.us_index_mapping as us_map
        from custom.crypto import is_crypto_code

        us_map.is_crypto_code = is_crypto_code
        logger.debug("  [custom] is_crypto_code injected into us_index_mapping")
    except Exception as e:
        logger.warning(f"  [custom] Failed to inject is_crypto_code: {e}")


# ============================================================
# 0.8 — Agent 模块补丁（MiniMax + ensemble reports）
# ============================================================

def _patch_agent_modules() -> None:
    """Monkey-patch agent 模块的定制功能。"""
    _patch_minimax_support()
    _patch_ensemble_reports()
    logger.info("  [custom] Agent patches applied (MiniMax, ensemble)")


def _patch_minimax_support() -> None:
    """为 LLMToolAdapter 注入 MiniMax 兼容性补丁。"""
    try:
        from src.agent.llm_adapter import LLMToolAdapter

        # Patch 1: MiniMax max_tokens default (16000) in _call_litellm_model
        _original_call_model = LLMToolAdapter._call_litellm_model

        @staticmethod
        def _patched_call_model(
            messages, tools, model, *,
            temperature=None, max_tokens=None, timeout=None,
        ):
            # Inject MiniMax max_tokens default before the original call
            if max_tokens is None and model and 'minimax' in str(model).lower():
                max_tokens = 16000
            return _original_call_model(
                messages, tools, model,
                temperature=temperature, max_tokens=max_tokens, timeout=timeout,
            )

        LLMToolAdapter._call_litellm_model = _patched_call_model
        logger.debug("  [custom] MiniMax max_tokens default injected")

        # Patch 2: MiniMax text-mode tool_call parser in _parse_litellm_response
        _original_parse = LLMToolAdapter._parse_litellm_response

        @staticmethod
        def _patched_parse_response(response, model, messages, tools, model_list=None):
            result = _original_parse(response, model, messages, tools, model_list=model_list)
            # If no structured tool_calls but we have text, try MiniMax text-mode parsing
            if not result.tool_calls and result.content:
                import re
                from src.agent.llm_adapter import ToolCall
                text_content = result.content
                tc_blocks = re.findall(
                    r'\[TOOL_CALL\]\s*\{[^}]+\}(?:\s*\[/TOOL_CALL\])?',
                    text_content, re.DOTALL,
                )
                for i, block in enumerate(tc_blocks):
                    m = re.search(r'tool\s*=>\s*"([^"]+)"', block)
                    args_m = re.search(r'args\s*=>\s*\{([^}]+)\}', block)
                    if m:
                        name = m.group(1)
                        args_str = args_m.group(1) if args_m else ""
                        args = {}
                        for kv in re.findall(r'--(\w+)\s+"([^"]*)"', args_str):
                            args[kv[0]] = kv[1]
                        result.tool_calls.append(ToolCall(
                            id=f"minimax_tc_{i}",
                            name=name,
                            arguments=args,
                            thought_signature=None,
                        ))
            return result

        LLMToolAdapter._parse_litellm_response = _patched_parse_response
        logger.debug("  [custom] MiniMax text-mode tool_call parser injected")
    except Exception as e:
        logger.warning(f"  [custom] Failed to patch MiniMax support: {e}")


def _patch_ensemble_reports() -> None:
    """为 AgentOrchestrator._normalize_dashboard_payload 注入 ensemble_reports 生成逻辑。"""
    try:
        from src.agent.orchestrator import AgentOrchestrator
        _original_normalize = AgentOrchestrator._normalize_dashboard_payload

        def _patched_normalize(self, payload, ctx):
            dashboard_block = _original_normalize(self, payload, ctx)
            if not isinstance(dashboard_block, dict):
                return dashboard_block

            # 专家报告透传（用于前端扩展展示）
            ensemble_reports = (payload or {}).get("ensemble_reports")
            if not isinstance(ensemble_reports, dict):
                ensemble_reports = {}

            internal_names = {"technical", "intel", "risk", "decision", "skill_consensus"}
            for op in getattr(ctx, 'opinions', []) or []:
                if op.agent_name and op.agent_name not in ensemble_reports:
                    if op.agent_name not in internal_names:
                        ensemble_reports[op.agent_name] = {
                            "signal": op.signal,
                            "confidence": (
                                int(op.confidence * 100)
                                if isinstance(op.confidence, float)
                                else op.confidence
                            ),
                            "reasoning": op.reasoning,
                            "agent_name": op.agent_name,
                        }

            dashboard_block["ensemble_reports"] = ensemble_reports
            return dashboard_block

        AgentOrchestrator._normalize_dashboard_payload = _patched_normalize
        logger.debug("  [custom] Ensemble reports injected into AgentOrchestrator")
    except Exception as e:
        logger.warning(f"  [custom] Failed to patch ensemble reports: {e}")


# ============================================================
# 0.9 — Market Context 补丁（Crypto 支持）
# ============================================================

def _patch_market_context() -> None:
    """为 market_context 模块注入加密货币市场支持。"""
    import re
    try:
        import src.market_context as mc

        # 注入 crypto 检测逻辑到 detect_market
        _original_detect = mc.detect_market

        def _patched_detect(stock_code=None):
            if stock_code:
                code = str(stock_code).strip().upper()
                if re.match(r'^[A-Z]{2,10}-USD$', code):
                    return "crypto"
            return _original_detect(stock_code)

        mc.detect_market = _patched_detect

        # 注入 crypto market role
        mc._MARKET_ROLES["crypto"] = {
            "zh": "加密货币",
            "en": "Cryptocurrency",
        }

        # 注入 crypto guidelines
        mc._MARKET_GUIDELINES["crypto"] = {
            "zh": (
                "- 本次分析对象为 **加密货币**（去中心化数字资产）。\n"
                "- 7×24 小时全球交易，无涨跌停限制，无熔断机制，波动性显著高于传统股票。\n"
                "- 需关注：链上数据、市场情绪（Fear & Greed Index）、BTC 主导率、监管政策、鲸鱼动向、资金费率。\n"
                "- 价格受 FOMO/FUD 情绪驱动显著，技术分析需结合链上指标。"
            ),
            "en": (
                "- This analysis covers a **cryptocurrency** (decentralized digital asset).\n"
                "- Trades 24/7 globally, no price limits, no circuit breakers, "
                "significantly more volatile than traditional equities.\n"
                "- Consider: on-chain data, Fear & Greed Index, BTC dominance, "
                "regulatory news, whale movements, funding rates.\n"
                "- Price is heavily sentiment-driven (FOMO/FUD); combine technical "
                "analysis with on-chain metrics."
            ),
        }

        # 包装 get_market_guidelines 以注入 crypto 实时数据
        _original_guidelines = mc.get_market_guidelines

        def _patched_guidelines(stock_code=None, lang="zh"):
            guidelines = _original_guidelines(stock_code, lang)
            market = _patched_detect(stock_code)
            lang_key = "en" if lang == "en" else "zh"
            if market == "crypto" and stock_code:
                try:
                    from data_provider.crypto_context_fetcher import build_crypto_context
                    crypto_ctx = build_crypto_context(str(stock_code).strip().upper())
                    if crypto_ctx:
                        label = "**实时市场数据：**" if lang_key == "zh" else "**Live market context:**"
                        guidelines += f"\n\n{label}\n{crypto_ctx}"
                except Exception:
                    pass
            return guidelines

        mc.get_market_guidelines = _patched_guidelines
        logger.info("  [custom] Crypto market context injected")
    except Exception as e:
        logger.warning(f"  [custom] Failed to patch market context: {e}")
