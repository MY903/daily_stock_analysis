"""
单元测试：专家委员会共识引擎
- 权重注入、prompt 拼接、输入校验
"""
import os
import sys
from typing import Dict, Any

import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.agents.experts.warren_buffett import WarrenBuffettExpert
from src.agents.experts.li_lu import LiLuExpert
from src.agents.experts.paul_tudor_jones import PaulTudorJonesExpert
from src.agents.experts.jensen_huang import JensenHuangExpert
from src.agents.experts.nassim_taleb import NassimTalebExpert
from src.agents.consensus_engine import RayDalioAggregator


# ---------------------------------------------------------------------------
# 单元测试：不依赖 LLM
# ---------------------------------------------------------------------------

def test_consensus_engine_prompt_includes_weights():
    """权重参数必须被注入进 user prompt。"""
    aggregator = RayDalioAggregator()
    expert_reports = {
        "warren_buffett": {"signal": "bullish", "confidence": 90, "reasoning": "Great moat"},
        "nassim_taleb": {"signal": "bearish", "confidence": 70, "reasoning": "Tail risk"},
    }
    weights = {"warren_buffett": 0.3, "nassim_taleb": 0.7}
    prompt = aggregator.prepare_consensus_prompt("AAPL", expert_reports, weights)

    assert "warren_buffett" in prompt
    assert "nassim_taleb" in prompt
    assert "0.3" in prompt
    assert "0.7" in prompt


def test_consensus_engine_prompt_without_weights():
    """未传入 weights 时，prompt 中应显示默认值 1.0。"""
    aggregator = RayDalioAggregator()
    expert_reports = {
        "warren_buffett": {"signal": "bullish", "confidence": 80, "reasoning": "Value"},
    }
    prompt = aggregator.prepare_consensus_prompt("AAPL", expert_reports)
    assert "warren_buffett" in prompt
    assert "1.0" in prompt


def test_consensus_engine_missing_fields_are_patched():
    """报告缺少字段时应被自动补全，不抛出异常。"""
    aggregator = RayDalioAggregator()
    # 故意缺少 reasoning
    expert_reports = {
        "warren_buffett": {"signal": "bullish", "confidence": 80},
    }
    prompt = aggregator.prepare_consensus_prompt("AAPL", expert_reports)
    assert "warren_buffett" in prompt  # 不应抛异常


def test_expert_get_id():
    """每位专家都应返回唯一的 ID。"""
    experts = [
        WarrenBuffettExpert(),
        LiLuExpert(),
        PaulTudorJonesExpert(),
        JensenHuangExpert(),
        NassimTalebExpert(),
    ]
    ids = [e.get_expert_id() for e in experts]
    assert len(ids) == len(set(ids)), "专家 ID 不应重复"


def test_expert_prepare_prompt_returns_string():
    """每位专家的 prepare_prompt 都应返回非空字符串。"""
    ticker = "600519.SH"
    technical_data = {"current_price": "1800", "trend_summary": "上升", "technical_indicators": "RSI=60"}
    news_data = [{"date": "2026-04-01", "title": "茅台营收创新高"}]

    for ExpertCls in [WarrenBuffettExpert, LiLuExpert, PaulTudorJonesExpert, JensenHuangExpert, NassimTalebExpert]:
        expert = ExpertCls()
        prompt = expert.prepare_prompt(ticker, technical_data, news_data)
        assert isinstance(prompt, str) and len(prompt) > 50, f"{expert.get_expert_id()} prompt 过短或为空"

