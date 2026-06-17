# -*- coding: utf-8 -*-
"""Trading API endpoints."""

from __future__ import annotations

import asyncio
import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException

from config.settings import settings
from api.v1.schemas.trading import (
    AccountSummary,
    Order,
    Position,
    RiskConfigResponse,
    SignalCreate,
    SignalResponse,
    StrategyInfo,
    SystemStatus,
)
from src.trading.tiger_client import TigerClient
from src.trading.config import load_config
from src.trading.audit_logger import AuditLogger
from src.trading.risk_manager import RiskManager
from src.trading.strategy.registry import StrategyRegistry

logger = logging.getLogger(__name__)

router = APIRouter()

# Module-level singletons for lightweight trading components
_audit_logger = AuditLogger()
_risk_manager = RiskManager()


# ==================== Helper ====================


def _create_tiger_client() -> TigerClient:
    """Create and connect a TigerClient instance."""
    config = load_config()
    client = TigerClient(config)
    client.connect()
    return client


async def _run_sync(fn, *args, **kwargs):
    """Run a synchronous function in a thread pool to avoid blocking the event loop."""
    return await asyncio.to_thread(fn, *args, **kwargs)


def _to_signal_response(record: dict) -> SignalResponse:
    """Convert an audit log record dict to a SignalResponse."""
    import json
    from datetime import datetime

    signal_json_raw = record.get("signal_json", "{}")
    try:
        parsed = json.loads(signal_json_raw) if isinstance(signal_json_raw, str) else signal_json_raw
    except (json.JSONDecodeError, TypeError):
        parsed = {}

    return SignalResponse(
        signal_id=record.get("signal_id", ""),
        symbol=record.get("symbol", parsed.get("symbol", "")),
        action=record.get("action", parsed.get("action", "")),
        quantity=parsed.get("quantity"),
        price_target=parsed.get("price_target"),
        confidence=parsed.get("confidence", 0.0),
        status=record.get("status", "UNKNOWN"),
        created_at=datetime.fromiso_string(record["created_at"]) if isinstance(record.get("created_at"), str) else datetime.now(),
        rationale=parsed.get("rationale", ""),
    )


# ==================== Endpoints ====================


@router.get(
    "/status",
    response_model=SystemStatus,
    responses={
        200: {"description": "系统运行状态"},
        500: {"description": "服务器错误"},
    },
    summary="系统运行状态",
    description="获取交易系统运行状态，包括交易模式、Tiger API 连接状态和市场状态",
)
def get_status() -> SystemStatus:
    try:
        client = _create_tiger_client()
        try:
            market_status = client.get_market_status()
            return SystemStatus(
                trading_mode=settings.TRADING_MODE.value,
                tiger_connected=client.is_connected,
                market_status=market_status,
            )
        finally:
            client.disconnect()
    except Exception as exc:
        logger.error(f"获取系统状态失败: {exc}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": f"获取系统状态失败: {str(exc)}"},
        )


@router.get(
    "/account",
    response_model=AccountSummary,
    responses={
        200: {"description": "账户资产摘要"},
        500: {"description": "服务器错误"},
    },
    summary="账户资产摘要",
    description="获取当前账户的净值、可用现金和购买力",
)
def get_account() -> AccountSummary:
    try:
        client = _create_tiger_client()
        try:
            summary = client.get_account_summary()
            return AccountSummary(
                net_value=summary.get("net_value", 0.0),
                cash=summary.get("cash", 0.0),
                buying_power=summary.get("buying_power", 0.0),
            )
        finally:
            client.disconnect()
    except Exception as exc:
        logger.error(f"获取账户摘要失败: {exc}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": f"获取账户摘要失败: {str(exc)}"},
        )


