"""
凭据安全配置管理

从 .env 文件加载所有敏感配置（Tiger Brokers API 凭据、飞书通知凭据等），
替代硬编码的 tiger_openapi_config.properties 和 trading.yaml 中的明文凭据。

使用 pydantic-settings 的 BaseSettings 实现类型安全、自动补全和验证。
"""

import enum

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class TradingMode(str, enum.Enum):
    """交易运行模式（与 TIGER_ENV 一一映射）"""
    SANDBOX = "SANDBOX"  # 仅测试：纯模拟环境，不产生真实订单
    PAPER = "PAPER"      # 纸交验证：模拟下单，但验证完整流程
    PROD = "PROD"        # 实盘：生产环境，真实交易


class Settings(BaseSettings):
    """应用全局配置，所有字段优先从 .env 文件加载"""

    # ============================================================
    # Tiger Brokers OpenAPI 凭据（原 tiger_openapi_config.properties）
    # ============================================================

    TIGER_PRIVATE_KEY: str = Field(
        default="",
        description="Tiger OpenAPI RSA 私钥（PKCS#1 格式，对应 private_key_pk1）",
    )
    TIGER_TIGER_ID: str = Field(
        default="",
        description="Tiger OpenAPI 开发者 ID（tiger_id）",
    )
    TIGER_ACCOUNT: str = Field(
        default="",
        description="Tiger OpenAPI 交易账号（account）",
    )
    TIGER_TOKEN: str = Field(
        default="",
        description="Tiger OpenAPI 访问令牌（token）",
    )
    TIGER_LICENSE: str = Field(
        default="",
        description="Tiger OpenAPI 许可证编号（license）",
    )
    TIGER_ENV: str = Field(
        default="SANDBOX",
        description="Tiger 运行环境：SANDBOX（模拟）/ PAPER（模拟）/ PROD（实盘）",
    )

    # ============================================================
    # 交易策略参数
    # ============================================================

    TRADING_SYMBOL: str = Field(
        default="TQQQ",
        description="交易标的代码",
    )
    TRADING_AUTO_TRADE: bool = Field(
        default=False,
        description="是否开启自动下单（false = 仅发通知不下单）。默认由 TRADING_MODE 决定：SANDBOX=False, PAPER/PROD=True",
    )

    # ============================================================
    # 飞书/Lark 通知配置
    # ============================================================

    LARK_WEBHOOK_URL: str = Field(
        default="",
        description="飞书群机器人 Webhook URL（对应 trading.yaml notification.webhook_url）",
    )
    LARK_WEBHOOK_SECRET: str = Field(
        default="",
        description="飞书群机器人签名校验密钥",
    )
    LARK_APP_ID: str = Field(
        default="",
        description="飞书应用 App ID（用于 Stream Bot / 云文档模式）",
    )
    LARK_APP_SECRET: str = Field(
        default="",
        description="飞书应用 App Secret",
    )

    # ============================================================
    # 风控参数
    # ============================================================

    RISK_MAX_POSITION_PCT: float = Field(
        default=5.0,
        description="单标的最高仓位占比（%）",
    )
    RISK_MAX_DAILY_LOSS_PCT: float = Field(
        default=8.0,
        description="单日最大亏损占比（%）",
    )
    RISK_SIGNAL_TTL_MINUTES: int = Field(
        default=30,
        description="交易信号有效时长（分钟），超时自动失效",
    )
    RISK_MAX_ORDER_VALUE: float = Field(
        default=10000.0,
        description="单笔订单最大价值（美元），quantity × price ≤ 此值",
    )
    RISK_MAX_ORDERS_PER_MIN: int = Field(
        default=3,
        description="同一标的每分钟最大下单次数",
    )
    RISK_MAX_DAILY_ORDERS: int = Field(
        default=20,
        description="每日最大总订单数",
    )

    # ============================================================
    # 量化运行模式
    # ============================================================

    QUANT_DRY_RUN: bool = Field(
        default=True,
        description="是否为 Dry-Run 模式（True 时模拟交易不下真实订单）。默认由 TRADING_MODE 决定：SANDBOX/PAPER=True, PROD=False",
    )

    # ============================================================
    # 日志配置
    # ============================================================

    LOG_LEVEL: str = Field(
        default="INFO",
        description="日志级别：DEBUG / INFO / WARNING / ERROR",
    )

    # -----------------------------------------------------------
    # model_config：从 .env 文件加载，忽略多余字段
    # -----------------------------------------------------------

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # -----------------------------------------------------------
    # 派生属性
    # -----------------------------------------------------------

    @property
    def TRADING_MODE(self) -> TradingMode:
        """当前交易运行模式（从 TIGER_ENV 派生）"""
        return TradingMode(self.TIGER_ENV.upper())

    @property
    def is_sandbox(self) -> bool:
        """是否为纯模拟环境 (SANDBOX)"""
        return self.TRADING_MODE == TradingMode.SANDBOX

    @property
    def is_paper(self) -> bool:
        """是否为纸交验证模式 (PAPER)"""
        return self.TRADING_MODE == TradingMode.PAPER

    @property
    def is_prod(self) -> bool:
        """是否为实盘模式 (PROD)"""
        return self.TRADING_MODE == TradingMode.PROD

    @property
    def has_tiger_creds(self) -> bool:
        """是否已配置 Tiger OpenAPI 完整凭据"""
        return bool(
            self.TIGER_PRIVATE_KEY
            and self.TIGER_TIGER_ID
            and self.TIGER_ACCOUNT
            and self.TIGER_TOKEN
            and self.TIGER_LICENSE
        )


# 模块级单例，供业务代码直接导入使用
settings = Settings()
