from __future__ import annotations

import time
import uuid
from typing import Any

from local_proxy.admin.payment_provider import (
    build_order_provider_payload,
    normalize_webhook_payload,
    verify_provider_signature,
)
from local_proxy.http.proxy_auth import generate_proxy_api_key, hash_proxy_api_key, preview_proxy_api_key


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0


def _coerce_text(value: Any) -> str:
    return str(value or "").strip()


ALLOWED_PAYMENT_ORDER_TRANSITIONS = {
    "pending": {"paid", "failed", "cancelled"},
    "paid": set(),
    "failed": set(),
    "cancelled": set(),
}


class AdminAnalyticsService:
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

    def _managed_users(self) -> dict[str, dict]:
        if self.storage is None:
            return {}
        items = self.storage.list_admin_users()
        return {str(item.get("external_key") or ""): item for item in items if isinstance(item, dict)}

    def _group_map(self) -> tuple[dict[str, dict], dict[str, list[str]]]:
        groups = {}
        memberships: dict[str, list[str]] = {}
        if self.storage is None:
            return groups, memberships
        for group in self.storage.list_admin_groups():
            groups[str(group.get("id") or "")] = group
        for row in self.storage.list_admin_user_groups():
            user_id = str(row.get("user_id") or "")
            group_id = str(row.get("group_id") or "")
            if user_id and group_id:
                memberships.setdefault(user_id, []).append(group_id)
        return groups, memberships

    def _consumer_key(self, row: dict) -> tuple[str, str, str, str]:
        consumer_id = _coerce_text(row.get("proxy_consumer_id"))
        consumer_name = _coerce_text(row.get("proxy_consumer_name"))
        consumer_type = _coerce_text(row.get("proxy_consumer_type")) or "anonymous"
        preview = _coerce_text(row.get("proxy_consumer_preview"))
        if not consumer_id:
            consumer_id = "anonymous"
        if not consumer_name:
            consumer_name = "未归属"
        return consumer_id, consumer_name, consumer_type, preview

    def _resolve_user_metadata(self, consumer_id: str, consumer_name: str, consumer_type: str, preview: str) -> dict:
        managed_users = self._managed_users()
        external_key = consumer_id if consumer_id != "anonymous" else ""
        stored = managed_users.get(external_key, {})
        return {
            "id": _coerce_text(stored.get("id")) or consumer_id,
            "name": _coerce_text(stored.get("name")) or consumer_name,
            "type": _coerce_text(stored.get("source_type")) or consumer_type,
            "preview": preview,
            "external_key": external_key,
            "enabled": stored.get("enabled") is not False if stored else True,
            "note": _coerce_text(stored.get("note")),
        }

    def list_users(self, limit: int = 200) -> dict:
        rows = self._load_recent_requests()
        groups, memberships = self._group_map()
        users: dict[str, dict] = {}
        for row in rows:
            consumer_id, consumer_name, consumer_type, preview = self._consumer_key(row)
            resolved = self._resolve_user_metadata(consumer_id, consumer_name, consumer_type, preview)
            user_id = resolved["id"]
            group_ids = memberships.get(user_id, [])
            primary_group = groups.get(group_ids[0], {}) if group_ids else {}
            entry = users.setdefault(
                user_id,
                {
                    **resolved,
                    "request_count": 0,
                    "error_count": 0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "input_bytes": 0,
                    "output_bytes": 0,
                    "last_seen_at": "",
                    "group_ids": group_ids,
                    "group_id": _coerce_text(primary_group.get("id")) or "",
                    "group_name": _coerce_text(primary_group.get("name")) or "",
                },
            )
            entry["request_count"] += 1
            if row.get("error") or _safe_int(row.get("status_code")) >= 400:
                entry["error_count"] += 1
            entry["prompt_tokens"] += _safe_int(row.get("prompt_tokens"))
            entry["completion_tokens"] += _safe_int(row.get("completion_tokens"))
            entry["total_tokens"] += _safe_int(row.get("total_tokens"))
            entry["input_bytes"] += _safe_int(row.get("input_bytes"))
            entry["output_bytes"] += _safe_int(row.get("bytes_sent"))
            started_at = _coerce_text(row.get("started_at"))
            if started_at and started_at > _coerce_text(entry.get("last_seen_at")):
                entry["last_seen_at"] = started_at

        stored_users = self._managed_users()
        for external_key, stored in stored_users.items():
            user_id = _coerce_text(stored.get("id"))
            if not user_id or user_id in users:
                continue
            group_ids = memberships.get(user_id, [])
            primary_group = groups.get(group_ids[0], {}) if group_ids else {}
            users[user_id] = {
                "id": user_id,
                "name": _coerce_text(stored.get("name")) or "未命名用户",
                "type": _coerce_text(stored.get("source_type")) or "managed",
                "preview": "",
                "external_key": external_key,
                "enabled": stored.get("enabled") is not False,
                "note": _coerce_text(stored.get("note")),
                "request_count": 0,
                "error_count": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "input_bytes": 0,
                "output_bytes": 0,
                "last_seen_at": "",
                "group_ids": group_ids,
                "group_id": _coerce_text(primary_group.get("id")) or "",
                "group_name": _coerce_text(primary_group.get("name")) or "",
            }

        items = sorted(
            users.values(),
            key=lambda item: (
                -_safe_int(item.get("request_count")),
                -_safe_int(item.get("total_tokens")),
                _coerce_text(item.get("name")),
            ),
        )
        return {"ok": True, "items": items[:limit], "total": len(items)}

    def upsert_user(self, payload: dict) -> dict:
        if self.storage is None:
            raise RuntimeError("storage not configured")
        item = {
            "id": _coerce_text(payload.get("id")) or f"user_{uuid.uuid4().hex[:16]}",
            "name": _coerce_text(payload.get("name")),
            "external_key": _coerce_text(payload.get("external_key")),
            "source_type": _coerce_text(payload.get("source_type")) or "managed",
            "enabled": payload.get("enabled") is not False,
            "note": _coerce_text(payload.get("note")),
        }
        if not item["name"] or not item["external_key"]:
            raise ValueError("name and external_key are required")
        group_ids = payload.get("group_ids") if isinstance(payload.get("group_ids"), list) else []
        saved = self.storage.upsert_admin_user(item)
        self.storage.replace_admin_user_groups(saved["id"], group_ids)
        return {"ok": True, "item": saved}

    def list_groups(self) -> dict:
        rows = self._load_recent_requests()
        stored_groups = {}
        memberships: dict[str, list[str]] = {}
        if self.storage is not None:
            for group in self.storage.list_admin_groups():
                stored_groups[_coerce_text(group.get("id"))] = {
                    **group,
                    "user_ids": set(),
                    "request_count": 0,
                    "error_count": 0,
                    "total_tokens": 0,
                    "input_bytes": 0,
                    "output_bytes": 0,
                }
            for row in self.storage.list_admin_user_groups():
                user_id = _coerce_text(row.get("user_id"))
                group_id = _coerce_text(row.get("group_id"))
                if user_id and group_id:
                    memberships.setdefault(user_id, []).append(group_id)
                    if group_id in stored_groups:
                        stored_groups[group_id]["user_ids"].add(user_id)

        users = self.list_users(limit=5000).get("items", [])
        user_map = {str(item.get("id") or ""): item for item in users if isinstance(item, dict)}
        for row in rows:
            consumer_id, consumer_name, consumer_type, preview = self._consumer_key(row)
            resolved = self._resolve_user_metadata(consumer_id, consumer_name, consumer_type, preview)
            user_id = resolved["id"]
            target_group_ids = memberships.get(user_id) or []
            if not target_group_ids:
                target_group_ids = [f"default:{resolved['type']}"]
                stored_groups.setdefault(
                    target_group_ids[0],
                    {
                        "id": target_group_ids[0],
                        "name": "托管 Key" if resolved["type"] == "managed" else ("环境 Key" if resolved["type"] == "env" else "未分组"),
                        "description": "",
                        "enabled": True,
                        "sort_order": 0,
                        "user_ids": set(),
                        "request_count": 0,
                        "error_count": 0,
                        "total_tokens": 0,
                        "input_bytes": 0,
                        "output_bytes": 0,
                    },
                )
            for group_id in target_group_ids:
                entry = stored_groups.setdefault(
                    group_id,
                    {
                        "id": group_id,
                        "name": group_id,
                        "description": "",
                        "enabled": True,
                        "sort_order": 0,
                        "user_ids": set(),
                        "request_count": 0,
                        "error_count": 0,
                        "total_tokens": 0,
                        "input_bytes": 0,
                        "output_bytes": 0,
                    },
                )
                entry["user_ids"].add(user_id)
                entry["request_count"] += 1
                if row.get("error") or _safe_int(row.get("status_code")) >= 400:
                    entry["error_count"] += 1
                entry["total_tokens"] += _safe_int(row.get("total_tokens"))
                entry["input_bytes"] += _safe_int(row.get("input_bytes"))
                entry["output_bytes"] += _safe_int(row.get("bytes_sent"))

        items = []
        for entry in stored_groups.values():
            items.append(
                {
                    **entry,
                    "user_count": len(entry.get("user_ids") or []),
                }
            )
            items[-1].pop("user_ids", None)
        items.sort(key=lambda item: (_safe_int(item.get("sort_order")), -_safe_int(item.get("request_count")), _coerce_text(item.get("name"))))
        return {"ok": True, "items": items, "total": len(items)}

    def upsert_group(self, payload: dict) -> dict:
        if self.storage is None:
            raise RuntimeError("storage not configured")
        item = {
            "id": _coerce_text(payload.get("id")) or f"group_{uuid.uuid4().hex[:16]}",
            "name": _coerce_text(payload.get("name")),
            "description": _coerce_text(payload.get("description")),
            "enabled": payload.get("enabled") is not False,
            "sort_order": _safe_int(payload.get("sort_order")),
        }
        if not item["name"]:
            raise ValueError("group name is required")
        saved = self.storage.upsert_admin_group(item)
        return {"ok": True, "item": saved}

    def list_usage(self, limit: int = 200) -> dict:
        rows = self._load_recent_requests(limit=max(limit, 500))
        items = []
        for row in rows[:limit]:
            consumer_id, consumer_name, consumer_type, preview = self._consumer_key(row)
            resolved = self._resolve_user_metadata(consumer_id, consumer_name, consumer_type, preview)
            prompt_tokens = _safe_int(row.get("prompt_tokens"))
            completion_tokens = _safe_int(row.get("completion_tokens"))
            total_tokens = _safe_int(row.get("total_tokens")) or (prompt_tokens + completion_tokens)
            items.append(
                {
                    "request_id": _coerce_text(row.get("request_id")),
                    "started_at": _coerce_text(row.get("started_at")),
                    "consumer_id": resolved["id"],
                    "consumer_name": resolved["name"],
                    "consumer_type": resolved["type"],
                    "consumer_preview": preview,
                    "model": _coerce_text(row.get("logical_model") or row.get("model")),
                    "resolved_model": _coerce_text(row.get("resolved_model")),
                    "pool_name": _coerce_text(row.get("pool_name")),
                    "route_url": _coerce_text(row.get("route_url") or row.get("upstream_url")),
                    "status_code": _safe_int(row.get("status_code")),
                    "duration_ms": _safe_int(row.get("duration_ms")),
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": total_tokens,
                    "input_bytes": _safe_int(row.get("input_bytes")),
                    "output_bytes": _safe_int(row.get("bytes_sent")),
                    "cache_read_tokens": _safe_int(row.get("cache_read_input_tokens")),
                    "cache_write_tokens": _safe_int(row.get("cache_creation_input_tokens")),
                    "local_cache_status": _coerce_text(row.get("local_response_cache_status") or row.get("cache_status")),
                    "upstream_cache_status": _coerce_text(row.get("upstream_prompt_cache_status")),
                    "error": _coerce_text(row.get("error")),
                }
            )
        return {"ok": True, "items": items, "total": len(items)}

    def dashboard_summary(self) -> dict:
        users = self.list_users(limit=500).get("items", [])
        groups = self.list_groups().get("items", [])
        usage = self.list_usage(limit=500).get("items", [])
        return {
            "ok": True,
            "user_count": len(users),
            "group_count": len(groups),
            "request_count": len(usage),
            "total_tokens": sum(_safe_int(item.get("total_tokens")) for item in usage),
            "input_bytes": sum(_safe_int(item.get("input_bytes")) for item in usage),
            "output_bytes": sum(_safe_int(item.get("output_bytes")) for item in usage),
            "error_count": sum(1 for item in usage if _safe_int(item.get("status_code")) >= 400 or item.get("error")),
            "top_users": users[:5],
            "top_groups": groups[:5],
        }

    def list_api_keys(self) -> dict:
        if self.storage is None:
            return {"ok": True, "items": [], "total": 0}
        users = {str(item.get("id") or ""): item for item in self.list_users(limit=5000).get("items", [])}
        items = []
        for row in self.storage.list_admin_api_keys():
            user = users.get(str(row.get("user_id") or ""), {})
            items.append(
                {
                    **row,
                    "user_name": _coerce_text(user.get("name")) or _coerce_text(row.get("user_id")),
                }
            )
        return {"ok": True, "items": items, "total": len(items)}

    def create_api_key(self, payload: dict) -> dict:
        if self.storage is None:
            raise RuntimeError("storage not configured")
        user_id = _coerce_text(payload.get("user_id"))
        name = _coerce_text(payload.get("name")) or "默认业务 Key"
        if not user_id:
            raise ValueError("user_id is required")
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

    def list_subscription_plans(self) -> dict:
        if self.storage is None:
            return {"ok": True, "items": [], "total": 0}
        return {"ok": True, "items": self.storage.list_admin_subscription_plans(), "total": len(self.storage.list_admin_subscription_plans())}

    def upsert_subscription_plan(self, payload: dict) -> dict:
        if self.storage is None:
            raise RuntimeError("storage not configured")
        item = {
            "id": _coerce_text(payload.get("id")) or f"plan_{uuid.uuid4().hex[:16]}",
            "name": _coerce_text(payload.get("name")),
            "group_id": _coerce_text(payload.get("group_id")),
            "price_cents": _safe_int(payload.get("price_cents")),
            "validity_days": _safe_int(payload.get("validity_days") or 30),
            "daily_limit": _safe_int(payload.get("daily_limit")),
            "weekly_limit": _safe_int(payload.get("weekly_limit")),
            "monthly_limit": _safe_int(payload.get("monthly_limit")),
            "enabled": payload.get("enabled") is not False,
            "note": _coerce_text(payload.get("note")),
        }
        if not item["name"]:
            raise ValueError("plan name is required")
        return {"ok": True, "item": self.storage.upsert_admin_subscription_plan(item)}

    def list_user_subscriptions(self) -> dict:
        if self.storage is None:
            return {"ok": True, "items": [], "total": 0}
        return {"ok": True, "items": self.storage.list_admin_user_subscriptions(), "total": len(self.storage.list_admin_user_subscriptions())}

    def assign_subscription(self, payload: dict) -> dict:
        if self.storage is None:
            raise RuntimeError("storage not configured")
        item = {
            "id": _coerce_text(payload.get("id")) or f"sub_{uuid.uuid4().hex[:16]}",
            "user_id": _coerce_text(payload.get("user_id")),
            "plan_id": _coerce_text(payload.get("plan_id")),
            "group_id": _coerce_text(payload.get("group_id")),
            "status": _coerce_text(payload.get("status")) or "active",
            "started_at": payload.get("started_at"),
            "expires_at": payload.get("expires_at"),
            "daily_used": _safe_int(payload.get("daily_used")),
            "weekly_used": _safe_int(payload.get("weekly_used")),
            "monthly_used": _safe_int(payload.get("monthly_used")),
        }
        if not item["user_id"] or not item["plan_id"]:
            raise ValueError("user_id and plan_id are required")
        return {"ok": True, "item": self.storage.upsert_admin_user_subscription(item)}

    def extend_subscription(self, subscription_id: str, payload: dict) -> dict:
        if self.storage is None:
            raise RuntimeError("storage not configured")
        extra_days = _safe_int(payload.get("days"))
        if extra_days <= 0:
            raise ValueError("days must be greater than 0")
        return {"ok": True, "item": self.storage.extend_admin_user_subscription(subscription_id, extra_days)}

    def revoke_subscription(self, subscription_id: str) -> dict:
        if self.storage is None:
            raise RuntimeError("storage not configured")
        return {"ok": True, "item": self.storage.revoke_admin_user_subscription(subscription_id)}

    def reset_subscription_quota(self, subscription_id: str, payload: dict) -> dict:
        if self.storage is None:
            raise RuntimeError("storage not configured")
        return {
            "ok": True,
            "item": self.storage.reset_admin_user_subscription_quota(
                subscription_id,
                daily=payload.get("daily") is True,
                weekly=payload.get("weekly") is True,
                monthly=payload.get("monthly") is True,
            ),
        }

    def list_payment_channels(self) -> dict:
        if self.storage is None:
            return {"ok": True, "items": [], "total": 0}
        items = self.storage.list_admin_payment_channels()
        return {"ok": True, "items": items, "total": len(items)}

    def upsert_payment_channel(self, payload: dict) -> dict:
        if self.storage is None:
            raise RuntimeError("storage not configured")
        item = {
            "id": _coerce_text(payload.get("id")) or f"channel_{uuid.uuid4().hex[:16]}",
            "name": _coerce_text(payload.get("name")),
            "provider": _coerce_text(payload.get("provider")) or "manual",
            "config": payload.get("config") if isinstance(payload.get("config"), dict) else {},
            "enabled": payload.get("enabled") is not False,
        }
        if not item["name"]:
            raise ValueError("channel name is required")
        return {"ok": True, "item": self.storage.upsert_admin_payment_channel(item)}

    def payment_channel_config_template(self, provider: str) -> dict:
        provider_name = _coerce_text(provider) or "manual"
        if provider_name == "wechat":
            return {
                "mode": "native",
                "merchant_id": "",
                "app_id": "",
                "notify_url": "",
                "webhook_secret": "",
            }
        if provider_name == "alipay":
            return {
                "app_id": "",
                "notify_url": "",
                "webhook_secret": "",
                "return_url": "",
            }
        return {
            "mode": "manual",
            "notify_url": "",
        }

    def list_payment_orders(self) -> dict:
        if self.storage is None:
            return {"ok": True, "items": [], "total": 0}
        plans = {str(item.get("id") or ""): item for item in self.list_subscription_plans().get("items", [])}
        users = {str(item.get("id") or ""): item for item in self.list_users(limit=5000).get("items", [])}
        channels = {str(item.get("id") or ""): item for item in self.list_payment_channels().get("items", [])}
        items = []
        for row in self.storage.list_admin_payment_orders():
            items.append(
                {
                    **row,
                    "user_name": _coerce_text(users.get(str(row.get("user_id") or ""), {}).get("name")) or _coerce_text(row.get("user_id")),
                    "plan_name": _coerce_text(plans.get(str(row.get("plan_id") or ""), {}).get("name")) or _coerce_text(row.get("plan_id")),
                    "channel_name": _coerce_text(channels.get(str(row.get("channel_id") or ""), {}).get("name")) or _coerce_text(row.get("channel_id")),
                }
            )
        return {"ok": True, "items": items, "total": len(items)}

    def create_payment_order(self, payload: dict) -> dict:
        if self.storage is None:
            raise RuntimeError("storage not configured")
        user_id = _coerce_text(payload.get("user_id"))
        plan_id = _coerce_text(payload.get("plan_id"))
        channel_id = _coerce_text(payload.get("channel_id"))
        amount_cents = _safe_int(payload.get("amount_cents"))
        if not user_id or not plan_id:
            raise ValueError("user_id and plan_id are required")
        item = {
            "id": f"order_{uuid.uuid4().hex[:16]}",
            "user_id": user_id,
            "plan_id": plan_id,
            "subscription_id": "",
            "channel_id": channel_id,
            "amount_cents": amount_cents,
            "currency": _coerce_text(payload.get("currency")) or "CNY",
            "status": "pending",
            "provider_order_id": "",
            "resume_token": f"resume_{uuid.uuid4().hex[:16]}",
            "payload": payload.get("payload") if isinstance(payload.get("payload"), dict) else {},
            "paid_at": None,
        }
        saved = self.storage.upsert_admin_payment_order(item)
        channel = {}
        if channel_id:
            channel = next((entry for entry in self.list_payment_channels().get("items", []) if _coerce_text(entry.get("id")) == channel_id), {})
        provider = _coerce_text(channel.get("provider")) or "manual"
        channel_config = channel.get("config") if isinstance(channel.get("config"), dict) else {}
        provider_payload = build_order_provider_payload(
            provider=provider,
            channel_config=channel_config,
            order=saved,
        )
        saved["provider"] = provider
        saved["provider_payload"] = provider_payload
        saved = self.storage.upsert_admin_payment_order(saved)
        return {"ok": True, "item": saved}

    def fulfill_payment_order(self, order_id: str, payload: dict) -> dict:
        if self.storage is None:
            raise RuntimeError("storage not configured")
        current = self.storage.get_admin_payment_order(order_id)
        if not current:
            raise ValueError("payment order not found")
        current_status = _coerce_text(current.get("status")) or "pending"
        target_status = _coerce_text(payload.get("status")) or "paid"
        allowed = ALLOWED_PAYMENT_ORDER_TRANSITIONS.get(current_status, set())
        if target_status == current_status:
            return {"ok": True, "item": current}
        if target_status not in allowed:
            raise ValueError(f"invalid payment status transition: {current_status} -> {target_status}")

        if target_status != "paid":
            current["status"] = target_status
            current["payload"] = {
                **(current.get("payload") if isinstance(current.get("payload"), dict) else {}),
                **(payload if isinstance(payload, dict) else {}),
            }
            saved = self.storage.upsert_admin_payment_order(current)
            return {"ok": True, "item": saved}

        plan_id = _coerce_text(current.get("plan_id"))
        plan = next((item for item in self.list_subscription_plans().get("items", []) if _coerce_text(item.get("id")) == plan_id), None)
        if not plan:
            raise ValueError("subscription plan not found")

        now = payload.get("paid_at") or time.time()
        expires_at = float(now) + max(1, _safe_int(plan.get("validity_days") or 30)) * 86400
        subscription = self.storage.upsert_admin_user_subscription(
            {
                "id": _coerce_text(current.get("subscription_id")) or f"sub_{uuid.uuid4().hex[:16]}",
                "user_id": _coerce_text(current.get("user_id")),
                "plan_id": plan_id,
                "group_id": _coerce_text(plan.get("group_id")),
                "status": "active",
                "started_at": now,
                "expires_at": expires_at,
                "daily_used": 0,
                "weekly_used": 0,
                "monthly_used": 0,
            }
        )
        current["subscription_id"] = _coerce_text(subscription.get("id"))
        current["status"] = "paid"
        current["provider_order_id"] = _coerce_text(payload.get("provider_order_id")) or _coerce_text(current.get("provider_order_id"))
        current["paid_at"] = now
        current["payload"] = {
            **(current.get("payload") if isinstance(current.get("payload"), dict) else {}),
            **(payload if isinstance(payload, dict) else {}),
        }
        saved = self.storage.upsert_admin_payment_order(current)
        return {"ok": True, "item": saved, "subscription": subscription}

    def process_payment_webhook(self, order_id: str, payload: dict, signature: str = "") -> dict:
        if self.storage is None:
            raise RuntimeError("storage not configured")
        order = self.storage.get_admin_payment_order(order_id)
        if not order:
            raise ValueError("payment order not found")
        channel = {}
        channel_id = _coerce_text(order.get("channel_id"))
        if channel_id:
            channel = next((item for item in self.list_payment_channels().get("items", []) if _coerce_text(item.get("id")) == channel_id), {})
        provider = _coerce_text(payload.get("provider")) or _coerce_text(channel.get("provider")) or "manual"
        channel_config = channel.get("config") if isinstance(channel.get("config"), dict) else {}
        normalized_payload = normalize_webhook_payload(
            provider=provider,
            order_id=order_id,
            payload=payload if isinstance(payload, dict) else {},
        )
        event_id = _coerce_text(normalized_payload.get("event_id"))

        existing_event = self.storage.get_payment_webhook_event(event_id)
        if existing_event.get("processed"):
            return {"ok": True, "duplicate": True, "item": order}

        if not verify_provider_signature(
            provider=provider,
            channel_config=channel_config,
            raw_signature=signature,
            payload=normalized_payload,
        ):
            raise ValueError("invalid payment webhook signature")

        self.storage.record_payment_webhook_event(
            {
                "event_id": event_id,
                "order_id": order_id,
                "provider": provider,
                "signature": signature,
                "payload": normalized_payload,
                "processed": False,
            }
        )
        result = self.fulfill_payment_order(order_id, normalized_payload)
        self.storage.record_payment_webhook_event(
            {
                "event_id": event_id,
                "order_id": order_id,
                "provider": provider,
                "signature": signature,
                "payload": normalized_payload,
                "processed": True,
            }
        )
        return result
