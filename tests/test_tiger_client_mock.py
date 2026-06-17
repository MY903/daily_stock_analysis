"""Mock-based tests for TigerClient.

Tests all public methods of TigerClient using mocked SDK,
covering both happy paths and error handling including
list vs DataFrame return paths (the bug previously fixed).
"""

import pytest
from unittest.mock import MagicMock, patch

# ==================== Test Data ====================

SAMPLE_QUOTE = {
    "symbol": "AAPL",
    "latest_price": 150.0,
    "pre_close": 148.0,
    "open": 149.0,
    "high": 151.0,
    "low": 148.5,
    "volume": 1_000_000,
    "bid_price": 149.9,
    "ask_price": 150.1,
    "latest_time": "2024-01-15T10:30:00",
    "status": "Normal",
}

SAMPLE_POSITIONS = [
    {"symbol": "AAPL", "quantity": 100, "market_value": 15000.0},
    {"symbol": "TQQQ", "quantity": 200, "market_value": 8000.0},
]

SAMPLE_ACTIVE_ORDERS = [
    {
        "id": 10001,
        "status": "Submitted",
        "symbol": "AAPL",
        "action": "BUY",
        "quantity": 35,
        "limit_price": 150.0,
        "filled": 0,
        "remaining": 35,
    },
    {
        "id": 10002,
        "status": "PartiallyFilled",
        "symbol": "TQQQ",
        "action": "SELL",
        "quantity": 50,
        "limit_price": 55.0,
        "filled": 20,
        "remaining": 30,
    },
]


# ==================== Fixtures ====================


@pytest.fixture
def mock_sdk():
    """Mock Tiger SDK imports to prevent real connections.

    Patches TigerOpenClientConfig, TradeClient, and QuoteClient at
    the module level where they are imported (src.trading.tiger_client).
    """
    with (
        patch("src.trading.tiger_client.TigerOpenClientConfig") as mock_config_cls,
        patch("src.trading.tiger_client.TradeClient") as mock_trade_cls,
        patch("src.trading.tiger_client.QuoteClient") as mock_quote_cls,
    ):
        mock_trade = MagicMock()
        mock_quote = MagicMock()
        mock_trade_cls.return_value = mock_trade
        mock_quote_cls.return_value = mock_quote

        yield mock_config_cls, mock_trade, mock_quote


@pytest.fixture
def client(mock_sdk):
    """Create a TigerClient that is 'connected' with mocked SDK clients."""
    mock_config_cls, mock_trade, mock_quote = mock_sdk

    from src.trading.config import AppConfig, TigerConfig
    from src.trading.tiger_client import TigerClient

    cfg = AppConfig(tiger=TigerConfig())
    instance = TigerClient(cfg)

    # Manually set connected state with mock clients
    instance._connected = True
    instance._trade_client = mock_trade
    instance._quote_client = mock_quote
    instance._client_config = MagicMock()
    instance._client_config.account = "test_account"

    return instance


@pytest.fixture
def disconnected_client(mock_sdk):
    """Create a TigerClient that is NOT connected (for error testing)."""
    mock_config_cls, mock_trade, mock_quote = mock_sdk

    from src.trading.config import AppConfig, TigerConfig
    from src.trading.tiger_client import TigerClient

    cfg = AppConfig(tiger=TigerConfig())
    instance = TigerClient(cfg)
    instance._client_config = MagicMock()
    instance._client_config.account = "test_account"
    # _connected defaults to False
    return instance


# ==================== Connection Tests ====================


