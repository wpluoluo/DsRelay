from __future__ import annotations

import uuid

from local_proxy.http.proxy_auth import generate_proxy_api_key, hash_proxy_api_key, preview_proxy_api_key

from .base import AdminServiceBase, coerce_text, safe_float, safe_int


class AdminApiKeysMixin(AdminServiceBase):
    def _resolve_key_group_id(self, account: dict, raw_group_id: object) -> str:
        group_id = coerce_text(raw_group_id)
        if not group_id:
            return ""
        self._validate_group_set([group_id])
        self._validate_account_allowed_groups(account, [group_id])
        return group_id

    def list_api_keys(self, *, account_id: str = "") -> dict:
        if self.storage is None:
            return {"ok": True, "items": [], "total": 0}
        normalized_account_id = coerce_text(account_id)
        if normalized_account_id:
            self._require_account(normalized_account_id)
        accounts = {str(item.get("id") or ""): item for item in self.list_users(limit=5000).get("items", [])}
        key_counts: dict[str, int] = {}
        active_key_counts: dict[str, int] = {}
        raw_rows = []
        for row in self.storage.list_admin_api_keys():
            storage_account_id = coerce_text(row.get("account_id"))
            if normalized_account_id and storage_account_id != normalized_account_id:
                continue
            raw_rows.append(row)
        usage_by_key: dict[str, dict] = {}
        for request_row in self._load_recent_requests(limit=5000):
            key_id = coerce_text(request_row.get("proxy_api_key_id"))
            if not key_id:
                continue
            if normalized_account_id:
                consumer_id = coerce_text(request_row.get("proxy_consumer_id"))
                account = accounts.get(normalized_account_id, {})
                if consumer_id and consumer_id != coerce_text(account.get("external_key")):
                    continue
            entry = usage_by_key.setdefault(
                key_id,
                {
                    "request_count": 0,
                    "error_count": 0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "input_bytes": 0,
                    "output_bytes": 0,
                    "actual_cost": 0.0,
                    "total_cost": 0.0,
                    "last_used_request_at": "",
                },
            )
            prompt_tokens = safe_int(request_row.get("prompt_tokens"))
            completion_tokens = safe_int(request_row.get("completion_tokens"))
            total_tokens = safe_int(request_row.get("total_tokens")) or prompt_tokens + completion_tokens
            started_at = coerce_text(request_row.get("started_at"))
            entry["request_count"] += 1
            if request_row.get("error") or safe_int(request_row.get("status_code")) >= 400:
                entry["error_count"] += 1
            entry["prompt_tokens"] += prompt_tokens
            entry["completion_tokens"] += completion_tokens
            entry["total_tokens"] += total_tokens
            entry["input_bytes"] += safe_int(request_row.get("input_bytes"))
            entry["output_bytes"] += safe_int(request_row.get("bytes_sent"))
            entry["actual_cost"] += safe_float(request_row.get("actual_cost")) or safe_float(request_row.get("total_cost"))
            entry["total_cost"] += safe_float(request_row.get("total_cost"))
            if started_at and started_at > entry["last_used_request_at"]:
                entry["last_used_request_at"] = started_at
        for row in raw_rows:
            storage_account_id = coerce_text(row.get("account_id"))
            if not storage_account_id:
                continue
            key_counts[storage_account_id] = key_counts.get(storage_account_id, 0) + 1
            if row.get("enabled") is not False:
                active_key_counts[storage_account_id] = active_key_counts.get(storage_account_id, 0) + 1
        items = []
        for row in raw_rows:
            storage_account_id = coerce_text(row.get("account_id"))
            account = accounts.get(storage_account_id, {})
            usage = usage_by_key.get(coerce_text(row.get("id")), {})
            group_id = coerce_text(row.get("group_id"))
            group_name = coerce_text(row.get("group_name"))
            active_group_id = group_id or coerce_text(account.get("active_group_id"))
            active_group_name = group_name or coerce_text(account.get("active_group_name"))
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
                "active_group_id": active_group_id,
                "active_group_name": active_group_name,
                "active_subscription_status": account.get("active_subscription_status"),
                "active_subscription_expires_at": account.get("active_subscription_expires_at"),
                "request_count": safe_int(usage.get("request_count")),
                "error_count": safe_int(usage.get("error_count")),
                "prompt_tokens": safe_int(usage.get("prompt_tokens")),
                "completion_tokens": safe_int(usage.get("completion_tokens")),
                "total_tokens": safe_int(usage.get("total_tokens")),
                "input_bytes": safe_int(usage.get("input_bytes")),
                "output_bytes": safe_int(usage.get("output_bytes")),
                "actual_cost": safe_float(usage.get("actual_cost")),
                "total_cost": safe_float(usage.get("total_cost")),
                "last_used_request_at": coerce_text(usage.get("last_used_request_at")),
            })
        for current_account_id, account in accounts.items():
            account["key_count"] = key_counts.get(current_account_id, 0)
            account["active_key_count"] = active_key_counts.get(current_account_id, 0)
        return {"ok": True, "items": items, "total": len(items)}

    def create_api_key(self, payload: dict) -> dict:
        if self.storage is None:
            raise RuntimeError("storage not configured")
        account_id = coerce_text(payload.get("account_id"))
        name = coerce_text(payload.get("name")) or "默认业务 Key"
        if not account_id:
            raise ValueError("account_id is required")
        account = self._require_account(account_id)
        self._validate_account_active(account)
        group_id = self._resolve_key_group_id(account, payload.get("group_id"))
        raw_key = generate_proxy_api_key()
        saved = self.storage.upsert_admin_api_key(
            {
                "id": f"uak_{uuid.uuid4().hex[:16]}",
                "account_id": account_id,
                "group_id": group_id,
                "name": name,
                "key_hash": hash_proxy_api_key(raw_key),
                "key_preview": preview_proxy_api_key(raw_key),
                "enabled": payload.get("enabled") is not False,
            }
        )
        return {"ok": True, "item": saved, "generated_key": raw_key}

    def update_api_key(self, key_id: str, payload: dict) -> dict:
        if self.storage is None:
            raise RuntimeError("storage not configured")
        current = self.storage.get_admin_api_key(key_id)
        if not current:
            raise ValueError("api key not found")
        next_account_id = coerce_text(current.get("account_id"))
        if "account_id" in payload:
            next_account_id = coerce_text(payload.get("account_id"))
        next_name = coerce_text(payload.get("name")) or coerce_text(current.get("name")) or "默认业务 Key"
        account = self._require_account(next_account_id)
        self._validate_account_active(account)
        next_group_id = self._resolve_key_group_id(account, payload.get("group_id")) if "group_id" in payload else coerce_text(current.get("group_id"))
        saved = self.storage.upsert_admin_api_key(
            {
                **current,
                "account_id": next_account_id,
                "group_id": next_group_id,
                "name": next_name,
                "enabled": payload.get("enabled", current.get("enabled")) is not False,
            }
        )
        return {"ok": True, "item": saved}

    def set_api_key_enabled(self, key_id: str, enabled: bool) -> dict:
        if self.storage is None:
            raise RuntimeError("storage not configured")
        self.storage.set_admin_api_key_enabled(key_id, enabled)
        return {"ok": True}

    def delete_api_key(self, key_id: str) -> dict:
        if self.storage is None:
            raise RuntimeError("storage not configured")
        current = self.storage.get_admin_api_key(key_id)
        if not current:
            raise ValueError("api key not found")
        self.storage.delete_admin_api_key(key_id)
        return {"ok": True, "id": key_id}
