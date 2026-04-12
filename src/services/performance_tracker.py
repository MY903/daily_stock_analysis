import sqlite3
import os
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any

logger = logging.getLogger(__name__)

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

    def record_prediction(self, analyst_id: str, ticker: str, signal: str, confidence: int) -> int:
        """
        记录一次专家的预测，返回新插入记录的 row ID。
        """
        date_str = datetime.now().strftime("%Y-%m-%d")
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO track_record (analyst_id, ticker, prediction_date, signal, confidence)
                VALUES (?, ?, ?, ?, ?)
            """, (analyst_id, ticker, date_str, signal, confidence))
            conn.commit()
            return cursor.lastrowid

    def get_analyst_weights(self, lookback_days: int = 30) -> Dict[str, float]:
        """
        计算各大师的动态权重，并进行归一化处理。
        算法：raw_weight = (accuracy + 0.1) ^ 1.5，归一化后所有权重之和为 1.0。
        如果没有历史战绩，使用等权基准值（1.0）参与归一化，确保新专家不被惩罚。
        """
        raw_weights = {}
        analysts = ["warren_buffett", "li_lu", "paul_tudor_jones", "jensen_huang", "nassim_taleb"]

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cutoff = (datetime.utcnow() - timedelta(days=lookback_days)).strftime("%Y-%m-%d %H:%M:%S")
            for aid in analysts:
                # 获取 lookback_days 内最近 20 场已结算的战绩
                cursor.execute("""
                    SELECT is_correct FROM track_record
                    WHERE analyst_id = ? AND is_correct IS NOT NULL
                      AND created_at >= ?
                    ORDER BY created_at DESC LIMIT 20
                """, (aid, cutoff))
                records = cursor.fetchall()

                if not records:
                    # 新专家无历史：赋予等权基准，不做惩罚
                    raw_weights[aid] = 1.0
                    logger.debug(f"[Weights] {aid}: no history, using baseline 1.0")
                    continue

                correct_count = sum(1 for r in records if r[0] == 1)
                accuracy = correct_count / len(records)
                # 权重 = (胜率 + 0.1) ^ 1.5，保证即使胜率为 0 也有微弱存在感
                raw_weights[aid] = (accuracy + 0.1) ** 1.5
                logger.debug(f"[Weights] {aid}: accuracy={accuracy:.2f}, raw={raw_weights[aid]:.4f}")

        # 归一化：所有权重之和为 1.0
        total = sum(raw_weights.values())
        weights = {aid: round(w / total, 4) for aid, w in raw_weights.items()}
        logger.info(f"[Weights] 归一化后权重: {weights}")
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
        回填 5 天后的实际表现并判定胜负（幂等：已结算记录不会被重复更新）。
        判定逻辑：
        - signal=bullish 且 return > 1% -> 1 (Correct)
        - signal=bearish 且 return < -1% -> 1 (Correct)
        - signal=neutral 且 |return| < 2% -> 1 (Correct)
        - 其他 -> 0 (Wrong)
        """
        with sqlite3.connect(self.db_path, isolation_level='IMMEDIATE') as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT signal FROM track_record WHERE id = ? AND is_correct IS NULL", (record_id,))
            row = cursor.fetchone()
            if not row:
                logger.debug(f"[Backfill] record {record_id} already settled or not found, skipping")
                return

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
                WHERE id = ? AND is_correct IS NULL
            """, (actual_return, is_correct, record_id))
            conn.commit()
            logger.info(f"[Backfill] record {record_id}: signal={signal}, return={actual_return:.4f}, correct={is_correct}")
