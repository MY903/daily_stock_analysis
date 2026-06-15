"""策略基类

定义交易策略的统一接口。
"""

import logging
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any

from src.trading.config import AppConfig

logger = logging.getLogger(__name__)


# 通用市场数据类型
MarketData = Dict[str, Any]
PositionInfo = Dict[str, Any]


class Signal:
    """交易信号"""

    def __init__(self, action: str, reason: str, price: float = 0.0,
                 trigger_price: Optional[float] = None):
        """
        Args:
            action: "buy" / "take_profit" / "stop_loss" / "hold"
            reason: 信号描述
            price: 触发时的最新价格
            trigger_price: 买入触发价（百分比策略时为动态计算值）
        """
        self.action = action
        self.reason = reason
        self.price = price
        self.trigger_price = trigger_price or 0.0

    def __repr__(self) -> str:
        return f"Signal(action={self.action}, price={self.price}, reason={self.reason})"


class BaseStrategy(ABC):
    """策略基类

    支持两种接口风格：
    1. evaluate() — 结合状态机的完整评估（现有风格）
    2. should_enter() / should_exit() — 独立信号判断（新风格）
    """

    def __init__(self, config: AppConfig):
        self._config = config

    @property
    def symbol(self) -> str:
        """策略关联的标的"""
        return self._config.trading.symbol

    @property
    @abstractmethod
    def name(self) -> str:
        """策略名称"""
        ...

    @abstractmethod
    def evaluate(self, quote: Dict[str, Any], state: str,
                 context: Dict[str, Any]) -> Optional[Signal]:
        """评估当前行情，生成交易信号

        Args:
            quote: 最新行情数据
            state: 当前状态机状态
            context: 状态上下文（包含持仓信息）

        Returns:
            Signal 或 None（无信号）
        """
        ...

    def should_enter(self, market_data: MarketData) -> bool:
        """判断是否应该入场

        子类可覆盖此方法以提供独立的入场判断逻辑。
        默认实现返回 False（由 evaluate 驱动的策略无需覆盖）。

        Args:
            market_data: 市场行情数据

        Returns:
            True 表示应入场
        """
        return False

    def should_exit(self, position: PositionInfo) -> bool:
        """判断是否应该出场

        子类可覆盖此方法以提供独立的出场判断逻辑。
        默认实现返回 False（由 evaluate 驱动的策略无需覆盖）。

        Args:
            position: 当前持仓信息

        Returns:
            True 表示应出场
        """
        return False
