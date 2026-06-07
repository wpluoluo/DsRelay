from __future__ import annotations

import time
import uuid

from local_proxy.admin.payment_provider import (
    build_order_provider_payload,
    normalize_webhook_payload,
    verify_provider_signature,
)
from local_proxy.platform import normalize_admin_payment_channel_payload, normalize_admin_payment_order_payload

from .base import ALLOWED_PAYMENT_ORDER_TRANSITIONS, AdminServiceBase, coerce_text, safe_int


class AdminPaymentsMixin(AdminServiceBase):
    def _record_payment_fulfillment_log(
        self,
        *,
        order_id: str,
        action: str,
        payload: dict,
        subscription_id: str = "",
        actor_type: str = "admin",
        actor_id: str = "",
        note_text: str = "",
    ) -> None:
        if self.storage is None:
            return
        self.storage.record_payment_fulfillment_log(
            {
                "id": f"pfl_{uuid.uuid4().hex[:16]}",
                "order_id": order_id,
                "subscription_id": subscription_id,
                "action": action,
                "actor_type": actor_type,
                "actor_id": actor_id,
                "note_text": note_text,
                "payload": payload if isinstance(payload, dict) else {},
            }
        )

    def list_payment_channels(self) -> dict:
        if self.storage is None:
            return {"ok": True, "items": [], "total": 0}
        items = self.storage.list_admin_payment_channels()
        return {"ok": True, "items": items, "total": len(items)}

    def upsert_payment_channel(self, payload: dict) -> dict:
        if self.storage is None:
            raise RuntimeError("storage not configured")
        allowed_group_ids = payload.get("allowed_group_ids") if isinstance(payload.get("allowed_group_ids"), list) else []
        if allowed_group_ids:
            self._validate_group_set([coerce_text(item) for item in allowed_group_ids])
        item = normalize_admin_payment_channel_payload(
            {
                **payload,
                "id": coerce_text(payload.get("id")) or f"channel_{uuid.uuid4().hex[:16]}",
            }
        )
        if not item["name"]:
            raise ValueError("channel name is required")
        return {"ok": True, "item": self.storage.upsert_admin_payment_channel(item)}

    def payment_channel_config_template(self, provider: str) -> dict:
        provider_name = coerce_text(provider) or "manual"
        if provider_name == "wechat":
            return {
                "mode": "native",
                "merchant_id": "",
                "app_id": "",
                "notify_url": "",
                "webhook_secret": "",
            }
        if provider_name == "alipay":
            return {
                "app_id": "",
                "notify_url": "",
                "webhook_secret": "",
                "return_url": "",
            }
        return {"mode": "manual", "notify_url": ""}

    def list_payment_orders(self) -> dict:
        if self.storage is None:
            return {"ok": True, "items": [], "total": 0}
        plans = {str(item.get("id") or ""): item for item in self.list_subscription_plans().get("items", [])}
        accounts = {str(item.get("id") or ""): item for item in self.list_accounts(limit=5000).get("items", [])}
        channels = {str(item.get("id") or ""): item for item in self.list_payment_channels().get("items", [])}
        items = []
        for row in self.storage.list_admin_payment_orders():
            storage_account_id = coerce_text(row.get("user_id"))
            payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
            items.append(
                {
                    **row,
                    "account_id": storage_account_id,
                    "account_name": coerce_text(accounts.get(storage_account_id, {}).get("name")) or storage_account_id,
                    "plan_name": coerce_text(plans.get(str(row.get("plan_id") or ""), {}).get("name")) or coerce_text(row.get("plan_id")),
                    "channel_name": coerce_text(channels.get(str(row.get("channel_id") or ""), {}).get("name")) or coerce_text(row.get("channel_id")),
                    "rate_multiplier": payload.get("rate_multiplier"),
                    "base_price_cents": payload.get("base_price_cents"),
                    "final_price_cents": payload.get("final_price_cents"),
                    "fulfillment_logs": self.storage.list_payment_fulfillment_logs(coerce_text(row.get("id"))),
                }
            )
        return {"ok": True, "items": items, "total": len(items)}

    def create_payment_order(self, payload: dict) -> dict:
        if self.storage is None:
            raise RuntimeError("storage not configured")
        account_id = coerce_text(payload.get("account_id")) or coerce_text(payload.get("user_id"))
        plan_id = coerce_text(payload.get("plan_id"))
        channel_id = coerce_text(payload.get("channel_id"))
        amount_cents = safe_int(payload.get("amount_cents"))
        if not account_id or not plan_id:
            raise ValueError("account_id and plan_id are required")
        account = self.storage.get_admin_user(account_id)
        if not account:
            raise ValueError("account not found")
        self._validate_account_active(account)
        plan = next((item for item in self.storage.list_admin_subscription_plans() if coerce_text(item.get("id")) == plan_id), None)
        if not plan:
            raise ValueError("subscription plan not found")
        resolved_group_id = self._resolve_plan_group_id(plan, payload)
        group = self._group_record(resolved_group_id)
        if resolved_group_id:
            self._validate_group_set([resolved_group_id])
            self._validate_account_allowed_groups(account, [resolved_group_id])
        resolved_amount_cents, applied_multiplier = self._resolve_plan_amount_cents(plan, resolved_group_id)
        if amount_cents <= 0:
            amount_cents = resolved_amount_cents
        order_payload = payload.get("payload") if isinstance(payload.get("payload"), dict) else {}
        order_payload = {
            **order_payload,
            "group_id": resolved_group_id,
            "base_price_cents": max(0, safe_int(plan.get("price_cents"))),
            "rate_multiplier": applied_multiplier,
            "final_price_cents": amount_cents,
        }
        item = normalize_admin_payment_order_payload({
            "id": f"order_{uuid.uuid4().hex[:16]}",
            "account_id": account_id,
            "plan_id": plan_id,
            "subscription_id": "",
            "channel_id": channel_id,
            "amount_cents": amount_cents,
            "currency": coerce_text(payload.get("currency")) or "CNY",
            "status": "pending",
            "provider_order_id": "",
            "resume_token": f"resume_{uuid.uuid4().hex[:16]}",
            "payload": order_payload,
            "provider_payload": {},
            "paid_at": None,
        })
        saved = self.storage.upsert_admin_payment_order(item)
        channel = {}
        if channel_id:
            channel = next((entry for entry in self.list_payment_channels().get("items", []) if coerce_text(entry.get("id")) == channel_id), {})
            self._validate_payment_channel_scope(
                channel,
                group_id=resolved_group_id,
                protocol=coerce_text(payload.get("protocol")),
                platform=coerce_text(group.get("platform")),
            )
        provider = coerce_text(channel.get("provider")) or "manual"
        channel_config = channel.get("config") if isinstance(channel.get("config"), dict) else {}
        provider_payload = build_order_provider_payload(provider=provider, channel_config=channel_config, order=saved)
        saved["provider"] = provider
        saved["provider_payload"] = provider_payload
        saved = self.storage.upsert_admin_payment_order(saved)
        return {"ok": True, "item": saved}

    def update_payment_order_status(self, order_id: str, payload: dict) -> dict:
        if self.storage is None:
            raise RuntimeError("storage not configured")
        current = self.storage.get_admin_payment_order(order_id)
        if not current:
            raise ValueError("payment order not found")
        target_status = coerce_text(payload.get("status"))
        if not target_status:
            raise ValueError("status is required")
        if target_status == "paid":
            return self.fulfill_payment_order(order_id, payload)
        current_status = coerce_text(current.get("status")) or "pending"
        if target_status == current_status:
            return {"ok": True, "item": current}
        allowed = ALLOWED_PAYMENT_ORDER_TRANSITIONS.get(current_status, set())
        if target_status not in allowed:
            raise ValueError(f"invalid payment status transition: {current_status} -> {target_status}")
        current["status"] = target_status
        current["provider_order_id"] = coerce_text(payload.get("provider_order_id")) or coerce_text(current.get("provider_order_id"))
        current["payload"] = {
            **(current.get("payload") if isinstance(current.get("payload"), dict) else {}),
            **(payload if isinstance(payload, dict) else {}),
        }
        saved = self.storage.upsert_admin_payment_order(current)
        self._record_payment_fulfillment_log(
            order_id=order_id,
            action=f"order_status_{target_status}",
            payload=payload,
            note_text=f"payment order moved to {target_status}",
        )
        return {"ok": True, "item": saved}

    def fulfill_payment_order(self, order_id: str, payload: dict) -> dict:
        if self.storage is None:
            raise RuntimeError("storage not configured")
        current = self.storage.get_admin_payment_order(order_id)
        if not current:
            raise ValueError("payment order not found")
        current_status = coerce_text(current.get("status")) or "pending"
        target_status = coerce_text(payload.get("status")) or "paid"
        allowed = ALLOWED_PAYMENT_ORDER_TRANSITIONS.get(current_status, set())
        if target_status == current_status:
            return {"ok": True, "item": current}
        if target_status not in allowed:
            raise ValueError(f"invalid payment status transition: {current_status} -> {target_status}")

        if target_status != "paid":
            current["status"] = target_status
            current["payload"] = {
                **(current.get("payload") if isinstance(current.get("payload"), dict) else {}),
                **(payload if isinstance(payload, dict) else {}),
            }
            saved = self.storage.upsert_admin_payment_order(current)
            return {"ok": True, "item": saved}

        plan_id = coerce_text(current.get("plan_id"))
        plan = next((item for item in self.list_subscription_plans().get("items", []) if coerce_text(item.get("id")) == plan_id), None)
        if not plan:
            raise ValueError("subscription plan not found")
        account = self.storage.get_admin_user(coerce_text(current.get("user_id")))
        if not account:
            raise ValueError("account not found")
        resolved_group_id = self._resolve_plan_group_id(plan, current)
        if resolved_group_id:
            self._validate_group_set([resolved_group_id])
            self._validate_account_allowed_groups(account, [resolved_group_id])

        now = payload.get("paid_at") or time.time()
        expires_at = float(now) + max(1, safe_int(plan.get("validity_days") or 30)) * 86400
        subscription = self.storage.upsert_admin_user_subscription(
            {
                "id": coerce_text(current.get("subscription_id")) or f"sub_{uuid.uuid4().hex[:16]}",
                "user_id": coerce_text(current.get("user_id")),
                "plan_id": plan_id,
                "group_id": resolved_group_id,
                "status": "active",
                "started_at": now,
                "expires_at": expires_at,
                "daily_used": 0,
                "weekly_used": 0,
                "monthly_used": 0,
            }
        )
        current["subscription_id"] = coerce_text(subscription.get("id"))
        current["status"] = "paid"
        current["provider_order_id"] = coerce_text(payload.get("provider_order_id")) or coerce_text(current.get("provider_order_id"))
        current["paid_at"] = now
        current["payload"] = {
            **(current.get("payload") if isinstance(current.get("payload"), dict) else {}),
            **(payload if isinstance(payload, dict) else {}),
        }
        saved = self.storage.upsert_admin_payment_order(current)
        self._record_payment_fulfillment_log(
            order_id=order_id,
            subscription_id=coerce_text(subscription.get("id")),
            action="payment_fulfilled",
            payload=payload,
            note_text="payment order fulfilled and subscription activated",
        )
        return {"ok": True, "item": saved, "subscription": subscription}

    def process_payment_webhook(self, order_id: str, payload: dict, signature: str = "") -> dict:
        if self.storage is None:
            raise RuntimeError("storage not configured")
        order = self.storage.get_admin_payment_order(order_id)
        if not order:
            raise ValueError("payment order not found")
        channel = {}
        channel_id = coerce_text(order.get("channel_id"))
        if channel_id:
            channel = next((item for item in self.list_payment_channels().get("items", []) if coerce_text(item.get("id")) == channel_id), {})
        provider = coerce_text(payload.get("provider")) or coerce_text(channel.get("provider")) or "manual"
        channel_config = channel.get("config") if isinstance(channel.get("config"), dict) else {}
        normalized_payload = normalize_webhook_payload(
            provider=provider,
            order_id=order_id,
            payload=payload if isinstance(payload, dict) else {},
        )
        event_id = coerce_text(normalized_payload.get("event_id"))
        if not event_id:
            raise ValueError("webhook event_id is required")

        existing_event = self.storage.get_payment_webhook_event(event_id)
        if existing_event.get("processed"):
            return {"ok": True, "duplicate": True, "item": order}

        if not verify_provider_signature(
            provider=provider,
            channel_config=channel_config,
            raw_signature=signature,
            payload=normalized_payload,
        ):
            raise ValueError("invalid payment webhook signature")

        self.storage.record_payment_webhook_event(
            {
                "event_id": event_id,
                "order_id": order_id,
                "provider": provider,
                "signature": signature,
                "payload": normalized_payload,
                "processed": False,
            }
        )
        result = self.fulfill_payment_order(order_id, normalized_payload)
        self.storage.record_payment_webhook_event(
            {
                "event_id": event_id,
                "order_id": order_id,
                "provider": provider,
                "signature": signature,
                "payload": normalized_payload,
                "processed": True,
            }
        )
        return result
