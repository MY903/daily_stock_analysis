import asyncio
import json
import os
import subprocess
import sys
from typing import Dict, Any

# 将 src 目录添加到路径，以便导入
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.agents.experts.warren_buffett import WarrenBuffettExpert
from src.agents.experts.li_lu import LiLuExpert
from src.agents.experts.paul_tudor_jones import PaulTudorJonesExpert
from src.agents.experts.jensen_huang import JensenHuangExpert
from src.agents.experts.nassim_taleb import NassimTalebExpert
from src.agents.consensus_engine import RayDalioAggregator

async def call_expert_cli(expert_id: str, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
    """
    异步调用 Gemini CLI 子进程。
    """
    full_prompt = f"System: {system_prompt}\n\nUser: {user_prompt}"
    cmd = ["gemini", "-p", f"Expert: {expert_id}. Output JSON ONLY."]
    
    # 使用 asyncio.create_subprocess_exec 实现非阻塞调用
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    
    stdout, stderr = await process.communicate(input=full_prompt.encode('utf-8'))
    
    if process.returncode != 0:
        print(f"Error calling {expert_id}: {stderr.decode()}")
        return {"signal": "neutral", "confidence": 0, "reasoning": "Error"}
    
    output = stdout.decode().strip()
    # 清洗逻辑
    if "```json" in output:
        output = output.split("```json")[1].split("```")[0].strip()
    elif "```" in output:
        output = output.split("```")[1].split("```")[0].strip()
    
    try:
        return json.loads(output)
    except:
        print(f"Failed to parse JSON for {expert_id}: {output}")
        return {"signal": "neutral", "confidence": 0, "reasoning": "Parse Error"}

async def run_ensemble_test():
    """
    模拟大模型委员会并发分析过程。
    """
    ticker = "300308.SZ (中际旭创 - AI 算力光模块龙头)"
    technical_data = {
        "current_price": "165.50 CNY",
        "trend_summary": "处于上升通道，近日小幅回调至 20 日均线支撑位。",
        "technical_indicators": "MACD 金叉，RSI 位于 65 偏强区。"
    }
    news_data = [
        {"date": "2026-04-01", "title": "英伟达 B200 芯片订单需求超预期，光模块需求暴增"},
        {"date": "2026-04-02", "title": "财报显示中际旭创净利润同比增长 100%+"},
        {"date": "2026-04-03", "title": "市场传言某些算力禁令可能升级"}
    ]
    
    # 1. 初始化专家委员会
    experts = [
        WarrenBuffettExpert(),
        LiLuExpert(),
        PaulTudorJonesExpert(),
        JensenHuangExpert(),
        NassimTalebExpert()
    ]
    
    print(f"🚀 启动委员会对 {ticker} 的并发分析...")
    
    # 2. 并发调用所有专家 (Asyncio Gather)
    tasks = []
    for e in experts:
        tasks.append(call_expert_cli(
            e.get_expert_id(), 
            e.SYSTEM_PROMPT, 
            e.prepare_prompt(ticker, technical_data, news_data)
        ))
    
    expert_results = await asyncio.gather(*tasks)
    
    # 组合结果
    expert_reports = {experts[i].get_expert_id(): expert_results[i] for i in range(len(experts))}
    
    for eid, rep in expert_reports.items():
        print(f"✅ {eid} 完成分析: {rep.get('signal')} ({rep.get('confidence')}%)")
    
    # 3. 秘书长达里奥汇总
    print(f"\n👔 秘书长雷·达里奥正在主持最终裁决...")
    aggregator = RayDalioAggregator()
    final_report = await call_expert_cli(
        aggregator.get_expert_id(),
        aggregator.SYSTEM_PROMPT,
        aggregator.prepare_consensus_prompt(ticker, expert_reports)
    )
    
    print("\n" + "="*50)
    print(f"【最终结论】: {final_report.get('final_rating')}")
    print(f"【共识点】: {final_report.get('consensus_summary')}")
    print(f"【分歧点】: {final_report.get('divergence_analysis')}")
    print(f"【操作建议】: {final_report.get('action_plan')}")
    print("="*50)

if __name__ == "__main__":
    asyncio.run(run_ensemble_test())
