import asyncio
import os
import sys
import sqlite3
from typing import Dict, Any

# 将 src 目录添加到路径
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.services.performance_tracker import PerformanceTracker
from src.agents.consensus_engine import RayDalioAggregator
from tests.test_ensemble_consensus import call_expert_cli

async def test_dynamic_weighting_logic():
    print("🚀 开始动态权重压力测试...")
    
    db_path = "workspace/test_performance.db"
    if os.path.exists(db_path): os.remove(db_path)
    
    tracker = PerformanceTracker(db_path=db_path)
    
    # 1. 制造“极端反转”的战绩：
    # 塔勒布：最近 5 场全对 (Accuracy 100%) -> Weight ~ 1.0
    # 巴菲特：最近 5 场全错 (Accuracy 0%) -> Weight ~ 0.1
    for i in range(5):
        tracker.record_prediction("nassim_taleb", "MOCK", "bearish", 90)
        # 获取刚插入的 ID
        with sqlite3.connect(db_path) as conn:
            rid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        tracker.backfill_result(rid, -0.05) # 跌 5%，塔勒布对
        
        tracker.record_prediction("warren_buffett", "MOCK", "bullish", 90)
        with sqlite3.connect(db_path) as conn:
            rid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        tracker.backfill_result(rid, -0.05) # 跌 5%，巴菲特错
        
    weights = tracker.get_analyst_weights()
    print(f"📊 当前权重分布: {weights}")
    
    # 2. 构造分歧场景
    ticker = "MOCK_TECH_STOCK"
    expert_reports = {
        "warren_buffett": {
            "signal": "bullish", 
            "confidence": 95, 
            "reasoning": "我认为这是人类历史上最伟大的护城河，必须全仓买入！"
        },
        "nassim_taleb": {
            "signal": "bearish", 
            "confidence": 80, 
            "reasoning": "这完全是一个脆弱的火鸡陷阱，技术债务极高，随时可能崩盘。"
        },
        "li_lu": {"signal": "neutral", "confidence": 50, "reasoning": "待观察"},
        "paul_tudor_jones": {"signal": "neutral", "confidence": 50, "reasoning": "震荡"},
        "jensen_huang": {"signal": "neutral", "confidence": 50, "reasoning": "技术平平"}
    }
    
    # 3. 询问达里奥
    print(f"\n👔 达里奥正在针对分歧进行拍板 (巴菲特看多 vs 塔勒布看空)...")
    aggregator = RayDalioAggregator()
    final_report = await call_expert_cli(
        aggregator.get_expert_id(),
        aggregator.SYSTEM_PROMPT,
        aggregator.prepare_consensus_prompt(ticker, expert_reports, weights)
    )
    
    print("\n" + "="*50)
    print(f"【最终结论】: {final_report.get('final_rating')}")
    print(f"【达里奥的偏向】: {final_report.get('consensus_summary')}")
    print(f"【分歧分析】: {final_report.get('divergence_analysis')}")
    print("="*50)
    
    # 验证：因为巴菲特权重极低（0.1），达里奥不应该给出 Strong Buy 或 Buy
    rating = final_report.get('final_rating')
    if "Sell" in rating or "Hold" in rating:
        print("\n✅ 测试通过：达里奥成功识别了低胜率专家的噪音，并采纳了高胜率专家的建议。")
    else:
        print(f"\n❌ 测试失败：达里奥仍然被低胜率专家误导（Rating: {rating}）。")

if __name__ == "__main__":
    asyncio.run(test_dynamic_weighting_logic())
