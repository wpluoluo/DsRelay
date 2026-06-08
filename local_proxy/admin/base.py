from __future__ import annotations

from typing import Any


def safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0


def safe_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except Exception:
        return 0.0


def coerce_text(value: Any) -> str:
    return str(value or "").strip()


ALLOWED_PAYMENT_ORDER_TRANSITIONS = {
    "pending": {"paid", "failed", "cancelled"},
    "paid": set(),
    "failed": set(),
    "cancelled": set(),
}


class AdminServiceBase:
    storage: Any
    request_recorder: Any

    def __init__(self, storage: Any = None, request_recorder: Any = None):
        self.storage = storage
        self.request_recorder = request_recorder

    def _load_recent_requests(self, limit: int = 5000) -> list[dict]:
        rows: list[dict] = []
        if self.storage is not None:
            try:
                rows = self.storage.load_recent_requests(limit)
            except Exception:
                rows = []
        if not rows and self.request_recorder is not None:
            snapshot = self.request_recorder.snapshot()
            rows = list(snapshot.get("recent_requests") or [])
        return [row for row in rows if isinstance(row, dict)]

    def _managed_accounts(self) -> dict[str, dict]:
        if self.storage is None:
            return {}
        items = self.storage.list_admin_accounts()
        return {str(item.get("external_key") or ""): item for item in items if isinstance(item, dict)}

    def _group_map(self) -> tuple[dict[str, dict], dict[str, list[str]]]:
        groups = {}
        memberships: dict[str, list[str]] = {}
        if self.storage is None:
            return groups, memberships
        for group in self.storage.list_admin_groups():
            groups[str(group.get("id") or "")] = group
        for row in self.storage.list_admin_account_groups():
            account_id = str(row.get("account_id") or "")
            group_id = str(row.get("group_id") or "")
            if account_id and group_id:
                memberships.setdefault(account_id, []).append(group_id)
        return groups, memberships

    def _group_policy_map(self) -> dict[str, dict]:
        groups, _ = self._group_map()
        return groups

    def _normalize_group_ids(self, group_ids: list[str] | tuple[str, ...] | None) -> list[str]:
        normalized = []
        seen = set()
        for group_id in group_ids or []:
            value = coerce_text(group_id)
            if not value or value in seen:
                continue
            normalized.append(value)
            seen.add(value)
        return normalized

    def _validate_group_ids_exist(self, group_ids: list[str]) -> None:
        groups = self._group_policy_map()
        missing = [group_id for group_id in group_ids if group_id not in groups]
        if missing:
            raise ValueError(f"group not found: {', '.join(missing)}")

    def _validate_group_set(self, group_ids: list[str]) -> None:
        normalized = self._normalize_group_ids(group_ids)
        self._validate_group_ids_exist(normalized)
        groups = self._group_policy_map()
        exclusive_ids = [group_id for group_id in normalized if bool(groups.get(group_id, {}).get("is_exclusive"))]
        if len(exclusive_ids) > 1:
            raise ValueError("exclusive groups cannot be assigned together")

    def _validate_account_allowed_groups(self, account: dict, target_group_ids: list[str]) -> None:
        allowed = self._normalize_group_ids(account.get("allowed_group_ids") if isinstance(account.get("allowed_group_ids"), list) else [])
        if not allowed:
            return
        denied = [group_id for group_id in self._normalize_group_ids(target_group_ids) if group_id not in allowed]
        if denied:
            raise ValueError(f"user is not allowed to access groups: {', '.join(denied)}")

    def _resolve_plan_group_id(self, plan: dict, payload: dict | None = None) -> str:
        payload = payload if isinstance(payload, dict) else {}
        return coerce_text(payload.get("group_id")) or coerce_text(plan.get("group_id"))

    def _group_record(self, group_id: str) -> dict:
        target = coerce_text(group_id)
        if not target:
            return {}
        return self._group_policy_map().get(target, {})

    def _require_account(self, account_id: str) -> dict:
        if self.storage is None:
            raise RuntimeError("storage not configured")
        account = self.storage.get_admin_account(account_id)
        if not account:
            raise ValueError("user not found")
        return account

    def _get_active_subscription_context(self, account_id: str) -> dict:
        if self.storage is None:
            return {}
        try:
            item = self.storage.get_active_subscription_context_for_account(account_id)
        except Exception:
            item = {}
        return item if isinstance(item, dict) else {}

    def _get_account_subscription_status(self, account_id: str) -> dict:
        context = self._get_active_subscription_context(account_id)
        subscription_id = coerce_text(context.get("id"))
        status = coerce_text(context.get("status")) or ("active" if subscription_id else "inactive")
        return {
            "subscription_active": bool(subscription_id) and status == "active",
            "active_subscription_id": subscription_id,
            "active_plan_id": coerce_text(context.get("plan_id")),
            "active_plan_name": coerce_text(context.get("plan_name")),
            "active_group_id": coerce_text(context.get("group_id")),
            "active_group_name": coerce_text(context.get("group_name")),
            "active_subscription_status": status,
            "active_subscription_expires_at": context.get("expires_at"),
            "active_subscription_price_cents": safe_int(context.get("price_cents")),
        }

    def _validate_account_active(self, account: dict) -> None:
        if account.get("enabled") is False:
            raise ValueError("user is disabled")
        status = coerce_text(account.get("status")) or "active"
        if status != "active":
            raise ValueError(f"user status is not active: {status}")

    def _payment_channel_policy(self, channel: dict) -> dict:
        config = channel.get("config") if isinstance(channel.get("config"), dict) else {}
        return {
            "allowed_group_ids": self._normalize_group_ids(config.get("allowed_group_ids") if isinstance(config.get("allowed_group_ids"), list) else []),
            "allowed_protocols": self._normalize_group_ids(config.get("allowed_protocols") if isinstance(config.get("allowed_protocols"), list) else []),
            "allowed_platforms": self._normalize_group_ids(config.get("allowed_platforms") if isinstance(config.get("allowed_platforms"), list) else []),
        }

    def _validate_payment_channel_scope(self, channel: dict, *, group_id: str, protocol: str = "", platform: str = "") -> None:
        policy = self._payment_channel_policy(channel)
        if group_id and policy["allowed_group_ids"] and group_id not in policy["allowed_group_ids"]:
            raise ValueError(f"payment channel does not allow group: {group_id}")
        if protocol and policy["allowed_protocols"] and protocol not in policy["allowed_protocols"]:
            raise ValueError(f"payment channel does not allow protocol: {protocol}")
        if platform and policy["allowed_platforms"] and platform not in policy["allowed_platforms"]:
            raise ValueError(f"payment channel does not allow platform: {platform}")

    def _resolve_plan_amount_cents(self, plan: dict, group_id: str = "") -> tuple[int, float]:
        base_price_cents = max(0, safe_int(plan.get("price_cents")))
        group = self._group_record(group_id)
        try:
            rate_multiplier = float(group.get("rate_multiplier") or 1.0)
        except Exception:
            rate_multiplier = 1.0
        if rate_multiplier <= 0:
            rate_multiplier = 1.0
        final_price_cents = int(round(base_price_cents * rate_multiplier))
        return final_price_cents, rate_multiplier

    def _consumer_key(self, row: dict) -> tuple[str, str, str, str]:
        consumer_id = coerce_text(row.get("proxy_consumer_id"))
        consumer_name = coerce_text(row.get("proxy_consumer_name"))
        consumer_type = coerce_text(row.get("proxy_consumer_type")) or "anonymous"
        preview = coerce_text(row.get("proxy_consumer_preview"))
        if not consumer_id:
            consumer_id = "anonymous"
        if not consumer_name:
            consumer_name = "未归属"
        return consumer_id, consumer_name, consumer_type, preview

    def _resolve_account_metadata(self, consumer_id: str, consumer_name: str, consumer_type: str, preview: str) -> dict:
        managed_accounts = self._managed_accounts()
        external_key = consumer_id if consumer_id != "anonymous" else ""
        stored = managed_accounts.get(external_key, {})
        extra = stored.get("extra") if isinstance(stored.get("extra"), dict) else {}
        return {
            "id": coerce_text(stored.get("id")) or consumer_id,
            "name": coerce_text(stored.get("name")) or consumer_name,
            "source_type": coerce_text(stored.get("source_type")) or consumer_type,
            "preview": preview,
            "external_key": external_key,
            "role": coerce_text(stored.get("role")) or "user",
            "status": coerce_text(stored.get("status")) or "active",
            "balance_cents": safe_int(stored.get("balance_cents")),
            "concurrency_limit": safe_int(stored.get("concurrency_limit")),
            "allowed_group_ids": stored.get("allowed_group_ids") if isinstance(stored.get("allowed_group_ids"), list) else [],
            "extra": extra,
            "email": coerce_text(extra.get("email")),
            "username": coerce_text(extra.get("username")),
            "rpm_limit": safe_int(extra.get("rpm_limit")),
            "enabled": stored.get("enabled") is not False if stored else True,
            "note": coerce_text(stored.get("note")),
        }
