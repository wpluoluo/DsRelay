from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class UserSourceType(StrEnum):
    MANAGED = "managed"
    ENV = "env"
    ANONYMOUS = "anonymous"


class UserRole(StrEnum):
    USER = "user"
    ADMIN = "admin"


class UserStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"


class PaymentStatus(StrEnum):
    PENDING = "pending"
    PAID = "paid"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(slots=True)
class AdminUserRecord:
    id: str
    name: str
    external_key: str
    source_type: str = UserSourceType.MANAGED
    role: str = UserRole.USER
    status: str = UserStatus.ACTIVE
    balance_cents: int = 0
    concurrency_limit: int = 0
    allowed_group_ids: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    note: str = ""


@dataclass(slots=True)
class AdminGroupRecord:
    id: str
    name: str
    description: str = ""
    platform: str = ""
    is_exclusive: bool = False
    rate_multiplier: float = 1.0
    extra: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    sort_order: int = 0


@dataclass(slots=True)
class AdminPaymentChannelRecord:
    id: str
    name: str
    provider: str
    config: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True


@dataclass(slots=True)
class AdminPaymentOrderRecord:
    id: str
    user_id: str
    plan_id: str
    status: str = PaymentStatus.PENDING
    channel_id: str = ""
    subscription_id: str = ""
    amount_cents: int = 0
    currency: str = "CNY"
    provider_order_id: str = ""
    resume_token: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    provider_payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AdminProtocolProfile:
    key: str
    label: str
    supports_tools: bool
    supports_stream: bool
    supports_system_prompt: bool
    supports_images: bool
