import sqlite3
import os
from datetime import datetime
from typing import Dict, List, Any

class PerformanceTracker:
    """
    专家战绩追踪器：负责持久化大师们的预测结果，并计算动态权重。
    """
    def __init__(self, db_path: str = "workspace/analyst_performance.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS track_record (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    analyst_id TEXT,
                    ticker TEXT,
                    prediction_date TEXT,
                    signal TEXT,
                    confidence INTEGER,
                    actual_return_5d REAL,
                    is_correct INTEGER DEFAULT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    def record_prediction(self, analyst_id: str, ticker: str, signal: str, confidence: int):
        """
        记录一次专家的预测。
        """
        date_str = datetime.now().strftime("%Y-%m-%d")
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO track_record (analyst_id, ticker, prediction_date, signal, confidence)
                VALUES (?, ?, ?, ?, ?)
            """, (analyst_id, ticker, date_str, signal, confidence))
            conn.commit()

    def get_analyst_weights(self, lookback_days: int = 30) -> Dict[str, float]:
        """
        计算各大师的动态权重。
        算法：Weight = Base_Weight * (Accuracy ^ 1.5)
        如果没有历史战绩，默认返回 1.0。
        """
        weights = {}
        analysts = ["warren_buffett", "li_lu", "paul_tudor_jones", "jensen_huang", "nassim_taleb"]
        
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            for aid in analysts:
                # 获取最近 N 场已结算的战绩
                cursor.execute("""
                    SELECT is_correct FROM track_record 
                    WHERE analyst_id = ? AND is_correct IS NOT NULL
                    ORDER BY created_at DESC LIMIT 20
                """, (aid,))
                records = cursor.fetchall()
                
                if not records:
                    weights[aid] = 0.5 # 初始保守权重
                    continue
                
                correct_count = sum(1 for r in records if r[0] == 1)
                accuracy = correct_count / len(records)
                
                # 权重 = (胜率 + 0.1) ^ 1.5，保证即使胜率为 0 也有微弱存在感
                weights[aid] = round((accuracy + 0.1) ** 1.5, 2)
                
        return weights

    def get_analyst_performance(self) -> List[Dict[str, Any]]:
        """
        获取大师们的详细战绩统计。
        """
        performance = []
        analysts = {
            "warren_buffett": "巴菲特",
            "li_lu": "李录",
            "paul_tudor_jones": "保罗·都铎·琼斯",
            "jensen_huang": "黄仁勋",
            "nassim_taleb": "塔勒布"
        }
        
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            for aid, name in analysts.items():
                # 总预测数
                cursor.execute("SELECT COUNT(*) FROM track_record WHERE analyst_id = ?", (aid,))
                total = cursor.fetchone()[0]
                
                # 已结算数
                cursor.execute("SELECT COUNT(*) FROM track_record WHERE analyst_id = ? AND is_correct IS NOT NULL", (aid,))
                settled = cursor.fetchone()[0]
                
                # 胜场数
                cursor.execute("SELECT COUNT(*) FROM track_record WHERE analyst_id = ? AND is_correct = 1", (aid,))
                wins = cursor.fetchone()[0]
                
                accuracy = (wins / settled) if settled > 0 else 0.5
                
                performance.append({
                    "id": aid,
                    "name": name,
                    "total_predictions": total,
                    "win_rate": round(accuracy * 100, 1),
                    "win_count": wins,
                    "settled_count": settled
                })
        
        # 按胜率排序
        performance.sort(key=lambda x: x["win_rate"], reverse=True)
        return performance

    def backfill_result(self, record_id: int, actual_return: float):
        """
        回填 5 天后的实际表现并判定胜负。
        判定逻辑：
        - signal=bullish 且 return > 1% -> 1 (Correct)
        - signal=bearish 且 return < -1% -> 1 (Correct)
        - 其他 -> 0 (Wrong)
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT signal FROM track_record WHERE id = ?", (record_id,))
            row = cursor.fetchone()
            if not row: return
            
            signal = row[0]
            is_correct = 0
            if signal == "bullish" and actual_return > 0.01:
                is_correct = 1
            elif signal == "bearish" and actual_return < -0.01:
                is_correct = 1
            elif signal == "neutral" and abs(actual_return) < 0.02:
                is_correct = 1
                
            cursor.execute("""
                UPDATE track_record 
                SET actual_return_5d = ?, is_correct = ? 
                WHERE id = ?
            """, (actual_return, is_correct, record_id))
            conn.commit()
