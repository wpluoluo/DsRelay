from __future__ import annotations

from dataclasses import asdict
from typing import Any

from .models import (
    AdminGroupRecord,
    AdminPaymentChannelRecord,
    AdminPaymentOrderRecord,
    AdminUserRecord,
    PaymentStatus,
    UserRole,
    UserSourceType,
    UserStatus,
)


def _text(value: Any, *, default: str = "") -> str:
    return str(value or default).strip()


def _int(value: Any, *, default: int = 0) -> int:
    try:
        return int(value if value is not None else default)
    except Exception:
        return default


def _float(value: Any, *, default: float = 0.0) -> float:
    try:
        return float(value if value is not None else default)
    except Exception:
        return default


def normalize_admin_user_payload(payload: dict[str, Any]) -> dict[str, Any]:
    source_type = _text(payload.get("source_type"), default=UserSourceType.MANAGED)
    if source_type not in {item.value for item in UserSourceType}:
        source_type = UserSourceType.MANAGED
    role = _text(payload.get("role"), default=UserRole.USER)
    if role not in {item.value for item in UserRole}:
        role = UserRole.USER
    status = _text(payload.get("status"), default=UserStatus.ACTIVE)
    if status not in {item.value for item in UserStatus}:
        status = UserStatus.ACTIVE
    allowed_group_ids = payload.get("allowed_group_ids") if isinstance(payload.get("allowed_group_ids"), list) else []
    extra = payload.get("extra") if isinstance(payload.get("extra"), dict) else {}
    record = AdminUserRecord(
        id=_text(payload.get("id")),
        name=_text(payload.get("name")),
        external_key=_text(payload.get("external_key")),
        source_type=source_type,
        role=role,
        status=status,
        balance_cents=max(0, _int(payload.get("balance_cents"))),
        concurrency_limit=max(0, _int(payload.get("concurrency_limit"))),
        allowed_group_ids=[_text(item) for item in allowed_group_ids if _text(item)],
        extra=extra,
        enabled=payload.get("enabled") is not False,
        note=_text(payload.get("note")),
    )
    return asdict(record)


def normalize_admin_group_payload(payload: dict[str, Any]) -> dict[str, Any]:
    extra = payload.get("extra") if isinstance(payload.get("extra"), dict) else {}
    record = AdminGroupRecord(
        id=_text(payload.get("id")),
        name=_text(payload.get("name")),
        description=_text(payload.get("description")),
        platform=_text(payload.get("platform")),
        is_exclusive=payload.get("is_exclusive") is True,
        rate_multiplier=max(0.0, _float(payload.get("rate_multiplier"), default=1.0)),
        extra=extra,
        enabled=payload.get("enabled") is not False,
        sort_order=_int(payload.get("sort_order")),
    )
    return asdict(record)


def normalize_admin_payment_channel_payload(payload: dict[str, Any]) -> dict[str, Any]:
    config = payload.get("config") if isinstance(payload.get("config"), dict) else {}
    allowed_group_ids = payload.get("allowed_group_ids") if isinstance(payload.get("allowed_group_ids"), list) else []
    allowed_protocols = payload.get("allowed_protocols") if isinstance(payload.get("allowed_protocols"), list) else []
    allowed_platforms = payload.get("allowed_platforms") if isinstance(payload.get("allowed_platforms"), list) else []
    record = AdminPaymentChannelRecord(
        id=_text(payload.get("id")),
        name=_text(payload.get("name")),
        provider=_text(payload.get("provider"), default="manual") or "manual",
        config={
            **config,
            "allowed_group_ids": [_text(item) for item in allowed_group_ids if _text(item)],
            "allowed_protocols": [_text(item) for item in allowed_protocols if _text(item)],
            "allowed_platforms": [_text(item) for item in allowed_platforms if _text(item)],
        },
        enabled=payload.get("enabled") is not False,
    )
    return asdict(record)


def normalize_admin_payment_order_payload(payload: dict[str, Any]) -> dict[str, Any]:
    status = _text(payload.get("status"), default=PaymentStatus.PENDING)
    if status not in {item.value for item in PaymentStatus}:
        status = PaymentStatus.PENDING
    record = AdminPaymentOrderRecord(
        id=_text(payload.get("id")),
        user_id=_text(payload.get("user_id")),
        plan_id=_text(payload.get("plan_id")),
        status=status,
        channel_id=_text(payload.get("channel_id")),
        subscription_id=_text(payload.get("subscription_id")),
        amount_cents=max(0, _int(payload.get("amount_cents"))),
        currency=_text(payload.get("currency"), default="CNY") or "CNY",
        provider_order_id=_text(payload.get("provider_order_id")),
        resume_token=_text(payload.get("resume_token")),
        payload=payload.get("payload") if isinstance(payload.get("payload"), dict) else {},
        provider_payload=payload.get("provider_payload") if isinstance(payload.get("provider_payload"), dict) else {},
    )
    return asdict(record)
