"""行情监控 — yfinance 轮询模式

使用 yfinance 免费数据源获取美股实时行情，替代 Tiger WebSocket
（Tiger API 美股行情需付费订阅）。

数据源优先级：
1. yfinance Ticker.fast_info（最快，延迟约 15 分钟）
2. yfinance Ticker.history(period='1d')（更稳定）
3. Stooq CSV 接口（终极兜底）

设计要点：
- 轮询间隔可配置（默认 15 秒）
- 非交易时段自动降频（60 秒）
- 保持与策略层的回调接口不变
"""

import csv
import logging
import threading
import time
from datetime import datetime, timezone, timedelta
from io import StringIO
from typing import Optional, Callable, Dict, Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from src.trading.config import AppConfig

logger = logging.getLogger(__name__)

# 美东时区偏移 (UTC-4 夏令时 / UTC-5 标准)
US_EASTERN_OFFSET_SUMMER = timedelta(hours=-4)
US_EASTERN_OFFSET_WINTER = timedelta(hours=-5)


def _is_us_market_hours() -> bool:
    """判断当前是否在美股交易时段（含盘前盘后）

    美东时间 04:00 ~ 20:00（盘前 04:00, 常规 09:30-16:00, 盘后至 20:00）
    使用简化判断，覆盖盘前盘后时段。
    """
    now_utc = datetime.now(timezone.utc)
    # 简化处理：使用 UTC-4 (EDT) 估算
    now_et = now_utc + US_EASTERN_OFFSET_SUMMER
    hour = now_et.hour
    weekday = now_et.weekday()  # 0=Monday

    # 周末不开盘
    if weekday >= 5:
        return False

    # 盘前 04:00 ~ 盘后 20:00
    return 4 <= hour < 20