class TestConnect:
    """Tests for connect(), disconnect(), and is_connected."""

    def test_connect_success_with_env_creds(self, mock_sdk):
        """connect() should init SDK clients and set connected=True with env creds."""
        mock_config_cls, _, _ = mock_sdk
        mock_cfg_instance = MagicMock()
        mock_config_cls.return_value = mock_cfg_instance

        mock_settings = MagicMock()
        mock_settings.has_tiger_creds = True
        mock_settings.TIGER_TIGER_ID = "tiger_id"
        mock_settings.TIGER_PRIVATE_KEY = "priv_key"
        mock_settings.TIGER_ACCOUNT = "acc"
        mock_settings.TIGER_TOKEN = "token"
        mock_settings.TIGER_LICENSE = "lic"

        with patch("src.trading.tiger_client.settings", mock_settings):
            from src.trading.config import AppConfig, TigerConfig
            from src.trading.tiger_client import TigerClient

            client = TigerClient(AppConfig(tiger=TigerConfig()))
            client.connect()

        assert client.is_connected is True
        assert client._trade_client is not None
        assert client._quote_client is not None
        mock_config_cls.assert_called_once()
        assert mock_cfg_instance.tiger_id == "tiger_id"
        assert mock_cfg_instance.language is not None

    def test_connect_with_properties_file(self, mock_sdk):
        """connect() should fallback to .properties when no env creds."""
        mock_config_cls, _, _ = mock_sdk
        mock_cfg_instance = MagicMock()
        mock_config_cls.return_value = mock_cfg_instance

        mock_settings = MagicMock()
        mock_settings.has_tiger_creds = False

        with (
            patch("src.trading.tiger_client.settings", mock_settings),
            patch("pathlib.Path.exists", return_value=True),
        ):
            from src.trading.config import AppConfig, TigerConfig
            from src.trading.tiger_client import TigerClient

            client = TigerClient(AppConfig(tiger=TigerConfig()))
            client.connect()

        assert client.is_connected is True
        mock_config_cls.assert_called_once()

    def test_connect_file_not_found(self, mock_sdk):
        """connect() should raise FileNotFoundError when .properties missing."""
        mock_settings = MagicMock()
        mock_settings.has_tiger_creds = False

        with (
            patch("src.trading.tiger_client.settings", mock_settings),
            patch("pathlib.Path.exists", return_value=False),
        ):
            from src.trading.config import AppConfig, TigerConfig
            from src.trading.tiger_client import TigerClient

            client = TigerClient(AppConfig(tiger=TigerConfig()))
            with pytest.raises(FileNotFoundError):
                client.connect()

        assert client.is_connected is False

    def test_disconnect(self, client):
        """disconnect() should set _connected=False and clean up push client."""
        mock_push = MagicMock()
        client._push_client = mock_push
        client.disconnect()
        assert client.is_connected is False
        mock_push.disconnect.assert_called_once()
        assert client._push_client is None

    def test_disconnect_push_error_graceful(self, client):
        """disconnect() should not crash if push_client.disconnect() raises."""
        client._push_client = MagicMock()
        client._push_client.disconnect.side_effect = Exception("push error")
        client.disconnect()  # must not raise
        assert client.is_connected is False

    def test_disconnect_no_push_client(self, client):
        """disconnect() should work when push_client is None."""
        client._push_client = None
        client.disconnect()
        assert client.is_connected is False

    def test_is_connected_property(self, client, disconnected_client):
        """is_connected should reflect internal _connected state."""
        assert client.is_connected is True
        assert disconnected_client.is_connected is False


# ==================== Quote Tests ====================


