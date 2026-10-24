from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Status(str, Enum):
    CREATED = "created"
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELED = "canceled"
    PARTIALLY_REFUNDED = "partially_refunded"
    REFUNDED = "refunded"


@dataclass
class Attempt:
    id: str
    provider: str
    status: str = "pending"
    error_code: Optional[str] = None
    latency_ms: int = 0
    provider_ref: Optional[str] = None
    created: str = ""

    def to_dict(self):
        return {
            "id": self.id,
            "provider": self.provider,
            "status": self.status,
            "error_code": self.error_code,
            "latency_ms": self.latency_ms,
            "created": self.created,
        }


@dataclass
class Intent:
    id: str
    amount: int
    currency: str
    method: str
    idempotency_key: str
    status: Status = Status.CREATED
    metadata: dict = field(default_factory=dict)
    attempts: list = field(default_factory=list)
    amount_refunded: int = 0
    provider: Optional[str] = None
    provider_ref: Optional[str] = None
    failure_code: Optional[str] = None
    routing_hint: Optional[str] = None
    created: str = ""

    def to_dict(self):
        return {
            "id": self.id,
            "status": self.status.value,
            "amount": self.amount,
            "amount_refunded": self.amount_refunded,
            "currency": self.currency,
            "method": self.method,
            "next_action": None,
            "attempts": [a.to_dict() for a in self.attempts],
            "metadata": self.metadata,
            "created": self.created,
        }


@dataclass
class Refund:
    id: str
    payment_intent_id: str
    amount: int
    status: str
    created: str = ""

    def to_dict(self):
        return {
            "id": self.id,
            "payment_intent_id": self.payment_intent_id,
            "amount": self.amount,
            "status": self.status,
            "created": self.created,
        }
