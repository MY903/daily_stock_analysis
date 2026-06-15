from enum import Enum
from dataclasses import dataclass
import logging
from datetime import datetime, date
from typing import Optional

from config.settings import settings
from src.trading.signal import Signal
from src.trading.loss_persistence import DailyLossStore

logger = logging.getLogger(__name__)


class RiskVerdict(Enum):
    PASS = "PASS"  # 风控通过
    REJECT = "REJECT"  # 风控拒绝


@dataclass
class RiskCheckResult:
    verdict: RiskVerdict
    reason: str = ""
    rule: str = ""  # 触发的风控规则名


class RiskManager:
    """
    交易风控管理器。

    规则：
    1. 单标的最大仓位 ≤ RISK_MAX_POSITION_PCT (默认5%)
    2. 每日累计亏损 ≤ RISK_MAX_DAILY_LOSS_PCT (默认8%)
    3. 最大持仓标的数 ≤ 10
    4. 信号有效期 ≤ RISK_SIGNAL_TTL_MINUTES (默认30分钟)
    5. 异常价格偏离 ≤ 10%（相对参考价）
    6. 同标的冷却时间 ≥ 30秒
    7. 单笔订单价值 ≤ RISK_MAX_ORDER_VALUE (默认 $10,000)
    8. 同标的每分钟下单频率 ≤ RISK_MAX_ORDERS_PER_MIN (默认 3)
    9. 每日总订单数 ≤ RISK_MAX_DAILY_ORDERS (默认 20)
    10. 日亏损熔断：每日累计亏损 ≥ RISK_MAX_DAILY_LOSS_PCT 时拦截所有交易
    """

    def __init__(self, loss_db_path: str = "data/daily_loss.db"):
        self._daily_loss_pct: float = 0.0
        self._daily_trades: dict[str, list] = {}  # symbol -> [trade_records]
        self._last_signal_time: dict[str, datetime] = {}  # symbol -> last_signal_time
        self._positions: dict[str, dict] = {}  # symbol -> position_info
        self._total_equity: float = 1_000_000.0  # 模拟总资产
        self._max_positions: int = 10
        # ---- 新规则所需的状态 ----
        self._order_timestamps: dict[str, list[datetime]] = {}  # symbol -> [timestamps]
        self._daily_order_count: int = 0
        # ---- SQLite 持久化 ----
        self._loss_store = DailyLossStore(db_path=loss_db_path)
        restored = self._loss_store.load_today_loss()
        if restored > 0:
            self._daily_loss_pct = restored
            logger.info(f"从 SQLite 恢复今日累计亏损: {restored:.2f}%")
        # 交易日跟踪（用于自动重置）
        self._current_trading_date: Optional[str] = None

    def update_total_equity(self, equity: float):
        """更新总资产（用于仓位计算）"""
        self._total_equity = equity

    def sync_equity(self, tiger_client, trading_date: Optional[str] = None) -> None:
        """从 Tiger Client 同步实际资产并检测交易日变更。

        1. 调用 TigerClient.get_account_summary() 获取 net_value
        2. 调用 update_total_equity() 更新总资产
        3. 检测交易日是否变更，自动重置每日统计

        Args:
            tiger_client: TigerClient 实例（需已连接）
            trading_date: 可选，指定当前交易日日期字符串 (YYYY-MM-DD)
        """
        today = trading_date or date.today().isoformat()

        # 检测交易日变更 → 自动重置
        if self._current_trading_date and self._current_trading_date != today:
            logger.info(
                "交易日变更: %s -> %s，自动重置每日统计",
                self._current_trading_date, today,
            )
            self.reset_daily()
        self._current_trading_date = today

        # 从 Tiger SDK 同步资产
        summary = tiger_client.get_account_summary()
        net_value = summary.get("net_value")
        if net_value is not None and net_value > 0:
            self.update_total_equity(float(net_value))
            logger.info(
                "总资产已同步: $%.2f (cash=%.2f, buying_power=%.2f)",
                net_value, summary.get("cash", 0), summary.get("buying_power", 0),
            )
        else:
            logger.warning(
                "获取账户摘要失败或净值为 0，保留当前总资产: $%.2f",
                self._total_equity,
            )

    def update_position(self, symbol: str, quantity: int, avg_price: float):
        """更新持仓信息"""
        self._positions[symbol] = {
            "quantity": quantity,
            "avg_price": avg_price,
            "updated_at": datetime.now(),
        }

    def update_daily_loss(self, symbol: str, loss_pct: float):
        """更新日亏损（百分比），同时写入 SQLite 持久化"""
        if symbol not in self._daily_trades:
            self._daily_trades[symbol] = []
        self._daily_trades[symbol].append({
            "loss_pct": loss_pct,
            "timestamp": datetime.now(),
        })
        # 计算总亏损（取所有标的的最大累计亏损）
        total_loss = sum(
            sum(t["loss_pct"] for t in trades)
            for trades in self._daily_trades.values()
        )
        self._daily_loss_pct = total_loss
        # 持久化到 SQLite
        self._loss_store.append_loss(symbol, loss_pct, datetime.now())

    def reset_daily(self):
        """每日重置（开市前调用）"""
        self._daily_loss_pct = 0.0
        self._daily_trades.clear()
        self._daily_order_count = 0
        self._order_timestamps.clear()
        self._loss_store.reset_daily()
        logger.info("每日风控计数器已重置（含 SQLite）")

    def _get_position_pct(self, symbol: str) -> float:
        """计算单个标的当前仓位占比（%）"""
        pos = self._positions.get(symbol)
        if not pos or self._total_equity <= 0:
            return 0.0
        return (pos["quantity"] * pos["avg_price"] / self._total_equity) * 100

    # ==================== 检查方法 ====================

    def check_position_limit(self, symbol: str, quantity: int, estimated_price: float) -> RiskCheckResult:
        """检查仓位上限（≤ RISK_MAX_POSITION_PCT%）"""
        current_pct = self._get_position_pct(symbol)
        new_pct = (quantity * estimated_price / self._total_equity) * 100
        total_pct = current_pct + new_pct
        limit = settings.RISK_MAX_POSITION_PCT
        if total_pct > limit:
            return RiskCheckResult(
                verdict=RiskVerdict.REJECT,
                reason=f"仓位超限: 当前{current_pct:.1f}% + 新增{new_pct:.1f}% = {total_pct:.1f}% > 上限{limit:.1f}%",
                rule="position_limit",
            )
        return RiskCheckResult(verdict=RiskVerdict.PASS)

    def check_daily_loss_limit(self) -> RiskCheckResult:
        """检查日亏损上限（≤ RISK_MAX_DAILY_LOSS_PCT%）"""
        limit = settings.RISK_MAX_DAILY_LOSS_PCT
        if self._daily_loss_pct > limit:
            return RiskCheckResult(
                verdict=RiskVerdict.REJECT,
                reason=f"日亏损超限: {self._daily_loss_pct:.1f}% >= 上限{limit:.1f}%",
                rule="daily_loss_limit",
            )
        return RiskCheckResult(verdict=RiskVerdict.PASS)

    def check_max_positions(self, symbol: str) -> RiskCheckResult:
        """检查最大持仓标的数"""
        active = [s for s, p in self._positions.items() if p["quantity"] > 0]
        if symbol not in active and len(active) >= self._max_positions:
            return RiskCheckResult(
                verdict=RiskVerdict.REJECT,
                reason=f"持仓标的数超限: {len(active)} >= {self._max_positions}",
                rule="max_positions",
            )
        return RiskCheckResult(verdict=RiskVerdict.PASS)

    def check_signal_expiry(self, signal: Signal) -> RiskCheckResult:
        """检查信号是否过期"""
        if signal.is_expired():
            return RiskCheckResult(
                verdict=RiskVerdict.REJECT,
                reason=f"信号已过期 (ID: {signal.signal_id})",
                rule="signal_expiry",
            )
        return RiskCheckResult(verdict=RiskVerdict.PASS)

    def check_abnormal_price(self, symbol: str, price: float, ref_price: float) -> RiskCheckResult:
        """检查异常价格偏离（偏离参考价 > 10%）"""
        if ref_price <= 0:
            return RiskCheckResult(verdict=RiskVerdict.PASS)  # 无参考价则跳过
        deviation = abs(price - ref_price) / ref_price * 100
        if deviation > 10.0:
            return RiskCheckResult(
                verdict=RiskVerdict.REJECT,
                reason=f"异常价格偏离: {deviation:.1f}% > 10%（参考价: {ref_price:.2f}, 当前价: {price:.2f}）",
                rule="abnormal_price",
            )
        return RiskCheckResult(verdict=RiskVerdict.PASS)

    def check_cooldown(self, symbol: str) -> RiskCheckResult:
        """检查同标的冷却时间（≥30秒）"""
        last = self._last_signal_time.get(symbol)
        if last and (datetime.now() - last).total_seconds() < 30:
            remaining = 30 - (datetime.now() - last).total_seconds()
            return RiskCheckResult(
                verdict=RiskVerdict.REJECT,
                reason=f"{symbol} 冷却中，剩余 {remaining:.0f} 秒",
                rule="cooldown",
            )
        return RiskCheckResult(verdict=RiskVerdict.PASS)

    # ==================== 新规则检查（Phase 2） ====================

    def check_order_value_limit(self, symbol: str, quantity: int, price: float) -> RiskCheckResult:
        """检查单笔订单价值上限（≤ RISK_MAX_ORDER_VALUE）"""
        order_value = quantity * price
        limit = settings.RISK_MAX_ORDER_VALUE
        if order_value > limit:
            return RiskCheckResult(
                verdict=RiskVerdict.REJECT,
                reason=f"订单价值超限: ${order_value:.2f} > 上限${limit:.2f} ({symbol})",
                rule="order_value_limit",
            )
        return RiskCheckResult(verdict=RiskVerdict.PASS)

    def check_order_frequency(self, symbol: str) -> RiskCheckResult:
        """检查同标的每分钟下单频率（≤ RISK_MAX_ORDERS_PER_MIN）"""
        limit = settings.RISK_MAX_ORDERS_PER_MIN
        now = datetime.now()
        timestamps = self._order_timestamps.get(symbol, [])
        # 只统计最近 60 秒内的时间戳
        recent = [t for t in timestamps if (now - t).total_seconds() <= 60]
        # 更新存储，移除过期时间戳
        self._order_timestamps[symbol] = recent
        if len(recent) >= limit:
            return RiskCheckResult(
                verdict=RiskVerdict.REJECT,
                reason=f"{symbol} 下单频率超限: {len(recent)}次/分钟 >= 上限{limit}次/分钟",
                rule="order_frequency",
            )
        return RiskCheckResult(verdict=RiskVerdict.PASS)

    def check_daily_order_count(self) -> RiskCheckResult:
        """检查每日总订单数（≤ RISK_MAX_DAILY_ORDERS）"""
        limit = settings.RISK_MAX_DAILY_ORDERS
        if self._daily_order_count > limit:
            return RiskCheckResult(
                verdict=RiskVerdict.REJECT,
                reason=f"每日订单数超限: {self._daily_order_count} >= 上限{limit}",
                rule="daily_order_count",
            )
        return RiskCheckResult(verdict=RiskVerdict.PASS)

    def check_circuit_breaker(self) -> RiskCheckResult:
        """检查日亏损熔断：累计亏损 ≥ RISK_MAX_DAILY_LOSS_PCT 时拦截所有交易"""
        limit = settings.RISK_MAX_DAILY_LOSS_PCT
        if self._daily_loss_pct >= limit:
            return RiskCheckResult(
                verdict=RiskVerdict.REJECT,
                reason=f"日亏损熔断触发: {self._daily_loss_pct:.1f}% >= 上限{limit:.1f}%",
                rule="circuit_breaker",
            )
        return RiskCheckResult(verdict=RiskVerdict.PASS)

    # ==================== 综合检查 ====================

    def check_all(self, signal: Signal, estimated_price: float, ref_price: float = 0) -> list[RiskCheckResult]:
        """
        执行全部风控检查。

        Returns:
            所有风控结果列表（PASS + REJECT）
        """
        results = [
            self.check_signal_expiry(signal),
            self.check_cooldown(signal.symbol),
        ]
        if signal.quantity and estimated_price > 0:
            results.append(self.check_position_limit(signal.symbol, signal.quantity, estimated_price))
            results.append(self.check_order_value_limit(signal.symbol, signal.quantity, estimated_price))
        results.append(self.check_daily_loss_limit())
        results.append(self.check_max_positions(signal.symbol))
        results.append(self.check_order_frequency(signal.symbol))
        results.append(self.check_daily_order_count())
        results.append(self.check_circuit_breaker())
        if ref_price > 0:
            results.append(self.check_abnormal_price(signal.symbol, estimated_price, ref_price))
        return results

    def is_allowed(self, signal: Signal, estimated_price: float, ref_price: float = 0) -> RiskCheckResult:
        """
        综合判断信号是否允许执行。

        Returns:
            第一个 FAIL 或全部 PASS
        """
        results = self.check_all(signal, estimated_price, ref_price)
        for r in results:
            if r.verdict == RiskVerdict.REJECT:
                return r
        # 更新冷却时间
        self._last_signal_time[signal.symbol] = datetime.now()
        # 跟踪下单频率和每日订单数
        if signal.symbol not in self._order_timestamps:
            self._order_timestamps[signal.symbol] = []
        self._order_timestamps[signal.symbol].append(datetime.now())
        self._daily_order_count += 1
        return RiskCheckResult(verdict=RiskVerdict.PASS)
