"""
AI 信号生成管道

提供技术规则信号、AI 信号解析和信号聚合功能。
"""

import logging
from typing import Optional

from src.trading.signal import Signal, SignalSource, SignalAction

logger = logging.getLogger(__name__)


def _compute_sma(prices: list[float], period: int) -> Optional[float]:
    """计算简单移动平均"""
    if len(prices) < period:
        return None
    return sum(prices[-period:]) / period


def _compute_rsi(prices: list[float], period: int = 14) -> Optional[float]:
    """
    计算 RSI 指标。

    Args:
        prices: 收盘价序列（从旧到新）
        period: RSI 计算周期，默认 14

    Returns:
        RSI 值 (0-100)，数据不足时返回 None
    """
    if len(prices) < period + 1:
        return None
    # 计算 period 个价格差
    gains, losses = 0.0, 0.0
    for i in range(1, period + 1):
        diff = prices[-i] - prices[-i - 1]
        if diff >= 0:
            gains += diff
        else:
            losses += abs(diff)
    avg_gain = gains / period
    avg_loss = losses / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def _compute_volume_breakout_ratio(current_volume: float, volumes: list[float], period: int = 5) -> Optional[float]:
    """计算成交量突破比率（当前量 / 均量），数据不足返回 None"""
    if len(volumes) < period or volumes[-1] <= 0:
        return None
    avg_volume = sum(volumes[-period:]) / period
    if avg_volume <= 0:
        return None
    return current_volume / avg_volume


class TechnicalSignalSource:
    """基于技术指标的规则信号源"""

    def generate(self, symbol: str, ohlcv_data: Optional[list[dict]] = None) -> list[Signal]:
        """
        生成技术规则信号。

        检测规则：
        - MA crossover: 5日均线上穿20日均线 → BUY，下穿 → SELL
        - RSI 超买/超卖: RSI < 30 → BUY, RSI > 70 → SELL
        - Volume 突破: 成交量 > 5日均量 * 1.5 → HOLD(关注)

        Args:
            symbol: 股票代码
            ohlcv_data: OHLCV 数据列表，每项包含 close, volume 等字段。
                        若为 None 或数据不足，返回空列表。

        Returns:
            技术信号列表

        TODO: 接入 TigerClient.get_quote() 获取实时行情
        """
        signals = []
        if not ohlcv_data or len(ohlcv_data) < 20:
            logger.debug("数据不足，跳过 %s 的技术信号生成 (need >=20 bars, got %d)",
                         symbol, len(ohlcv_data) if ohlcv_data else 0)
            return signals

        close_prices = [bar.get("close", 0) for bar in ohlcv_data if bar.get("close")]
        volumes = [bar.get("volume", 0) for bar in ohlcv_data if bar.get("volume")]

        if len(close_prices) < 20:
            logger.debug("收盘价数据不足，跳过 %s", symbol)
            return signals

        # --- 1. MA Crossover ---
        ma5 = _compute_sma(close_prices, 5)
        ma20 = _compute_sma(close_prices, 20)
        if ma5 is not None and ma20 is not None:
            prev_ma5 = _compute_sma(close_prices[:-1], 5)
            prev_ma20 = _compute_sma(close_prices[:-1], 20)
            if prev_ma5 is not None and prev_ma20 is not None:
                if prev_ma5 <= prev_ma20 and ma5 > ma20:
                    signals.append(Signal(
                        symbol=symbol,
                        action=SignalAction.BUY,
                        confidence=0.65,
                        rationale=f"MA5 上穿 MA20 (MA5={ma5:.2f}, MA20={ma20:.2f})",
                        source=SignalSource.RULE,
                    ))
                    logger.info("%s: MA5 上穿 MA20 → BUY", symbol)
                elif prev_ma5 >= prev_ma20 and ma5 < ma20:
                    signals.append(Signal(
                        symbol=symbol,
                        action=SignalAction.SELL,
                        confidence=0.65,
                        rationale=f"MA5 下穿 MA20 (MA5={ma5:.2f}, MA20={ma20:.2f})",
                        source=SignalSource.RULE,
                    ))
                    logger.info("%s: MA5 下穿 MA20 → SELL", symbol)

        # --- 2. RSI 超买/超卖 ---
        rsi = _compute_rsi(close_prices)
        if rsi is not None:
            if rsi < 30:
                signals.append(Signal(
                    symbol=symbol,
                    action=SignalAction.BUY,
                    confidence=0.70,
                    rationale=f"RSI 超卖: {rsi:.1f} < 30",
                    source=SignalSource.RULE,
                ))
                logger.info("%s: RSI=%.1f 超卖 → BUY", symbol, rsi)
            elif rsi > 70:
                signals.append(Signal(
                    symbol=symbol,
                    action=SignalAction.SELL,
                    confidence=0.70,
                    rationale=f"RSI 超买: {rsi:.1f} > 70",
                    source=SignalSource.RULE,
                ))
                logger.info("%s: RSI=%.1f 超买 → SELL", symbol, rsi)

        # --- 3. Volume 突破 ---
        if len(volumes) >= 5:
            current_volume = volumes[-1]
            ratio = _compute_volume_breakout_ratio(current_volume, volumes)
            if ratio is not None and ratio > 1.5:
                avg_vol_5 = sum(volumes[-5:]) / 5
                signals.append(Signal(
                    symbol=symbol,
                    action=SignalAction.HOLD,
                    confidence=0.60,
                    rationale=f"成交量突破: 当前量{current_volume:.0f} = 5日均量{avg_vol_5:.0f} * {ratio:.1f}",
                    source=SignalSource.RULE,
                ))
                logger.info("%s: 成交量突破 %.1f 倍 → HOLD(关注)", symbol, ratio)

        return signals