@router.get(
    "/positions",
    response_model=List[Position],
    responses={
        200: {"description": "当前持仓列表"},
        500: {"description": "服务器错误"},
    },
    summary="当前持仓",
    description="获取当前所有持仓信息",
)
def get_positions() -> List[Position]:
    try:
        client = _create_tiger_client()
        try:
            raw = client.get_positions()
            positions = []
            for p in raw:
                positions.append(Position(
                    symbol=p.get("symbol", ""),
                    quantity=int(p.get("quantity", 0)),
                    avg_price=float(p.get("avg_price", 0.0) or 0.0),
                    market_value=float(p.get("market_value", 0.0) or 0.0),
                    pnl_pct=float(p.get("unrealized_pnl_pct", 0.0) or 0.0),
                ))
            return positions
        finally:
            client.disconnect()
    except Exception as exc:
        logger.error(f"获取持仓失败: {exc}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": f"获取持仓失败: {str(exc)}"},
        )


@router.get(
    "/orders",
    response_model=List[Order],
    responses={
        200: {"description": "活跃订单列表"},
        500: {"description": "服务器错误"},
    },
    summary="活跃订单",
    description="获取当前所有活跃订单",
)
def get_orders() -> List[Order]:
    try:
        client = _create_tiger_client()
        try:
            raw = client.get_active_orders()
            orders = []
            for o in raw:
                orders.append(Order(
                    order_id=str(o.get("id", "")),
                    symbol=o.get("symbol", ""),
                    action=o.get("action", ""),
                    quantity=int(o.get("total_quantity", 0) or 0),
                    filled=int(o.get("filled_quantity", 0) or 0),
                    price=float(o.get("limit_price", 0.0) or 0.0),
                    status=o.get("status", "UNKNOWN"),
                ))
            return orders
        finally:
            client.disconnect()
    except Exception as exc:
        logger.error(f"获取订单失败: {exc}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": f"获取订单失败: {str(exc)}"},
        )


@router.post(
    "/signals",
    response_model=SignalResponse,
    responses={
        200: {"description": "信号创建成功"},
        500: {"description": "服务器错误"},
    },
    summary="创建交易信号",
    description="创建并发送交易信号，SANDBOX/PAPER 模式自动执行，PROD 模式推送飞书确认卡片",
)
async def create_signal(req: SignalCreate) -> SignalResponse:
    try:
        from src.trading.pipeline import QuantWeaselPipeline

        pipeline = QuantWeaselPipeline()
        signal = await pipeline.generate_and_push_signal(
            symbol=req.symbol,
            action=req.action,
            quantity=req.quantity,
            confidence=req.confidence,
            rationale=req.rationale,
        )
        if signal is None:
            raise HTTPException(
                status_code=500,
                detail={"error": "signal_failed", "message": "信号创建或推送失败"},
            )
        return SignalResponse(
            signal_id=signal.signal_id,
            symbol=signal.symbol,
            action=signal.action.value,
            quantity=signal.quantity,
            price_target=signal.price_target,
            confidence=signal.confidence,
            status=signal.status.value,
            created_at=signal.created_at,
            rationale=signal.rationale,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"创建信号失败: {exc}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": f"创建信号失败: {str(exc)}"},
        )


@router.get(
    "/signals",
    response_model=List[SignalResponse],
    responses={
        200: {"description": "信号历史列表"},
        500: {"description": "服务器错误"},
    },
    summary="信号历史",
    description="获取交易信号历史记录，支持按状态筛选和分页",
)
def get_signals(
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> List[SignalResponse]:
    try:
        records = _audit_logger.get_all_signals(limit=limit, offset=offset, status=status)
        return [_to_signal_response(r) for r in records]
    except Exception as exc:
        logger.error(f"查询信号历史失败: {exc}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": f"查询信号历史失败: {str(exc)}"},
        )


