"""Tiger Brokers OpenAPI 客户端封装

封装 tigeropen SDK 的连接、认证、行情订阅和交易操作。
"""

import logging
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable

from tigeropen.tiger_open_config import TigerOpenClientConfig
from tigeropen.trade.trade_client import TradeClient
from tigeropen.quote.quote_client import QuoteClient
from tigeropen.push.push_client import PushClient
from tigeropen.common.util.contract_utils import stock_contract
from tigeropen.common.util.order_utils import limit_order, stop_limit_order
from tigeropen.common.consts import Market, Language

from src.trading.config import AppConfig

logger = logging.getLogger(__name__)


class TigerClient:
    """Tiger OpenAPI 客户端

    封装行情查询、订单管理和实时推送功能。
    """

    def __init__(self, config: AppConfig):
        self._config = config
        self._client_config: Optional[TigerOpenClientConfig] = None
        self._trade_client: Optional[TradeClient] = None
        self._quote_client: Optional[QuoteClient] = None
        self._push_client: Optional[PushClient] = None
        self._connected = False

    def connect(self) -> None:
        """初始化 API 连接"""
        tiger_cfg = self._config.tiger

        config_path = tiger_cfg.absolute_config_path
        if not config_path.exists():
            raise FileNotFoundError(
                f"Tiger OpenAPI 配置文件不存在: {config_path}\n"
                f"请将 tiger_openapi_config.properties 放在: {config_path}"
            )

        # 根据环境选择 sandbox 或 production
        self._client_config = TigerOpenClientConfig(props_path=str(config_path))
        self._client_config.language = Language.zh_CN

        if not tiger_cfg.is_live:
            # 模拟盘
            self._client_config.is_paper = True
            logger.info("Tiger API 连接模式: 模拟盘 (PAPER)")
        else:
            logger.info("Tiger API 连接模式: 实盘 (LIVE)")

        # 初始化交易客户端
        self._trade_client = TradeClient(self._client_config)
        self._quote_client = QuoteClient(self._client_config)

        self._connected = True
        logger.info("Tiger API 客户端初始化完成 (tiger_id=%s)", self._client_config.tiger_id)

    def disconnect(self) -> None:
        """断开连接"""
        if self._push_client:
            try:
                self._push_client.disconnect()
            except Exception as e:
                logger.warning("断开 PushClient 时出错: %s", e)
            self._push_client = None
        self._connected = False
        logger.info("Tiger API 已断开连接")

    @property
    def is_connected(self) -> bool:
        return self._connected

    # ==================== 行情查询 ====================

    def get_quote(self, symbol: str) -> Dict[str, Any]:
        """获取单只股票实时行情

        Returns:
            包含 latest_price, bid_price, ask_price, volume 等字段的字典
        """
        self._ensure_connected()
        briefs = self._quote_client.get_stock_briefs([symbol])
        if briefs is not None and not briefs.empty:
            row = briefs.iloc[0]
            return {
                "symbol": symbol,
                "latest_price": row.get("latest_price"),
                "pre_close": row.get("pre_close"),
                "open": row.get("open"),
                "high": row.get("high"),
                "low": row.get("low"),
                "volume": row.get("volume"),
                "bid_price": row.get("bid_price"),
                "ask_price": row.get("ask_price"),
                "latest_time": row.get("latest_time"),
                "status": row.get("status"),
            }
        return {"symbol": symbol, "latest_price": None}

    def get_market_status(self) -> str:
        """获取美股市场状态"""
        self._ensure_connected()
        status = self._quote_client.get_market_status(Market.US)
        if status is not None and not status.empty:
            return status.iloc[0].get("status", "UNKNOWN")
        return "UNKNOWN"

    # ==================== 订单管理 ====================

    def place_limit_buy(self, symbol: str, quantity: int, price: float,
                        time_in_force: str = "GTC") -> Optional[int]:
        """下限价买入单

        Returns:
            订单 ID，失败返回 None
        """
        self._ensure_connected()
        contract = stock_contract(symbol, "USD")
        order = limit_order(
            account=self._client_config.account,
            contract=contract,
            action="BUY",
            quantity=quantity,
            limit_price=price,
        )
        order.time_in_force = time_in_force

        try:
            order_id = self._trade_client.place_order(order)
            logger.info("限价买入单已提交: symbol=%s, qty=%d, price=%.2f, order_id=%s",
                        symbol, quantity, price, order_id)
            return order_id
        except Exception as e:
            logger.error("下买入单失败: %s", e)
            return None

    def place_limit_sell(self, symbol: str, quantity: int, price: float,
                         time_in_force: str = "GTC") -> Optional[int]:
        """下限价卖出单（止盈）"""
        self._ensure_connected()
        contract = stock_contract(symbol, "USD")
        order = limit_order(
            account=self._client_config.account,
            contract=contract,
            action="SELL",
            quantity=quantity,
            limit_price=price,
        )
        order.time_in_force = time_in_force

        try:
            order_id = self._trade_client.place_order(order)
            logger.info("限价卖出单已提交: symbol=%s, qty=%d, price=%.2f, order_id=%s",
                        symbol, quantity, price, order_id)
            return order_id
        except Exception as e:
            logger.error("下卖出单失败: %s", e)
            return None

    def place_stop_limit_sell(self, symbol: str, quantity: int,
                              stop_price: float, limit_price: float,
                              time_in_force: str = "GTC") -> Optional[int]:
        """下止损限价卖出单"""
        self._ensure_connected()
        contract = stock_contract(symbol, "USD")
        order = stop_limit_order(
            account=self._client_config.account,
            contract=contract,
            action="SELL",
            quantity=quantity,
            stop_price=stop_price,
            limit_price=limit_price,
        )
        order.time_in_force = time_in_force

        try:
            order_id = self._trade_client.place_order(order)
            logger.info("止损限价卖出单已提交: symbol=%s, qty=%d, stop=%.2f, limit=%.2f, order_id=%s",
                        symbol, quantity, stop_price, limit_price, order_id)
            return order_id
        except Exception as e:
            logger.error("下止损单失败: %s", e)
            return None

    def cancel_order(self, order_id: int) -> bool:
        """撤销订单"""
        self._ensure_connected()
        try:
            self._trade_client.cancel_order(id=order_id)
            logger.info("订单已撤销: order_id=%d", order_id)
            return True
        except Exception as e:
            logger.error("撤销订单失败: order_id=%d, error=%s", order_id, e)
            return False

    def get_order(self, order_id: int) -> Optional[Dict[str, Any]]:
        """查询单笔订单状态"""
        self._ensure_connected()
        try:
            order = self._trade_client.get_order(id=order_id)
            if order is not None:
                return {
                    "id": order_id,
                    "status": getattr(order, "status", None),
                    "filled_quantity": getattr(order, "filled", 0),
                    "avg_fill_price": getattr(order, "avg_fill_price", 0),
                    "remaining": getattr(order, "remaining", 0),
                }
        except Exception as e:
            logger.error("查询订单失败: order_id=%d, error=%s", order_id, e)
        return None

    def get_active_orders(self) -> List[Dict[str, Any]]:
        """查询所有活跃订单"""
        self._ensure_connected()
        try:
            orders = self._trade_client.get_orders(
                states=["Initial", "PendingSubmit", "Submitted", "PartiallyFilled"]
            )
            if orders:
                result = []
                for o in orders:
                    if hasattr(o, '__dict__'):
                        d = {k: v for k, v in vars(o).items() if not k.startswith('_')}
                        result.append(d)
                    elif isinstance(o, dict):
                        result.append(o)
                return result
        except Exception as e:
            logger.error("查询活跃订单失败: %s", e)
        return []

    def get_positions(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """查询持仓"""
        self._ensure_connected()
        try:
            positions = self._trade_client.get_positions()
            if positions is not None:
                if isinstance(positions, list):
                    result = [vars(p) if hasattr(p, '__dict__') else p for p in positions]
                elif hasattr(positions, 'empty') and not positions.empty:
                    result = positions.to_dict("records")
                else:
                    result = []
                if symbol and result:
                    result = [p for p in result if p.get("symbol") == symbol]
                return result
        except Exception as e:
            logger.error("查询持仓失败: %s", e)
        return []

    def get_assets(self) -> Dict[str, Any]:
        """查询账户资产"""
        self._ensure_connected()
        try:
            assets = self._trade_client.get_assets(segment=True)
            if assets and isinstance(assets, list) and len(assets) > 0:
                account = assets[0]
                # PortfolioAccount: _summary contains aggregated data
                summary = getattr(account, '_summary', None)
                if summary:
                    return {
                        "net_value": getattr(summary, 'net_liquidation', None),
                        "cash": getattr(summary, 'cash', None),
                        "buying_power": getattr(summary, 'buying_power', None),
                        "available_funds": getattr(summary, 'available_funds', None),
                        "unrealized_pnl": getattr(summary, 'unrealized_pnl', None),
                        "realized_pnl": getattr(summary, 'realized_pnl', None),
                    }
        except Exception as e:
            logger.error("查询资产失败: %s", e)
        return {}

    # ==================== 实时推送 ====================

    def start_push(self, symbol: str,
                   on_quote: Optional[Callable] = None,
                   on_order: Optional[Callable] = None) -> None:
        """启动 WebSocket 实时推送

        Args:
            symbol: 订阅行情的标的
            on_quote: 行情回调 (symbol, items, hour_trading)
            on_order: 订单状态回调 (data)
        """
        self._ensure_connected()

        protocol, host, port = self._client_config.socket_host_port

        self._push_client = PushClient(host, port, use_ssl=(protocol == "ssl"))

        if on_quote:
            self._push_client.quote_changed = on_quote
        if on_order:
            self._push_client.order_changed = on_order

        # 连接并订阅
        self._push_client.connect(
            self._client_config.tiger_id,
            self._client_config.private_key
        )
        self._push_client.subscribe_quote([symbol])
        logger.info("WebSocket 已连接，订阅行情: %s", symbol)

    def stop_push(self) -> None:
        """停止 WebSocket 推送"""
        if self._push_client:
            try:
                self._push_client.disconnect()
            except Exception as e:
                logger.warning("停止推送时出错: %s", e)
            self._push_client = None
            logger.info("WebSocket 推送已停止")

    # ==================== 内部方法 ====================

    def _ensure_connected(self) -> None:
        if not self._connected:
            raise RuntimeError("Tiger API 未连接，请先调用 connect()")
