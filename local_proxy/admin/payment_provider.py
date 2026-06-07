from __future__ import annotations

import hashlib
import hmac
import time
from typing import Any


def _coerce_text(value: Any) -> str:
    return str(value or "").strip()


def build_order_provider_payload(*, provider: str, channel_config: dict, order: dict) -> dict:
    provider_name = _coerce_text(provider) or "manual"
    order_id = _coerce_text(order.get("id"))
    amount_cents = int(order.get("amount_cents") or 0)
    currency = _coerce_text(order.get("currency")) or "CNY"

    if provider_name == "wechat":
        return {
            "provider": "wechat",
            "mode": _coerce_text(channel_config.get("mode")) or "native",
            "merchant_id": _coerce_text(channel_config.get("merchant_id")),
            "notify_url": _coerce_text(channel_config.get("notify_url")),
            "out_trade_no": order_id,
            "amount": {"total": amount_cents, "currency": currency},
        }

    if provider_name == "alipay":
        return {
            "provider": "alipay",
            "app_id": _coerce_text(channel_config.get("app_id")),
            "notify_url": _coerce_text(channel_config.get("notify_url")),
            "out_trade_no": order_id,
            "total_amount": f"{amount_cents / 100:.2f}",
            "subject": _coerce_text(order.get("plan_name")) or order_id,
        }

    return {
        "provider": "manual",
        "mode": "manual",
        "out_trade_no": order_id,
        "amount": {"total": amount_cents, "currency": currency},
    }


def verify_provider_signature(*, provider: str, channel_config: dict, raw_signature: str, payload: dict) -> bool:
    provider_name = _coerce_text(provider) or "manual"
    if provider_name == "manual":
        return True

    secret = _coerce_text(channel_config.get("webhook_secret"))
    if not secret:
        return False

    message = (
        _coerce_text(payload.get("provider_order_id"))
        + "|"
        + _coerce_text(payload.get("status"))
        + "|"
        + _coerce_text(payload.get("event_id"))
    )
    expected = hmac.new(secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, raw_signature or "")


def normalize_webhook_payload(*, provider: str, order_id: str, payload: dict) -> dict:
    provider_name = _coerce_text(provider) or "manual"
    current_time = float(payload.get("paid_at") or time.time())

    normalized = {
        "provider": provider_name,
        "event_id": _coerce_text(payload.get("event_id")) or f"evt_{provider_name}_{order_id}_{_coerce_text(payload.get('provider_order_id')) or 'unknown'}",
        "provider_order_id": _coerce_text(payload.get("provider_order_id")) or order_id,
        "status": _coerce_text(payload.get("status")) or "paid",
        "paid_at": current_time,
    }

    if provider_name == "wechat":
        normalized["transaction_id"] = _coerce_text(payload.get("transaction_id"))
    elif provider_name == "alipay":
        normalized["trade_no"] = _coerce_text(payload.get("trade_no"))

    for key, value in payload.items():
        if key not in normalized:
            normalized[key] = value
    return normalized
