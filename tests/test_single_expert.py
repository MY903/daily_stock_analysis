"""
单元测试：单一专家节点
- 验证专家 prompt 生成的正确性（无 LLM 依赖）
- 验证专家 ID 唯一性与基本结构
"""
import os
import sys

import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.agents.experts.warren_buffett import WarrenBuffettExpert


TICKER = "600519.SH (贵州茅台)"
TECHNICAL_DATA = {
    "current_price": "1450.00 CNY",
    "trend_summary": "自 1700 元高点回落，目前处于半年均线下方，呈缩量阴跌态势。",
    "technical_indicators": "RSI(14) 接近 30，显示超卖；MACD 死叉已持续 5 个交易日。",
}
NEWS_DATA = [
    {"date": "2026-04-01", "title": "部分机构下调白酒行业全年增长预期"},
    {"date": "2026-04-02", "title": "茅台集团：稳步推进高质量增长，品牌护城河稳固"},
    {"date": "2026-04-03", "title": "外资连续 3 日净流出白酒板块"},
]


def test_warren_buffett_prompt_is_non_empty():
    """巴菲特专家的 prepare_prompt 应返回非空字符串，包含股票代码。"""
    expert = WarrenBuffettExpert()
    prompt = expert.prepare_prompt(TICKER, TECHNICAL_DATA, NEWS_DATA)
    assert isinstance(prompt, str)
    assert len(prompt) > 50
    assert TICKER in prompt or "600519" in prompt


def test_warren_buffett_system_prompt_defined():
    """SYSTEM_PROMPT 应为非空字符串。"""
    expert = WarrenBuffettExpert()
    assert isinstance(expert.SYSTEM_PROMPT, str)
    assert len(expert.SYSTEM_PROMPT) > 20


def test_warren_buffett_expert_id():
    """expert_id 应为非空字符串，且包含可识别的标识。"""
    expert = WarrenBuffettExpert()
    eid = expert.get_expert_id()
    assert isinstance(eid, str) and len(eid) > 0
    assert "buffett" in eid.lower() or "warren" in eid.lower()


def test_prompt_contains_technical_data():
    """prompt 中应包含技术指标的关键信息。"""
    expert = WarrenBuffettExpert()
    prompt = expert.prepare_prompt(TICKER, TECHNICAL_DATA, NEWS_DATA)
    assert "1450" in prompt or "RSI" in prompt or "MACD" in prompt


def test_prompt_contains_news():
    """prompt 中应包含至少一条新闻标题。"""
    expert = WarrenBuffettExpert()
    prompt = expert.prepare_prompt(TICKER, TECHNICAL_DATA, NEWS_DATA)
    assert any(news["title"] in prompt for news in NEWS_DATA)
