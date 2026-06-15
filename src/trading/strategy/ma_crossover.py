"""MA 交叉策略

基于快慢移动平均线的交叉信号决定入场和出场。
- 快线（默认 5 周期）上穿慢线（默认 20 周期）→ 入场
- 快线下穿慢线 → 出场
"""

import logging
from typing import Dict, Any, List, Optional

from src.trading.config import AppConfig
from src.trading.strategy.base import BaseStrategy, MarketData, PositionInfo, Signal
from src.trading.strategy.registry import StrategyRegistry

logger = logging.getLogger(__name__)


def _sma(values: List[float], period: int) -> Optional[float]:
    """计算简单移动平均线（纯 Python，无外部依赖）

    Args:
        values: 价格列表（按时间升序排列，最新的在最后）
        period: 计算周期

    Returns:
        平均值，数据不足时返回 None
    """
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def _extract_closes(data: Dict[str, Any]) -> List[float]:
    """从数据中提取收盘价序列

    market_data / position 中通过 "klines" 键传递 K 线数据，
    支持两种常见格式：
    1. dict 格式: [{"close": 100.0, "high": 101.0, ...}, ...]
    2. list 格式: [[open, high, low, close, volume, ...], ...]
       按 tuple/list 第 4 个元素（index=3）提取收盘价。

    Args:
        data: 市场数据或持仓信息字典

    Returns:
        收盘价列表（升序排列，最新的在最后）
    """
    klines = data.get("klines", [])
    if not klines:
        return []

    first = klines[0]
    if isinstance(first, dict):
        return [float(k["close"]) for k in klines if k.get("close") is not None]

    if isinstance(first, (list, tuple)) and len(first) >= 4:
        return [float(k[3]) for k in klines]

    return []


@StrategyRegistry.register
class MACrossoverStrategy(BaseStrategy):
    """MA 交叉策略

    使用快慢移动平均线的交叉信号判断趋势方向：
    - 快线上穿慢线  → 上升趋势启动，入场做多
    - 快线下穿慢线  → 上升趋势结束，出场离场

    配置项（通过 trading.yaml 的 ``ma:`` 节配置）:
        fast_period (int): 快线周期，默认 5
        slow_period (int): 慢线周期，默认 20
    """

    def __init__(self, config: AppConfig):
        super().__init__(config)
        ma_config = config.trading.ma
        self._fast_period = ma_config.fast_period
        self._slow_period = ma_config.slow_period

        if self._fast_period >= self._slow_period:
            logger.warning(
                "快线周期 (%d) >= 慢线周期 (%d)，交叉信号可能异常",
                self._fast_period,
                self._slow_period,
            )

    # ---------------------------------------------------------------
    # BaseStrategy 接口
    # ---------------------------------------------------------------

    @property
    def name(self) -> str:
        """策略名称"""
        return "MA-Crossover"

    def evaluate(
        self,
        quote: Dict[str, Any],
        state: str,
        context: Dict[str, Any],
    ) -> Optional[Signal]:
        """MA 交叉策略由 should_enter/should_exit 驱动，不依赖 evaluate"""
        return None

    # ---------------------------------------------------------------
    # 入场 / 出场信号
    # ---------------------------------------------------------------

    def should_enter(self, market_data: MarketData) -> bool:
        """判断是否入场：快线上穿慢线

        计算逻辑：
        1. 从 market_data["klines"] 提取收盘价序列
        2. 分别计算前一周期的快/慢 SMA 和当前周期的快/慢 SMA
        3. 当前周期快线 > 慢线 且 前一周期快线 <= 慢线 → 上穿

        Args:
            market_data: 行情数据，需包含 ``klines`` 键
                （每根 K 线为 dict 或 list 格式）

        Returns:
            True 表示快线刚完成上穿
        """
        closes = _extract_closes(market_data)
        if len(closes) < self._slow_period + 1:
            return False

        fast_prev = _sma(closes[:-1], self._fast_period)
        fast_curr = _sma(closes, self._fast_period)
        slow_prev = _sma(closes[:-1], self._slow_period)
        slow_curr = _sma(closes, self._slow_period)

        if None in (fast_prev, fast_curr, slow_prev, slow_curr):
            return False

        # 上穿：前一周期快线 <= 慢线，当前周期快线 > 慢线
        return fast_prev <= slow_prev and fast_curr > slow_curr

    def should_exit(self, position: PositionInfo) -> bool:
        """判断是否出场：快线下穿慢线

        计算逻辑：
        1. 从 position["klines"] 提取收盘价序列
        2. 分别计算前一周期的快/慢 SMA 和当前周期的快/慢 SMA
        3. 当前周期快线 < 慢线 且 前一周期快线 >= 慢线 → 下穿

        Args:
            position: 持仓信息，需包含 ``klines`` 键
                （同 market_data 格式）

        Returns:
            True 表示快线刚完成下穿
        """
        closes = _extract_closes(position)
        if len(closes) < self._slow_period + 1:
            return False

        fast_prev = _sma(closes[:-1], self._fast_period)
        fast_curr = _sma(closes, self._fast_period)
        slow_prev = _sma(closes[:-1], self._slow_period)
        slow_curr = _sma(closes, self._slow_period)

        if None in (fast_prev, fast_curr, slow_prev, slow_curr):
            return False

        # 下穿：前一周期快线 >= 慢线，当前周期快线 < 慢线
        return fast_prev >= slow_prev and fast_curr < slow_curr
