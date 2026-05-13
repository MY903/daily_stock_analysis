"""TQQQ 摆动交易策略

基于固定价位的买入/止盈/止损策略，适用于 TQQQ (3x 纳斯达克 100 杠杆 ETF)。

逻辑：
- IDLE 状态：当价格 <= 买入触发价 时，发出买入信号
- HOLDING 状态：
  - 当价格 >= 止盈价（买入价 * (1 + tp_pct)）时，发出止盈信号
  - 当价格 <= 止损价（买入价 * (1 - sl_pct)）时，发出止损信号
"""

import logging
from typing import Optional, Dict, Any

from src.trading.config import AppConfig
from src.trading.state_machine import TradingState
from src.trading.strategy.base import BaseStrategy, Signal

logger = logging.getLogger(__name__)


class TQQQSwingStrategy(BaseStrategy):
    """TQQQ 摆动交易策略"""

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
            return self._check_buy_signal(latest_price)
        elif current_state == TradingState.HOLDING:
            return self._check_exit_signal(latest_price, context)

        return None

    def _check_buy_signal(self, price: float) -> Optional[Signal]:
        """检查买入信号：价格 <= 触发价"""
        trigger = self._trading.entry.trigger_price
        if price <= trigger:
            return Signal(
                action="buy",
                reason=f"价格 {price:.2f} <= 触发价 {trigger:.2f}",
                price=price,
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
