from __future__ import annotations

import uuid

from local_proxy.platform import normalize_admin_user_payload

from .base import AdminServiceBase, coerce_text


class AdminUsersMixin(AdminServiceBase):
    def get_user(self, user_id: str) -> dict:
        if self.storage is None:
            raise RuntimeError("storage not configured")
        item = self.storage.get_admin_user(user_id)
        if not item:
            raise ValueError("user not found")
        return {"ok": True, "item": item}

    def upsert_user(self, payload: dict) -> dict:
        if self.storage is None:
            raise RuntimeError("storage not configured")
        item = normalize_admin_user_payload(
            {
                **payload,
                "id": coerce_text(payload.get("id")) or f"user_{uuid.uuid4().hex[:16]}",
            }
        )
        if not item["name"] or not item["external_key"]:
            raise ValueError("name and external_key are required")
        group_ids = self._normalize_group_ids(payload.get("group_ids") if isinstance(payload.get("group_ids"), list) else [])
        self._validate_group_set(group_ids)
        self._validate_group_set(item["allowed_group_ids"])
        saved = self.storage.upsert_admin_user(item)
        self.storage.replace_admin_user_groups(saved["id"], group_ids)
        return {"ok": True, "item": saved}

    def set_user_balance(self, user_id: str, payload: dict) -> dict:
        current = self._require_user(user_id)
        current["balance_cents"] = max(0, int(payload.get("balance_cents") or 0))
        saved = self.storage.upsert_admin_user(current)
        return {"ok": True, "item": saved}

    def set_user_concurrency(self, user_id: str, payload: dict) -> dict:
        current = self._require_user(user_id)
        current["concurrency_limit"] = max(0, int(payload.get("concurrency_limit") or 0))
        saved = self.storage.upsert_admin_user(current)
        return {"ok": True, "item": saved}

    def set_user_allowed_groups(self, user_id: str, payload: dict) -> dict:
        current = self._require_user(user_id)
        allowed_group_ids = payload.get("allowed_group_ids") if isinstance(payload.get("allowed_group_ids"), list) else []
        current["allowed_group_ids"] = self._normalize_group_ids(allowed_group_ids)
        self._validate_group_set(current["allowed_group_ids"])
        saved = self.storage.upsert_admin_user(current)
        return {"ok": True, "item": saved}

    def set_user_membership_groups(self, user_id: str, payload: dict) -> dict:
        current = self._require_user(user_id)
        group_ids = payload.get("group_ids") if isinstance(payload.get("group_ids"), list) else []
        normalized_group_ids = self._normalize_group_ids(group_ids)
        self._validate_group_set(normalized_group_ids)
        self._validate_user_allowed_groups(current, normalized_group_ids)
        self.storage.replace_admin_user_groups(current["id"], normalized_group_ids)
        refreshed = self.storage.get_admin_user(current["id"]) or current
        refreshed["group_ids"] = normalized_group_ids
        return {"ok": True, "item": refreshed}

    def set_user_role_status(self, user_id: str, payload: dict) -> dict:
        current = self._require_user(user_id)
        merged = normalize_admin_user_payload(
            {
                **current,
                "role": payload.get("role", current.get("role")),
                "status": payload.get("status", current.get("status")),
                "enabled": payload.get("enabled", current.get("enabled")),
            }
        )
        saved = self.storage.upsert_admin_user(merged)
        return {"ok": True, "item": saved}

    def _require_user(self, user_id: str) -> dict:
        if self.storage is None:
            raise RuntimeError("storage not configured")
        current = self.storage.get_admin_user(user_id)
        if not current:
            raise ValueError("user not found")
        return current
