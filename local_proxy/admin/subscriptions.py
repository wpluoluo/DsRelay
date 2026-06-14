from __future__ import annotations

import uuid

from .base import AdminServiceBase, coerce_text, safe_int


class AdminSubscriptionsMixin(AdminServiceBase):
    def list_subscription_plans(self) -> dict:
        if self.storage is None:
            return {"ok": True, "items": [], "total": 0}
        groups = {str(item.get("id") or ""): item for item in self.list_groups().get("items", [])}
        items = []
        for item in self.storage.list_admin_subscription_plans():
            group_id = coerce_text(item.get("group_id"))
            group = groups.get(group_id, {})
            final_price_cents, applied_multiplier = self._resolve_plan_amount_cents(item, group_id)
            items.append(
                {
                    **item,
                    "group_name": coerce_text(group.get("name")),
                    "rate_multiplier": applied_multiplier,
                    "final_price_cents": final_price_cents,
                }
            )
        return {"ok": True, "items": items, "total": len(items)}

    def upsert_subscription_plan(self, payload: dict) -> dict:
        if self.storage is None:
            raise RuntimeError("storage not configured")
        group_id = coerce_text(payload.get("group_id"))
        if group_id:
            self._validate_group_set([group_id])
        item = {
            "id": coerce_text(payload.get("id")) or f"plan_{uuid.uuid4().hex[:16]}",
            "name": coerce_text(payload.get("name")),
            "group_id": group_id,
            "price_cents": safe_int(payload.get("price_cents")),
            "validity_days": safe_int(payload.get("validity_days") or 30),
            "daily_limit": safe_int(payload.get("daily_limit")),
            "weekly_limit": safe_int(payload.get("weekly_limit")),
            "monthly_limit": safe_int(payload.get("monthly_limit")),
            "enabled": payload.get("enabled") is not False,
            "note": coerce_text(payload.get("note")),
        }
        if not item["name"]:
            raise ValueError("plan name is required")
        return {"ok": True, "item": self.storage.upsert_admin_subscription_plan(item)}

    def list_account_subscriptions(self) -> dict:
        if self.storage is None:
            return {"ok": True, "items": [], "total": 0}
        items = self.storage.list_admin_account_subscriptions()
        groups = {str(item.get("id") or ""): item for item in self.list_groups().get("items", [])}
        plans = {str(item.get("id") or ""): item for item in self.storage.list_admin_subscription_plans()}
        normalized = []
        for item in items:
            storage_account_id = coerce_text(item.get("account_id"))
            group_id = coerce_text(item.get("group_id"))
            group = groups.get(group_id, {})
            plan = plans.get(coerce_text(item.get("plan_id")), {})
            normalized.append(
                {
                    **item,
                    "account_id": storage_account_id,
                    "account_name": coerce_text(item.get("account_name")) or storage_account_id,
                    "group_name": coerce_text(item.get("group_name")) or coerce_text(group.get("name")),
                    "rate_multiplier": group.get("rate_multiplier"),
                    "daily_limit": safe_int(plan.get("daily_limit")),
                    "weekly_limit": safe_int(plan.get("weekly_limit")),
                    "monthly_limit": safe_int(plan.get("monthly_limit")),
                }
            )
        return {"ok": True, "items": normalized, "total": len(normalized)}

    def assign_subscription(self, payload: dict) -> dict:
        if self.storage is None:
            raise RuntimeError("storage not configured")
        account_id = coerce_text(payload.get("account_id"))
        plan_id = coerce_text(payload.get("plan_id"))
        if not account_id or not plan_id:
            raise ValueError("account_id and plan_id are required")
        account = self.storage.get_admin_account(account_id)
        if not account:
            raise ValueError("account not found")
        self._validate_account_active(account)
        plan = next((item for item in self.storage.list_admin_subscription_plans() if coerce_text(item.get("id")) == plan_id), None)
        if not plan:
            raise ValueError("subscription plan not found")
        resolved_group_id = self._resolve_plan_group_id(plan, payload)
        if resolved_group_id:
            self._validate_group_set([resolved_group_id])
            self._validate_account_allowed_groups(account, [resolved_group_id])
        item = {
            "id": coerce_text(payload.get("id")) or f"sub_{uuid.uuid4().hex[:16]}",
            "account_id": account_id,
            "plan_id": plan_id,
            "group_id": resolved_group_id,
            "status": coerce_text(payload.get("status")) or "active",
            "started_at": payload.get("started_at"),
            "expires_at": payload.get("expires_at"),
            "daily_used": safe_int(payload.get("daily_used")),
            "weekly_used": safe_int(payload.get("weekly_used")),
            "monthly_used": safe_int(payload.get("monthly_used")),
        }
        saved = self.storage.upsert_admin_account_subscription(item)
        if resolved_group_id:
            _, memberships = self._group_map()
            next_group_ids = sorted(set(memberships.get(account_id, [])) | {resolved_group_id})
            self.storage.replace_admin_account_groups(account_id, next_group_ids)
        return {"ok": True, "item": saved}

    def extend_subscription(self, subscription_id: str, payload: dict) -> dict:
        if self.storage is None:
            raise RuntimeError("storage not configured")
        extra_days = safe_int(payload.get("days"))
        if extra_days <= 0:
            raise ValueError("days must be greater than 0")
        return {"ok": True, "item": self.storage.extend_admin_account_subscription(subscription_id, extra_days)}

    def revoke_subscription(self, subscription_id: str) -> dict:
        if self.storage is None:
            raise RuntimeError("storage not configured")
        return {"ok": True, "item": self.storage.revoke_admin_account_subscription(subscription_id)}

    def reset_subscription_quota(self, subscription_id: str, payload: dict) -> dict:
        if self.storage is None:
            raise RuntimeError("storage not configured")
        return {
            "ok": True,
            "item": self.storage.reset_admin_account_subscription_quota(
                subscription_id,
                daily=payload.get("daily") is True,
                weekly=payload.get("weekly") is True,
                monthly=payload.get("monthly") is True,
            ),
        }
