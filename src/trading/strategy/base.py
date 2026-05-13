"""策略基类

定义交易策略的统一接口。
"""

import logging
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any

from src.trading.config import AppConfig

logger = logging.getLogger(__name__)


class Signal:
    """交易信号"""

    def __init__(self, action: str, reason: str, price: float = 0.0):
        """
        Args:
            action: "buy" / "take_profit" / "stop_loss" / "hold"
            reason: 信号描述
            price: 触发时的最新价格
        """
        self.action = action
        self.reason = reason
        self.price = price

    def __repr__(self) -> str:
        return f"Signal(action={self.action}, price={self.price}, reason={self.reason})"


class BaseStrategy(ABC):
    """策略基类"""

    def __init__(self, config: AppConfig):
        self._config = config

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
