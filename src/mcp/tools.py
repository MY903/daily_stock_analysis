"""
MCP tool definitions for DSA core capabilities.

Each tool is a simple function that:
1. Accepts typed parameters
2. Returns JSON-serializable results
3. Has a clear description for AI consumption
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.services.decision_signal_service import DecisionSignalService
from src.services.stock_service import StockService
from src.services.analysis_service import AnalysisService
from src.trading.strategy.base import Signal
from src.trading.signal_generator import SignalGenerator

logger = logging.getLogger(__name__)

# Tool registry: maps tool_name -> tool function
TOOL_REGISTRY: Dict[str, Dict[str, Any]] = {}


def register_tool(
    name: str,
    description: str,
    parameters: Dict[str, Any],
):
    """Decorator to register an MCP tool.

    Args:
        name: Tool name (snake_case).
        description: Human-readable description for AI consumption.
        parameters: JSON Schema for tool parameters.

    Returns:
        Decorator.
    """
    def decorator(func):
        TOOL_REGISTRY[name] = {
            "name": name,
            "description": description,
            "parameters": parameters,
            "handler": func,
        }
        return func
    return decorator


# ==================== Tool Implementations ====================


@register_tool(
    name="analyze_stock",
    description="运行完整股票分析并返回分析报告摘要，支持 A 股/港股/美股。需要显式传入股票代码。",
    parameters={
        "type": "object",
        "properties": {
            "stock_code": {
                "type": "string",
                "description": "股票代码，例如 600519（A股）、00700（港股）、AAPL（美股）",
            },
            "market": {
                "type": "string",
                "description": "市场：cn/hk/us，留空则自动检测",
                "enum": ["cn", "hk", "us", ""],
            },
        },
        "required": ["stock_code"],
    },
)
async def analyze_stock(stock_code: str, market: str = "") -> Dict[str, Any]:
    """Run stock analysis and return a summary."""
    try:
        service = AnalysisService()
        result = await service.analyze(stock_code, market=market or None)
        return {
            "status": "ok",
            "stock_code": stock_code,
            "summary": result.get("summary", "")[:1000],
            "score": result.get("score"),
            "signals": result.get("decision_signals", []),
        }
    except Exception as e:
        logger.exception("analyze_stock failed for %s", stock_code)
        return {"status": "error", "stock_code": stock_code, "error": str(e)}


@register_tool(
    name="get_stock_info",
    description="获取股票基本信息，包括名称、当前价格、涨跌幅、市值。支持 A 股/港股/美股。",
    parameters={
        "type": "object",
        "properties": {
            "stock_code": {
                "type": "string",
                "description": "股票代码",
            },
        },
        "required": ["stock_code"],
    },
)
def get_stock_info(stock_code: str) -> Dict[str, Any]:
    """Get stock basic information and realtime quote."""
    try:
        service = StockService()
        info = service.get_stock_info(stock_code)
        return {"status": "ok", "data": info}
    except Exception as e:
        logger.exception("get_stock_info failed for %s", stock_code)
        return {"status": "error", "stock_code": stock_code, "error": str(e)}


@register_tool(
    name="get_decision_signals",
    description="获取当前活跃的 AI 决策信号列表，包含买卖建议、置信度和原因。可按股票代码筛选。",
    parameters={
        "type": "object",
        "properties": {
            "stock_code": {
                "type": "string",
                "description": "可选，按股票代码筛选",
            },
            "status": {
                "type": "string",
                "description": "信号状态：active/expired/closed",
                "default": "active",
            },
            "limit": {
                "type": "integer",
                "description": "返回数量上限",
                "default": 20,
            },
        },
    },
)
def get_decision_signals(
    stock_code: str = "",
    status: str = "active",
    limit: int = 20,
) -> Dict[str, Any]:
    """Query active decision signals."""
    try:
        service = DecisionSignalService()
        result = service.list_signals(
            stock_code=stock_code or None,
            status=status,
            page=1,
            page_size=min(limit, 50),
        )
        return {"status": "ok", "signals": result.get("items", []), "total": result.get("total", 0)}
    except Exception as e:
        logger.exception("get_decision_signals failed")
        return {"status": "error", "error": str(e)}


@register_tool(
    name="generate_trading_signals",
    description="基于技术指标（RSI、SMA、成交量）生成交易信号。支持指定的股票代码列表。",
    parameters={
        "type": "object",
        "properties": {
            "symbols": {
                "type": "array",
                "items": {"type": "string"},
                "description": "股票代码列表",
            },
        },
        "required": ["symbols"],
    },
)
def generate_trading_signals(symbols: List[str]) -> Dict[str, Any]:
    """Generate technical trading signals for given symbols."""
    try:
        generator = SignalGenerator()
        signals = generator.generate_pre_market_signals(symbols)
        return {
            "status": "ok",
            "signals": [
                {
                    "symbol": s.symbol if hasattr(s, "symbol") else "",
                    "action": s.action if hasattr(s, "action") else "",
                    "reason": s.reason if hasattr(s, "reason") else "",
                    "price": s.price if hasattr(s, "price") else 0,
                    "confidence": s.confidence if hasattr(s, "confidence") else 0,
                }
                for s in signals
            ],
        }
    except Exception as e:
        logger.exception("generate_trading_signals failed")
        return {"status": "error", "error": str(e)}


@register_tool(
    name="get_portfolio_summary",
    description="获取当前持仓摘要，包括各标的最新盈亏、仓位比例。",
    parameters={
        "type": "object",
        "properties": {
            "account_id": {
                "type": "integer",
                "description": "可选，账户 ID",
            },
        },
    },
)
def get_portfolio_summary(account_id: Optional[int] = None) -> Dict[str, Any]:
    """Get portfolio summary."""
    try:
        from src.services.portfolio_service import PortfolioService
        service = PortfolioService()
        summary = service.get_summary(account_id=account_id)
        return {"status": "ok", "portfolio": summary}
    except Exception as e:
        logger.exception("get_portfolio_summary failed")
        return {"status": "error", "error": str(e)}


@register_tool(
    name="get_market_review",
    description="获取最新大盘复盘摘要，包含市场趋势、热点板块和风险提示。",
    parameters={
        "type": "object",
        "properties": {},
    },
)
def get_market_review() -> Dict[str, Any]:
    """Get latest market review summary."""
    try:
        from src.services.market_light_service import MarketLightService
        service = MarketLightService()
        review = service.get_latest_summary()
        return {"status": "ok", "review": review}
    except Exception as e:
        logger.exception("get_market_review failed")
        return {"status": "error", "error": str(e)}


def list_tools() -> List[Dict[str, Any]]:
    """List all registered MCP tools."""
    return [
        {
            "name": info["name"],
            "description": info["description"],
            "parameters": info["parameters"],
        }
        for info in TOOL_REGISTRY.values()
    ]


async def call_tool(name: str, arguments: Dict[str, Any]) -> Any:
    """Call a registered MCP tool with arguments.

    Args:
        name: Tool name.
        arguments: Tool arguments dict.

    Returns:
        Tool result (JSON-serializable).
    """
    info = TOOL_REGISTRY.get(name)
    if not info:
        return {"status": "error", "error": f"Unknown tool: {name}"}

    handler = info["handler"]
    try:
        if asyncio.iscoroutinefunction(handler):
            return await handler(**arguments)
        return handler(**arguments)
    except Exception as e:
        logger.exception("Tool %s failed", name)
        return {"status": "error", "error": str(e)}


import asyncio
