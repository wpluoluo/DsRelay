from __future__ import annotations

import uuid

from local_proxy.http.proxy_auth import generate_proxy_api_key, hash_proxy_api_key, preview_proxy_api_key

from .base import AdminServiceBase, coerce_text


class AdminApiKeysMixin(AdminServiceBase):
    def list_api_keys(self) -> dict:
        if self.storage is None:
            return {"ok": True, "items": [], "total": 0}
        accounts = {str(item.get("id") or ""): item for item in self.list_accounts(limit=5000).get("items", [])}
        items = []
        for row in self.storage.list_admin_api_keys():
            storage_account_id = coerce_text(row.get("user_id"))
            account = accounts.get(storage_account_id, {})
            items.append({
                **row,
                "account_id": storage_account_id,
                "account_name": coerce_text(account.get("name")) or storage_account_id,
                "account_source_type": account.get("source_type"),
                "account_enabled": account.get("enabled"),
                "account_note": account.get("note"),
                "subscription_active": account.get("subscription_active"),
                "active_subscription_id": account.get("active_subscription_id"),
                "active_plan_id": account.get("active_plan_id"),
                "active_plan_name": account.get("active_plan_name"),
                "active_group_id": account.get("active_group_id"),
                "active_group_name": account.get("active_group_name"),
                "active_subscription_status": account.get("active_subscription_status"),
                "active_subscription_expires_at": account.get("active_subscription_expires_at"),
            })
        return {"ok": True, "items": items, "total": len(items)}

    def create_api_key(self, payload: dict) -> dict:
        if self.storage is None:
            raise RuntimeError("storage not configured")
        account_id = coerce_text(payload.get("account_id")) or coerce_text(payload.get("user_id"))
        name = coerce_text(payload.get("name")) or "默认业务 Key"
        if not account_id:
            raise ValueError("account_id is required")
        account = self._require_account(account_id)
        self._validate_account_active(account)
        membership_rows = self.storage.list_admin_account_groups()
        group_ids = [
            coerce_text(row.get("group_id"))
            for row in membership_rows
            if coerce_text(row.get("user_id")) == account_id and coerce_text(row.get("group_id"))
        ]
        self._validate_account_allowed_groups(account, group_ids)
        raw_key = generate_proxy_api_key()
        saved = self.storage.upsert_admin_api_key(
            {
                "id": f"uak_{uuid.uuid4().hex[:16]}",
                "user_id": account_id,
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
