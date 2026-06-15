from pydantic import BaseModel, Field
from enum import Enum
from uuid import uuid4
from datetime import datetime, timedelta
from typing import Optional


class SignalStatus(str, Enum):
    PENDING = "PENDING"       # 等待人工确认
    CONFIRMED = "CONFIRMED"   # 人工确认通过
    REJECTED = "REJECTED"     # 人工拒绝
    EXPIRED = "EXPIRED"       # 超时未确认
    EXECUTED = "EXECUTED"     # 已执行
    FAILED = "FAILED"         # 执行失败


class SignalSource(str, Enum):
    AI = "ai"         # AI 信号
    RULE = "rule"     # 技术规则信号
    HYBRID = "hybrid" # AI+规则混合


class SignalAction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class ConfirmAction(str, Enum):
    CONFIRM = "CONFIRM"
    REJECT = "REJECT"
    MODIFY = "MODIFY"


class Signal(BaseModel):
    signal_id: str = Field(default_factory=lambda: str(uuid4()))
    symbol: str
    action: SignalAction
    price_target: Optional[float] = None
    quantity: Optional[int] = None
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    rationale: str = ""
    source: SignalSource = SignalSource.AI
    created_at: datetime = Field(default_factory=datetime.now)
    expires_at: Optional[datetime] = None
    status: SignalStatus = SignalStatus.PENDING

    def __init__(self, **data):
        super().__init__(**data)
        if self.expires_at is None:
            self.expires_at = self.created_at + timedelta(minutes=30)

    def is_expired(self) -> bool:
        return datetime.now() > self.expires_at if self.expires_at else False

    def can_transition_to(self, new_status: SignalStatus) -> bool:
        VALID_TRANSITIONS = {
            SignalStatus.PENDING: [SignalStatus.CONFIRMED, SignalStatus.REJECTED, SignalStatus.EXPIRED],
            SignalStatus.CONFIRMED: [SignalStatus.EXECUTED, SignalStatus.FAILED],
            SignalStatus.REJECTED: [],
            SignalStatus.EXPIRED: [],
            SignalStatus.EXECUTED: [],
            SignalStatus.FAILED: [],
        }
        return new_status in VALID_TRANSITIONS.get(self.status, [])


class ConfirmResult(BaseModel):
    signal_id: str
    action: ConfirmAction
    modified_quantity: Optional[int] = None
    timestamp: datetime = Field(default_factory=datetime.now)
    user_id: str = "system"
