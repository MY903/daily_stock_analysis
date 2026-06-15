from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional
from src.trading.signal import Signal, ConfirmResult


class SignalStatusChange(BaseModel):
    from_status: str
    to_status: str
    timestamp: datetime = Field(default_factory=datetime.now)
    reason: str = ""


class AuditLogEntry(BaseModel):
    log_id: str = Field(default_factory=lambda: str(__import__('uuid').uuid4()))
    signal: Signal
    created_at: datetime = Field(default_factory=datetime.now)
    pushed_at: Optional[datetime] = None
    confirm_result: Optional[ConfirmResult] = None
    executed_at: Optional[datetime] = None
    execution_result: Optional[str] = None  # order_id, error message, etc.
    completed_at: Optional[datetime] = None
    status_changes: list[SignalStatusChange] = Field(default_factory=list)

    @property
    def is_complete(self) -> bool:
        return self.completed_at is not None

    @property
    def duration_seconds(self) -> Optional[float]:
        if self.created_at and self.completed_at:
            return (self.completed_at - self.created_at).total_seconds()
        return None
