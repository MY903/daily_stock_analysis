"""策略注册表

提供策略的注册、发现和实例化功能。
所有策略必须显式注册，不支持文件系统扫描。

用法:
    # 显式注册
    StrategyRegistry.register(TQQQSwingStrategy)

    # 或作为装饰器
    @StrategyRegistry.register
    class MyStrategy(BaseStrategy):
        ...
"""

from dataclasses import replace
from typing import Dict, List, Type

from src.trading.config import AppConfig
from src.trading.strategy.base import BaseStrategy


class StrategyRegistry:
    """策略注册表

    维护一个全局的策略类注册中心，支持：
    - register(cls): 注册策略类（装饰器/函数二合一）
    - list_strategies(): 列出所有已注册策略名称
    - get(name): 按名称获取策略类
    - from_config(config): 从配置批量实例化策略

    策略名称来源于 cls.name 属性，必须是非空字符串。
    """

    _registry: Dict[str, Type[BaseStrategy]] = {}

    @classmethod
    def register(cls, strategy_cls: Type[BaseStrategy]) -> Type[BaseStrategy]:
        """注册策略类

        可同时作为装饰器或普通函数使用：
            @StrategyRegistry.register          # 装饰器用法
            StrategyRegistry.register(MyStrategy)  # 函数用法

        Args:
            strategy_cls: 要注册的策略类（BaseStrategy 的子类）

        Returns:
            原策略类（便于用作装饰器时返回原类）

        Raises:
            ValueError: 策略名称重复或 name 属性无效
        """
        name = cls._resolve_strategy_name(strategy_cls)
        if name in cls._registry:
            raise ValueError(f"策略名称已存在: {name}")
        cls._registry[name] = strategy_cls
        return strategy_cls

    @staticmethod
    def _resolve_strategy_name(strategy_cls: Type[BaseStrategy]) -> str:
        """解析策略名称，支持 name 作为类变量或实例属性

        Args:
            strategy_cls: 策略类

        Returns:
            策略名称字符串

        Raises:
            ValueError: 无法解析有效的策略名称
        """
        # 方式 1: name 是类层面的字符串
        raw = strategy_cls.__dict__.get("name")
        if isinstance(raw, str) and raw.strip():
            return raw.strip()

        # 方式 2: name 是实例属性（@property），通过临时实例读取
        try:
            raw = strategy_cls(AppConfig()).name
            if isinstance(raw, str) and raw.strip():
                return raw.strip()
        except Exception:
            pass

        raise ValueError(
            f"策略 {strategy_cls.__name__} 必须定义非空的 name 属性"
            f"（类变量或实例属性均可）"
        )

    @classmethod
    def list_strategies(cls) -> List[str]:
        """返回所有已注册策略的名称列表

        Returns:
            策略名称列表
        """
        return list(cls._registry.keys())

    @classmethod
    def get(cls, name: str) -> Type[BaseStrategy]:
        """根据名称获取策略类

        Args:
            name: 策略名称（对应 strategy_cls.name）

        Returns:
            策略类

        Raises:
            KeyError: 策略未注册
        """
        if name not in cls._registry:
            raise KeyError(
                f"策略未注册: {name}。"
                f"可用策略: {cls.list_strategies() or '(无)'}"
            )
        return cls._registry[name]

    @classmethod
    def from_config(cls, config: AppConfig) -> List[BaseStrategy]:
        """从配置实例化策略

        遍历 config.trading.symbols，为每个标的创建所有已注册策略的实例。
        每个实例会获得一个独立的配置副本，其中的 trading.symbol 被设为当前标的。

        Args:
            config: 应用配置

        Returns:
            策略实例列表。长度为 symbols × registered_strategies。

        示例:
            config.trading.symbols = ["TQQQ", "SOXL"]
            如果已注册 TQQQSwingStrategy 和 MACrossoverStrategy，
            将返回 4 个实例（2 标的 × 2 策略）。
        """
        instances: List[BaseStrategy] = []
        for symbol in config.trading.symbols:
            # 为每个标的创建独立的配置副本
            sym_config = replace(
                config,
                trading=replace(config.trading, symbol=symbol),
            )
            for strategy_cls in cls._registry.values():
                instances.append(strategy_cls(sym_config))
        return instances
