#!/usr/bin/env python3
"""TQQQ 自动交易机器人入口

用法:
    python trading_main.py                    # 使用默认配置启动
    python trading_main.py --config path.yaml # 指定配置文件
    python trading_main.py --dry-run          # 试运行（检查连接后退出）
    python trading_main.py --status           # 查看当前状态
"""

import argparse
import json
import logging
import sys
from pathlib import Path

# 确保项目根目录在 sys.path 中
project_root = Path(__file__).resolve().parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.trading.config import load_config
from src.trading.bot import TradingBot
from src.trading.state_machine import StateMachine


def setup_logging(level: str = "INFO", log_dir: str = "./logs") -> None:
    """配置日志"""
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    import time
    log_file = log_path / f"tqqq_bot_{time.strftime('%Y-%m-%d')}.log"

    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_file, encoding="utf-8"),
        ],
    )


def cmd_start(args: argparse.Namespace) -> None:
    """启动交易机器人"""
    config = load_config(args.config)
    setup_logging(config.logging.level, config.logging.log_dir)

    logger = logging.getLogger(__name__)
    logger.info("配置加载完成: symbol=%s, env=%s, auto_trade=%s",
                config.trading.symbol, config.tiger.environment,
                config.trading.auto_trade)

    bot = TradingBot(config)
    bot.start()


def cmd_dry_run(args: argparse.Namespace) -> None:
    """试运行：验证配置和连接"""
    config = load_config(args.config)
    setup_logging("INFO", config.logging.log_dir)

    logger = logging.getLogger(__name__)
    logger.info("=== 试运行模式 ===")
    logger.info("标的: %s", config.trading.symbol)
    logger.info("环境: %s", config.tiger.environment)
    logger.info("自动交易: %s", config.trading.auto_trade)

    # 验证 Tiger API 连接
    from src.trading.tiger_client import TigerClient
    client = TigerClient(config)

    try:
        client.connect()
        logger.info("Tiger API 连接成功（用于交易执行）")

        # 获取账户资产
        assets = client.get_assets()
        logger.info("账户资产: %s", assets)

        # 获取持仓
        positions = client.get_positions()
        logger.info("当前持仓: %s", positions)

    except Exception as e:
        logger.error("Tiger API 验证失败: %s", e)
        sys.exit(1)
    finally:
        client.disconnect()

    # 验证 yfinance 行情数据源（免费，无需付费订阅）
    from src.trading.monitor import QuoteMonitor
    monitor = QuoteMonitor(client=None, config=config)
    quote = monitor.poll_quote()
    if quote and quote.get("latest_price"):
        logger.info("行情数据源验证成功 (source=%s): %s $%.2f",
                    quote.get("source"), config.trading.symbol,
                    quote["latest_price"])
        if quote.get("change_pct") is not None:
            logger.info("涨跌幅: %.2f%%", quote["change_pct"])
    else:
        logger.error("行情数据源验证失败: 无法获取 %s 价格", config.trading.symbol)
        sys.exit(1)

    logger.info("=== 试运行通过 ===")


def cmd_status(args: argparse.Namespace) -> None:
    """查看当前状态（读取持久化文件）"""
    config = load_config(args.config)
    setup_logging("INFO", config.logging.log_dir)

    sm = StateMachine(data_dir=config.logging.data_dir)
    sm.restore()

    status = sm.to_dict()
    print(json.dumps(status, indent=2, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="TQQQ 自动交易机器人",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--config", "-c",
        type=str,
        default=None,
        help="配置文件路径 (默认: config/trading.yaml)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="试运行模式：验证配置和 API 连接",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="查看当前交易状态",
    )

    args = parser.parse_args()

    if args.dry_run:
        cmd_dry_run(args)
    elif args.status:
        cmd_status(args)
    else:
        cmd_start(args)


if __name__ == "__main__":
    main()
