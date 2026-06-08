from __future__ import annotations

import uuid

from local_proxy.platform import normalize_admin_account_payload

from .base import AdminServiceBase, coerce_text


class AdminUsersMixin(AdminServiceBase):
    def create_user(self, payload: dict) -> dict:
        if self.storage is None:
            raise RuntimeError("storage not configured")
        external_key = coerce_text(payload.get("external_key")) or f"user_{uuid.uuid4().hex[:16]}"
        item = normalize_admin_account_payload(
            {
                **payload,
                "id": coerce_text(payload.get("id")) or f"user_{uuid.uuid4().hex[:16]}",
                "external_key": external_key,
                "source_type": "managed",
                "role": "user",
            }
        )
        if not item["name"]:
            raise ValueError("name is required")
        group_ids = self._normalize_group_ids(payload.get("group_ids") if isinstance(payload.get("group_ids"), list) else [])
        self._validate_group_set(group_ids)
        saved = self.storage.upsert_admin_account(item)
        self.storage.replace_admin_account_groups(saved["id"], group_ids)
        refreshed = self.storage.get_admin_account(saved["id"]) or saved
        refreshed["group_ids"] = group_ids
        return {"ok": True, "item": refreshed}

    def update_user(self, user_id: str, payload: dict) -> dict:
        current = self._require_account(user_id)
        item = normalize_admin_account_payload(
            {
                **current,
                **payload,
                "id": current["id"],
                "external_key": coerce_text(payload.get("external_key")) or coerce_text(current.get("external_key")),
                "source_type": "managed",
                "role": "user",
            }
        )
        if not item["name"]:
            raise ValueError("name is required")
        group_ids = payload.get("group_ids")
        normalized_group_ids = (
            self._normalize_group_ids(group_ids) if isinstance(group_ids, list) else self._normalize_group_ids(current.get("group_ids") if isinstance(current.get("group_ids"), list) else [])
        )
        self._validate_group_set(normalized_group_ids)
        saved = self.storage.upsert_admin_account(item)
        self.storage.replace_admin_account_groups(saved["id"], normalized_group_ids)
        refreshed = self.storage.get_admin_account(saved["id"]) or saved
        refreshed["group_ids"] = normalized_group_ids
        return {"ok": True, "item": refreshed}

    def set_user_enabled(self, user_id: str, enabled: bool) -> dict:
        current = self._require_account(user_id)
        merged = normalize_admin_account_payload(
            {
                **current,
                "enabled": enabled,
                "status": "active" if enabled else "disabled",
                "source_type": "managed",
                "role": "user",
            }
        )
        saved = self.storage.upsert_admin_account(merged)
        return {"ok": True, "item": saved}

    def reset_user_external_key(self, user_id: str) -> dict:
        current = self._require_account(user_id)
        merged = normalize_admin_account_payload(
            {
                **current,
                "external_key": f"user_{uuid.uuid4().hex[:16]}",
                "source_type": "managed",
                "role": "user",
            }
        )
        saved = self.storage.upsert_admin_account(merged)
        return {"ok": True, "item": saved}

    def delete_user(self, user_id: str) -> dict:
        if self.storage is None:
            raise RuntimeError("storage not configured")
        current = self._require_account(user_id)
        self.storage.delete_admin_account(current["id"])
        return {"ok": True, "id": current["id"]}