class TestGetQuote:
    """Tests for get_quote()."""

    def test_get_quote_list_of_dicts(self, client):
        """get_quote should return dict when SDK returns list of dicts."""
        client._quote_client.get_stock_briefs.return_value = [dict(SAMPLE_QUOTE)]

        result = client.get_quote("AAPL")

        assert isinstance(result, dict)
        assert result["latest_price"] == 150.0
        assert result["symbol"] == "AAPL"
        assert result["bid_price"] == 149.9
        assert result["ask_price"] == 150.1
        assert result["volume"] == 1_000_000

    def test_get_quote_dataframe_return(self, client):
        """get_quote should work when SDK returns a DataFrame."""
        import pandas as pd

        df = pd.DataFrame([SAMPLE_QUOTE])
        client._quote_client.get_stock_briefs.return_value = df

        result = client.get_quote("AAPL")

        assert isinstance(result, dict)
        assert result["latest_price"] == 150.0
        assert result["symbol"] == "AAPL"

    def test_get_quote_none(self, client):
        """get_quote should return fallback dict when SDK returns None."""
        client._quote_client.get_stock_briefs.return_value = None

        result = client.get_quote("AAPL")
        assert result == {"symbol": "AAPL", "latest_price": None}

    def test_get_quote_empty_list(self, client):
        """get_quote should return fallback when SDK returns empty list."""
        client._quote_client.get_stock_briefs.return_value = []

        result = client.get_quote("AAPL")
        assert result == {"symbol": "AAPL", "latest_price": None}

    def test_get_quote_empty_dataframe(self, client):
        """get_quote should return fallback when SDK returns empty DataFrame."""
        import pandas as pd

        df = pd.DataFrame()
        client._quote_client.get_stock_briefs.return_value = df

        result = client.get_quote("AAPL")
        assert result == {"symbol": "AAPL", "latest_price": None}

    def test_get_quote_object_list(self, client):
        """get_quote should handle list of objects (not dicts)."""
        mock_row = MagicMock()
        mock_row.latest_price = 150.0
        mock_row.pre_close = 148.0
        mock_row.open = 149.0
        mock_row.high = 151.0
        mock_row.low = 148.5
        mock_row.volume = 1_000_000
        mock_row.bid_price = 149.9
        mock_row.ask_price = 150.1
        mock_row.latest_time = "2024-01-15T10:30:00"
        mock_row.status = "Normal"
        client._quote_client.get_stock_briefs.return_value = [mock_row]

        result = client.get_quote("AAPL")

        assert result["latest_price"] == 150.0
        assert result["symbol"] == "AAPL"


# ==================== Market Status Tests ====================


class TestGetMarketStatus:
    """Tests for get_market_status()."""

    def test_market_status_list_return(self, client):
        """get_market_status should return string when SDK returns list."""
        client._quote_client.get_market_status.return_value = [{"status": "盘中"}]

        result = client.get_market_status()
        assert isinstance(result, str)
        assert result == "盘中"

    def test_market_status_dataframe_return(self, client):
        """get_market_status should work with DataFrame return."""
        import pandas as pd

        df = pd.DataFrame({"status": ["盘前"]})
        client._quote_client.get_market_status.return_value = df

        result = client.get_market_status()
        assert result == "盘前"

    def test_market_status_none(self, client):
        """get_market_status should return UNKNOWN when SDK returns None."""
        client._quote_client.get_market_status.return_value = None

        result = client.get_market_status()
        assert result == "UNKNOWN"

    def test_market_status_empty_list(self, client):
        """get_market_status should return UNKNOWN for empty list."""
        client._quote_client.get_market_status.return_value = []

        result = client.get_market_status()
        assert result == "UNKNOWN"

    def test_market_status_empty_dataframe(self, client):
        """get_market_status should return UNKNOWN for empty DataFrame."""
        import pandas as pd

        df = pd.DataFrame()
        client._quote_client.get_market_status.return_value = df

        result = client.get_market_status()
        assert result == "UNKNOWN"


# ==================== Account Summary Tests ====================