class AISignalSource:
    """AI 信号源——解析 LLM 的结构化输出"""

    def parse_llm_response(self, llm_json: dict) -> list[Signal]:
        """
        解析 LLM 的 JSON 响应为 Signal 列表。

        LLM 输出格式示例：
        {
            "signals": [
                {
                    "symbol": "AAPL",
                    "action": "BUY",
                    "confidence": 0.85,
                    "price_target": 150.0,
                    "quantity": 100,
                    "rationale": "Strong bullish divergence on RSI"
                }
            ]
        }

        也支持顶层直接包含信号字段（单信号简写）：
        {
            "symbol": "AAPL",
            "action": "BUY",
            "confidence": 0.85,
            "rationale": "..."
        }

        Args:
            llm_json: LLM 返回的 JSON 字典

        Returns:
            Signal 列表
        """
        signals = []
        if not isinstance(llm_json, dict):
            logger.warning("LLM 响应不是 dict 类型: %s", type(llm_json))
            return signals

        # 尝试从 "signals" 字段读取列表
        raw_signals = llm_json.get("signals", [])

        # 兼容单信号格式（顶层直接是信号字段）
        if not raw_signals and "symbol" in llm_json:
            raw_signals = [llm_json]

        if not isinstance(raw_signals, list):
            logger.warning("LLM signals 字段不是 list: %s", type(raw_signals))
            return signals

        for raw in raw_signals:
            if not isinstance(raw, dict):
                continue
            try:
                action_str = raw.get("action", "HOLD").upper()
                if action_str not in ("BUY", "SELL", "HOLD"):
                    action_str = "HOLD"

                confidence = min(max(float(raw.get("confidence", 0.5)), 0.0), 1.0)

                signal = Signal(
                    symbol=raw.get("symbol", "UNKNOWN"),
                    action=SignalAction(action_str),
                    price_target=raw.get("price_target"),
                    quantity=raw.get("quantity"),
                    confidence=confidence,
                    rationale=raw.get("rationale", ""),
                    source=SignalSource.AI,
                )
                signals.append(signal)
            except (ValueError, TypeError) as e:
                logger.warning("解析 LLM 信号失败: %s, raw=%s", e, raw)
                continue

        return signals


class SignalAggregator:
    """信号聚合器——去重、冲突解决"""

    def aggregate(self, signals: list[Signal]) -> list[Signal]:
        """
        聚合信号：
        1. 同标的同方向合并，保留高置信度
        2. 同标的不同方向冲突解决，保留置信度高的
        3. 按置信度降序排列

        Args:
            signals: 原始信号列表

        Returns:
            聚合后的信号列表
        """
        if not signals:
            return []

        # 按 symbol 分组
        by_symbol: dict[str, list[Signal]] = {}
        for s in signals:
            by_symbol.setdefault(s.symbol, []).append(s)

        result: list[Signal] = []
        for symbol, sym_signals in by_symbol.items():
            if len(sym_signals) == 1:
                result.append(sym_signals[0])
                continue

            # 按方向分组，每个方向只保留最高置信度
            best_per_action: dict[str, Signal] = {}
            for s in sym_signals:
                key = s.action.value  # "BUY" / "SELL" / "HOLD"
                if key not in best_per_action or s.confidence > best_per_action[key].confidence:
                    best_per_action[key] = s

            # 冲突解决：同一标的有多个方向时，仅保留置信度最高的那个信号
            best = max(best_per_action.values(), key=lambda x: x.confidence)
            result.append(best)

        # 按置信度降序排列
        result.sort(key=lambda x: x.confidence, reverse=True)
        return result


class SignalGenerator:
    """信号生成主入口"""

    def __init__(self):
        self.technical_source = TechnicalSignalSource()
        self.ai_source = AISignalSource()
        self.aggregator = SignalAggregator()

    def generate_pre_market_signals(self, symbols: list[str]) -> list[Signal]:
        """
        盘前生成信号：仅用技术规则（无实时 LLM）。

        Args:
            symbols: 待扫描的股票代码列表

        Returns:
            聚合后的信号列表
        """
        signals: list[Signal] = []
        for symbol in symbols:
            signals.extend(self.technical_source.generate(symbol))
        return self.aggregator.aggregate(signals)

    def generate_intraday_signals(self, symbols: list[str], market_data: Optional[dict] = None) -> list[Signal]:
        """
        盘中生成信号：技术 + AI。

        Args:
            symbols: 待扫描的股票代码列表
            market_data: 盘中市场数据（预留接口，当前未使用）

        Returns:
            聚合后的信号列表
        """
        # 当前为骨架实现，先返回技术信号
        signals: list[Signal] = []
        for symbol in symbols:
            tech_signals = self.technical_source.generate(symbol)
            signals.extend(tech_signals)
        return self.aggregator.aggregate(signals)

    def parse_ai_signals(self, llm_json: dict) -> list[Signal]:
        """解析 LLM 输出为 AI 信号列表。"""
        return self.ai_source.parse_llm_response(llm_json)
