from __future__ import annotations

import hashlib
import uuid

from local_proxy.platform import normalize_admin_account_payload

from .base import AdminServiceBase, coerce_text, safe_int


def _normalize_user_extra(payload: dict, current: dict | None = None) -> dict:
    current_extra = current.get("extra") if isinstance(current, dict) and isinstance(current.get("extra"), dict) else {}
    extra = {**current_extra}
    if "email" in payload:
        extra["email"] = coerce_text(payload.get("email"))
    if "username" in payload:
        extra["username"] = coerce_text(payload.get("username"))
    if "rpm_limit" in payload:
        extra["rpm_limit"] = max(0, safe_int(payload.get("rpm_limit")))
    password = coerce_text(payload.get("password"))
    clear_password = str(payload.get("clear_password") or "").strip().lower() in {"1", "true", "yes", "on"}
    if password:
        extra["password_hash"] = hashlib.sha256(password.encode("utf-8")).hexdigest()
        extra["password_set"] = True
    elif clear_password:
        extra.pop("password_hash", None)
        extra["password_set"] = False
    return extra


class AdminUsersMixin(AdminServiceBase):
    def _ensure_account_identity_unique(
        self,
        *,
        current_id: str = "",
        next_id: str = "",
        external_key: str = "",
        email: str = "",
        username: str = "",
    ) -> None:
        if self.storage is None:
            return
        target_id = coerce_text(next_id)
        current_key = coerce_text(current_id)
        normalized_external_key = coerce_text(external_key).lower()
        normalized_email = coerce_text(email).lower()
        normalized_username = coerce_text(username).lower()
        for account in self.storage.list_admin_accounts():
            if not isinstance(account, dict):
                continue
            account_id = coerce_text(account.get("id"))
            if current_key and account_id == current_key:
                continue
            extra = account.get("extra") if isinstance(account.get("extra"), dict) else {}
            if target_id and account_id == target_id:
                raise ValueError("user id already exists")
            if normalized_external_key and coerce_text(account.get("external_key")).lower() == normalized_external_key:
                raise ValueError("external key already exists")
            if normalized_email and coerce_text(extra.get("email")).lower() == normalized_email:
                raise ValueError("email already exists")
            if normalized_username and coerce_text(extra.get("username")).lower() == normalized_username:
                raise ValueError("username already exists")

    def create_user(self, payload: dict) -> dict:
        if self.storage is None:
            raise RuntimeError("storage not configured")
        email = coerce_text(payload.get("email"))
        username = coerce_text(payload.get("username"))
        display_name = coerce_text(payload.get("name")) or username or email
        next_id = coerce_text(payload.get("id")) or f"acct_{uuid.uuid4().hex[:16]}"
        external_key = coerce_text(payload.get("external_key")) or email or username or f"acct_{uuid.uuid4().hex[:16]}"
        allowed_group_ids = self._normalize_group_ids(payload.get("allowed_group_ids") if isinstance(payload.get("allowed_group_ids"), list) else [])
        group_ids = self._normalize_group_ids(payload.get("group_ids") if isinstance(payload.get("group_ids"), list) else [])
        self._validate_group_set(group_ids)
        self._validate_group_set(allowed_group_ids)
        self._ensure_account_identity_unique(
            next_id=next_id,
            external_key=external_key,
            email=email,
            username=username,
        )
        item = normalize_admin_account_payload(
            {
                **payload,
                "id": next_id,
                "name": display_name,
                "external_key": external_key,
                "source_type": "managed",
                "role": coerce_text(payload.get("role")) or "user",
                "status": coerce_text(payload.get("status")) or ("active" if payload.get("enabled") is not False else "disabled"),
                "balance_cents": safe_int(payload.get("balance_cents") if "balance_cents" in payload else payload.get("balance")),
                "concurrency_limit": safe_int(payload.get("concurrency_limit") if "concurrency_limit" in payload else payload.get("concurrency")),
                "allowed_group_ids": allowed_group_ids,
                "extra": _normalize_user_extra(payload),
            }
        )
        if not item["name"]:
            raise ValueError("name is required")
        saved = self.storage.upsert_admin_account(item)
        self.storage.replace_admin_account_groups(saved["id"], group_ids)
        refreshed = self.storage.get_admin_account(saved["id"]) or saved
        refreshed["group_ids"] = group_ids
        refreshed.update(self._get_account_subscription_status(saved["id"]))
        return {"ok": True, "item": refreshed}

    def update_user(self, account_id: str, payload: dict) -> dict:
        current = self._require_account(account_id)
        email = coerce_text(payload.get("email"))
        username = coerce_text(payload.get("username"))
        display_name = coerce_text(payload.get("name")) or username or email or coerce_text(current.get("name"))
        allowed_group_ids = (
            self._normalize_group_ids(payload.get("allowed_group_ids"))
            if isinstance(payload.get("allowed_group_ids"), list)
            else self._normalize_group_ids(current.get("allowed_group_ids") if isinstance(current.get("allowed_group_ids"), list) else [])
        )
        next_external_key = coerce_text(payload.get("external_key")) or coerce_text(current.get("external_key"))
        group_ids = payload.get("group_ids")
        normalized_group_ids = (
            self._normalize_group_ids(group_ids) if isinstance(group_ids, list) else self._normalize_group_ids(current.get("group_ids") if isinstance(current.get("group_ids"), list) else [])
        )
        self._validate_group_set(normalized_group_ids)
        self._validate_group_set(allowed_group_ids)
        self._ensure_account_identity_unique(
            current_id=current["id"],
            next_id=current["id"],
            external_key=next_external_key,
            email=email or coerce_text(current.get("email")),
            username=username or coerce_text(current.get("username")),
        )
        item = normalize_admin_account_payload(
            {
                **current,
                **payload,
                "id": current["id"],
                "name": display_name,
                "external_key": next_external_key,
                "source_type": "managed",
                "role": coerce_text(payload.get("role")) or coerce_text(current.get("role")) or "user",
                "status": coerce_text(payload.get("status")) or ("active" if payload.get("enabled", current.get("enabled")) is not False else "disabled"),
                "balance_cents": safe_int(payload.get("balance_cents") if "balance_cents" in payload else current.get("balance_cents")),
                "concurrency_limit": safe_int(payload.get("concurrency_limit") if "concurrency_limit" in payload else current.get("concurrency_limit")),
                "allowed_group_ids": allowed_group_ids,
                "extra": _normalize_user_extra(payload, current),
            }
        )
        if not item["name"]:
            raise ValueError("name is required")
        saved = self.storage.upsert_admin_account(item)
        self.storage.replace_admin_account_groups(saved["id"], normalized_group_ids)
        refreshed = self.storage.get_admin_account(saved["id"]) or saved
        refreshed["group_ids"] = normalized_group_ids
        refreshed.update(self._get_account_subscription_status(saved["id"]))
        return {"ok": True, "item": refreshed}

    def set_user_enabled(self, account_id: str, enabled: bool) -> dict:
        current = self._require_account(account_id)
        merged = normalize_admin_account_payload(
            {
                **current,
                "enabled": enabled,
                "status": "active" if enabled else "disabled",
                "source_type": "managed",
                "role": coerce_text(current.get("role")) or "user",
            }
        )
        saved = self.storage.upsert_admin_account(merged)
        return {"ok": True, "item": saved}

    def reset_user_external_key(self, account_id: str) -> dict:
        current = self._require_account(account_id)
        merged = normalize_admin_account_payload(
            {
                **current,
                "external_key": f"acct_{uuid.uuid4().hex[:16]}",
                "source_type": "managed",
                "role": coerce_text(current.get("role")) or "user",
            }
        )
        saved = self.storage.upsert_admin_account(merged)
        return {"ok": True, "item": saved}

    def delete_user(self, account_id: str) -> dict:
        if self.storage is None:
            raise RuntimeError("storage not configured")
        current = self._require_account(account_id)
        self.storage.delete_admin_account(current["id"])
        return {"ok": True, "id": current["id"]}

    def adjust_user_balance(self, account_id: str, payload: dict) -> dict:
        if self.storage is None:
            raise RuntimeError("storage not configured")
        current = self._require_account(account_id)
        operation = coerce_text(payload.get("operation") or payload.get("type") or "deposit")
        amount_cents = safe_int(payload.get("amount_cents"))
        if not amount_cents:
            amount = payload.get("amount")
            try:
                amount_cents = int(round(float(amount or 0) * 100))
            except Exception:
                amount_cents = 0
        if amount_cents <= 0:
            raise ValueError("amount is required")
        if operation in {"withdraw", "subtract", "deduct"}:
            delta = -amount_cents
            event_type = "withdraw"
        else:
            delta = amount_cents
            event_type = "deposit"
        event = self.storage.adjust_admin_account_balance(
            current["id"],
            delta,
            event_type=event_type,
            note=coerce_text(payload.get("note") or payload.get("notes")),
            actor_type=coerce_text(payload.get("actor_type")) or "admin",
            actor_id=coerce_text(payload.get("actor_id")),
        )
        refreshed = self.storage.get_admin_account(current["id"]) or current
        refreshed.update(self._get_account_subscription_status(current["id"]))
        return {"ok": True, "item": refreshed, "event": event}

    def list_user_balance_events(self, account_id: str, limit: int = 200) -> dict:
        if self.storage is None:
            return {"ok": True, "items": [], "total": 0}
        current = self._require_account(account_id)
        rows = self.storage.list_admin_balance_events(current["id"], limit=limit)
        return {"ok": True, "items": rows, "total": len(rows)}