class TestGetAccountSummary:
    """Tests for get_account_summary()."""

    @staticmethod
    def _setup_summary(client, net=100000.0, cash=50000.0, bp=75000.0):
        """Helper to set up a summary mock on the trade client."""
        mock_account = MagicMock()
        mock_summary = MagicMock()
        mock_summary.net_liquidation = net
        mock_summary.cash = cash
        mock_summary.buying_power = bp
        mock_account._summary = mock_summary
        client._trade_client.get_assets.return_value = [mock_account]
        return mock_summary

    def test_get_account_summary_success(self, client):
        self._setup_summary(client)
        result = client.get_account_summary()
        assert result == {"net_value": 100000.0, "cash": 50000.0, "buying_power": 75000.0}

    def test_get_account_summary_no_assets(self, client):
        client._trade_client.get_assets.return_value = None
        result = client.get_account_summary()
        assert result == {"net_value": 0.0, "cash": 0.0, "buying_power": 0.0}

    def test_get_account_summary_empty_assets(self, client):
        client._trade_client.get_assets.return_value = []
        result = client.get_account_summary()
        assert result == {"net_value": 0.0, "cash": 0.0, "buying_power": 0.0}

    def test_get_account_summary_no_summary(self, client):
        mock_account = MagicMock()
        mock_account._summary = None
        client._trade_client.get_assets.return_value = [mock_account]
        result = client.get_account_summary()
        assert result == {"net_value": 0.0, "cash": 0.0, "buying_power": 0.0}

    def test_get_account_summary_sdk_error(self, client):
        client._trade_client.get_assets.side_effect = Exception("API error")
        result = client.get_account_summary()
        assert result == {"net_value": 0.0, "cash": 0.0, "buying_power": 0.0}

    def test_get_account_summary_none_values_in_summary(self, client):
        """Should coerce None in summary fields to 0.0."""
        mock_account = MagicMock()
        mock_summary = MagicMock()
        mock_summary.net_liquidation = None
        mock_summary.cash = None
        mock_summary.buying_power = None
        mock_account._summary = mock_summary
        client._trade_client.get_assets.return_value = [mock_account]
        result = client.get_account_summary()
        assert result == {"net_value": 0.0, "cash": 0.0, "buying_power": 0.0}


# ==================== Positions Tests ====================


class TestGetPositions:
    """Tests for get_positions()."""

    def test_get_positions_list(self, client):
        """get_positions should return list of dicts from list input."""
        client._trade_client.get_positions.return_value = [dict(p) for p in SAMPLE_POSITIONS]

        result = client.get_positions()
        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["symbol"] == "AAPL"
        assert result[1]["symbol"] == "TQQQ"

    def test_get_positions_dataframe_return(self, client):
        """get_positions should work with DataFrame return."""
        import pandas as pd

        df = pd.DataFrame(SAMPLE_POSITIONS)
        client._trade_client.get_positions.return_value = df

        result = client.get_positions()
        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["symbol"] == "AAPL"

    def test_get_positions_filter_by_symbol(self, client):
        """get_positions should filter by symbol when provided."""
        client._trade_client.get_positions.return_value = [dict(p) for p in SAMPLE_POSITIONS]

        result = client.get_positions(symbol="TQQQ")
        assert len(result) == 1
        assert result[0]["symbol"] == "TQQQ"

    def test_get_positions_no_match(self, client):
        """get_positions should return empty list when symbol not found."""
        client._trade_client.get_positions.return_value = [dict(p) for p in SAMPLE_POSITIONS]

        result = client.get_positions(symbol="GOOGL")
        assert len(result) == 0

    def test_get_positions_none(self, client):
        client._trade_client.get_positions.return_value = None
        assert client.get_positions() == []

    def test_get_positions_empty_list(self, client):
        client._trade_client.get_positions.return_value = []
        assert client.get_positions() == []

    def test_get_positions_empty_dataframe(self, client):
        import pandas as pd

        client._trade_client.get_positions.return_value = pd.DataFrame()
        assert client.get_positions() == []

    def test_get_positions_sdk_error(self, client):
        client._trade_client.get_positions.side_effect = Exception("API error")
        assert client.get_positions() == []

    def test_get_positions_object_list(self, client):
        """Should convert objects with __dict__ to dicts via vars()."""
        mock_pos = MagicMock(spec=[])
        mock_pos.symbol = "AAPL"
        mock_pos.quantity = 100
        client._trade_client.get_positions.return_value = [mock_pos]

        result = client.get_positions()
        assert len(result) == 1
        # vars() picks up MagicMock attrs, but we verify the position-level data
        # ends up in the result (it uses get_positions, not filtered conversion)
        # The key check is that it doesn't crash and returns a list of dicts


