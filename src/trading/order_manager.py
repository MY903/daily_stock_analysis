"""订单管理器

负责订单的创建、监控、撤销和状态同步。
包含防重复下单和 GTC 订单清理逻辑。

支持多标的：订单按 symbol 分组管理，冷却期按 symbol 隔离。
"""

import logging
import time
from typing import Optional, Dict, Any, Tuple, List

from src.trading.config import AppConfig
from src.trading.tiger_client import TigerClient

logger = logging.getLogger(__name__)


class OrderManager:
    """订单管理器

    功能：
    - 提交买入/止盈/止损订单
    - 轮询订单状态
    - 防重复下单（signal_cooldown 内不重复触发）
    - 清理过期 GTC 挂单
    - 多标的支持：操作按 symbol 隔离
    """

    def __init__(self, client: TigerClient, config: AppConfig):
        self._client = client
        self._config = config
        # 冷却 key: "{symbol}:{signal_type}" -> timestamp
        self._last_signal_time: Dict[str, float] = {}

    # ==================== 防重复下单（按 symbol 隔离） ====================

    def _signal_key(self, signal_type: str, symbol: str) -> str:
        """生成信号冷却 key"""
        return f"{symbol}:{signal_type}"

    def can_place_order(self, signal_type: str,
                        symbol: Optional[str] = None) -> bool:
        """检查是否可以下单（防重复）

        冷却期按 symbol 隔离，TQQQ 的买入冷却不影响 AAPL 的买入。

        Args:
            signal_type: 信号类型，如 "buy", "take_profit", "stop_loss"
            symbol: 标的，默认使用配置中的 symbol

        Returns:
            是否允许下单
        """
        symbol = symbol or self._config.trading.symbol
        cooldown = self._config.bot.signal_cooldown
        key = self._signal_key(signal_type, symbol)
        last_time = self._last_signal_time.get(key, 0)
        elapsed = time.time() - last_time
        if elapsed < cooldown:
            logger.debug("信号冷却中: %s/%s (剩余 %.0f 秒)",
                         symbol, signal_type, cooldown - elapsed)
            return False
        return True

    def record_signal(self, signal_type: str,
                      symbol: Optional[str] = None) -> None:
        """记录信号触发时间

        Args:
            signal_type: 信号类型
            symbol: 标的，默认使用配置中的 symbol
        """
        symbol = symbol or self._config.trading.symbol
        key = self._signal_key(signal_type, symbol)
        self._last_signal_time[key] = time.time()

    # ==================== 订单提交（按 symbol） ====================

    def submit_buy_order(self, symbol: Optional[str] = None) -> Optional[int]:
        """提交买入限价单

        Args:
            symbol: 标的，默认使用配置中的 symbol

        Returns:
            订单 ID，失败或模式限制返回 None
        """
        trading = self._config.trading
        symbol = symbol or trading.symbol
        entry = trading.entry

        if not self.can_place_order("buy", symbol):
            return None

        if not trading.auto_trade:
            logger.info("[ALERT-ONLY] 买入信号触发，但未开启自动交易: "
                        "symbol=%s, price=%.2f, qty=%d",
                        symbol, entry.trigger_price, entry.quantity)
            self.record_signal("buy", symbol)
            return None

        order_id = self._client.place_limit_buy(
            symbol=symbol,
            quantity=entry.quantity,
            price=entry.trigger_price,
            time_in_force=entry.time_in_force,
        )

        if order_id is not None:
            self.record_signal("buy", symbol)
        return order_id

    def submit_take_profit_order(self, quantity: int,
                                 fill_price: float,
                                 symbol: Optional[str] = None) -> Optional[int]:
        """提交止盈限价单

        Args:
            quantity: 卖出数量
            fill_price: 买入成交价（用于计算止盈价）
            symbol: 标的，默认使用配置中的 symbol

        Returns:
            订单 ID
        """
        trading = self._config.trading
        symbol = symbol or trading.symbol
        tp = trading.take_profit
        target_price = round(fill_price * (1 + tp.percentage), 2)

        if not self.can_place_order("take_profit", symbol):
            return None

        if not trading.auto_trade:
            logger.info("[ALERT-ONLY] 止盈条件满足（仅通知）: symbol=%s, target=%.2f",
                        symbol, target_price)
            self.record_signal("take_profit", symbol)
            return None

        order_id = self._client.place_limit_sell(
            symbol=symbol,
            quantity=quantity,
            price=target_price,
            time_in_force=tp.time_in_force,
        )

        if order_id is not None:
            self.record_signal("take_profit", symbol)
        return order_id

    def submit_stop_loss_order(self, quantity: int,
                               fill_price: float,
                               symbol: Optional[str] = None) -> Optional[int]:
        """提交止损限价单

        Args:
            quantity: 卖出数量
            fill_price: 买入成交价（用于计算止损价）
            symbol: 标的，默认使用配置中的 symbol

        Returns:
            订单 ID
        """
        trading = self._config.trading
        symbol = symbol or trading.symbol
        sl = trading.stop_loss
        stop_price = round(fill_price * (1 - sl.percentage), 2)
        limit_price = round(stop_price * (1 - sl.limit_offset), 2)

        if not self.can_place_order("stop_loss", symbol):
            return None

        if not trading.auto_trade:
            logger.info("[ALERT-ONLY] 止损条件满足（仅通知）: symbol=%s, stop=%.2f",
                        symbol, stop_price)
            self.record_signal("stop_loss", symbol)
            return None

        order_id = self._client.place_stop_limit_sell(
            symbol=symbol,
            quantity=quantity,
            stop_price=stop_price,
            limit_price=limit_price,
            time_in_force=sl.time_in_force,
        )

        if order_id is not None:
            self.record_signal("stop_loss", symbol)
        return order_id

    def submit_exit_orders(self, quantity: int,
                           fill_price: float,
                           symbol: Optional[str] = None
                           ) -> Tuple[Optional[int], Optional[int]]:
        """同时提交止盈和止损订单（买入成交后调用）

        Args:
            quantity: 卖出数量
            fill_price: 买入成交价
            symbol: 标的，默认使用配置中的 symbol

        Returns:
            (止盈订单ID, 止损订单ID)
        """
        symbol = symbol or self._config.trading.symbol
        tp_id = self.submit_take_profit_order(quantity, fill_price, symbol)
        sl_id = self.submit_stop_loss_order(quantity, fill_price, symbol)
        return tp_id, sl_id

    # ==================== 订单查询 ====================

    def check_order_status(self, order_id: int) -> Optional[Dict[str, Any]]:
        """查询订单当前状态

        Returns:
            订单信息字典，包含 status, filled_quantity, avg_fill_price 等
        """
        return self._client.get_order(order_id)

    def is_order_filled(self, order_id: int) -> Tuple[bool, float]:
        """检查订单是否完全成交

        Returns:
            (是否成交, 成交均价)
        """
        info = self.check_order_status(order_id)
        if info is None:
            return False, 0.0

        status = info.get("status", "")
        if status in ("Filled",):
            return True, info.get("avg_fill_price", 0.0)
        return False, 0.0

    def is_order_cancelled(self, order_id: int) -> bool:
        """检查订单是否已被撤销"""
        info = self.check_order_status(order_id)
        if info is None:
            return False
        status = info.get("status", "")
        return status in ("Cancelled", "Inactive", "ApiCancelled")

    def get_active_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """查询活跃订单，支持按 symbol 过滤

        Args:
            symbol: 如果指定，只返回该标的的活跃订单

        Returns:
            活跃订单列表
        """
        orders = self._client.get_active_orders()
        if symbol and orders:
            orders = [o for o in orders if o.get("symbol") == symbol
                      or o.get("contractSymbol") == symbol
                      or o.get("contract_code") == symbol]
        return orders

    # ==================== 订单撤销 ====================

    def cancel_order(self, order_id: int) -> bool:
        """撤销指定订单"""
        return self._client.cancel_order(order_id)

    def cancel_all_active_orders(self) -> int:
        """撤销所有活跃订单（启动时清理用）

        Returns:
            撤销的订单数量
        """
        active = self._client.get_active_orders()
        cancelled = 0
        for order in active:
            oid = order.get("id") or order.get("order_id")
            if oid:
                if self._client.cancel_order(int(oid)):
                    cancelled += 1
        if cancelled > 0:
            logger.info("已撤销 %d 个活跃订单", cancelled)
        return cancelled

    def cancel_all_for_symbol(self, symbol: str) -> int:
        """撤销指定标的的所有活跃订单

        Args:
            symbol: 标的代码

        Returns:
            撤销的订单数量
        """
        active = self.get_active_orders(symbol=symbol)
        cancelled = 0
        for order in active:
            oid = order.get("id") or order.get("order_id")
            if oid:
                if self._client.cancel_order(int(oid)):
                    cancelled += 1
        if cancelled > 0:
            logger.info("已撤销 %s 的 %d 个活跃订单", symbol, cancelled)
        return cancelled

    # ==================== 持仓查询 ====================

    def get_position_quantity(self, symbol: Optional[str] = None) -> int:
        """获取当前持仓数量

        Args:
            symbol: 标的，默认使用配置中的 symbol

        Returns:
            持仓股数
        """
        symbol = symbol or self._config.trading.symbol
        positions = self._client.get_positions(symbol=symbol)
        if positions:
            total = sum(int(p.get("quantity", 0)) for p in positions)
            return total
        return 0

    def validate_position_before_sell(self, expected_qty: int,
                                      symbol: Optional[str] = None) -> bool:
        """卖出前校验持仓数量

        Args:
            expected_qty: 预期持仓数量
            symbol: 标的，默认使用配置中的 symbol

        Returns:
            True 如果持仓足够
        """
        symbol = symbol or self._config.trading.symbol
        actual = self.get_position_quantity(symbol)
        if actual < expected_qty:
            logger.error("持仓校验失败: %s 预期 %d 股，实际 %d 股",
                         symbol, expected_qty, actual)
            return False
        return True