class QuoteMonitor:
    """行情监控（yfinance 轮询模式）

    通过 yfinance 免费数据源定期获取美股实时行情，
    在价格变动时触发回调通知策略层。

    接口与原 WebSocket 模式保持一致：
    - set_price_callback()
    - start() / stop()
    - latest_quote / is_running
    - poll_quote()
    """

    def __init__(self, client, config: AppConfig):
        self._client = client  # 保留引用（用于订单操作，不用于行情）
        self._config = config
        self._running = False
        self._latest_quote: Dict[str, Any] = {}
        self._on_price_update: Optional[Callable[[Dict[str, Any]], None]] = None
        self._poll_thread: Optional[threading.Thread] = None

        # 轮询参数
        self._poll_interval_active = 15  # 交易时段轮询间隔（秒）
        self._poll_interval_idle = 60    # 非交易时段轮询间隔（秒）
        self._consecutive_failures = 0
        self._max_consecutive_failures = 10

    def set_price_callback(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """设置价格更新回调"""
        self._on_price_update = callback

    @property
    def latest_quote(self) -> Dict[str, Any]:
        return self._latest_quote

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self) -> None:
        """启动行情监控"""
        symbol = self._config.trading.symbol
        logger.info("启动行情监控 (yfinance 轮询): %s", symbol)
        logger.info("轮询间隔: 交易时段 %ds / 非交易时段 %ds",
                    self._poll_interval_active, self._poll_interval_idle)

        self._running = True
        self._poll_thread = threading.Thread(
            target=self._poll_loop,
            daemon=True,
            name="yfinance-poll"
        )
        self._poll_thread.start()

    def stop(self) -> None:
        """停止行情监控"""
        self._running = False
        logger.info("行情监控已停止")

    def poll_quote(self) -> Optional[Dict[str, Any]]:
        """主动轮询一次行情"""
        symbol = self._config.trading.symbol
        quote = self._fetch_price(symbol)
        if quote and quote.get("latest_price") is not None:
            self._latest_quote = quote
        return quote

    def _poll_loop(self) -> None:
        """轮询主循环"""
        symbol = self._config.trading.symbol

        # 启动时立即获取一次
        self._do_poll(symbol)

        while self._running:
            # 动态调整轮询间隔
            if _is_us_market_hours():
                interval = self._poll_interval_active
            else:
                interval = self._poll_interval_idle

            time.sleep(interval)

            if not self._running:
                break

            self._do_poll(symbol)

    def _do_poll(self, symbol: str) -> None:
        """执行一次轮询并通知回调"""
        quote = self._fetch_price(symbol)

        if quote and quote.get("latest_price") is not None:
            self._consecutive_failures = 0
            self._latest_quote = quote

            # 通知策略层
            if self._on_price_update:
                try:
                    self._on_price_update(quote)
                except Exception as e:
                    logger.error("价格回调处理异常: %s", e)
        else:
            self._consecutive_failures += 1
            if self._consecutive_failures >= self._max_consecutive_failures:
                logger.error("连续 %d 次获取行情失败",
                             self._consecutive_failures)

    def _fetch_price(self, symbol: str) -> Optional[Dict[str, Any]]:
        """获取价格数据（yfinance -> Stooq 多级 fallback）

        Returns:
            包含 latest_price 的行情字典，失败返回 None
        """
        # 第一优先：yfinance fast_info
        quote = self._fetch_via_yfinance(symbol)
        if quote:
            return quote

        # 第二优先：Stooq CSV 兜底
        quote = self._fetch_via_stooq(symbol)
        if quote:
            return quote

        logger.warning("所有数据源均无法获取 %s 行情", symbol)
        return None

    def _fetch_via_yfinance(self, symbol: str) -> Optional[Dict[str, Any]]:
        """通过 yfinance 获取行情"""
        try:
            import yfinance as yf

            ticker = yf.Ticker(symbol)

            # 尝试 fast_info（更快）
            price = None
            prev_close = None
            high = None
            low = None
            open_price = None
            volume = None

            try:
                info = ticker.fast_info
                if info is not None:
                    price = getattr(info, 'lastPrice', None) or getattr(info, 'last_price', None)
                    prev_close = getattr(info, 'previousClose', None) or getattr(info, 'previous_close', None)
                    open_price = getattr(info, 'open', None)
                    high = getattr(info, 'dayHigh', None) or getattr(info, 'day_high', None)
                    low = getattr(info, 'dayLow', None) or getattr(info, 'day_low', None)
                    volume = getattr(info, 'lastVolume', None) or getattr(info, 'last_volume', None)
            except Exception:
                pass

            # 如果 fast_info 没拿到价格，用 history 兜底
            if price is None:
                hist = ticker.history(period='2d')
                if hist is not None and not hist.empty:
                    today = hist.iloc[-1]
                    prev = hist.iloc[-2] if len(hist) > 1 else today
                    price = float(today['Close'])
                    prev_close = float(prev['Close'])
                    open_price = float(today['Open'])
                    high = float(today['High'])
                    low = float(today['Low'])
                    volume = int(today['Volume'])

            if price is None or price <= 0:
                return None

            # 计算涨跌幅
            change_pct = None
            if prev_close and prev_close > 0:
                change_pct = round((price - prev_close) / prev_close * 100, 2)

            quote_data = {
                "symbol": symbol,
                "latest_price": float(price),
                "prev_close": float(prev_close) if prev_close else None,
                "open": float(open_price) if open_price else None,
                "high": float(high) if high else None,
                "low": float(low) if low else None,
                "volume": int(volume) if volume else None,
                "change_pct": change_pct,
                "source": "yfinance",
                "timestamp": time.time(),
            }

            logger.debug("[yfinance] %s 价格: %.2f (%.2f%%)",
                         symbol, price, change_pct or 0)
            return quote_data

        except Exception as e:
            logger.debug("[yfinance] 获取 %s 失败: %s", symbol, e)
            return None

    def _fetch_via_stooq(self, symbol: str) -> Optional[Dict[str, Any]]:
        """通过 Stooq CSV 接口获取行情（终极兜底）"""
        try:
            stooq_symbol = f"{symbol.lower()}.us"
            url = f"https://stooq.com/q/l/?s={stooq_symbol}&e=csv"
            request = Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; DSA-Trading/1.0)",
                    "Accept": "text/plain,text/csv,*/*",
                },
            )

            with urlopen(request, timeout=15) as response:
                payload = response.read().decode("utf-8", "ignore").strip()

            if not payload or "NO DATA" in payload.upper():
                return None

            # 解析 CSV
            reader = csv.reader(StringIO(payload))
            first_row = next(reader, None)
            if first_row is None:
                return None

            # 检查是否有 header
            header_tokens = [cell.strip().lower() for cell in first_row]
            has_header = 'close' in header_tokens or 'open' in header_tokens

            if has_header:
                row = next(reader, None)
                if row is None:
                    return None
                # 按 header 解析
                col_map = {h: i for i, h in enumerate(header_tokens)}
                price = float(row[col_map['close']]) if 'close' in col_map else None
                open_price = float(row[col_map['open']]) if 'open' in col_map else None
                high = float(row[col_map['high']]) if 'high' in col_map else None
                low = float(row[col_map['low']]) if 'low' in col_map else None
                volume = int(float(row[col_map['volume']])) if 'volume' in col_map else None
            else:
                # 无 header，按位置解析
                row = first_row
                normalized = [cell.strip() for cell in row if cell.strip()]
                if len(normalized) < 7:
                    return None
                # 通常格式: Symbol, Date, Time, Open, High, Low, Close, Volume
                price = float(normalized[-2]) if len(normalized) >= 7 else None
                open_price = float(normalized[3]) if len(normalized) >= 7 else None
                high = float(normalized[4]) if len(normalized) >= 7 else None
                low = float(normalized[5]) if len(normalized) >= 7 else None
                volume = int(float(normalized[-1])) if len(normalized) >= 8 else None

            if price is None or price <= 0:
                return None

            quote_data = {
                "symbol": symbol.upper(),
                "latest_price": price,
                "open": open_price,
                "high": high,
                "low": low,
                "volume": volume,
                "source": "stooq",
                "timestamp": time.time(),
            }

            logger.debug("[Stooq] %s 价格: %.2f", symbol, price)
            return quote_data

        except Exception as e:
            logger.debug("[Stooq] 获取 %s 失败: %s", symbol, e)
            return None
