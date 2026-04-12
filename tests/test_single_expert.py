import os
import subprocess
import json
import sys
from typing import Dict, Any

# 将 src 目录添加到路径，以便导入
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.agents.experts.warren_buffett import WarrenBuffettExpert

def test_warren_buffett_integration():
    """
    测试巴菲特专家节点通过 Gemini CLI Headless 模式的集成。
    """
    expert = WarrenBuffettExpert()
    
    # 模拟茅台在行情阴跌且有负面舆情时的上下文
    ticker = "600519.SH (贵州茅台)"
    technical_data = {
        "current_price": "1450.00 CNY",
        "trend_summary": "自 1700 元高点回落，目前处于半年均线下方，呈缩量阴跌态势。",
        "technical_indicators": "RSI(14) 接近 30，显示超卖；MACD 死叉已持续 5 个交易日。"
    }
    news_data = [
        {"date": "2026-04-01", "title": "部分机构下调白酒行业全年增长预期"},
        {"date": "2026-04-02", "title": "茅台集团：稳步推进高质量增长，品牌护城河稳固"},
        {"date": "2026-04-03", "title": "外资连续 3 日净流出白酒板块"}
    ]
    
    user_prompt = expert.prepare_prompt(ticker, technical_data, news_data)
    system_prompt = expert.SYSTEM_PROMPT
    
    print(f"--- 正在调用 Gemini CLI (Expert: {expert.get_expert_id()}) ---")
    
    # 模拟我们已有的 Headless 路由逻辑
    full_prompt = f"System: {system_prompt}\n\nUser: {user_prompt}"
    
    try:
        # 强制使用 -p 模式
        cmd = ["gemini", "-p", "请作为巴菲特，仅根据上下文输出 JSON 分析结果。"]
        result = subprocess.run(
            cmd,
            input=full_prompt,
            capture_output=True,
            text=True,
            encoding='utf-8',
            timeout=120
        )
        
        if result.returncode != 0:
            print(f"Error calling Gemini: {result.stderr}")
            return

        output = result.stdout.strip()
        print(f"Raw Output: {output}")
        
        # 清洗反引号逻辑
        if "```json" in output:
            output = output.split("```json")[1].split("```")[0].strip()
        elif "```" in output:
            output = output.split("```")[1].split("```")[0].strip()
            
        # 尝试解析 JSON
        data = json.loads(output)
        
        print("\n--- 专家分析结果 ---")
        print(f"Signal: {data.get('signal')}")
        print(f"Confidence: {data.get('confidence')}%")
        print(f"Reasoning: {data.get('reasoning')}")
        
        # 断言字段完整性
        assert "signal" in data
        assert "confidence" in data
        assert "reasoning" in data
        assert data["signal"] in ["bullish", "bearish", "neutral"]
        
        print("\n[SUCCESS] 阶段二：单一“大师”节点验证通过。")
        
    except Exception as e:
        print(f"Test failed: {str(e)}")

if __name__ == "__main__":
    test_warren_buffett_integration()
