"""
双调度系统：盘前批量信号生成 + 盘中实时信号检查。

使用 APScheduler 实现定时任务调度。
"""

import logging
from datetime import datetime, time, timedelta
from typing import Optional, Callable

logger = logging.getLogger(__name__)

try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.interval import IntervalTrigger
    APSCHEDULER_AVAILABLE = True
except ImportError:
    APSCHEDULER_AVAILABLE = False
    logger.warning("APScheduler 未安装，调度系统将在 no-op 模式下运行")


class TradingCalendar:
    """简易交易日历"""

    # 美股主要节假日（月-日）
    HOLIDAYS = {
        "01-01",  # 元旦
        "01-20",  # 马丁·路德·金日
        "02-17",  # 总统日
        "04-18",  # 耶稣受难日
        "05-26",  # 阵亡将士纪念日
        "07-04",  # 独立日
        "09-01",  # 劳动节
        "11-27",  # 感恩节
        "12-25",  # 圣诞节
    }

    @classmethod
    def is_trading_day(cls, dt: Optional[datetime] = None) -> bool:
        """判断是否为交易日"""
        if dt is None:
            dt = datetime.now()
        # 周末不开市
        if dt.weekday() >= 5:
            return False
        # 节假日不开市
        key = dt.strftime("%m-%d")
        return key not in cls.HOLIDAYS

    @classmethod
    def is_market_hours(cls, dt: Optional[datetime] = None) -> bool:
        """判断是否在交易时间内（9:30-16:00 ET）"""
        if dt is None:
            dt = datetime.now()
        if not cls.is_trading_day(dt):
            return False
        # 简化判断：不考虑夏令时，假设 UTC-4 (EDT)
        market_open = dt.replace(hour=13, minute=30, second=0)  # 9:30 ET = 13:30 UTC
        market_close = dt.replace(hour=20, minute=0, second=0)  # 16:00 ET = 20:00 UTC
        return market_open <= dt <= market_close

    @classmethod
    def is_pre_market(cls, dt: Optional[datetime] = None) -> bool:
        """判断是否在盘前时段（4:00-9:30 ET）"""
        if dt is None:
            dt = datetime.now()
        if not cls.is_trading_day(dt):
            return False
        pre_open = dt.replace(hour=8, minute=0, second=0)  # 4:00 ET = 8:00 UTC
        market_open = dt.replace(hour=13, minute=30, second=0)  # 9:30 ET = 13:30 UTC
        return pre_open <= dt < market_open


class PreMarketScheduler:
    """盘前批量信号调度器"""

    def __init__(self, signal_generator, card_handler):
        self._generator = signal_generator
        self._card_handler = card_handler
        self._symbols: list[str] = ["TQQQ"]
        self._last_run: Optional[datetime] = None

    def set_symbols(self, symbols: list[str]):
        """设置监控标的列表"""
        self._symbols = symbols

    async def run(self) -> int:
        """
        执行盘前信号生成和推送。
        
        Returns:
            生成的信号数量
        """
        if not TradingCalendar.is_trading_day():
            logger.info("盘前调度: 今日非交易日，跳过")
            return 0

        signals = self._generator.generate_pre_market_signals(self._symbols)
        logger.info("盘前调度: 生成 %d 条信号", len(signals))

        for signal in signals:
            await self._card_handler.push_signal_card(signal)

        self._last_run = datetime.now()
        return len(signals)

    @property
    def should_run(self) -> bool:
        """检查是否应该运行盘前调度"""
        if not TradingCalendar.is_trading_day():
            return False
        if self._last_run:
            # 一天只运行一次
            return self._last_run.date() < datetime.now().date()
        return True

    def next_run_time(self) -> Optional[str]:
        """下次运行时间"""
        now = datetime.now()
        if not TradingCalendar.is_trading_day(now):
            return None
        # 默认 9:00 ET = 13:00 UTC 运行
        target = now.replace(hour=13, minute=0, second=0, microsecond=0)
        if now > target:
            return None  # 今天已过
        return target.isoformat()


class IntradayScheduler:
    """盘中实时信号调度器"""

    def __init__(self, signal_generator, card_handler):
        self._generator = signal_generator
        self._card_handler = card_handler
        self._symbols: list[str] = ["TQQQ"]
        self._poll_interval: int = 60  # 秒
        self._last_run: Optional[datetime] = None

    def set_symbols(self, symbols: list[str]):
        """设置监控标的"""
        self._symbols = symbols

    def set_poll_interval(self, seconds: int):
        """设置轮询间隔"""
        self._poll_interval = seconds

    async def run(self) -> int:
        """
        执行盘中信号检查和推送。
        
        Returns:
            生成的信号数量
        """
        if not TradingCalendar.is_market_hours():
            return 0

        signals = self._generator.generate_pre_market_signals(self._symbols)
        if signals:
            logger.info("盘中调度: 发现 %d 条新信号", len(signals))
            for signal in signals:
                await self._card_handler.push_signal_card(signal)

        self._last_run = datetime.now()
        return len(signals)

    @property
    def should_run(self) -> bool:
        """检查是否应该运行盘中调度"""
        return TradingCalendar.is_market_hours()

    @property
    def poll_interval(self) -> int:
        return self._poll_interval


class SignalScheduler:
    """双调度管理器（统一入口）"""

    def __init__(self, pre_market: PreMarketScheduler, intraday: IntradayScheduler):
        self._pre_market = pre_market
        self._intraday = intraday
        self._scheduler: Optional[BackgroundScheduler] = None
        self._running = False

    def start(self):
        """启动调度系统"""
        if not APSCHEDULER_AVAILABLE:
            logger.warning("APScheduler 不可用，调度系统未启动")
            return

        self._scheduler = BackgroundScheduler()
        
        # 盘前调度：每个交易日 13:00 UTC (9:00 ET)
        self._scheduler.add_job(
            self._run_pre_market,
            CronTrigger(hour=13, minute=0, day_of_week="mon-fri"),
            id="pre_market",
            name="盘前信号生成",
        )
        
        # 盘中调度：交易时间内每分钟
        self._scheduler.add_job(
            self._run_intraday,
            IntervalTrigger(minutes=1),
            id="intraday",
            name="盘中信号检查",
        )
        
        self._scheduler.start()
        self._running = True
        logger.info("双调度系统已启动 (盘前9:00 ET / 盘中每分钟)")

    def stop(self):
        """停止调度系统"""
        if self._scheduler and self._running:
            self._scheduler.shutdown(wait=False)
            self._running = False
            logger.info("双调度系统已停止")

    async def _run_pre_market(self):
        """盘前任务"""
        await self._pre_market.run()

    async def _run_intraday(self):
        """盘中任务"""
        if TradingCalendar.is_market_hours():
            await self._intraday.run()

    def run_once(self) -> dict:
        """手动触发一次检查（用于测试和CLI）"""
        import asyncio
        pre_count = asyncio.run(self._pre_market.run())
        intra_count = asyncio.run(self._intraday.run())
        return {
            "pre_market_signals": pre_count,
            "intraday_signals": intra_count,
        }
