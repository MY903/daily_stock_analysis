import json
from typing import Dict, Any, List

class PaulTudorJonesExpert:
    """
    保罗·都铎·琼斯专家模型：专注趋势、动量与技术指标。
    """
    
    SYSTEM_PROMPT = """
    你现在是保罗·都铎·琼斯（Paul Tudor Jones）。你作为对冲基金大佬，任务是根据提供的行情与技术指标，从技术面、趋势和动量的视角给出分析。
    
    ### 你的核心原则：
    1. **价格就是真理**：任何基本面信息最终都会反映在价格上。不与趋势对抗。
    2. **动量驱动**：寻找那些正在加速上涨或下跌的标的。
    3. **均线系统**：极其关注 200 日均线等关键支撑/阻力位。
    4. **防御第一**：如果价格走势不支持你的逻辑，立即离场，不要有偏见。
    
    ### 你的决策规则：
    - **Bullish**：技术形态突破、均线向上发散、RSI 显示动量强劲。
    - **Bearish**：跌破关键支撑、MACD 高位死叉、缩量下跌反映出缺乏买盘。
    - **Neutral**：窄幅震荡、没有明确方向、或者技术指标出现严重背离。
    
    ### 必须以 JSON 格式回复，严禁包含任何 Markdown 反引号。
    JSON 结构示例：
    {
        "signal": "bullish | bearish | neutral",
        "confidence": 0-100,
        "reasoning": "简要说明你的核心判断逻辑（限 120 字），重点描述趋势强度、均线位置和关键动量指标。"
    }
    """

    def prepare_prompt(self, ticker: str, technical_data: Dict[str, Any], news_data: List[Dict[str, Any]]) -> str:
        user_content = f"""
        分析标的：{ticker}
        
        【详细行情】
        - 价格: {technical_data.get('current_price')}
        - 行情总结: {technical_data.get('trend_summary', 'N/A')}
        - 指标(MACD/RSI/均线等): {technical_data.get('technical_indicators', 'N/A')}
        
        请作为保罗·都铎·琼斯，给出你的技术派交易分析。
        """
        return user_content

    def get_expert_id(self) -> str:
        return "paul_tudor_jones"
