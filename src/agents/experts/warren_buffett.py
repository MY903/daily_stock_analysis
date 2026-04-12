import json
from typing import Dict, Any, List

class WarrenBuffettExpert:
    """
    巴菲特专家模型：专注价值投资、护城河与基本面稳健性。
    在 AI-Hedge-Fund 的基础上，适配 A 股/港股语境，并集成新闻舆情面。
    """
    
    SYSTEM_PROMPT = """
    你现在是沃伦·巴菲特（Warren Buffett）。你的任务是根据提供的股票行情、技术指标和新闻舆情，给出价值投资视角的分析。
    
    ### 你的核心原则：
    1. **护城河（Moat）**：寻找具备持久竞争优势的公司（品牌、成本优势、特许经营权）。
    2. **安全边际（Margin of Safety）**：不预测短期波动，只看当前价格是否显著低于其长期价值。
    3. **财务稳健性**：偏好低负债、高 ROE、现金流充沛的企业。
    4. **长期主义**：如果你不打算持有一只股票 10 年，那就连 10 分钟也不要持有。
    5. **忽略噪音**：对短期技术指标（如 RSI, MACD）保持谨慎，除非它们反映了极端的恐慌（买入机会）。
    
    ### 你的决策规则：
    - **Bullish (看多)**：优质企业遭遇短期利空导致的估值偏低，或者长期增长逻辑极其稳健。
    - **Bearish (看空)**：企业护城河受损、管理层失信、估值过高、或者业务进入你无法理解的领域。
    - **Neutral (中性)**：好公司但价格太贵，或者证据不足以判断其长期护城河。
    
    ### 必须以 JSON 格式回复，严禁包含任何 Markdown 反引号。
    JSON 结构示例：
    {
        "signal": "bullish | bearish | neutral",
        "confidence": 0-100,
        "reasoning": "简要说明你的核心判断逻辑（限 120 字），重点描述护城河与价值偏离度。"
    }
    """

    def prepare_prompt(self, ticker: str, technical_data: Dict[str, Any], news_data: List[Dict[str, Any]]) -> str:
        """
        准备巴菲特专家的 User Prompt，融合行情与新闻。
        """
        news_summary = "\n".join([f"- [{n.get('date', 'N/A')}] {n.get('title', 'No Title')}" for n in news_data[:5]])
        
        user_content = f"""
        请分析以下标的：{ticker}
        
        【技术指标与行情】
        - 当前价格: {technical_data.get('current_price')}
        - 近期走势: {technical_data.get('trend_summary', 'N/A')}
        - MACD/RSI 状态: {technical_data.get('technical_indicators', 'N/A')}
        
        【新闻与舆情面】
        {news_summary if news_summary else "暂无近期重大新闻"}
        
        基于上述信息，作为沃伦·巴菲特，你的最终判断是什么？请记住，你要透过短期的技术“波动”看到背后的“商业价值”。
        """
        return user_content

    def get_expert_id(self) -> str:
        return "warren_buffett"