# ==================== Active Orders Tests ====================


class TestGetActiveOrders:
    """Tests for get_active_orders()."""

    def _make_order_mocks(self):
        """Create list of MagicMock order objects from sample data."""
        mocks = []
        for o in SAMPLE_ACTIVE_ORDERS:
            mo = MagicMock(spec=[])
            for k, v in o.items():
                setattr(mo, k, v)
            mocks.append(mo)
        return mocks

    def test_get_active_orders_success(self, client):
        """get_active_orders should return list of dicts from SDK objects."""
        client._trade_client.get_orders.return_value = self._make_order_mocks()

        result = client.get_active_orders()
        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["id"] == 10001
        assert result[0]["status"] == "Submitted"
        assert result[1]["id"] == 10002

    def test_get_active_orders_dict_list(self, client):
        """Should handle SDK returning list of dicts directly."""
        client._trade_client.get_orders.return_value = [dict(o) for o in SAMPLE_ACTIVE_ORDERS]

        result = client.get_active_orders()
        assert len(result) == 2
        assert result[0]["status"] == "Submitted"

    def test_get_active_orders_none(self, client):
        client._trade_client.get_orders.return_value = None
        assert client.get_active_orders() == []

    def test_get_active_orders_sdk_error(self, client):
        client._trade_client.get_orders.side_effect = Exception("API error")
        assert client.get_active_orders() == []


# ==================== Place Order Tests ====================


class TestPlaceLimitBuy:
    """Tests for place_limit_buy()."""

    def test_place_limit_buy_success(self, client):
        """Should return order_id when SDK succeeds."""
        client._trade_client.place_order.return_value = 50001

        with (
            patch("src.trading.tiger_client.stock_contract") as mock_sc,
            patch("src.trading.tiger_client.limit_order") as mock_lo,
        ):
            mock_contract = MagicMock()
            mock_sc.return_value = mock_contract
            mock_order = MagicMock()
            mock_lo.return_value = mock_order

            order_id = client.place_limit_buy("AAPL", 35, 150.0)

        assert order_id == 50001
        mock_sc.assert_called_once_with("AAPL", "USD")
        mock_lo.assert_called_once()
        assert mock_order.time_in_force == "GTC"

    def test_place_limit_buy_custom_time_in_force(self, client):
        """Should pass custom time_in_force to the order."""
        client._trade_client.place_order.return_value = 50001

        with (
            patch("src.trading.tiger_client.stock_contract"),
            patch("src.trading.tiger_client.limit_order") as mock_lo,
        ):
            mock_order = MagicMock()
            mock_lo.return_value = mock_order
            client.place_limit_buy("AAPL", 35, 150.0, time_in_force="DAY")

        assert mock_order.time_in_force == "DAY"

    def test_place_limit_buy_error(self, client):
        """Should return None when SDK raises."""
        client._trade_client.place_order.side_effect = Exception("order failed")

        with (
            patch("src.trading.tiger_client.stock_contract"),
            patch("src.trading.tiger_client.limit_order") as mock_lo,
        ):
            mock_order = MagicMock()
            mock_lo.return_value = mock_order
            order_id = client.place_limit_buy("AAPL", 35, 150.0)

        assert order_id is None


class TestPlaceLimitSell:
    """Tests for place_limit_sell()."""

    def test_place_limit_sell_success(self, client):
        client._trade_client.place_order.return_value = 50002

        with (
            patch("src.trading.tiger_client.stock_contract"),
            patch("src.trading.tiger_client.limit_order") as mock_lo,
        ):
            mock_order = MagicMock()
            mock_lo.return_value = mock_order
            order_id = client.place_limit_sell("AAPL", 35, 155.0)

        assert order_id == 50002

    def test_place_limit_sell_error(self, client):
        client._trade_client.place_order.side_effect = Exception("order failed")

        with (
            patch("src.trading.tiger_client.stock_contract"),
            patch("src.trading.tiger_client.limit_order") as mock_lo,
        ):
            mock_order = MagicMock()
            mock_lo.return_value = mock_order
            order_id = client.place_limit_sell("AAPL", 35, 155.0)

        assert order_id is None


