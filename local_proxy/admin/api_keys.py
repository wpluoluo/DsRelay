from __future__ import annotations

import uuid

from local_proxy.http.proxy_auth import generate_proxy_api_key, hash_proxy_api_key, preview_proxy_api_key

from .base import AdminServiceBase, coerce_text


class AdminApiKeysMixin(AdminServiceBase):
    def list_api_keys(self) -> dict:
        if self.storage is None:
            return {"ok": True, "items": [], "total": 0}
        users = {str(item.get("id") or ""): item for item in self.list_users(limit=5000).get("items", [])}
        items = []
        for row in self.storage.list_admin_api_keys():
            user = users.get(str(row.get("user_id") or ""), {})
            items.append({
                **row,
                "user_name": coerce_text(user.get("name")) or coerce_text(row.get("user_id")),
                "subscription_active": user.get("subscription_active"),
                "active_subscription_id": user.get("active_subscription_id"),
                "active_plan_id": user.get("active_plan_id"),
                "active_plan_name": user.get("active_plan_name"),
                "active_group_id": user.get("active_group_id"),
                "active_group_name": user.get("active_group_name"),
                "active_subscription_status": user.get("active_subscription_status"),
                "active_subscription_expires_at": user.get("active_subscription_expires_at"),
            })
        return {"ok": True, "items": items, "total": len(items)}

    def create_api_key(self, payload: dict) -> dict:
        if self.storage is None:
            raise RuntimeError("storage not configured")
        user_id = coerce_text(payload.get("user_id"))
        name = coerce_text(payload.get("name")) or "默认业务 Key"
        if not user_id:
            raise ValueError("user_id is required")
        user = self._require_user(user_id)
        self._validate_user_active(user)
        membership_rows = self.storage.list_admin_user_groups()
        group_ids = [
            coerce_text(row.get("group_id"))
            for row in membership_rows
            if coerce_text(row.get("user_id")) == user_id and coerce_text(row.get("group_id"))
        ]
        self._validate_user_allowed_groups(user, group_ids)
        raw_key = generate_proxy_api_key()
        saved = self.storage.upsert_admin_api_key(
            {
                "id": f"uak_{uuid.uuid4().hex[:16]}",
                "user_id": user_id,
                "name": name,
                "key_hash": hash_proxy_api_key(raw_key),
                "key_preview": preview_proxy_api_key(raw_key),
                "enabled": payload.get("enabled") is not False,
            }
        )
        return {"ok": True, "item": saved, "generated_key": raw_key}

    def set_api_key_enabled(self, key_id: str, enabled: bool) -> dict:
        if self.storage is None:
            raise RuntimeError("storage not configured")
        self.storage.set_admin_api_key_enabled(key_id, enabled)
        return {"ok": True}
