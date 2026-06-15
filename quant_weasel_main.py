#!/usr/bin/env python3
"""
QuantWeasel - AI 量化交易系统 CLI 入口

Usage:
    # 盘前模式
    python quant_weasel_main.py --mode premarket --dry-run

    # 盘中模式
    python quant_weasel_main.py --mode intraday --dry-run

    # 手动信号
    python quant_weasel_main.py --mode manual --symbol AAPL --action BUY --quantity 100

    # 守护模式（调度+过期检查）
    python quant_weasel_main.py --mode daemon
"""

import asyncio
import logging

from config.settings import settings
from src.trading.pipeline import QuantWeaselPipeline


def main():
    parser = QuantWeaselPipeline.build_parser()
    args = parser.parse_args()

    # 配置日志
    logging.basicConfig(
        level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # 创建并运行
    pipeline = QuantWeaselPipeline()
    asyncio.run(pipeline.run_cli(args))


if __name__ == "__main__":
    main()