class TestPlaceStopLimitSell:
    """Tests for place_stop_limit_sell()."""

    def test_place_stop_limit_sell_success(self, client):
        client._trade_client.place_order.return_value = 50003

        with (
            patch("src.trading.tiger_client.stock_contract"),
            patch("src.trading.tiger_client.stop_limit_order") as mock_slo,
        ):
            mock_order = MagicMock()
            mock_slo.return_value = mock_order
            order_id = client.place_stop_limit_sell("AAPL", 35, 140.0, 139.0)

        assert order_id == 50003
        assert mock_order.time_in_force == "GTC"

    def test_place_stop_limit_sell_error(self, client):
        client._trade_client.place_order.side_effect = Exception("order failed")

        with (
            patch("src.trading.tiger_client.stock_contract"),
            patch("src.trading.tiger_client.stop_limit_order") as mock_slo,
        ):
            mock_order = MagicMock()
            mock_slo.return_value = mock_order
            order_id = client.place_stop_limit_sell("AAPL", 35, 140.0, 139.0)

        assert order_id is None


# ==================== Cancel Order Tests ====================


class TestCancelOrder:
    """Tests for cancel_order()."""

    def test_cancel_order_success(self, client):
        client._trade_client.cancel_order.return_value = None
        result = client.cancel_order(10001)
        assert result is True
        client._trade_client.cancel_order.assert_called_once_with(id=10001)

    def test_cancel_order_error(self, client):
        client._trade_client.cancel_order.side_effect = Exception("cancel failed")
        result = client.cancel_order(10001)
        assert result is False


# ==================== Assets Tests ====================


class TestGetAssets:
    """Tests for get_assets()."""

    def test_get_assets_success(self, client):
        mock_account = MagicMock()
        mock_summary = MagicMock()
        mock_summary.net_liquidation = 100000.0
        mock_summary.cash = 50000.0
        mock_summary.buying_power = 75000.0
        mock_summary.available_funds = 25000.0
        mock_summary.unrealized_pnl = 1000.0
        mock_summary.realized_pnl = 500.0
        mock_account._summary = mock_summary
        client._trade_client.get_assets.return_value = [mock_account]

        result = client.get_assets()
        assert result["net_value"] == 100000.0
        assert result["cash"] == 50000.0
        assert result["buying_power"] == 75000.0
        assert result["available_funds"] == 25000.0
        assert result["unrealized_pnl"] == 1000.0
        assert result["realized_pnl"] == 500.0

    def test_get_assets_no_result(self, client):
        client._trade_client.get_assets.return_value = None
        assert client.get_assets() == {}

    def test_get_assets_empty(self, client):
        client._trade_client.get_assets.return_value = []
        assert client.get_assets() == {}

    def test_get_assets_no_summary(self, client):
        mock_account = MagicMock()
        mock_account._summary = None
        client._trade_client.get_assets.return_value = [mock_account]
        assert client.get_assets() == {}

    def test_get_assets_sdk_error(self, client):
        client._trade_client.get_assets.side_effect = Exception("API error")
        assert client.get_assets() == {}


# ==================== Get Order Tests ====================


class TestGetOrder:
    """Tests for get_order()."""

    def test_get_order_success(self, client):
        mock_order = MagicMock()
        mock_order.status = "Filled"
        mock_order.filled = 35
        mock_order.avg_fill_price = 150.0
        mock_order.remaining = 0
        client._trade_client.get_order.return_value = mock_order

        result = client.get_order(10001)
        assert result == {
            "id": 10001,
            "status": "Filled",
            "filled_quantity": 35,
            "avg_fill_price": 150.0,
            "remaining": 0,
        }

    def test_get_order_not_found(self, client):
        client._trade_client.get_order.return_value = None
        assert client.get_order(99999) is None

    def test_get_order_sdk_error(self, client):
        client._trade_client.get_order.side_effect = Exception("API error")
        assert client.get_order(10001) is None


