from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid

from local_proxy.admin.base import coerce_text, safe_float, safe_int


class AccountPortalService:
    def __init__(self, admin_service):
        self.admin_service = admin_service

    @property
    def storage(self):
        return self.admin_service.storage

    def find_account_by_identifier(self, identifier: str) -> dict | None:
        needle = coerce_text(identifier).lower()
        if not needle or self.storage is None:
            return None
        for account in self.storage.list_admin_accounts():
            extra = account.get("extra") if isinstance(account.get("extra"), dict) else {}
            candidates = {
                coerce_text(account.get("id")).lower(),
                coerce_text(account.get("name")).lower(),
                coerce_text(account.get("external_key")).lower(),
                coerce_text(extra.get("email")).lower(),
                coerce_text(extra.get("username")).lower(),
            }
            if needle in candidates:
                return account
        return None

    def authenticate_account(self, identifier: str, password: str) -> dict | None:
        account = self.find_account_by_identifier(identifier)
        if not account:
            return None
        if account.get("enabled") is False or coerce_text(account.get("status")) not in {"", "active"}:
            return None
        extra = account.get("extra") if isinstance(account.get("extra"), dict) else {}
        password_hash = coerce_text(extra.get("password_hash"))
        if not password_hash:
            return None
        candidate = hashlib.sha256(coerce_text(password).encode("utf-8")).hexdigest()
        if not hmac.compare_digest(password_hash, candidate):
            return None
        return account

    def find_account_by_affiliate_code(self, aff_code: str) -> dict | None:
        needle = coerce_text(aff_code).lower()
        if not needle or self.storage is None:
            return None
        for account in self.storage.list_admin_accounts():
            if not isinstance(account, dict):
                continue
            extra = account.get("extra") if isinstance(account.get("extra"), dict) else {}
            if coerce_text(extra.get("aff_code")).lower() == needle:
                return account
        return None

    def register_account(self, payload: dict) -> dict:
        if self.storage is None:
            raise RuntimeError("storage not configured")
        email = coerce_text(payload.get("email"))
        username = coerce_text(payload.get("username"))
        password = coerce_text(payload.get("password"))
        display_name = coerce_text(payload.get("name")) or username or email
        if not display_name:
            raise ValueError("name, email, or username is required")
        if not password:
            raise ValueError("password is required")
        created = self.admin_service.create_user(
            {
                "name": display_name,
                "email": email,
                "username": username,
                "password": password,
                "external_key": email or username,
                "role": "user",
                "enabled": True,
                "status": "active",
                "balance_cents": 0,
                "concurrency_limit": 1,
                "rpm_limit": 0,
                "group_ids": [],
                "allowed_group_ids": [],
                "note": coerce_text(payload.get("note")),
            }
        )
        item = created.get("item") if isinstance(created, dict) else None
        if not isinstance(item, dict):
            raise ValueError("register account failed")
        aff_code = coerce_text(payload.get("aff_code"))
        if aff_code:
            item = self._attach_affiliate_invite(item, aff_code)
        return {"ok": True, "item": self._account_item(item)}

    def account_me(self, account_id: str) -> dict:
        account = self._require_account(account_id)
        return {"ok": True, "item": self._account_item(account)}

    def update_profile(self, account_id: str, payload: dict) -> dict:
        account = self._require_account(account_id)
        next_payload = {}
        for key in ("name", "email", "username", "password", "clear_password"):
            if key in payload:
                next_payload[key] = payload.get(key)
        updated = self.admin_service.update_user(account["id"], next_payload)
        item = updated.get("item") if isinstance(updated, dict) else None
        if not isinstance(item, dict):
            item = self._require_account(account["id"])
        return {"ok": True, "item": self._account_item(item)}

    def list_groups(self, account_id: str) -> dict:
        account = self._require_account(account_id)
        allowed_ids = self._visible_group_ids(account)
        groups = []
        for item in self.storage.list_admin_groups() if self.storage is not None else []:
            if not isinstance(item, dict):
                continue
            if item.get("enabled") is False:
                continue
            group_id = coerce_text(item.get("id"))
            if allowed_ids and group_id and group_id not in allowed_ids:
                continue
            groups.append(item)
        groups.sort(key=lambda item: (safe_int(item.get("sort_order")), coerce_text(item.get("name"))))
        return {"ok": True, "items": groups, "total": len(groups)}

    def list_channels(self, account_id: str) -> dict:
        account = self._require_account(account_id)
        visible_group_ids = self._visible_group_ids(account)
        items = []
        for channel in self.admin_service.list_channels().get("items", []):
            if channel.get("enabled") is False:
                continue
            channel_groups = [
                coerce_text(item)
                for item in (channel.get("group_ids") if isinstance(channel.get("group_ids"), list) else [])
                if coerce_text(item)
            ]
            if visible_group_ids and channel_groups and not set(visible_group_ids).intersection(channel_groups):
                continue
            items.append(channel)
        return {"ok": True, "items": items, "total": len(items)}

    def list_api_keys(self, account_id: str) -> dict:
        account = self._require_account(account_id)
        usage_by_key: dict[str, dict] = {}
        for request_row in self.admin_service._load_recent_requests(limit=5000):
            key_id = coerce_text(request_row.get("proxy_api_key_id"))
            if not key_id:
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
        subscription_status = self.admin_service._get_account_subscription_status(account["id"])
        items = []
        for row in self.storage.list_admin_api_keys() if self.storage is not None else []:
            if coerce_text(row.get("account_id")) != account["id"]:
                continue
            usage = usage_by_key.get(coerce_text(row.get("id")), {})
            items.append(
                {
                    **row,
                    "account_name": coerce_text(account.get("name")) or account["id"],
                    "account_source_type": account.get("source_type"),
                    "account_enabled": account.get("enabled"),
                    "account_note": account.get("note"),
                    **subscription_status,
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
                }
            )
        return {"ok": True, "items": items, "total": len(items)}

    def create_api_key(self, account_id: str, payload: dict) -> dict:
        account = self._require_account(account_id)
        self.admin_service._validate_account_active(account)
        next_payload = {
            "account_id": account["id"],
            "name": coerce_text(payload.get("name")) or "默认业务 Key",
            "group_id": coerce_text(payload.get("group_id")),
            "enabled": payload.get("enabled") is not False,
        }
        return self.admin_service.create_api_key(next_payload)

    def update_api_key(self, account_id: str, key_id: str, payload: dict) -> dict:
        key = self._require_api_key(account_id, key_id)
        next_payload = {
            "account_id": coerce_text(key.get("account_id")),
            "name": coerce_text(payload.get("name")) or coerce_text(key.get("name")),
            "enabled": payload.get("enabled", key.get("enabled")) is not False,
        }
        if "group_id" in payload:
            next_payload["group_id"] = coerce_text(payload.get("group_id"))
        return self.admin_service.update_api_key(key_id, next_payload)

    def set_api_key_enabled(self, account_id: str, key_id: str, enabled: bool) -> dict:
        self._require_api_key(account_id, key_id)
        return self.admin_service.set_api_key_enabled(key_id, enabled)

    def delete_api_key(self, account_id: str, key_id: str) -> dict:
        self._require_api_key(account_id, key_id)
        return self.admin_service.delete_api_key(key_id)

    def list_usage(self, account_id: str, *, started_after=None, started_before=None, limit: int = 5000) -> dict:
        account = self._require_account(account_id)
        items = [
            item
            for item in self.admin_service.list_usage(
                limit=max(200, min(10000, safe_int(limit) or 5000)),
                started_after=started_after,
                started_before=started_before,
            ).get("items", [])
            if coerce_text(item.get("consumer_id") or item.get("account_id")) == account["id"]
        ]
        return {"ok": True, "items": items, "total": len(items)}

    def usage_stats(self, account_id: str, *, started_after=None, started_before=None) -> dict:
        usage = self.list_usage(account_id, started_after=started_after, started_before=started_before).get("items", [])
        summary = {
            "request_count": 0,
            "error_count": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "input_bytes": 0,
            "output_bytes": 0,
            "cache_read_tokens": 0,
            "cache_write_tokens": 0,
            "actual_cost": 0.0,
            "total_cost": 0.0,
        }
        for row in usage:
            prompt_tokens = safe_int(row.get("prompt_tokens"))
            completion_tokens = safe_int(row.get("completion_tokens"))
            total_tokens = safe_int(row.get("total_tokens")) or prompt_tokens + completion_tokens
            summary["request_count"] += 1
            if row.get("error") or safe_int(row.get("status_code")) >= 400:
                summary["error_count"] += 1
            summary["prompt_tokens"] += prompt_tokens
            summary["completion_tokens"] += completion_tokens
            summary["total_tokens"] += total_tokens
            summary["input_bytes"] += safe_int(row.get("input_bytes"))
            summary["output_bytes"] += safe_int(row.get("output_bytes"))
            summary["cache_read_tokens"] += safe_int(row.get("cache_read_tokens"))
            summary["cache_write_tokens"] += safe_int(row.get("cache_write_tokens"))
            summary["actual_cost"] += safe_float(row.get("actual_cost"))
            summary["total_cost"] += safe_float(row.get("total_cost"))
        return {"ok": True, "summary": summary}

    def list_subscription_plans(self, account_id: str) -> dict:
        account = self._require_account(account_id)
        allowed_ids = self._visible_group_ids(account)
        items = []
        for plan in self.admin_service.list_subscription_plans().get("items", []):
            if plan.get("enabled") is False:
                continue
            group_id = coerce_text(plan.get("group_id"))
            if allowed_ids and group_id and group_id not in allowed_ids:
                continue
            items.append(plan)
        return {"ok": True, "items": items, "total": len(items)}

    def list_payment_channels(self, account_id: str) -> dict:
        account = self._require_account(account_id)
        allowed_ids = self._visible_group_ids(account)
        items = []
        for channel in self.admin_service.list_payment_channels().get("items", []):
            if channel.get("enabled") is False:
                continue
            channel_groups = [
                coerce_text(item)
                for item in (channel.get("allowed_group_ids") if isinstance(channel.get("allowed_group_ids"), list) else [])
                if coerce_text(item)
            ]
            if allowed_ids and channel_groups and not set(allowed_ids).intersection(channel_groups):
                continue
            items.append(channel)
        return {"ok": True, "items": items, "total": len(items)}

    def list_subscriptions(self, account_id: str) -> dict:
        account = self._require_account(account_id)
        items = [
            item
            for item in self.admin_service.list_account_subscriptions().get("items", [])
            if coerce_text(item.get("account_id")) == account["id"]
        ]
        return {"ok": True, "items": items, "total": len(items)}

    def list_orders(self, account_id: str) -> dict:
        account = self._require_account(account_id)
        items = [
            item
            for item in self.admin_service.list_payment_orders().get("items", [])
            if coerce_text(item.get("account_id")) == account["id"]
        ]
        return {"ok": True, "items": items, "total": len(items)}

    def create_order(self, account_id: str, payload: dict) -> dict:
        account = self._require_account(account_id)
        self.admin_service._validate_account_active(account)
        return self.admin_service.create_payment_order(
            {
                **(payload if isinstance(payload, dict) else {}),
                "account_id": account["id"],
            }
        )

    def cancel_order(self, account_id: str, order_id: str) -> dict:
        self._require_order(account_id, order_id)
        return self.admin_service.update_payment_order_status(order_id, {"status": "cancelled"})

    def redeem_profile(self, account_id: str) -> dict:
        account = self._require_account(account_id)
        return self.admin_service.account_redeem_profile(account["id"])

    def redeem_code(self, account_id: str, payload: dict) -> dict:
        account = self._require_account(account_id)
        return self.admin_service.redeem_account_code(account["id"], payload)

    def affiliate_detail(self, account_id: str) -> dict:
        account = self._require_account(account_id)
        return self.admin_service.account_affiliate_detail(account["id"])

    def transfer_affiliate_quota(self, account_id: str) -> dict:
        account = self._require_account(account_id)
        return self.admin_service.transfer_account_affiliate_quota(account["id"])

    def _account_item(self, account: dict) -> dict:
        item = dict(account)
        extra = item.get("extra") if isinstance(item.get("extra"), dict) else {}
        item["email"] = coerce_text(item.get("email") or extra.get("email"))
        item["username"] = coerce_text(item.get("username") or extra.get("username"))
        item["rpm_limit"] = safe_int(item.get("rpm_limit") or extra.get("rpm_limit"))
        item["password_set"] = bool(extra.get("password_set") or extra.get("password_hash"))
        groups, memberships = self.admin_service._group_map()
        group_ids = memberships.get(coerce_text(item.get("id")), [])
        item["group_ids"] = group_ids
        if group_ids:
            first_group = groups.get(group_ids[0], {})
            item["group_id"] = coerce_text(first_group.get("id"))
            item["group_name"] = coerce_text(first_group.get("name"))
        item.update(self.admin_service._get_account_subscription_status(coerce_text(item.get("id"))))
        return item

    def _attach_affiliate_invite(self, account: dict, aff_code: str) -> dict:
        inviter = self.find_account_by_affiliate_code(aff_code)
        if not inviter:
            return account
        invited_account_id = coerce_text(account.get("id"))
        inviter_account_id = coerce_text(inviter.get("id"))
        normalized_aff_code = coerce_text(aff_code)
        if not invited_account_id or not inviter_account_id or invited_account_id == inviter_account_id or self.storage is None:
            return account

        current_account = self.storage.get_admin_account(invited_account_id) or account
        extra = current_account.get("extra") if isinstance(current_account.get("extra"), dict) else {}
        if coerce_text(extra.get("invited_by_account_id")) == inviter_account_id:
            return current_account

        next_extra = {
            **extra,
            "invited_by_account_id": inviter_account_id,
            "invited_by_aff_code": normalized_aff_code,
        }
        saved_account = self.storage.upsert_admin_account({**current_account, "extra": next_extra})

        invite_items = self.admin_service._load_content_bucket("affiliate-invites")
        now = time.time()
        invite_payload = {
            "account_id": inviter_account_id,
            "invited_account_id": invited_account_id,
            "aff_code": normalized_aff_code,
            "invitee_name": coerce_text(saved_account.get("name")),
            "invitee_email": coerce_text(next_extra.get("email")),
            "invitee_username": coerce_text(next_extra.get("username")),
        }
        invite_item = {
            "id": f"aff_invite_{uuid.uuid4().hex[:16]}",
            "title": f"{normalized_aff_code} invite",
            "status": "active",
            "summary": coerce_text(saved_account.get("name")) or invited_account_id,
            "content": json.dumps(invite_payload, ensure_ascii=False, separators=(",", ":")),
            "note": "",
            "created_at": now,
            "updated_at": now,
        }
        deduped_items = [
            item
            for item in invite_items
            if not (
                coerce_text(self.admin_service._content_payload(item).get("invited_account_id")) == invited_account_id
                and coerce_text(self.admin_service._content_payload(item).get("aff_code")).lower() == normalized_aff_code.lower()
            )
        ]
        self.admin_service._save_content_bucket("affiliate-invites", [invite_item, *deduped_items])
        return saved_account

    def _allowed_group_ids(self, account: dict) -> list[str]:
        allowed = account.get("allowed_group_ids") if isinstance(account.get("allowed_group_ids"), list) else []
        return [coerce_text(item) for item in allowed if coerce_text(item)]

    def _visible_group_ids(self, account: dict) -> list[str]:
        allowed = self._allowed_group_ids(account)
        if allowed:
            return allowed
        return []

    def _require_account(self, account_id: str) -> dict:
        target = coerce_text(account_id)
        if not target or self.storage is None:
            raise ValueError("account is required")
        account = self.storage.get_admin_account(target)
        if not account:
            raise ValueError("account not found")
        return account

    def _require_api_key(self, account_id: str, key_id: str) -> dict:
        account = self._require_account(account_id)
        key = self.storage.get_admin_api_key(key_id) if self.storage is not None else {}
        if not key or coerce_text(key.get("account_id")) != account["id"]:
            raise ValueError("api key not found")
        return key

    def _require_order(self, account_id: str, order_id: str) -> dict:
        account = self._require_account(account_id)
        order = self.storage.get_admin_payment_order(order_id) if self.storage is not None else {}
        if not order or coerce_text(order.get("account_id")) != account["id"]:
            raise ValueError("order not found")
        return order
