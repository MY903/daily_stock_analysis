# -*- coding: utf-8 -*-
"""
T+0 选股池周度定时任务
====================

职责：
1. 每周一上午 9:00 自动运行选股筛选器
2. 通过飞书机器人推送选股结果
3. 支持优雅退出和异常处理

依赖：
- schedule: 轻量级定时任务库
"""

import logging
import signal
import sys
import time
import threading
from datetime import datetime
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


class GracefulShutdown:
    """
    优雅退出处理器
    
    捕获 SIGTERM/SIGINT 信号，确保任务完成后再退出
    """
    
    def __init__(self):
        self.shutdown_requested = False
        self._lock = threading.Lock()
        
        # 注册信号处理器
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """信号处理函数"""
        with self._lock:
            if not self.shutdown_requested:
                logger.info(f"收到退出信号 ({signum})，等待当前任务完成...")
                self.shutdown_requested = True
    
    @property
    def should_shutdown(self) -> bool:
        """检查是否应该退出"""
        with self._lock:
            return self.shutdown_requested


class WeeklyScheduler:
    """
    周度定时任务调度器
    
    基于 schedule 库实现，支持：
    - 每周固定时间执行（默认周一 9:00）
    - 启动时立即执行一次
    - 优雅退出
    """
    
    def __init__(self, weekday: str = "monday", schedule_time: str = "09:00"):
        """
        初始化调度器
        
        Args:
            weekday: 每周执行星期几，可选值：monday, tuesday, ..., sunday
            schedule_time: 每日执行时间，格式 "HH:MM"
        """
        try:
            import schedule
            self.schedule = schedule
        except ImportError:
            logger.error("schedule 库未安装，请执行：pip install schedule")
            raise ImportError("请安装 schedule 库：pip install schedule")
        
        self.weekday = weekday.lower()
        self.schedule_time = schedule_time
        self.shutdown_handler = GracefulShutdown()
        self._task_callback = None
        self._running = False
        
        # 验证 weekday 参数
        valid_weekdays = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        if self.weekday not in valid_weekdays:
            raise ValueError(f"Invalid weekday: {weekday}. Must be one of {valid_weekdays}")
        
    def set_weekly_task(self, task, run_immediately: bool = True):
        """
        设置每周定时任务
        
        Args:
            task: 要执行的任务函数（无参数）
            run_immediately: 是否在设置后立即执行一次
        """
        self._task_callback = task
        
        # 根据 weekday 设置定时任务
        schedule_method = getattr(self.schedule.every(), self.weekday)
        schedule_method.at(self.schedule_time).do(self._safe_run_task)
        
        logger.info(f"已设置每周定时任务，执行时间：{self.weekday.capitalize()} at {self.schedule_time}")
        
        if run_immediately:
            logger.info("立即执行一次任务...")
            self._safe_run_task()
    
    def _safe_run_task(self):
        """安全执行任务（带异常捕获）"""
        if self._task_callback is None:
            return
        
        try:
            logger.info("=" * 60)
            logger.info(f"定时任务开始执行 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            logger.info("=" * 60)
            
            self._task_callback()
            
            logger.info(f"定时任务执行完成 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            logger.info("=" * 60)
            
        except Exception as e:
            logger.exception(f"定时任务执行失败：{e}")
    
    def run(self):
        """
        运行调度器主循环
        
        阻塞运行，直到收到退出信号
        """
        self._running = True
        logger.info("调度器开始运行...")
        logger.info(f"下次执行时间：{self._get_next_run_time()}")
        
        while self._running and not self.shutdown_handler.should_shutdown:
            self.schedule.run_pending()
            time.sleep(30)  # 每 30 秒检查一次
            
            # 每小时打印一次心跳
            if datetime.now().minute == 0 and datetime.now().second < 30:
                logger.info(f"调度器运行中... 下次执行：{self._get_next_run_time()}")
        
        logger.info("调度器已停止")
    
    def _get_next_run_time(self) -> str:
        """获取下次执行时间"""
        jobs = self.schedule.get_jobs()
        if jobs:
            next_run = min(job.next_run for job in jobs)
            return next_run.strftime('%Y-%m-%d %H:%M:%S')
        return "未设置"
    
    def stop(self):
        """停止调度器"""
        self._running = False


def run_weekly_screener():
    """
    执行每周选股任务（带飞书通知）
    """
    from scripts.t0_stock_screener import run_screener
    
    logger.info("🚀 Starting weekly T+0 stock screening...")
    run_screener(send_notification=True)
    logger.info("✅ Weekly screening completed")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="T+0 Stock Screener Weekly Scheduler")
    parser.add_argument(
        "--weekday",
        type=str,
        default="monday",
        choices=["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"],
        help="Which day of the week to run (default: monday)"
    )
    parser.add_argument(
        "--time",
        type=str,
        default="09:00",
        help="Time to run in HH:MM format (default: 09:00)"
    )
    parser.add_argument(
        "--no-immediate",
        action="store_true",
        help="Don't run immediately on startup"
    )
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("T+0 选股池周度定时任务调度器")
    print("=" * 60)
    print(f"执行时间：每{args.weekday.capitalize()} {args.time}")
    print(f"立即执行：{'否' if args.no_immediate else '是'}")
    print("=" * 60)
    print()
    
    scheduler = WeeklyScheduler(weekday=args.weekday, schedule_time=args.time)
    scheduler.set_weekly_task(run_weekly_screener, run_immediately=not args.no_immediate)
    
    try:
        scheduler.run()
    except KeyboardInterrupt:
        print("\n\n收到中断信号，正在退出...")
        scheduler.stop()
        logger.info("调度器已退出")