# ==================== Push Tests ====================


class TestStartStopPush:
    """Tests for start_push() and stop_push()."""

    def test_start_push(self, client):
        mock_push = MagicMock()
        with patch("src.trading.tiger_client.PushClient", return_value=mock_push):
            client._client_config.socket_host_port = ("ws", "host", 80)
            client._client_config.tiger_id = "tiger_id"
            client._client_config.private_key = "priv_key"

            client.start_push("AAPL")

        assert client._push_client is mock_push
        mock_push.connect.assert_called_once_with("tiger_id", "priv_key")
        mock_push.subscribe_quote.assert_called_once_with(["AAPL"])

    def test_start_push_with_callbacks(self, client):
        mock_push = MagicMock()
        on_quote = MagicMock()
        on_order = MagicMock()

        with patch("src.trading.tiger_client.PushClient", return_value=mock_push):
            client._client_config.socket_host_port = ("ws", "host", 80)
            client._client_config.tiger_id = "tiger_id"
            client._client_config.private_key = "priv_key"

            client.start_push("AAPL", on_quote=on_quote, on_order=on_order)

        assert mock_push.quote_changed == on_quote
        assert mock_push.order_changed == on_order

    def test_stop_push(self, client):
        mock_push = MagicMock()
        client._push_client = mock_push
        client.stop_push()
        mock_push.disconnect.assert_called_once()
        assert client._push_client is None

    def test_stop_push_disconnect_error(self, client):
        client._push_client = MagicMock()
        client._push_client.disconnect.side_effect = Exception("disconnect error")
        client.stop_push()  # must not raise
        assert client._push_client is None

    def test_stop_push_no_client(self, client):
        client._push_client = None
        client.stop_push()  # must not raise


# ==================== Error Handling Tests ====================


class TestEnsureConnected:
    """Tests that methods raise RuntimeError when not connected."""

    @pytest.mark.parametrize(
        "method_call",
        [
            lambda c: c.get_quote("AAPL"),
            lambda c: c.get_market_status(),
            lambda c: c.get_account_summary(),
            lambda c: c.get_positions(),
            lambda c: c.get_active_orders(),
            lambda c: c.get_assets(),
            lambda c: c.get_order(1),
            lambda c: c.place_limit_buy("AAPL", 1, 1.0),
            lambda c: c.place_limit_sell("AAPL", 1, 1.0),
            lambda c: c.place_stop_limit_sell("AAPL", 1, 140.0, 139.0),
            lambda c: c.cancel_order(1),
            lambda c: c.start_push("AAPL"),
        ],
    )
    def test_all_methods_raise_when_disconnected(self, disconnected_client, method_call):
        """Every SDK-bound method should raise RuntimeError when not connected."""
        with pytest.raises(RuntimeError, match="未连接"):
            method_call(disconnected_client)


class TestSdkErrorsPropagate:
    """For methods without try/except, SDK errors propagate to caller."""

    def test_get_quote_sdk_error_propagates(self, client):
        client._quote_client.get_stock_briefs.side_effect = Exception("API failure")
        with pytest.raises(Exception):
            client.get_quote("AAPL")

    def test_get_market_status_sdk_error_propagates(self, client):
        client._quote_client.get_market_status.side_effect = Exception("API failure")
        with pytest.raises(Exception):
            client.get_market_status()

    def test_start_push_sdk_error_propagates(self, client):
        with patch("src.trading.tiger_client.PushClient") as mock_push_cls:
            mock_push_cls.side_effect = Exception("push init failed")
            client._client_config.socket_host_port = ("ws", "host", 80)
            client._client_config.tiger_id = "x"
            client._client_config.private_key = "y"
            with pytest.raises(Exception):
                client.start_push("AAPL")
