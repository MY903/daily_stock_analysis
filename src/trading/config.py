"""交易配置加载器

从 config/trading.yaml 加载交易参数，支持环境变量覆盖。
"""

import os
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


@dataclass
class TigerConfig:
    """Tiger OpenAPI 连接配置"""
    config_path: str = "tiger_openapi_config.properties"
    environment: str = "PAPER"  # PAPER / LIVE

    @property
    def is_live(self) -> bool:
        return self.environment.upper() == "LIVE"

    @property
    def absolute_config_path(self) -> Path:
        p = Path(self.config_path)
        if p.is_absolute():
            return p
        return PROJECT_ROOT / p


@dataclass
class EntryConfig:
    """买入配置"""
    trigger_price: float = 74.61
    quantity: int = 35
    order_type: str = "LMT"
    time_in_force: str = "GTC"


@dataclass
class TakeProfitConfig:
    """止盈配置"""
    percentage: float = 0.04
    order_type: str = "LMT"
    time_in_force: str = "GTC"


@dataclass
class StopLossConfig:
    """止损配置"""
    percentage: float = 0.032
    order_type: str = "STP_LMT"
    limit_offset: float = 0.005
    time_in_force: str = "GTC"


@dataclass
class TradingConfig:
    """交易策略配置"""
    symbol: str = "TQQQ"
    market: str = "US"
    auto_trade: bool = False
    entry: EntryConfig = field(default_factory=EntryConfig)
    take_profit: TakeProfitConfig = field(default_factory=TakeProfitConfig)
    stop_loss: StopLossConfig = field(default_factory=StopLossConfig)


@dataclass
class BotConfig:
    """机器人行为配置"""
    cooldown_seconds: int = 300
    pre_market: bool = True
    post_market: bool = True
    poll_interval: int = 30
    signal_cooldown: int = 60


@dataclass
class NotificationConfig:
    """通知配置"""
    enabled: bool = True
    platform: str = "feishu"
    webhook_url: str = ""
    webhook_secret: str = ""


@dataclass
class LoggingConfig:
    """日志配置"""
    level: str = "INFO"
    log_dir: str = "./logs"
    data_dir: str = "./data"


@dataclass
class AppConfig:
    """顶层应用配置"""
    tiger: TigerConfig = field(default_factory=TigerConfig)
    trading: TradingConfig = field(default_factory=TradingConfig)
    bot: BotConfig = field(default_factory=BotConfig)
    notification: NotificationConfig = field(default_factory=NotificationConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)


def _merge_env_overrides(config: AppConfig) -> None:
    """环境变量覆盖配置（优先级高于 YAML）"""
    env_map = {
        "TRADING_TIGER_ENV": ("tiger", "environment"),
        "TRADING_TIGER_CONFIG_PATH": ("tiger", "config_path"),
        "TRADING_SYMBOL": ("trading", "symbol"),
        "TRADING_AUTO_TRADE": ("trading", "auto_trade"),
        "TRADING_ENTRY_PRICE": ("trading.entry", "trigger_price"),
        "TRADING_ENTRY_QTY": ("trading.entry", "quantity"),
        "TRADING_TP_PCT": ("trading.take_profit", "percentage"),
        "TRADING_SL_PCT": ("trading.stop_loss", "percentage"),
        "TRADING_WEBHOOK_URL": ("notification", "webhook_url"),
        "TRADING_WEBHOOK_SECRET": ("notification", "webhook_secret"),
        "TRADING_LOG_LEVEL": ("logging", "level"),
    }

    for env_key, (section, attr) in env_map.items():
        value = os.environ.get(env_key)
        if value is None:
            continue

        # 获取目标对象
        if "." in section:
            parts = section.split(".")
            obj = getattr(config, parts[0])
            obj = getattr(obj, parts[1])
        else:
            obj = getattr(config, section)

        # 类型转换
        current = getattr(obj, attr)
        if isinstance(current, bool):
            converted = value.lower() in ("true", "1", "yes")
        elif isinstance(current, int):
            converted = int(value)
        elif isinstance(current, float):
            converted = float(value)
        else:
            converted = value

        setattr(obj, attr, converted)
        logger.debug("环境变量覆盖: %s -> %s.%s = %s", env_key, section, attr, converted)


def load_config(config_path: Optional[str] = None) -> AppConfig:
    """加载交易配置

    Args:
        config_path: 配置文件路径，默认为 config/trading.yaml

    Returns:
        AppConfig 实例
    """
    if config_path is None:
        config_path = str(PROJECT_ROOT / "config" / "trading.yaml")

    config_file = Path(config_path)

    if config_file.exists():
        logger.info("加载交易配置: %s", config_file)
        with open(config_file, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
    else:
        logger.warning("配置文件不存在: %s，使用默认配置", config_file)
        raw = {}

    # 解析各层配置
    tiger_raw = raw.get("tiger", {})
    trading_raw = raw.get("trading", {})
    bot_raw = raw.get("bot", {})
    notification_raw = raw.get("notification", {})
    logging_raw = raw.get("logging", {})

    # 构建嵌套配置
    entry_raw = trading_raw.pop("entry", {}) if isinstance(trading_raw, dict) else {}
    tp_raw = trading_raw.pop("take_profit", {}) if isinstance(trading_raw, dict) else {}
    sl_raw = trading_raw.pop("stop_loss", {}) if isinstance(trading_raw, dict) else {}

    config = AppConfig(
        tiger=TigerConfig(**{k: v for k, v in tiger_raw.items() if k in TigerConfig.__dataclass_fields__}),
        trading=TradingConfig(
            **{k: v for k, v in trading_raw.items() if k in TradingConfig.__dataclass_fields__},
            entry=EntryConfig(**{k: v for k, v in entry_raw.items() if k in EntryConfig.__dataclass_fields__}),
            take_profit=TakeProfitConfig(**{k: v for k, v in tp_raw.items() if k in TakeProfitConfig.__dataclass_fields__}),
            stop_loss=StopLossConfig(**{k: v for k, v in sl_raw.items() if k in StopLossConfig.__dataclass_fields__}),
        ),
        bot=BotConfig(**{k: v for k, v in bot_raw.items() if k in BotConfig.__dataclass_fields__}),
        notification=NotificationConfig(**{k: v for k, v in notification_raw.items() if k in NotificationConfig.__dataclass_fields__}),
        logging=LoggingConfig(**{k: v for k, v in logging_raw.items() if k in LoggingConfig.__dataclass_fields__}),
    )

    # 环境变量覆盖
    _merge_env_overrides(config)

    return config
