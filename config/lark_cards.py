# -*- coding: utf-8 -*-
"""
飞书互动卡片模板配置

定义所有卡片类型和相关配置。
"""

from bot.platforms.lark_interactive import (
    CARD_SIGNAL_CONFIRM,
    CARD_EXECUTION_RESULT,
    CARD_RISK_INTERCEPT,
    CARD_SIGNAL_EXPIRED,
)

CARD_TEMPLATES = {
    CARD_SIGNAL_CONFIRM: "信号确认卡片",
    CARD_EXECUTION_RESULT: "执行结果卡片",
    CARD_RISK_INTERCEPT: "风控拦截卡片",
    CARD_SIGNAL_EXPIRED: "信号过期卡片",
}

__all__ = ["CARD_TEMPLATES", "CARD_SIGNAL_CONFIRM", "CARD_EXECUTION_RESULT",
           "CARD_RISK_INTERCEPT", "CARD_SIGNAL_EXPIRED"]
