"""TQQQ 摆动交易策略

支持两种买入触发模式，适用于 TQQQ (3x 纳斯达克 100 杠杆 ETF)。

逻辑：
- IDLE 状态：
  - 百分比模式: 触发价 = 开盘价 * (1 - trigger_percentage)，日间动态计算
  - 固定模式: 当价格 <= 固定 trigger_price 时，发出买入信号
- HOLDING 状态：
  - 当价格 >= 止盈价（买入价 * (1 + tp_pct)）时，发出止盈信号
  - 当价格 <= 止损价（买入价 * (1 - sl_pct)）时，发出止损信号
"""

import logging
from typing import Optional, Dict, Any

from src.trading.config import AppConfig
from src.trading.state_machine import TradingState
from src.trading.strategy.base import BaseStrategy, Signal, MarketData, PositionInfo

logger = logging.getLogger(__name__)


class TQQQSwingStrategy(BaseStrategy):
    """TQQQ 摆动交易策略

    支持两种买入触发模式：
    1. 开盘百分比模式: trigger_percentage > 0，触发价 = 开盘价 * (1 - trigger_percentage)
    2. 固定价格模式: trigger_percentage == 0，使用固定的 trigger_price
    """

    def __init__(self, config: AppConfig):
        super().__init__(config)
        self._trading = config.trading

    @property
    def name(self) -> str:
        return "TQQQ-Swing"

    def evaluate(self, quote: Dict[str, Any], state: str,
                 context: Dict[str, Any]) -> Optional[Signal]:
        """评估行情并生成信号"""
        latest_price = self._extract_price(quote)
        if latest_price is None:
            return None

        current_state = TradingState(state)

        if current_state == TradingState.IDLE:
            return self._check_buy_signal(latest_price, quote)
        elif current_state == TradingState.HOLDING:
            return self._check_exit_signal(latest_price, context)

        return None

    def _check_buy_signal(self, price: float,
                          quote: Dict[str, Any]) -> Optional[Signal]:
        """检查买入信号

        优先使用开盘百分比模式（trigger_percentage > 0），
        计算 触发价 = 开盘价 * (1 - trigger_percentage)；
        兜底使用固定 trigger_price。
        """
        entry = self._trading.entry
        pct = entry.trigger_percentage

        if pct > 0:
            # 百分比模式：基于开盘价计算动态触发价
            open_price = quote.get("open")
            if open_price is None or open_price <= 0:
                logger.debug("百分比模式缺少开盘价，回退到固定触发价")
                trigger = entry.trigger_price
            else:
                trigger = round(open_price * (1 - pct), 2)
        else:
            trigger = entry.trigger_price

        if price <= trigger:
            return Signal(
                action="buy",
                reason=f"价格 {price:.2f} <= 触发价 {trigger:.2f}",
                price=price,
                trigger_price=trigger,
            )
        return None

    def _check_exit_signal(self, price: float,
                           context: Dict[str, Any]) -> Optional[Signal]:
        """检查止盈/止损信号"""
        fill_price = context.get("fill_price", 0)
        if not fill_price:
            return None

        # 止盈检查
        tp_price = fill_price * (1 + self._trading.take_profit.percentage)
        if price >= tp_price:
            return Signal(
                action="take_profit",
                reason=f"价格 {price:.2f} >= 止盈价 {tp_price:.2f} "
                       f"(+{self._trading.take_profit.percentage*100:.1f}%)",
                price=price,
            )

        # 止损检查
        sl_price = fill_price * (1 - self._trading.stop_loss.percentage)
        if price <= sl_price:
            return Signal(
                action="stop_loss",
                reason=f"价格 {price:.2f} <= 止损价 {sl_price:.2f} "
                       f"(-{self._trading.stop_loss.percentage*100:.1f}%)",
                price=price,
            )

        return None

    def get_target_prices(self, fill_price: float) -> Dict[str, float]:
        """计算目标价位（用于通知和展示）"""
        return {
            "entry": fill_price,
            "take_profit": round(fill_price * (1 + self._trading.take_profit.percentage), 2),
            "stop_loss": round(fill_price * (1 - self._trading.stop_loss.percentage), 2),
        }

    def should_enter(self, market_data: MarketData) -> bool:
        """判断是否应该入场

        当最新价格 <= 触发价时返回 True（与 _check_buy_signal 逻辑一致）。

        Args:
            market_data: 行情字典，需包含 latest_price 和可选的 open

        Returns:
            True 表示应入场
        """
        price = self._extract_price(market_data)
        if price is None:
            return False
        signal = self._check_buy_signal(price, market_data)
        return signal is not None

    def should_exit(self, position: PositionInfo) -> bool:
        """判断是否应该出场

        当最新价格 >= 止盈价 或 <= 止损价时返回 True。

        Args:
            position: 持仓信息，需包含 fill_price 和 latest_price

        Returns:
            True 表示应出场
        """
        fill_price = position.get("fill_price", 0)
        latest_price = position.get("latest_price", 0)
        if not fill_price or not latest_price:
            return False

        # 止盈检查
        tp_price = fill_price * (1 + self._trading.take_profit.percentage)
        if latest_price >= tp_price:
            return True

        # 止损检查
        sl_price = fill_price * (1 - self._trading.stop_loss.percentage)
        if latest_price <= sl_price:
            return True

        return False

    @staticmethod
    def _extract_price(quote: Dict[str, Any]) -> Optional[float]:
        """从行情数据中提取最新价格"""
        price = quote.get("latest_price")
        if price is not None:
            return float(price)
        # WebSocket 推送格式
        items = quote.get("items", [])
        for item in items:
            if isinstance(item, dict):
                p = item.get("latest_price") or item.get("latestPrice")
                if p is not None:
                    return float(p)
        return None
