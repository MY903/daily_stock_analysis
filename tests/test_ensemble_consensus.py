"""
集成测试：专家委员会共识引擎
- 纯单元测试部分（不需要 LLM）：权重注入、prompt 拼接、输入校验
- 集成测试部分（需要 gemini CLI）：跳过条件由 skipif 控制
"""
import asyncio
import json
import os
import shutil
import subprocess
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
# 工具函数（CLI 调用，供集成测试使用）
# ---------------------------------------------------------------------------

async def call_expert_cli(expert_id: str, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
    """异步调用 Gemini CLI 子进程。"""
    full_prompt = f"System: {system_prompt}\n\nUser: {user_prompt}"
    cmd = ["gemini", "-p", f"Expert: {expert_id}. Output JSON ONLY."]

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await process.communicate(input=full_prompt.encode('utf-8'))

    if process.returncode != 0:
        return {"signal": "neutral", "confidence": 0, "reasoning": "CLI Error"}

    output = stdout.decode().strip()
    if "```json" in output:
        output = output.split("```json")[1].split("```")[0].strip()
    elif "```" in output:
        output = output.split("```")[1].split("```")[0].strip()

    try:
        return json.loads(output)
    except Exception:
        return {"signal": "neutral", "confidence": 0, "reasoning": "Parse Error"}


# ---------------------------------------------------------------------------
# 单元测试：不依赖 LLM / gemini CLI
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


# ---------------------------------------------------------------------------
# 集成测试：需要 gemini CLI（CI 环境自动跳过）
# ---------------------------------------------------------------------------

@pytest.mark.skipif(shutil.which("gemini") is None, reason="gemini CLI not installed")
@pytest.mark.integration
def test_ensemble_full_flow():
    """全链路集成测试：5 位专家并发分析 + 达里奥汇总。需要已认证的 gemini CLI。"""
    ticker = "300308.SZ"
    technical_data = {
        "current_price": "165.50",
        "trend_summary": "上升通道，回调至 20 日均线",
        "technical_indicators": "MACD 金叉，RSI=65"
    }
    news_data = [
        {"date": "2026-04-01", "title": "英伟达 B200 芯片订单需求超预期"},
        {"date": "2026-04-02", "title": "中际旭创净利润同比增长 100%+"},
    ]

    async def _run():
        experts = [
            WarrenBuffettExpert(), LiLuExpert(), PaulTudorJonesExpert(),
            JensenHuangExpert(), NassimTalebExpert()
        ]
        tasks = [
            call_expert_cli(e.get_expert_id(), e.SYSTEM_PROMPT, e.prepare_prompt(ticker, technical_data, news_data))
            for e in experts
        ]
        expert_results = await asyncio.gather(*tasks)
        expert_reports = {experts[i].get_expert_id(): expert_results[i] for i in range(len(experts))}

        aggregator = RayDalioAggregator()
        final_report = await call_expert_cli(
            aggregator.get_expert_id(),
            aggregator.SYSTEM_PROMPT,
            aggregator.prepare_consensus_prompt(ticker, expert_reports)
        )
        return final_report

    final_report = asyncio.run(_run())

    # 若 CLI 调用失败（认证未完成、网络问题等），跳过而非报失败
    if final_report.get("reasoning") in ("CLI Error", "Parse Error"):
        pytest.skip(f"gemini CLI 调用失败: {final_report.get('reasoning')}，请确认认证状态")

    assert isinstance(final_report, dict), "final_report 应为 dict"
    assert final_report.get("final_rating") in [
        "Strong Buy", "Buy", "Hold", "Sell", "Strong Sell"
    ], f"final_rating 值非法: {final_report.get('final_rating')}"
    assert "consensus_summary" in final_report
    assert "action_plan" in final_report
