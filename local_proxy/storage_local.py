from __future__ import annotations

import json
import time
import uuid
from copy import deepcopy
from pathlib import Path
from threading import RLock


def _safe_int(value) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0


def _safe_float(value) -> float:
    try:
        return float(value or 0.0)
    except Exception:
        return 0.0


def _clone(value):
    return deepcopy(value)


def _default_store() -> dict:
    return {
        "model_route_cache": {"routes": {}, "model_lists": {}, "capabilities": {}},
        "request_history": {},
        "pool_runtime_state": {},
        "app_config": {},
        "admin_accounts": {},
        "admin_groups": {},
        "admin_account_groups": [],
        "admin_api_keys": {},
        "admin_subscription_plans": {},
        "admin_account_subscriptions": {},
        "admin_balance_events": {},
        "admin_payment_channels": {},
        "admin_payment_orders": {},
        "admin_payment_webhook_events": {},
        "admin_payment_fulfillment_logs": {},
        "request_cache": {},
        "tool_result_cache": {},
        "interrupted_responses": {},
    }


class LocalProxyStorage:
    def __init__(self, file_path: str | Path):
        self._path = Path(file_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._data = _default_store()
        self._load_from_disk()

    def _load_from_disk(self) -> None:
        with self._lock:
            if not self._path.exists():
                self._persist_unlocked()
                return
            try:
                payload = json.loads(self._path.read_text(encoding="utf-8"))
            except Exception:
                payload = {}
            merged = _default_store()
            if isinstance(payload, dict):
                for key, default_value in merged.items():
                    incoming = payload.get(key)
                    if isinstance(default_value, dict):
                        merged[key] = incoming if isinstance(incoming, dict) else {}
                    elif isinstance(default_value, list):
                        merged[key] = incoming if isinstance(incoming, list) else []
            self._data = merged

    def _persist_unlocked(self) -> None:
        tmp_path = self._path.with_suffix(self._path.suffix + ".tmp")
        tmp_path.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        tmp_path.replace(self._path)

    def _ensure_dict_section(self, name: str) -> dict:
        section = self._data.get(name)
        if not isinstance(section, dict):
            section = {}
            self._data[name] = section
        return section

    def _ensure_list_section(self, name: str) -> list:
        section = self._data.get(name)
        if not isinstance(section, list):
            section = []
            self._data[name] = section
        return section

    def _filter_model_route_cache(self, cache: dict) -> dict:
        now = time.time()
        filtered = {"routes": {}, "model_lists": {}, "capabilities": {}}
        for bucket_name in ("routes", "capabilities"):
            bucket = cache.get(bucket_name) if isinstance(cache, dict) else {}
            if not isinstance(bucket, dict):
                continue
            for logical_key, route_map in bucket.items():
                if not isinstance(route_map, dict):
                    continue
                for route_url, model_map in route_map.items():
                    if not isinstance(model_map, dict):
                        continue
                    for model_key, entry in model_map.items():
                        if not isinstance(entry, dict):
                            continue
                        if _safe_float(entry.get("expires_at")) <= now:
                            continue
                        filtered[bucket_name].setdefault(str(logical_key), {}).setdefault(str(route_url), {})[
                            str(model_key)
                        ] = _clone(entry)
        model_lists = cache.get("model_lists") if isinstance(cache, dict) else {}
        if isinstance(model_lists, dict):
            for cache_key, item in model_lists.items():
                if not isinstance(item, dict):
                    continue
                if _safe_float(item.get("expires_at")) <= now:
                    continue
                models = item.get("models")
                if not isinstance(models, list):
                    continue
                filtered["model_lists"][str(cache_key)] = {
                    "models": _clone(models),
                    "fetched_at": _safe_float(item.get("fetched_at")),
                    "expires_at": _safe_float(item.get("expires_at")),
                }
        return filtered

    def load_model_route_cache(self) -> dict:
        with self._lock:
            return self._filter_model_route_cache(self._ensure_dict_section("model_route_cache"))

    def save_model_route_cache(self, cache: dict) -> None:
        with self._lock:
            self._data["model_route_cache"] = self._filter_model_route_cache(cache if isinstance(cache, dict) else {})
            self._persist_unlocked()

    def record_request(self, request_meta: dict, max_rows: int) -> None:
        if not isinstance(request_meta, dict):
            return
        request_id = str(request_meta.get("request_id") or "").strip()
        if not request_id:
            return
        now = time.time()
        with self._lock:
            section = self._ensure_dict_section("request_history")
            section[request_id] = {
                "request_id": request_id,
                "started_at": str(request_meta.get("started_at") or ""),
                "created_at": now,
                "meta": _clone(request_meta),
            }
            rows = sorted(
                [item for item in section.values() if isinstance(item, dict)],
                key=lambda item: _safe_float(item.get("created_at")),
                reverse=True,
            )
            trimmed = rows[: max(1, int(max_rows or 1))]
            self._data["request_history"] = {
                str(item.get("request_id") or ""): item for item in trimmed if str(item.get("request_id") or "")
            }
            self._persist_unlocked()

    def load_recent_requests(self, limit: int) -> list[dict]:
        with self._lock:
            rows = sorted(
                [item for item in self._ensure_dict_section("request_history").values() if isinstance(item, dict)],
                key=lambda item: _safe_float(item.get("created_at")),
                reverse=True,
            )
            return [
                _clone(item.get("meta"))
                for item in rows[: max(0, int(limit or 0))]
                if isinstance(item.get("meta"), dict)
            ]

    def clear_request_history(self) -> None:
        with self._lock:
            self._data["request_history"] = {}
            self._persist_unlocked()

    def load_pool_runtime_state(self, state_key: str = "default") -> dict:
        with self._lock:
            item = self._ensure_dict_section("pool_runtime_state").get(str(state_key))
            payload = item.get("payload") if isinstance(item, dict) else {}
            return _clone(payload if isinstance(payload, dict) else {})

    def save_pool_runtime_state(self, payload: dict, state_key: str = "default") -> None:
        if not isinstance(payload, dict):
            return
        with self._lock:
            self._ensure_dict_section("pool_runtime_state")[str(state_key)] = {
                "payload": _clone(payload),
                "updated_at": time.time(),
            }
            self._persist_unlocked()

    def load_app_config(self, config_key: str = "runtime_config") -> dict:
        with self._lock:
            item = self._ensure_dict_section("app_config").get(str(config_key))
            payload = item.get("payload") if isinstance(item, dict) else {}
            return _clone(payload if isinstance(payload, dict) else {})

    def save_app_config(self, payload: dict, config_key: str = "runtime_config") -> None:
        if not isinstance(payload, dict):
            return
        with self._lock:
            self._ensure_dict_section("app_config")[str(config_key)] = {
                "payload": _clone(payload),
                "updated_at": time.time(),
            }
            self._persist_unlocked()

    def list_admin_accounts(self) -> list[dict]:
        with self._lock:
            rows = [item for item in self._ensure_dict_section("admin_accounts").values() if isinstance(item, dict)]
            rows.sort(
                key=lambda item: (_safe_float(item.get("updated_at")), _safe_float(item.get("created_at"))),
                reverse=True,
            )
            return [_clone(item) for item in rows]

    def get_admin_account(self, account_id: str) -> dict:
        target = str(account_id or "").strip()
        if not target:
            return {}
        with self._lock:
            item = self._ensure_dict_section("admin_accounts").get(target)
            return _clone(item) if isinstance(item, dict) else {}

    def get_admin_account_by_external_key(self, external_key: str) -> dict:
        target = str(external_key or "").strip()
        if not target:
            return {}
        for item in self.list_admin_accounts():
            if str(item.get("external_key") or "") == target:
                return item
        return {}

    def upsert_admin_account(self, payload: dict) -> dict:
        now = time.time()
        item = {
            "id": str(payload.get("id") or "").strip(),
            "name": str(payload.get("name") or "").strip(),
            "external_key": str(payload.get("external_key") or "").strip(),
            "source_type": str(payload.get("source_type") or "").strip() or "managed",
            "role": str(payload.get("role") or "user").strip() or "user",
            "status": str(payload.get("status") or "active").strip() or "active",
            "balance_cents": _safe_int(payload.get("balance_cents")),
            "concurrency_limit": _safe_int(payload.get("concurrency_limit")),
            "allowed_group_ids": payload.get("allowed_group_ids") if isinstance(payload.get("allowed_group_ids"), list) else [],
            "extra": payload.get("extra") if isinstance(payload.get("extra"), dict) else {},
            "enabled": payload.get("enabled") is not False,
            "note": str(payload.get("note") or ""),
        }
        if not item["id"] or not item["name"] or not item["external_key"]:
            raise ValueError("missing required admin account fields")
        with self._lock:
            section = self._ensure_dict_section("admin_accounts")
            current = section.get(item["id"]) if isinstance(section.get(item["id"]), dict) else {}
            created_at = _safe_float(current.get("created_at")) or now
            item["created_at"] = created_at
            item["updated_at"] = now
            section[item["id"]] = _clone(item)
            self._persist_unlocked()
            return _clone(item)

    def delete_admin_account(self, account_id: str) -> None:
        target = str(account_id or "").strip()
        if not target:
            raise ValueError("account_id is required")
        with self._lock:
            orders = self._ensure_dict_section("admin_payment_orders")
            order_ids = [
                order_id
                for order_id, row in orders.items()
                if isinstance(row, dict) and str(row.get("account_id") or "") == target
            ]
            for order_id in order_ids:
                orders.pop(order_id, None)
            self._data["admin_account_groups"] = [
                row
                for row in self._ensure_list_section("admin_account_groups")
                if str((row or {}).get("account_id") or "") != target
            ]
            self._data["admin_balance_events"] = {
                event_id: row
                for event_id, row in self._ensure_dict_section("admin_balance_events").items()
                if not (isinstance(row, dict) and str(row.get("account_id") or "") == target)
            }
            self._data["admin_api_keys"] = {
                key_id: row
                for key_id, row in self._ensure_dict_section("admin_api_keys").items()
                if not (isinstance(row, dict) and str(row.get("account_id") or "") == target)
            }
            self._data["admin_account_subscriptions"] = {
                sub_id: row
                for sub_id, row in self._ensure_dict_section("admin_account_subscriptions").items()
                if not (isinstance(row, dict) and str(row.get("account_id") or "") == target)
            }
            self._data["admin_payment_fulfillment_logs"] = {
                log_id: row
                for log_id, row in self._ensure_dict_section("admin_payment_fulfillment_logs").items()
                if not (isinstance(row, dict) and str(row.get("order_id") or "") in order_ids)
            }
            self._data["admin_payment_webhook_events"] = {
                event_id: row
                for event_id, row in self._ensure_dict_section("admin_payment_webhook_events").items()
                if not (isinstance(row, dict) and str(row.get("order_id") or "") in order_ids)
            }
            self._ensure_dict_section("admin_accounts").pop(target, None)
            self._persist_unlocked()

    def adjust_admin_account_balance(
        self,
        account_id: str,
        amount_cents: int,
        *,
        event_type: str,
        note: str = "",
        actor_type: str = "admin",
        actor_id: str = "",
    ) -> dict:
        target = str(account_id or "").strip()
        if not target:
            raise ValueError("account_id is required")
        delta = int(amount_cents or 0)
        normalized_type = str(event_type or "").strip() or ("deposit" if delta >= 0 else "withdraw")
        now = time.time()
        with self._lock:
            accounts = self._ensure_dict_section("admin_accounts")
            current = accounts.get(target)
            if not isinstance(current, dict):
                raise ValueError("user not found")
            before_balance = _safe_int(current.get("balance_cents"))
            after_balance = before_balance + delta
            if after_balance < 0:
                raise ValueError("insufficient balance")
            current["balance_cents"] = after_balance
            current["updated_at"] = now
            accounts[target] = current
            event_id = f"bal_{uuid.uuid4().hex[:16]}"
            event = {
                "id": event_id,
                "account_id": target,
                "event_type": normalized_type,
                "amount_cents": delta,
                "before_balance_cents": before_balance,
                "after_balance_cents": after_balance,
                "note": str(note or ""),
                "actor_type": str(actor_type or "admin"),
                "actor_id": str(actor_id or ""),
                "created_at": now,
            }
            self._ensure_dict_section("admin_balance_events")[event_id] = _clone(event)
            self._persist_unlocked()
            return event

    def list_admin_balance_events(self, account_id: str | None = None, limit: int = 200) -> list[dict]:
        target = str(account_id or "").strip()
        accounts = {str(item.get("id") or ""): item for item in self.list_admin_accounts()}
        with self._lock:
            rows = [item for item in self._ensure_dict_section("admin_balance_events").values() if isinstance(item, dict)]
        if target:
            rows = [item for item in rows if str(item.get("account_id") or "") == target]
        rows.sort(key=lambda item: _safe_float(item.get("created_at")), reverse=True)
        items = []
        for row in rows[: max(0, int(limit or 0))]:
            item = _clone(row)
            item["account_name"] = str(accounts.get(str(item.get("account_id") or ""), {}).get("name") or "")
            items.append(item)
        return items

    def list_admin_groups(self) -> list[dict]:
        with self._lock:
            rows = [item for item in self._ensure_dict_section("admin_groups").values() if isinstance(item, dict)]
            rows.sort(
                key=lambda item: (
                    _safe_int(item.get("sort_order")),
                    -_safe_float(item.get("updated_at")),
                    -_safe_float(item.get("created_at")),
                )
            )
            return [_clone(item) for item in rows]

    def get_admin_group(self, group_id: str) -> dict:
        target = str(group_id or "").strip()
        if not target:
            return {}
        with self._lock:
            item = self._ensure_dict_section("admin_groups").get(target)
            return _clone(item) if isinstance(item, dict) else {}

    def upsert_admin_group(self, payload: dict) -> dict:
        now = time.time()
        item = {
            "id": str(payload.get("id") or "").strip(),
            "name": str(payload.get("name") or "").strip(),
            "description": str(payload.get("description") or ""),
            "platform": str(payload.get("platform") or "").strip(),
            "is_exclusive": payload.get("is_exclusive") is True,
            "rate_multiplier": _safe_float(payload.get("rate_multiplier") or 1) or 1.0,
            "extra": payload.get("extra") if isinstance(payload.get("extra"), dict) else {},
            "enabled": payload.get("enabled") is not False,
            "sort_order": _safe_int(payload.get("sort_order")),
        }
        if not item["id"] or not item["name"]:
            raise ValueError("missing required admin group fields")
        with self._lock:
            section = self._ensure_dict_section("admin_groups")
            current = section.get(item["id"]) if isinstance(section.get(item["id"]), dict) else {}
            item["created_at"] = _safe_float(current.get("created_at")) or now
            item["updated_at"] = now
            section[item["id"]] = _clone(item)
            self._persist_unlocked()
            return _clone(item)

    def delete_admin_group(self, group_id: str) -> None:
        target = str(group_id or "").strip()
        if not target:
            raise ValueError("group_id is required")
        with self._lock:
            self._data["admin_account_groups"] = [
                row
                for row in self._ensure_list_section("admin_account_groups")
                if str((row or {}).get("group_id") or "") != target
            ]
            for section_name in ("admin_api_keys", "admin_subscription_plans", "admin_account_subscriptions"):
                section = self._ensure_dict_section(section_name)
                for item in section.values():
                    if isinstance(item, dict) and str(item.get("group_id") or "") == target:
                        item["group_id"] = ""
                        item["updated_at"] = time.time()
            self._ensure_dict_section("admin_groups").pop(target, None)
            self._persist_unlocked()

    def replace_admin_account_groups(self, account_id: str, group_ids: list[str]) -> None:
        normalized_account_id = str(account_id or "").strip()
        if not normalized_account_id:
            raise ValueError("missing account_id")
        normalized_group_ids = sorted({str(group_id or "").strip() for group_id in (group_ids or []) if str(group_id or "").strip()})
        now = time.time()
        with self._lock:
            rows = [
                row
                for row in self._ensure_list_section("admin_account_groups")
                if str((row or {}).get("account_id") or "") != normalized_account_id
            ]
            rows.extend(
                {
                    "account_id": normalized_account_id,
                    "group_id": group_id,
                    "created_at": now,
                }
                for group_id in normalized_group_ids
            )
            self._data["admin_account_groups"] = rows
            self._persist_unlocked()

    def list_admin_account_groups(self) -> list[dict]:
        with self._lock:
            rows = [row for row in self._ensure_list_section("admin_account_groups") if isinstance(row, dict)]
            rows.sort(key=lambda item: _safe_float(item.get("created_at")), reverse=True)
            return [_clone(item) for item in rows]

    def list_admin_api_keys(self) -> list[dict]:
        groups = {str(item.get("id") or ""): item for item in self.list_admin_groups()}
        with self._lock:
            rows = [item for item in self._ensure_dict_section("admin_api_keys").values() if isinstance(item, dict)]
            rows.sort(
                key=lambda item: (_safe_float(item.get("updated_at")), _safe_float(item.get("created_at"))),
                reverse=True,
            )
            items = []
            for row in rows:
                item = _clone(row)
                item["group_name"] = str(groups.get(str(item.get("group_id") or ""), {}).get("name") or "")
                items.append(item)
            return items

    def get_admin_api_key(self, key_id: str) -> dict:
        target = str(key_id or "").strip()
        if not target:
            return {}
        with self._lock:
            item = self._ensure_dict_section("admin_api_keys").get(target)
            return _clone(item) if isinstance(item, dict) else {}

    def upsert_admin_api_key(self, payload: dict) -> dict:
        now = time.time()
        item = {
            "id": str(payload.get("id") or "").strip(),
            "account_id": str(payload.get("account_id") or "").strip(),
            "group_id": str(payload.get("group_id") or "").strip(),
            "name": str(payload.get("name") or "").strip(),
            "key_hash": str(payload.get("key_hash") or "").strip(),
            "key_preview": str(payload.get("key_preview") or "").strip(),
            "enabled": payload.get("enabled") is not False,
            "last_used_at": payload.get("last_used_at"),
        }
        if not item["id"] or not item["account_id"] or not item["name"] or not item["key_hash"] or not item["key_preview"]:
            raise ValueError("missing required admin api key fields")
        with self._lock:
            section = self._ensure_dict_section("admin_api_keys")
            current = section.get(item["id"]) if isinstance(section.get(item["id"]), dict) else {}
            item["created_at"] = _safe_float(current.get("created_at")) or now
            item["updated_at"] = now
            section[item["id"]] = _clone(item)
            self._persist_unlocked()
        if item["group_id"]:
            group = self.get_admin_group(item["group_id"])
            item["group_name"] = str(group.get("name") or "")
        else:
            item["group_name"] = ""
        return item

    def delete_admin_api_key(self, key_id: str) -> None:
        target = str(key_id or "").strip()
        if not target:
            raise ValueError("key_id is required")
        with self._lock:
            self._ensure_dict_section("admin_api_keys").pop(target, None)
            self._persist_unlocked()

    def touch_admin_api_key(self, key_id: str) -> None:
        now = time.time()
        with self._lock:
            item = self._ensure_dict_section("admin_api_keys").get(str(key_id or "").strip())
            if isinstance(item, dict):
                item["last_used_at"] = now
                item["updated_at"] = now
                self._persist_unlocked()

    def set_admin_api_key_enabled(self, key_id: str, enabled: bool) -> None:
        now = time.time()
        with self._lock:
            item = self._ensure_dict_section("admin_api_keys").get(str(key_id or "").strip())
            if isinstance(item, dict):
                item["enabled"] = bool(enabled)
                item["updated_at"] = now
                self._persist_unlocked()

    def find_admin_api_key_by_hash(self, key_hash: str) -> dict:
        normalized = str(key_hash or "").strip()
        if not normalized:
            return {}
        accounts = {str(item.get("id") or ""): item for item in self.list_admin_accounts()}
        groups = {str(item.get("id") or ""): item for item in self.list_admin_groups()}
        with self._lock:
            for row in self._ensure_dict_section("admin_api_keys").values():
                if not isinstance(row, dict) or str(row.get("key_hash") or "") != normalized:
                    continue
                account = accounts.get(str(row.get("account_id") or ""), {})
                allowed_group_ids = (
                    account.get("allowed_group_ids")
                    if isinstance(account.get("allowed_group_ids"), list)
                    else []
                )
                return {
                    "id": str(row.get("id") or ""),
                    "account_id": str(row.get("account_id") or ""),
                    "group_id": str(row.get("group_id") or ""),
                    "name": str(row.get("name") or ""),
                    "key_hash": str(row.get("key_hash") or ""),
                    "key_preview": str(row.get("key_preview") or ""),
                    "enabled": row.get("enabled") is not False,
                    "account_name": str(account.get("name") or ""),
                    "account_source_type": str(account.get("source_type") or ""),
                    "account_enabled": account.get("enabled") is not False if account else True,
                    "account_note": str(account.get("note") or ""),
                    "account_status": str(account.get("status") or ""),
                    "account_allowed_group_ids": _clone(allowed_group_ids if isinstance(allowed_group_ids, list) else []),
                    "group_name": str(groups.get(str(row.get("group_id") or ""), {}).get("name") or ""),
                }
        return {}

    def list_admin_subscription_plans(self) -> list[dict]:
        with self._lock:
            rows = [item for item in self._ensure_dict_section("admin_subscription_plans").values() if isinstance(item, dict)]
            rows.sort(
                key=lambda item: (_safe_float(item.get("updated_at")), _safe_float(item.get("created_at"))),
                reverse=True,
            )
            return [_clone(item) for item in rows]

    def upsert_admin_subscription_plan(self, payload: dict) -> dict:
        now = time.time()
        item = {
            "id": str(payload.get("id") or "").strip(),
            "name": str(payload.get("name") or "").strip(),
            "group_id": str(payload.get("group_id") or "").strip(),
            "price_cents": _safe_int(payload.get("price_cents")),
            "validity_days": _safe_int(payload.get("validity_days") or 30),
            "daily_limit": _safe_int(payload.get("daily_limit")),
            "weekly_limit": _safe_int(payload.get("weekly_limit")),
            "monthly_limit": _safe_int(payload.get("monthly_limit")),
            "enabled": payload.get("enabled") is not False,
            "note": str(payload.get("note") or ""),
        }
        if not item["id"] or not item["name"]:
            raise ValueError("missing required admin subscription plan fields")
        with self._lock:
            section = self._ensure_dict_section("admin_subscription_plans")
            current = section.get(item["id"]) if isinstance(section.get(item["id"]), dict) else {}
            item["created_at"] = _safe_float(current.get("created_at")) or now
            item["updated_at"] = now
            section[item["id"]] = _clone(item)
            self._persist_unlocked()
            return _clone(item)

    def list_admin_account_subscriptions(self) -> list[dict]:
        accounts = {str(item.get("id") or ""): item for item in self.list_admin_accounts()}
        plans = {str(item.get("id") or ""): item for item in self.list_admin_subscription_plans()}
        groups = {str(item.get("id") or ""): item for item in self.list_admin_groups()}
        with self._lock:
            rows = [item for item in self._ensure_dict_section("admin_account_subscriptions").values() if isinstance(item, dict)]
            rows.sort(
                key=lambda item: (_safe_float(item.get("updated_at")), _safe_float(item.get("created_at"))),
                reverse=True,
            )
            items = []
            for row in rows:
                item = _clone(row)
                account = accounts.get(str(item.get("account_id") or ""), {})
                plan = plans.get(str(item.get("plan_id") or ""), {})
                group = groups.get(str(item.get("group_id") or ""), {})
                item["account_name"] = str(account.get("name") or "")
                item["plan_name"] = str(plan.get("name") or "")
                item["group_name"] = str(group.get("name") or "")
                item["price_cents"] = _safe_int(plan.get("price_cents"))
                items.append(item)
            return items

    def upsert_admin_account_subscription(self, payload: dict) -> dict:
        now = time.time()
        expires_at = payload.get("expires_at")
        item = {
            "id": str(payload.get("id") or "").strip(),
            "account_id": str(payload.get("account_id") or "").strip(),
            "plan_id": str(payload.get("plan_id") or "").strip(),
            "group_id": str(payload.get("group_id") or "").strip(),
            "status": str(payload.get("status") or "active").strip() or "active",
            "started_at": _safe_float(payload.get("started_at") or now),
            "expires_at": _safe_float(expires_at) if expires_at is not None else None,
            "daily_used": _safe_int(payload.get("daily_used")),
            "weekly_used": _safe_int(payload.get("weekly_used")),
            "monthly_used": _safe_int(payload.get("monthly_used")),
        }
        if not item["id"] or not item["account_id"] or not item["plan_id"]:
            raise ValueError("missing required admin account subscription fields")
        with self._lock:
            section = self._ensure_dict_section("admin_account_subscriptions")
            current = section.get(item["id"]) if isinstance(section.get(item["id"]), dict) else {}
            item["created_at"] = _safe_float(current.get("created_at")) or now
            item["updated_at"] = now
            section[item["id"]] = _clone(item)
            self._persist_unlocked()
            return _clone(item)

    def list_admin_payment_channels(self) -> list[dict]:
        with self._lock:
            rows = [item for item in self._ensure_dict_section("admin_payment_channels").values() if isinstance(item, dict)]
            rows.sort(
                key=lambda item: (_safe_float(item.get("updated_at")), _safe_float(item.get("created_at"))),
                reverse=True,
            )
            return [_clone(item) for item in rows]

    def upsert_admin_payment_channel(self, payload: dict) -> dict:
        now = time.time()
        item = {
            "id": str(payload.get("id") or "").strip(),
            "name": str(payload.get("name") or "").strip(),
            "provider": str(payload.get("provider") or "").strip(),
            "config": payload.get("config") if isinstance(payload.get("config"), dict) else {},
            "enabled": payload.get("enabled") is not False,
        }
        if not item["id"] or not item["name"] or not item["provider"]:
            raise ValueError("missing required payment channel fields")
        with self._lock:
            section = self._ensure_dict_section("admin_payment_channels")
            current = section.get(item["id"]) if isinstance(section.get(item["id"]), dict) else {}
            item["created_at"] = _safe_float(current.get("created_at")) or now
            item["updated_at"] = now
            section[item["id"]] = _clone(item)
            self._persist_unlocked()
            return _clone(item)

    def list_admin_payment_orders(self) -> list[dict]:
        plans = {str(item.get("id") or ""): item for item in self.list_admin_subscription_plans()}
        groups = {str(item.get("id") or ""): item for item in self.list_admin_groups()}
        with self._lock:
            rows = [item for item in self._ensure_dict_section("admin_payment_orders").values() if isinstance(item, dict)]
            rows.sort(
                key=lambda item: (_safe_float(item.get("updated_at")), _safe_float(item.get("created_at"))),
                reverse=True,
            )
            items = []
            for row in rows:
                item = _clone(row)
                plan = plans.get(str(item.get("plan_id") or ""), {})
                group = groups.get(str(plan.get("group_id") or ""), {})
                item["group_id"] = str(plan.get("group_id") or "")
                item["group_name"] = str(group.get("name") or "")
                item["plan_price_cents"] = _safe_int(plan.get("price_cents"))
                items.append(item)
            return items

    def record_payment_fulfillment_log(self, payload: dict) -> dict:
        now = time.time()
        item = {
            "id": str(payload.get("id") or "").strip(),
            "order_id": str(payload.get("order_id") or "").strip(),
            "subscription_id": str(payload.get("subscription_id") or "").strip(),
            "action": str(payload.get("action") or "").strip(),
            "actor_type": str(payload.get("actor_type") or "").strip() or "system",
            "actor_id": str(payload.get("actor_id") or "").strip(),
            "note_text": str(payload.get("note_text") or "").strip(),
            "payload": payload.get("payload") if isinstance(payload.get("payload"), dict) else {},
            "created_at": now,
        }
        if not item["id"] or not item["order_id"] or not item["action"]:
            raise ValueError("missing required payment fulfillment log fields")
        with self._lock:
            self._ensure_dict_section("admin_payment_fulfillment_logs")[item["id"]] = _clone(item)
            self._persist_unlocked()
            return item

    def list_payment_fulfillment_logs(self, order_id: str) -> list[dict]:
        target = str(order_id or "").strip()
        if not target:
            return []
        with self._lock:
            rows = [
                item
                for item in self._ensure_dict_section("admin_payment_fulfillment_logs").values()
                if isinstance(item, dict) and str(item.get("order_id") or "") == target
            ]
            rows.sort(key=lambda item: _safe_float(item.get("created_at")), reverse=True)
            return [_clone(item) for item in rows]

    def get_admin_payment_order(self, order_id: str) -> dict:
        target = str(order_id or "").strip()
        if not target:
            return {}
        with self._lock:
            item = self._ensure_dict_section("admin_payment_orders").get(target)
            return _clone(item) if isinstance(item, dict) else {}

    def upsert_admin_payment_order(self, payload: dict) -> dict:
        now = time.time()
        paid_at = payload.get("paid_at")
        item = {
            "id": str(payload.get("id") or "").strip(),
            "account_id": str(payload.get("account_id") or "").strip(),
            "plan_id": str(payload.get("plan_id") or "").strip(),
            "subscription_id": str(payload.get("subscription_id") or "").strip(),
            "channel_id": str(payload.get("channel_id") or "").strip(),
            "amount_cents": _safe_int(payload.get("amount_cents")),
            "currency": str(payload.get("currency") or "CNY").strip() or "CNY",
            "status": str(payload.get("status") or "").strip(),
            "provider_order_id": str(payload.get("provider_order_id") or "").strip(),
            "resume_token": str(payload.get("resume_token") or "").strip(),
            "payload": payload.get("payload") if isinstance(payload.get("payload"), dict) else {},
            "provider_payload": payload.get("provider_payload") if isinstance(payload.get("provider_payload"), dict) else {},
            "paid_at": _safe_float(paid_at) if paid_at is not None else None,
        }
        if not item["id"] or not item["account_id"] or not item["plan_id"] or not item["status"]:
            raise ValueError("missing required payment order fields")
        with self._lock:
            section = self._ensure_dict_section("admin_payment_orders")
            current = section.get(item["id"]) if isinstance(section.get(item["id"]), dict) else {}
            item["created_at"] = _safe_float(current.get("created_at")) or now
            item["updated_at"] = now
            section[item["id"]] = _clone(item)
            self._persist_unlocked()
            return _clone(item)

    def record_payment_webhook_event(self, payload: dict) -> dict:
        now = time.time()
        item = {
            "event_id": str(payload.get("event_id") or "").strip(),
            "order_id": str(payload.get("order_id") or "").strip(),
            "provider": str(payload.get("provider") or "").strip(),
            "signature": str(payload.get("signature") or "").strip(),
            "payload": payload.get("payload") if isinstance(payload.get("payload"), dict) else {},
            "processed": payload.get("processed") is True,
        }
        if not item["event_id"] or not item["order_id"] or not item["provider"]:
            raise ValueError("missing required payment webhook event fields")
        with self._lock:
            section = self._ensure_dict_section("admin_payment_webhook_events")
            current = section.get(item["event_id"]) if isinstance(section.get(item["event_id"]), dict) else {}
            item["created_at"] = _safe_float(current.get("created_at")) or now
            item["updated_at"] = now
            section[item["event_id"]] = _clone(item)
            self._persist_unlocked()
            return _clone(item)

    def get_payment_webhook_event(self, event_id: str) -> dict:
        target = str(event_id or "").strip()
        if not target:
            return {}
        with self._lock:
            item = self._ensure_dict_section("admin_payment_webhook_events").get(target)
            return _clone(item) if isinstance(item, dict) else {}

    def get_admin_account_subscription(self, subscription_id: str) -> dict:
        target = str(subscription_id or "").strip()
        if not target:
            return {}
        with self._lock:
            item = self._ensure_dict_section("admin_account_subscriptions").get(target)
            return _clone(item) if isinstance(item, dict) else {}

    def get_active_subscription_context_for_account(self, account_id: str, group_id: str = "") -> dict:
        target = str(account_id or "").strip()
        if not target:
            return {}
        target_group_id = str(group_id or "").strip()
        now = time.time()
        plans = {str(item.get("id") or ""): item for item in self.list_admin_subscription_plans()}
        groups = {str(item.get("id") or ""): item for item in self.list_admin_groups()}
        with self._lock:
            rows = [
                item
                for item in self._ensure_dict_section("admin_account_subscriptions").values()
                if isinstance(item, dict)
                and str(item.get("account_id") or "") == target
                and str(item.get("status") or "") == "active"
                and (
                    item.get("expires_at") is None
                    or _safe_float(item.get("expires_at")) > now
                )
                and (not target_group_id or str(item.get("group_id") or "") == target_group_id)
            ]
        rows.sort(
            key=lambda item: (_safe_float(item.get("updated_at")), _safe_float(item.get("created_at"))),
            reverse=True,
        )
        if not rows:
            return {}
        row = _clone(rows[0])
        plan = plans.get(str(row.get("plan_id") or ""), {})
        group = groups.get(str(row.get("group_id") or ""), {})
        return {
            "subscription_id": str(row.get("id") or ""),
            "account_id": str(row.get("account_id") or ""),
            "plan_id": str(row.get("plan_id") or ""),
            "group_id": str(row.get("group_id") or ""),
            "status": str(row.get("status") or ""),
            "started_at": _safe_float(row.get("started_at")),
            "expires_at": _safe_float(row.get("expires_at")) if row.get("expires_at") is not None else None,
            "plan_name": str(plan.get("name") or ""),
            "plan_price_cents": _safe_int(plan.get("price_cents")),
            "price_cents": _safe_int(plan.get("price_cents")),
            "group_name": str(group.get("name") or ""),
        }

    def extend_admin_account_subscription(self, subscription_id: str, extra_days: int) -> dict:
        current = self.get_admin_account_subscription(subscription_id)
        if not current:
            raise ValueError("subscription not found")
        now = time.time()
        current_expires = current.get("expires_at")
        base = _safe_float(current_expires) or now
        current["expires_at"] = base + max(0, int(extra_days)) * 86400
        current["updated_at"] = now
        return self.upsert_admin_account_subscription(current)

    def revoke_admin_account_subscription(self, subscription_id: str) -> dict:
        current = self.get_admin_account_subscription(subscription_id)
        if not current:
            raise ValueError("subscription not found")
        current["status"] = "revoked"
        current["updated_at"] = time.time()
        return self.upsert_admin_account_subscription(current)

    def reset_admin_account_subscription_quota(
        self,
        subscription_id: str,
        *,
        daily: bool,
        weekly: bool,
        monthly: bool,
    ) -> dict:
        current = self.get_admin_account_subscription(subscription_id)
        if not current:
            raise ValueError("subscription not found")
        if daily:
            current["daily_used"] = 0
        if weekly:
            current["weekly_used"] = 0
        if monthly:
            current["monthly_used"] = 0
        current["updated_at"] = time.time()
        return self.upsert_admin_account_subscription(current)

    def load_request_cache(self, cache_key: str) -> dict:
        now = time.time()
        target = str(cache_key or "")
        if not target:
            return {}
        with self._lock:
            section = self._ensure_dict_section("request_cache")
            expired = [
                key for key, row in section.items()
                if isinstance(row, dict) and _safe_float(row.get("expires_at")) <= now
            ]
            for key in expired:
                section.pop(key, None)
            item = section.get(target)
            if expired:
                self._persist_unlocked()
            return _clone(item) if isinstance(item, dict) else {}

    def save_request_cache(self, payload: dict) -> None:
        if not isinstance(payload, dict):
            return
        cache_key = str(payload.get("cache_key") or "")
        response_body = payload.get("response_body")
        if not cache_key or not isinstance(response_body, dict):
            return
        with self._lock:
            self._ensure_dict_section("request_cache")[cache_key] = _clone(payload)
            self._persist_unlocked()

    def delete_expired_request_cache(self) -> None:
        now = time.time()
        with self._lock:
            section = self._ensure_dict_section("request_cache")
            keys = [
                key for key, row in section.items()
                if isinstance(row, dict) and _safe_float(row.get("expires_at")) <= now
            ]
            for key in keys:
                section.pop(key, None)
            if keys:
                self._persist_unlocked()

    def clear_request_cache(self) -> None:
        with self._lock:
            self._data["request_cache"] = {}
            self._persist_unlocked()

    def load_tool_result_cache_many(self, cache_keys: list[str]) -> dict:
        keys = [str(item or "") for item in (cache_keys or []) if str(item or "")]
        if not keys:
            return {}
        now = time.time()
        with self._lock:
            section = self._ensure_dict_section("tool_result_cache")
            expired = [
                key for key, row in section.items()
                if isinstance(row, dict) and _safe_float(row.get("expires_at")) <= now
            ]
            for key in expired:
                section.pop(key, None)
            if expired:
                self._persist_unlocked()
            return {
                key: _clone(section[key])
                for key in keys
                if isinstance(section.get(key), dict)
            }

    def save_tool_result_cache(self, payloads: list[dict]) -> int:
        valid_payloads = []
        for payload in payloads or []:
            if not isinstance(payload, dict):
                continue
            cache_key = str(payload.get("cache_key") or "")
            result_message = payload.get("result_message")
            if not cache_key or not isinstance(result_message, dict):
                continue
            valid_payloads.append((cache_key, _clone(payload)))
        if not valid_payloads:
            return 0
        with self._lock:
            section = self._ensure_dict_section("tool_result_cache")
            for cache_key, payload in valid_payloads:
                section[cache_key] = payload
            self._persist_unlocked()
        return len(valid_payloads)

    def clear_tool_result_cache(self) -> None:
        with self._lock:
            self._data["tool_result_cache"] = {}
            self._persist_unlocked()

    def load_interrupted_response(self, resume_key: str) -> dict:
        now = time.time()
        target = str(resume_key or "")
        if not target:
            return {}
        with self._lock:
            section = self._ensure_dict_section("interrupted_responses")
            expired = [
                key for key, row in section.items()
                if isinstance(row, dict) and _safe_float(row.get("expires_at")) <= now
            ]
            for key in expired:
                section.pop(key, None)
            item = section.get(target)
            if expired:
                self._persist_unlocked()
            return _clone(item) if isinstance(item, dict) else {}

    def save_interrupted_response(self, payload: dict) -> None:
        if not isinstance(payload, dict):
            return
        resume_key = str(payload.get("resume_key") or "")
        partial_text = str(payload.get("partial_text") or "")
        if not resume_key or not partial_text:
            return
        with self._lock:
            self._ensure_dict_section("interrupted_responses")[resume_key] = _clone(payload)
            self._persist_unlocked()

    def delete_interrupted_response(self, resume_key: str) -> None:
        target = str(resume_key or "")
        if not target:
            return
        with self._lock:
            self._ensure_dict_section("interrupted_responses").pop(target, None)
            self._persist_unlocked()

    def delete_interrupted_responses(self, resume_keys: list[str]) -> None:
        keys = [str(item or "") for item in (resume_keys or []) if str(item or "")]
        if not keys:
            return
        with self._lock:
            section = self._ensure_dict_section("interrupted_responses")
            for key in keys:
                section.pop(key, None)
            self._persist_unlocked()

    def delete_expired_interrupted_responses(self) -> None:
        now = time.time()
        with self._lock:
            section = self._ensure_dict_section("interrupted_responses")
            keys = [
                key for key, row in section.items()
                if isinstance(row, dict) and _safe_float(row.get("expires_at")) <= now
            ]
            for key in keys:
                section.pop(key, None)
            if keys:
                self._persist_unlocked()

    def count_interrupted_responses(self) -> int:
        now = time.time()
        with self._lock:
            section = self._ensure_dict_section("interrupted_responses")
            keys = [
                key for key, row in section.items()
                if isinstance(row, dict) and _safe_float(row.get("expires_at")) <= now
            ]
            for key in keys:
                section.pop(key, None)
            if keys:
                self._persist_unlocked()
            return sum(
                1
                for row in section.values()
                if isinstance(row, dict) and _safe_float(row.get("expires_at")) > now
            )
