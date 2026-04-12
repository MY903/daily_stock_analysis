import os
import sys
import unittest
import asyncio
from unittest.mock import MagicMock, patch

# 将 src 目录添加到路径
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.analyzer import GeminiAnalyzer, AnalysisResult
from src.config import Config

class TestEnsembleBackend(unittest.TestCase):
    def setUp(self):
        # 模拟配置，开启专家委员会路由
        self.config = MagicMock(spec=Config)
        self.config.litellm_model = "ensemble/gemini-2.0-flash"
        self.config.llm_model_list = []  # 添加此属性以防报错
        self.config.report_language = "zh"
        self.config.gemini_request_delay = 0
        self.config.report_integrity_enabled = False
        
        self.analyzer = GeminiAnalyzer(config=self.config)

    async def _mock_call_expert_async(self, expert_id, system_prompt, user_prompt):
        """模拟专家节点的异步返回"""
        if expert_id == "ray_dalio_consensus":
            return {
                "final_rating": "Strong Buy",
                "action_plan": "建议买入",
                "consensus_summary": "巴菲特、李录和琼斯在基本面和技术面上达成高度共识，均认可茅台深厚的品牌护城河、绝对定价权、充沛现金流以及当前强势的上升动能。",
                "divergence_analysis": "无明显分歧",
                "confidence": 85,
                "reasoning": "巴菲特、李录和琼斯在基本面和技术面上达成高度共识，均认可茅台深厚的品牌护城河、绝对定价权、充沛现金流以及当前强势的上升动能。",
                "trend_prediction": "Strong Buy",
                "operation_advice": "买入",
                "analysis_summary": "巴菲特、李录和琼斯在基本面和技术面上达成高度共识，均认可茅台深厚的品牌护城河、绝对定价权、充沛现金流以及当前强势的上升动能。"
            }
        return {
            "signal": "bullish",
            "confidence": 90,
            "reasoning": f"Expert {expert_id} is bullish on this high-quality stock."
        }

    def test_ensemble_pipeline_flow(self):
        """
        测试后端全量分析流水线：Data -> Analyzer(Ensemble) -> AnalysisResult
        """
        print("\n🚀 启动后端全量 Ensemble 流水线测试...")
        
        # 1. 构造模拟上下文（茅台案例）
        context = {
            "code": "600519.SH",
            "stock_name": "贵州茅台",
            "today": {
                "close": 1500.0,
                "open": 1480.0,
                "pct_chg": 1.5,
                "ma5": 1450.0,
                "ma10": 1420.0,
                "ma20": 1400.0
            },
            "ma_status": "均线多头排列",
            "trend_analysis": {
                "trend_status": "强势上涨"
            }
        }
        news_context = "2026-04-03: 茅台集团发布业绩快报，净利润超预期；白酒行业整体复苏趋势明显。"
        
        # 2. 使用 patch 模拟 _call_expert_async
        with patch.object(self.analyzer, '_call_expert_async', side_effect=self._mock_call_expert_async):
            # 执行分析 (由于是同步桥接异步，这会触发内部的 asyncio.run)
            result = self.analyzer.analyze(context, news_context)
            
            # 3. 验证结果
            print(f"✅ 分析成功！")
            print(f"最终评级: {result.trend_prediction}")
            print(f"操作建议: {result.operation_advice}")
            print(f"综合摘要: {result.analysis_summary}")
            
            self.assertIsInstance(result, AnalysisResult)
            self.assertTrue(result.success)
            self.assertIn("Buy", result.trend_prediction) # 预期在好消息下应该是看多
            
            # 4. 验证数据库记录
            db_path = "workspace/analyst_performance.db"
            self.assertTrue(os.path.exists(db_path), "数据库记录应已自动创建")
            
            import sqlite3
            with sqlite3.connect(db_path) as conn:
                count = conn.execute("SELECT COUNT(*) FROM track_record WHERE ticker='600519.SH'").fetchone()[0]
                print(f"📊 数据库中已产生 {count} 条专家预测记录")
                self.assertGreaterEqual(count, 5, "应该记录了 5 位专家的原始观点")

if __name__ == "__main__":
    unittest.main()
