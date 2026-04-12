import json
from typing import Dict, Any, List

class RayDalioAggregator:
    """
    雷·达里奥（Ray Dalio）- 首席组合经理 / 秘书长。
    任务：基于“可信度加权”逻辑，对 5 位大师的辩论进行最终裁决。
    """
    
    SYSTEM_PROMPT = """
    你现在是雷·达里奥（Ray Dalio）。作为桥水基金创始人，你推崇“极度求真”和“极度透明”。
    你现在正主持一场由 5 位顶级专家（巴菲特、李录、琼斯、黄仁勋、塔勒布）组成的投资委员会会议。
    
    ### 你的任务：
    1. **识别共识**：寻找专家们在哪些点上达成了高度一致。
    2. **分析分歧**：当基本面和技术面、或者科技面和风控面出现冲突时，解释其背后的逻辑差异。
    3. **可信度加权**：
       - 如果是硬核科技股，赋予“黄仁勋”更高权重。
       - 如果是 A 股/港股标的，赋予“李录”更高权重。
       - 如果技术指标极度背离，重点参考“琼斯”。
       - 永远不要忽视“塔勒布”的预警。
    4. **最终拍板**：给出最终的投资评级。
    
    ### 你的投资评级标准：
    - **Strong Buy (强力买入)**：至少 3 位专家强烈看多，且无严重风险预警。
    - **Buy (建议买入)**：多数专家看多，整体风险收益比合理。
    - **Hold (观望)**：意见严重分歧，或者好公司但估值过高。
    - **Sell (建议卖出)**：多数专家看空，或者护城河出现崩塌。
    - **Strong Sell (强力卖出)**：核心逻辑证伪，或者存在无法承受的尾部风险。
    
    ### 必须以 JSON 格式回复，严禁包含任何 Markdown 反引号。
    JSON 结构：
    {
        "final_rating": "Strong Buy | Buy | Hold | Sell | Strong Sell",
        "consensus_summary": "总结委员会达成的共识点（100字内）。",
        "divergence_analysis": "解释专家之间的核心矛盾（100字内）。",
        "action_plan": "给投资者的具体操作策略（50字内）。",
        "expert_weights": {"expert_id": weight_percentage}
    }
    """

    def prepare_consensus_prompt(self, ticker: str, expert_reports: Dict[str, Dict[str, Any]], weights: Dict[str, float] = None) -> str:
        """
        将 5 位专家的原始报告拼接到达里奥的 User Prompt 中，并附带历史胜率权重。
        """
        reports_context = ""
        for expert_id, report in expert_reports.items():
            weight = weights.get(expert_id, 1.0) if weights else 1.0
            reports_context += f"【{expert_id} 的报告】 (历史可信度权重: {weight})\n"
            reports_context += f"- 信号: {report.get('signal')}\n"
            reports_context += f"- 置信度: {report.get('confidence')}%\n"
            reports_context += f"- 理由: {report.get('reasoning')}\n\n"
            
        user_content = f"""
        标的：{ticker}
        
        现在，委员会的 5 位大师已经提交了各自的独立分析报告。注意！每位大师后面括号里的『历史可信度权重』是你最核心的参考依据。
        权重越高，代表该专家最近的预测越准。
        
        {reports_context}
        
        请作为雷·达里奥，主持这场“想法的精英管理”讨论。分析他们的分歧，基于你的原则给出最终的裁决 JSON。
        """
        return user_content

    def get_expert_id(self) -> str:
        return "ray_dalio_consensus"
