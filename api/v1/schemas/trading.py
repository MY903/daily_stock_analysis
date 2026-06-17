# -*- coding: utf-8 -*-
"""Trading API schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class SystemStatus(BaseModel):
    """系统运行状态"""

    trading_mode: str = Field(..., description="交易模式: SANDBOX/PAPER/PROD")
    tiger_connected: bool = Field(..., description="Tiger API 连接状态")
    market_status: str = Field(..., description="美股市场状态")


class AccountSummary(BaseModel):
    """账户资产摘要"""

    net_value: float = Field(0.0, description="账户净值")
    cash: float = Field(0.0, description="可用现金")
    buying_power: float = Field(0.0, description="购买力")


class Position(BaseModel):
    """持仓信息"""

    symbol: str = Field(..., description="股票代码")
    quantity: int = Field(0, description="持仓数量")
    avg_price: float = Field(0.0, description="平均成本价")
    market_value: float = Field(0.0, description="市值")
    pnl_pct: float = Field(0.0, description="盈亏百分比")


class Order(BaseModel):
    """订单信息"""

    order_id: str = Field(..., description="订单 ID")
    symbol: str = Field(..., description="股票代码")
    action: str = Field(..., description="订单方向: BUY/SELL")
    quantity: int = Field(0, description="订单数量")
    filled: int = Field(0, description="已成交数量")
    price: float = Field(0.0, description="订单价格")
    status: str = Field(..., description="订单状态")


class SignalCreate(BaseModel):
    """创建交易信号请求"""

    symbol: str = Field(..., description="股票代码")
    action: str = Field(..., description="交易方向: BUY/SELL/HOLD")
    quantity: int = Field(35, description="交易数量")
    confidence: float = Field(0.85, ge=0.0, le=1.0, description="置信度 0-1")
    rationale: str = Field("", description="交易理据")


class SignalResponse(BaseModel):
    """交易信号响应"""

    signal_id: str = Field(..., description="信号 ID")
    symbol: str = Field(..., description="股票代码")
    action: str = Field(..., description="交易方向")
    quantity: Optional[int] = Field(None, description="交易数量")
    price_target: Optional[float] = Field(None, description="目标价格")
    confidence: float = Field(..., description="置信度")
    status: str = Field(..., description="信号状态")
    created_at: datetime = Field(..., description="创建时间")
    rationale: str = Field("", description="交易理据")


class RiskConfigResponse(BaseModel):
    """风控参数响应"""

    max_position_pct: float = Field(..., description="单标的最高仓位占比（%）")
    max_daily_loss_pct: float = Field(..., description="单日最大亏损占比（%）")
    max_order_value: float = Field(..., description="单笔订单最大价值（美元）")
    max_orders_per_min: int = Field(..., description="同一标的每分钟最大下单次数")
    max_daily_orders: int = Field(..., description="每日最大总订单数")
    signal_ttl_minutes: int = Field(..., description="信号有效时长（分钟）")


class StrategyInfo(BaseModel):
    """策略信息"""

    name: str = Field(..., description="策略名称")
    class_name: str = Field(..., description="策略类名")
    enabled: bool = Field(True, description="是否启用")
