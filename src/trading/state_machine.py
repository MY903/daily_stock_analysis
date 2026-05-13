"""交易状态机

管理交易机器人的 5 个状态：IDLE / BUY_PENDING / HOLDING / SELL_PENDING / COOLDOWN
支持状态持久化，进程重启后可恢复。
"""

import json
import logging
import time
from enum import Enum
from pathlib import Path
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class TradingState(Enum):
    """交易状态枚举"""
    IDLE = "IDLE"                    # 空仓，等待买入信号
    BUY_PENDING = "BUY_PENDING"      # 买入单已提交，等待成交
    HOLDING = "HOLDING"              # 持仓中，监控止盈/止损
    SELL_PENDING = "SELL_PENDING"    # 卖出单已提交，等待成交
    COOLDOWN = "COOLDOWN"            # 冷却期


class StateMachine:
    """交易状态机

    状态转换图:
        IDLE → BUY_PENDING → HOLDING → SELL_PENDING → COOLDOWN → IDLE
    """

    def __init__(self, data_dir: str = "./data"):
        self._state = TradingState.IDLE
        self._data_dir = Path(data_dir)
        self._state_file = self._data_dir / "trading_state.json"
        self._context: Dict[str, Any] = {}
        self._cooldown_start: float = 0
        self._cooldown_duration: int = 300

        # 确保数据目录存在
        self._data_dir.mkdir(parents=True, exist_ok=True)

    @property
    def state(self) -> TradingState:
        return self._state

    @property
    def context(self) -> Dict[str, Any]:
        return self._context

    def set_cooldown_duration(self, seconds: int) -> None:
        """设置冷却时长"""
        self._cooldown_duration = seconds

    def transition_to_buy_pending(self, order_id: int, price: float,
                                   quantity: int) -> None:
        """IDLE → BUY_PENDING"""
        if self._state != TradingState.IDLE:
            logger.warning("非法状态转换: %s → BUY_PENDING", self._state.value)
            return

        self._state = TradingState.BUY_PENDING
        self._context = {
            "buy_order_id": order_id,
            "entry_price": price,
            "quantity": quantity,
            "buy_time": time.time(),
        }
        self._persist()
        logger.info("状态转换: IDLE → BUY_PENDING (order_id=%d, price=%.2f)",
                    order_id, price)

    def transition_to_holding(self, fill_price: float) -> None:
        """BUY_PENDING → HOLDING"""
        if self._state != TradingState.BUY_PENDING:
            logger.warning("非法状态转换: %s → HOLDING", self._state.value)
            return

        self._state = TradingState.HOLDING
        self._context["fill_price"] = fill_price
        self._context["hold_start"] = time.time()
        self._persist()
        logger.info("状态转换: BUY_PENDING → HOLDING (fill_price=%.2f)", fill_price)

    def transition_to_sell_pending(self, order_id: int, sell_type: str,
                                    target_price: float) -> None:
        """HOLDING → SELL_PENDING

        Args:
            sell_type: "take_profit" 或 "stop_loss"
        """
        if self._state != TradingState.HOLDING:
            logger.warning("非法状态转换: %s → SELL_PENDING", self._state.value)
            return

        self._state = TradingState.SELL_PENDING
        self._context["sell_order_id"] = order_id
        self._context["sell_type"] = sell_type
        self._context["target_price"] = target_price
        self._context["sell_time"] = time.time()
        self._persist()
        logger.info("状态转换: HOLDING → SELL_PENDING (type=%s, order_id=%d)",
                    sell_type, order_id)

    def transition_to_cooldown(self, fill_price: float) -> None:
        """SELL_PENDING → COOLDOWN"""
        if self._state != TradingState.SELL_PENDING:
            logger.warning("非法状态转换: %s → COOLDOWN", self._state.value)
            return

        self._state = TradingState.COOLDOWN
        self._cooldown_start = time.time()
        self._context["sell_fill_price"] = fill_price
        self._context["cooldown_start"] = self._cooldown_start

        # 计算盈亏
        entry = self._context.get("fill_price", 0)
        qty = self._context.get("quantity", 0)
        if entry and qty:
            pnl = (fill_price - entry) * qty
            pnl_pct = (fill_price - entry) / entry * 100
            self._context["pnl"] = round(pnl, 2)
            self._context["pnl_pct"] = round(pnl_pct, 2)

        self._persist()
        logger.info("状态转换: SELL_PENDING → COOLDOWN (fill=%.2f, pnl=%.2f)",
                    fill_price, self._context.get("pnl", 0))

    def transition_to_idle(self) -> None:
        """COOLDOWN → IDLE（冷却期结束）"""
        if self._state != TradingState.COOLDOWN:
            logger.warning("非法状态转换: %s → IDLE", self._state.value)
            return

        self._state = TradingState.IDLE
        self._context = {}
        self._persist()
        logger.info("状态转换: COOLDOWN → IDLE")

    def force_idle(self, reason: str = "") -> None:
        """强制重置为 IDLE（异常恢复用）"""
        old_state = self._state
        self._state = TradingState.IDLE
        self._context = {}
        self._persist()
        logger.warning("强制重置状态: %s → IDLE (原因: %s)", old_state.value, reason)

    def is_cooldown_expired(self) -> bool:
        """检查冷却期是否已结束"""
        if self._state != TradingState.COOLDOWN:
            return False
        elapsed = time.time() - self._cooldown_start
        return elapsed >= self._cooldown_duration

    def get_cooldown_remaining(self) -> int:
        """获取冷却期剩余时间（秒）"""
        if self._state != TradingState.COOLDOWN:
            return 0
        elapsed = time.time() - self._cooldown_start
        remaining = self._cooldown_duration - elapsed
        return max(0, int(remaining))

    # ==================== 持久化 ====================

    def _persist(self) -> None:
        """将状态持久化到文件"""
        data = {
            "state": self._state.value,
            "context": self._context,
            "cooldown_start": self._cooldown_start,
            "cooldown_duration": self._cooldown_duration,
            "updated_at": time.time(),
        }
        try:
            with open(self._state_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error("状态持久化失败: %s", e)

    def restore(self) -> bool:
        """从文件恢复状态

        Returns:
            是否成功恢复
        """
        if not self._state_file.exists():
            logger.info("无持久化状态文件，从 IDLE 开始")
            return False

        try:
            with open(self._state_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            self._state = TradingState(data["state"])
            self._context = data.get("context", {})
            self._cooldown_start = data.get("cooldown_start", 0)
            self._cooldown_duration = data.get("cooldown_duration", 300)

            logger.info("状态已恢复: state=%s, context=%s",
                        self._state.value, self._context)
            return True
        except Exception as e:
            logger.error("状态恢复失败: %s, 将从 IDLE 开始", e)
            self._state = TradingState.IDLE
            self._context = {}
            return False

    def to_dict(self) -> Dict[str, Any]:
        """导出当前状态为字典（用于通知和日志）"""
        return {
            "state": self._state.value,
            "context": self._context,
            "cooldown_remaining": self.get_cooldown_remaining(),
        }
