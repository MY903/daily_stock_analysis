# -*- coding: utf-8 -*-
"""定制加密货币功能模块"""

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# 加密货币代码正则：2-10 个大写字母 + -USD 后缀（如 BTC-USD, ETH-USD）
_CRYPTO_PATTERN = re.compile(r'^[A-Z]{2,10}-USD$')


def is_crypto_code(code: str) -> bool:
    """
    判断代码是否为加密货币符号（如 BTC-USD, ETH-USD）。
    """
    return bool(_CRYPTO_PATTERN.match((code or '').strip().upper()))