@router.post(
    "/signals/{signal_id}/confirm",
    responses={
        200: {"description": "信号确认成功"},
        404: {"description": "信号不存在"},
        500: {"description": "服务器错误"},
    },
    summary="确认信号",
    description="确认交易信号并执行下单",
)
async def confirm_signal(signal_id: str) -> dict:
    try:
        # Check signal exists
        history = _audit_logger.get_signal_history(signal_id)
        if not history:
            raise HTTPException(
                status_code=404,
                detail={"error": "not_found", "message": f"信号 {signal_id} 不存在"},
            )

        from src.trading.signal import ConfirmResult, ConfirmAction
        from src.trading.pipeline import QuantWeaselPipeline

        pipeline = QuantWeaselPipeline()
        confirm = ConfirmResult(
            signal_id=signal_id,
            action=ConfirmAction.CONFIRM,
        )
        _audit_logger.log_confirmed(signal_id, confirm)

        result = await pipeline.process_confirmed_signal(signal_id)
        return {
            "success": result.get("success", False),
            "signal_id": signal_id,
            "message": result.get("message", "信号已确认"),
            "order_id": result.get("order_id"),
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"确认信号失败: {exc}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": f"确认信号失败: {str(exc)}"},
        )


@router.post(
    "/signals/{signal_id}/reject",
    responses={
        200: {"description": "信号拒绝成功"},
        404: {"description": "信号不存在"},
        500: {"description": "服务器错误"},
    },
    summary="拒绝信号",
    description="拒绝交易信号，不执行下单",
)
async def reject_signal(signal_id: str) -> dict:
    try:
        history = _audit_logger.get_signal_history(signal_id)
        if not history:
            raise HTTPException(
                status_code=404,
                detail={"error": "not_found", "message": f"信号 {signal_id} 不存在"},
            )

        from src.trading.signal import ConfirmResult, ConfirmAction

        confirm = ConfirmResult(
            signal_id=signal_id,
            action=ConfirmAction.REJECT,
        )
        _audit_logger.log_confirmed(signal_id, confirm)
        logger.info("信号已拒绝: %s", signal_id)

        return {
            "success": True,
            "signal_id": signal_id,
            "message": "信号已拒绝",
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"拒绝信号失败: {exc}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": f"拒绝信号失败: {str(exc)}"},
        )


@router.get(
    "/risk-config",
    response_model=RiskConfigResponse,
    responses={
        200: {"description": "风控参数"},
        500: {"description": "服务器错误"},
    },
    summary="风控参数",
    description="获取当前风控参数配置",
)
def get_risk_config() -> RiskConfigResponse:
    try:
        return RiskConfigResponse(
            max_position_pct=settings.RISK_MAX_POSITION_PCT,
            max_daily_loss_pct=settings.RISK_MAX_DAILY_LOSS_PCT,
            max_order_value=settings.RISK_MAX_ORDER_VALUE,
            max_orders_per_min=settings.RISK_MAX_ORDERS_PER_MIN,
            max_daily_orders=settings.RISK_MAX_DAILY_ORDERS,
            signal_ttl_minutes=settings.RISK_SIGNAL_TTL_MINUTES,
        )
    except Exception as exc:
        logger.error(f"获取风控参数失败: {exc}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": f"获取风控参数失败: {str(exc)}"},
        )


@router.get(
    "/strategies",
    response_model=List[StrategyInfo],
    responses={
        200: {"description": "策略列表"},
        500: {"description": "服务器错误"},
    },
    summary="已注册策略",
    description="获取所有已注册的交易策略信息",
)
def get_strategies() -> List[StrategyInfo]:
    try:
        names = StrategyRegistry.list_strategies()
        strategies = []
        for name in names:
            try:
                cls = StrategyRegistry.get(name)
                strategies.append(StrategyInfo(
                    name=name,
                    class_name=cls.__name__,
                    enabled=True,
                ))
            except KeyError:
                continue
        return strategies
    except Exception as exc:
        logger.error(f"获取策略列表失败: {exc}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": f"获取策略列表失败: {str(exc)}"},
        )
