from __future__ import annotations

import time
import uuid

from .base import AdminServiceBase, coerce_text, safe_float, safe_int
from local_proxy.platform import normalize_admin_group_payload


class AdminAnalyticsMixin(AdminServiceBase):
    def _user_public_fields(self, account: dict) -> dict:
        extra = account.get("extra") if isinstance(account.get("extra"), dict) else {}
        user_id = coerce_text(account.get("id"))
        user_name = coerce_text(account.get("name"))
        return {
            "user_id": user_id,
            "user_name": user_name,
            "user_key": coerce_text(account.get("external_key")),
            "user_preview": coerce_text(account.get("preview")),
            "user_source_type": coerce_text(account.get("source_type")),
            "user_role": coerce_text(account.get("role")) or "user",
            "user_status": coerce_text(account.get("status")) or ("active" if account.get("enabled") is not False else "disabled"),
            "user_enabled": account.get("enabled") is not False,
            "user_email": coerce_text(account.get("email") or extra.get("email")),
            "user_username": coerce_text(account.get("username") or extra.get("username")),
            "user_rpm_limit": safe_int(account.get("rpm_limit") or extra.get("rpm_limit")),
            "user_password_set": bool(extra.get("password_set") or extra.get("password_hash")),
            "user_balance_cents": safe_int(account.get("balance_cents")),
            "user_concurrency_limit": safe_int(account.get("concurrency_limit")),
            "user_allowed_group_ids": account.get("allowed_group_ids") if isinstance(account.get("allowed_group_ids"), list) else [],
            "account_id": user_id,
            "account_name": user_name,
        }

    def list_provider_accounts(self, limit: int = 500) -> dict:
        config = {}
        if self.storage is not None:
            try:
                config = self.storage.load_app_config("runtime_config")
            except Exception:
                config = {}
        pools = config.get("pools") if isinstance(config, dict) else []
        if not isinstance(pools, list):
            pools = []

        usage_rows = self._load_recent_requests(limit=5000)
        route_stats: dict[str, dict] = {}
        for row in usage_rows:
            route_url = coerce_text(row.get("route_url") or row.get("upstream_url"))
            if not route_url:
                continue
            entry = route_stats.setdefault(
                route_url,
                {
                    "request_count": 0,
                    "error_count": 0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "input_bytes": 0,
                    "output_bytes": 0,
                    "last_seen_at": "",
                    "model_names": set(),
                },
            )
            entry["request_count"] += 1
            if row.get("error") or safe_int(row.get("status_code")) >= 400:
                entry["error_count"] += 1
            entry["prompt_tokens"] += safe_int(row.get("prompt_tokens"))
            entry["completion_tokens"] += safe_int(row.get("completion_tokens"))
            entry["total_tokens"] += safe_int(row.get("total_tokens"))
            entry["input_bytes"] += safe_int(row.get("input_bytes"))
            entry["output_bytes"] += safe_int(row.get("bytes_sent"))
            model_name = coerce_text(row.get("resolved_model") or row.get("logical_model") or row.get("model"))
            if model_name:
                entry["model_names"].add(model_name)
            started_at = coerce_text(row.get("started_at"))
            if started_at and started_at > coerce_text(entry.get("last_seen_at")):
                entry["last_seen_at"] = started_at

        items = []
        for pool_index, pool in enumerate(pools):
            if not isinstance(pool, dict):
                continue
            pool_name = coerce_text(pool.get("name")) or f"pool_{pool_index + 1}"
            urls = pool.get("urls") if isinstance(pool.get("urls"), list) else []
            keys = pool.get("keys") if isinstance(pool.get("keys"), list) else []
            route_policy = pool.get("route_policy") if isinstance(pool.get("route_policy"), dict) else {}
            for route_index, raw_url in enumerate(urls):
                route_url = coerce_text(raw_url)
                if not route_url:
                    continue
                stats = route_stats.get(route_url, {})
                key_count = len([item for item in keys if isinstance(item, dict) and coerce_text(item.get("key"))])
                hostname = route_url.split("://", 1)[-1].split("/", 1)[0]
                items.append(
                    {
                        "id": f"provider_{pool_index}_{route_index}",
                        "pool_name": pool_name,
                        "pool_index": pool_index,
                        "route_url": route_url,
                        "route_index": route_index + 1,
                        "provider_name": hostname or route_url,
                        "enabled": pool.get("enabled") is not False,
                        "priority": safe_int(pool.get("priority")),
                        "key_count": key_count,
                        "request_count": safe_int(stats.get("request_count")),
                        "error_count": safe_int(stats.get("error_count")),
                        "prompt_tokens": safe_int(stats.get("prompt_tokens")),
                        "completion_tokens": safe_int(stats.get("completion_tokens")),
                        "total_tokens": safe_int(stats.get("total_tokens")),
                        "input_bytes": safe_int(stats.get("input_bytes")),
                        "output_bytes": safe_int(stats.get("output_bytes")),
                        "last_seen_at": coerce_text(stats.get("last_seen_at")),
                        "models": sorted(stats.get("model_names") or []),
                        "protocol": coerce_text(route_policy.get("text_upstream_protocol")) or "openai_chat_completions",
                        "cooldown_seconds": safe_int(route_policy.get("route_cooldown_seconds")),
                        "backoff_attempts": safe_int(route_policy.get("rate_limit_retry_attempts")),
                    }
                )

        items.sort(
            key=lambda item: (
                safe_int(item.get("priority")),
                -safe_int(item.get("request_count")),
                coerce_text(item.get("pool_name")),
                coerce_text(item.get("route_url")),
            )
        )
        return {"ok": True, "items": items[:limit], "total": len(items)}

    def _extract_costs(self, row: dict) -> dict:
        total_cost = safe_float(row.get("total_cost"))
        actual_cost = safe_float(row.get("actual_cost"))
        account_cost = safe_float(row.get("account_cost"))
        if account_cost <= 0:
            account_stats_cost = safe_float(row.get("account_stats_cost"))
            account_multiplier = safe_float(row.get("account_rate_multiplier") or 1.0)
            if account_stats_cost > 0:
                account_cost = account_stats_cost * (account_multiplier or 1.0)
        if actual_cost <= 0:
            multiplier = safe_float(row.get("rate_multiplier") or 1.0)
            if total_cost > 0:
                actual_cost = total_cost * (multiplier or 1.0)
        return {
            "total_cost": total_cost,
            "actual_cost": actual_cost,
            "account_cost": account_cost,
        }

    def _parse_request_timestamp(self, value) -> float | None:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            try:
                return float(value)
            except Exception:
                return None
        text = coerce_text(value)
        if not text:
            return None
        try:
            if text.endswith("Z"):
                from datetime import datetime
                return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
            from datetime import datetime
            return datetime.fromisoformat(text).timestamp()
        except Exception:
            return None

    def _filter_rows_by_started_at(self, rows: list[dict], *, started_after=None, started_before=None) -> list[dict]:
        after_ts = self._parse_request_timestamp(started_after)
        before_ts = self._parse_request_timestamp(started_before)
        if after_ts is None and before_ts is None:
            return rows
        filtered = []
        for row in rows:
            row_ts = self._parse_request_timestamp(row.get("started_at"))
            if row_ts is None:
                continue
            if after_ts is not None and row_ts < after_ts:
                continue
            if before_ts is not None and row_ts > before_ts:
                continue
            filtered.append(row)
        return filtered

    def list_accounts(self, limit: int = 200) -> dict:
        rows = self._load_recent_requests()
        groups, memberships = self._group_map()
        accounts: dict[str, dict] = {}
        for row in rows:
            consumer_id, consumer_name, consumer_type, preview = self._consumer_key(row)
            resolved = self._resolve_account_metadata(consumer_id, consumer_name, consumer_type, preview)
            account_id = resolved["id"]
            group_ids = memberships.get(account_id, [])
            primary_group = groups.get(group_ids[0], {}) if group_ids else {}
            entry = accounts.setdefault(
                account_id,
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
                    "group_id": coerce_text(primary_group.get("id")) or "",
                    "group_name": coerce_text(primary_group.get("name")) or "",
                },
            )
            entry["request_count"] += 1
            if row.get("error") or safe_int(row.get("status_code")) >= 400:
                entry["error_count"] += 1
            entry["prompt_tokens"] += safe_int(row.get("prompt_tokens"))
            entry["completion_tokens"] += safe_int(row.get("completion_tokens"))
            entry["total_tokens"] += safe_int(row.get("total_tokens"))
            entry["input_bytes"] += safe_int(row.get("input_bytes"))
            entry["output_bytes"] += safe_int(row.get("bytes_sent"))
            started_at = coerce_text(row.get("started_at"))
            if started_at and started_at > coerce_text(entry.get("last_seen_at")):
                entry["last_seen_at"] = started_at

        stored_accounts = self._managed_accounts()
        for external_key, stored in stored_accounts.items():
            account_id = coerce_text(stored.get("id"))
            if not account_id or account_id in accounts:
                continue
            group_ids = memberships.get(account_id, [])
            primary_group = groups.get(group_ids[0], {}) if group_ids else {}
            accounts[account_id] = {
                "id": account_id,
                "name": coerce_text(stored.get("name")) or "未命名用户",
                "source_type": coerce_text(stored.get("source_type")) or "managed",
                "preview": "",
                "external_key": external_key,
                "role": coerce_text(stored.get("role")) or "user",
                "status": coerce_text(stored.get("status")) or "active",
                "balance_cents": safe_int(stored.get("balance_cents")),
                "concurrency_limit": safe_int(stored.get("concurrency_limit")),
                "allowed_group_ids": stored.get("allowed_group_ids") if isinstance(stored.get("allowed_group_ids"), list) else [],
                "extra": stored.get("extra") if isinstance(stored.get("extra"), dict) else {},
                "enabled": stored.get("enabled") is not False,
                "note": coerce_text(stored.get("note")),
                "request_count": 0,
                "error_count": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "input_bytes": 0,
                "output_bytes": 0,
                "last_seen_at": "",
                "group_ids": group_ids,
                "group_id": coerce_text(primary_group.get("id")) or "",
                "group_name": coerce_text(primary_group.get("name")) or "",
                **self._get_account_subscription_status(account_id),
            }

        for item in accounts.values():
            if "subscription_active" not in item:
                item.update(self._get_account_subscription_status(coerce_text(item.get("id"))))

        items = sorted(
            accounts.values(),
            key=lambda item: (
                -safe_int(item.get("request_count")),
                -safe_int(item.get("total_tokens")),
                coerce_text(item.get("name")),
            ),
        )
        return {"ok": True, "items": items[:limit], "total": len(items)}

    def list_users(self, limit: int = 200) -> dict:
        accounts_payload = self.list_accounts(limit=limit)
        key_counts: dict[str, int] = {}
        active_key_counts: dict[str, int] = {}
        subscription_counts: dict[str, int] = {}
        active_subscription_counts: dict[str, int] = {}
        if self.storage is not None:
            for row in self.storage.list_admin_api_keys():
                account_id = coerce_text(row.get("account_id"))
                if not account_id:
                    continue
                key_counts[account_id] = key_counts.get(account_id, 0) + 1
                if row.get("enabled") is not False:
                    active_key_counts[account_id] = active_key_counts.get(account_id, 0) + 1
            for row in self.storage.list_admin_account_subscriptions():
                account_id = coerce_text(row.get("account_id"))
                if not account_id:
                    continue
                subscription_counts[account_id] = subscription_counts.get(account_id, 0) + 1
                if coerce_text(row.get("status")) == "active":
                    active_subscription_counts[account_id] = active_subscription_counts.get(account_id, 0) + 1
        items = []
        for account in accounts_payload.get("items", []):
            account_id = coerce_text(account.get("id"))
            user_fields = self._user_public_fields(account)
            items.append(
                {
                    "id": account_id,
                    "name": coerce_text(account.get("name")) or "未命名用户",
                    "email": user_fields["user_email"],
                    "username": user_fields["user_username"],
                    "rpm_limit": user_fields["user_rpm_limit"],
                    "password_set": user_fields["user_password_set"],
                    "preview": coerce_text(account.get("preview")),
                    "source_type": coerce_text(account.get("source_type")),
                    "group_id": coerce_text(account.get("group_id")),
                    "group_name": coerce_text(account.get("group_name")),
                    "group_ids": account.get("group_ids") if isinstance(account.get("group_ids"), list) else [],
                    "enabled": account.get("enabled") is not False,
                    "status": coerce_text(account.get("status")) or "active",
                    "role": coerce_text(account.get("role")) or "user",
                    "note": coerce_text(account.get("note")),
                    "balance_cents": safe_int(account.get("balance_cents")),
                    "concurrency_limit": safe_int(account.get("concurrency_limit")),
                    "allowed_group_ids": account.get("allowed_group_ids") if isinstance(account.get("allowed_group_ids"), list) else [],
                    "prompt_tokens": safe_int(account.get("prompt_tokens")),
                    "completion_tokens": safe_int(account.get("completion_tokens")),
                    "total_tokens": safe_int(account.get("total_tokens")),
                    "input_bytes": safe_int(account.get("input_bytes")),
                    "output_bytes": safe_int(account.get("output_bytes")),
                    "error_count": safe_int(account.get("error_count")),
                    "request_count": safe_int(account.get("request_count")),
                    "last_seen_at": coerce_text(account.get("last_seen_at")),
                    "key_count": key_counts.get(account_id, 0),
                    "active_key_count": active_key_counts.get(account_id, 0),
                    "subscription_count": subscription_counts.get(account_id, 0),
                    "active_subscription_count": active_subscription_counts.get(account_id, 0),
                    "subscription_active": account.get("subscription_active") is True,
                    "active_plan_name": coerce_text(account.get("active_plan_name")),
                    "active_group_id": coerce_text(account.get("active_group_id")),
                    "active_group_name": coerce_text(account.get("active_group_name")),
                    **user_fields,
                }
            )
        return {"ok": True, "items": items, "total": len(items)}

    def list_groups(self) -> dict:
        rows = self._load_recent_requests()
        stored_groups = {}
        memberships: dict[str, list[str]] = {}
        if self.storage is not None:
            for group in self.storage.list_admin_groups():
                stored_groups[coerce_text(group.get("id"))] = {
                    **group,
                    "account_ids": set(),
                    "request_count": 0,
                    "error_count": 0,
                    "total_tokens": 0,
                    "input_bytes": 0,
                    "output_bytes": 0,
                }
            for row in self.storage.list_admin_account_groups():
                account_id = coerce_text(row.get("account_id"))
                group_id = coerce_text(row.get("group_id"))
                if account_id and group_id:
                    memberships.setdefault(account_id, []).append(group_id)
                    if group_id in stored_groups:
                        stored_groups[group_id]["account_ids"].add(account_id)

        for row in rows:
            consumer_id, consumer_name, consumer_type, preview = self._consumer_key(row)
            resolved = self._resolve_account_metadata(consumer_id, consumer_name, consumer_type, preview)
            account_id = resolved["id"]
            target_group_ids = memberships.get(account_id) or []
            if not target_group_ids:
                target_group_ids = [f"default:{resolved['source_type']}"]
                stored_groups.setdefault(
                    target_group_ids[0],
                    {
                        "id": target_group_ids[0],
                        "name": "托管 Key" if resolved["source_type"] == "managed" else ("环境 Key" if resolved["source_type"] == "env" else "未分组"),
                        "description": "",
                        "enabled": True,
                        "sort_order": 0,
                        "account_ids": set(),
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
                        "account_ids": set(),
                        "request_count": 0,
                        "error_count": 0,
                        "total_tokens": 0,
                        "input_bytes": 0,
                        "output_bytes": 0,
                    },
                )
                entry["account_ids"].add(account_id)
                entry["request_count"] += 1
                if row.get("error") or safe_int(row.get("status_code")) >= 400:
                    entry["error_count"] += 1
                entry["total_tokens"] += safe_int(row.get("total_tokens"))
                entry["input_bytes"] += safe_int(row.get("input_bytes"))
                entry["output_bytes"] += safe_int(row.get("bytes_sent"))

        items = []
        for entry in stored_groups.values():
            items.append({**entry, "account_count": len(entry.get("account_ids") or [])})
            items[-1].pop("account_ids", None)
        items.sort(key=lambda item: (safe_int(item.get("sort_order")), -safe_int(item.get("request_count")), coerce_text(item.get("name"))))
        return {"ok": True, "items": items, "total": len(items)}

    def upsert_group(self, payload: dict) -> dict:
        if self.storage is None:
            raise RuntimeError("storage not configured")
        copy_source_group_ids = self._normalize_group_ids(
            payload.get("copy_accounts_from_group_ids") if isinstance(payload.get("copy_accounts_from_group_ids"), list) else []
        )
        item = normalize_admin_group_payload(
            {
                **payload,
                "id": coerce_text(payload.get("id")) or f"group_{uuid.uuid4().hex[:16]}",
            }
        )
        if not item["name"]:
            raise ValueError("group name is required")
        if copy_source_group_ids:
            self._validate_group_ids_exist(copy_source_group_ids)
        saved = self.storage.upsert_admin_group(item)
        if copy_source_group_ids:
            target_group_id = coerce_text(saved.get("id"))
            existing_rows = self.storage.list_admin_account_groups()
            membership_by_account: dict[str, set[str]] = {}
            source_account_ids: set[str] = set()
            for row in existing_rows:
                account_id = coerce_text(row.get("account_id"))
                group_id = coerce_text(row.get("group_id"))
                if not account_id or not group_id:
                    continue
                membership_by_account.setdefault(account_id, set()).add(group_id)
                if group_id in copy_source_group_ids:
                    source_account_ids.add(account_id)
            for account_id in sorted(source_account_ids):
                next_group_ids = sorted(membership_by_account.get(account_id, set()) | {target_group_id})
                self.storage.replace_admin_account_groups(account_id, next_group_ids)
        return {"ok": True, "item": saved}

    def delete_group(self, group_id: str) -> dict:
        if self.storage is None:
            raise RuntimeError("storage not configured")
        target = coerce_text(group_id)
        if not target:
            raise ValueError("group_id is required")
        if not self.storage.get_admin_group(target):
            raise ValueError("group not found")
        self.storage.delete_admin_group(target)
        return {"ok": True, "id": target}

    def list_usage(self, limit: int = 200, *, started_after=None, started_before=None) -> dict:
        rows = self._load_recent_requests(limit=max(limit, 500))
        rows = self._filter_rows_by_started_at(rows, started_after=started_after, started_before=started_before)
        items = []
        for row in rows[:limit]:
            consumer_id, consumer_name, consumer_type, preview = self._consumer_key(row)
            resolved = self._resolve_account_metadata(consumer_id, consumer_name, consumer_type, preview)
            prompt_tokens = safe_int(row.get("prompt_tokens"))
            completion_tokens = safe_int(row.get("completion_tokens"))
            total_tokens = safe_int(row.get("total_tokens")) or (prompt_tokens + completion_tokens)
            items.append(
                {
                    "request_id": coerce_text(row.get("request_id")),
                    "started_at": coerce_text(row.get("started_at")),
                    "consumer_id": resolved["id"],
                    "consumer_name": resolved["name"],
                    "consumer_type": resolved["source_type"],
                    "consumer_preview": preview,
                    **self._user_public_fields(resolved),
                    "api_key_id": coerce_text(row.get("proxy_api_key_id")),
                    "api_key_name": coerce_text(row.get("proxy_api_key_name")),
                    "api_key_preview": coerce_text(row.get("proxy_api_key_preview")),
                    "api_key_type": coerce_text(row.get("proxy_api_key_type")),
                    "subscription_id": coerce_text(row.get("proxy_subscription_id")),
                    "plan_id": coerce_text(row.get("proxy_plan_id")),
                    "plan_name": coerce_text(row.get("proxy_plan_name")),
                    "group_id": coerce_text(row.get("proxy_group_id")),
                    "group_name": coerce_text(row.get("proxy_group_name")),
                    "plan_price_cents": safe_int(row.get("proxy_plan_price_cents")),
                    "model": coerce_text(row.get("logical_model") or row.get("model")),
                    "resolved_model": coerce_text(row.get("resolved_model")),
                    "pool_name": coerce_text(row.get("pool_name")),
                    "route_url": coerce_text(row.get("route_url") or row.get("upstream_url")),
                    "status_code": safe_int(row.get("status_code")),
                    "duration_ms": safe_int(row.get("duration_ms")),
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": total_tokens,
                    "input_bytes": safe_int(row.get("input_bytes")),
                    "output_bytes": safe_int(row.get("bytes_sent")),
                    "cache_read_tokens": safe_int(row.get("cache_read_input_tokens")),
                    "cache_write_tokens": safe_int(row.get("cache_creation_input_tokens")),
                    "local_cache_status": coerce_text(row.get("local_response_cache_status") or row.get("cache_status")),
                    "upstream_cache_status": coerce_text(row.get("upstream_prompt_cache_status")),
                    "error": coerce_text(row.get("error")),
                    **self._extract_costs(row),
                }
            )
        return {"ok": True, "items": items, "total": len(items)}

    def billing_summary(self, limit: int = 5000, *, started_after=None, started_before=None) -> dict:
        rows = self._load_recent_requests(limit=max(limit, 1000))
        rows = self._filter_rows_by_started_at(rows, started_after=started_after, started_before=started_before)
        usage_items = self.list_usage(
            limit=max(limit, 1000),
            started_after=started_after,
            started_before=started_before,
        ).get("items", [])
        subscriptions = {}
        orders_by_subscription: dict[str, list[dict]] = {}
        orders_by_account_plan: dict[tuple[str, str], list[dict]] = {}
        if self.storage is not None:
            try:
                for item in self.storage.list_admin_account_subscriptions():
                    if isinstance(item, dict):
                        subscriptions[coerce_text(item.get("id"))] = item
            except Exception:
                subscriptions = {}
            try:
                for order in self.storage.list_payment_orders():
                    if not isinstance(order, dict):
                        continue
                    subscription_id = coerce_text(order.get("subscription_id"))
                    if subscription_id:
                        orders_by_subscription.setdefault(subscription_id, []).append(order)
                    account_plan_key = (
                        coerce_text(order.get("account_id")),
                        coerce_text(order.get("plan_id")),
                    )
                    if account_plan_key[0] and account_plan_key[1]:
                        orders_by_account_plan.setdefault(account_plan_key, []).append(order)
            except Exception:
                orders_by_subscription = {}
                orders_by_account_plan = {}

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
            "amount_cents": 0,
            "total_cost": 0.0,
            "actual_cost": 0.0,
            "account_cost": 0.0,
            "active_subscription_count": 0,
            "covered_request_count": 0,
        }
        by_account: dict[str, dict] = {}
        by_group: dict[str, dict] = {}
        by_plan: dict[str, dict] = {}
        by_subscription: dict[str, dict] = {}
        by_order: dict[str, dict] = {}

        active_subscription_ids = {
            coerce_text(item.get("id"))
            for item in subscriptions.values()
            if coerce_text(item.get("status")) == "active"
        }
        summary["active_subscription_count"] = len([item for item in active_subscription_ids if item])

        for item in usage_items:
            request_count = 1
            error_count = 1 if safe_int(item.get("status_code")) >= 400 or item.get("error") else 0
            prompt_tokens = safe_int(item.get("prompt_tokens"))
            completion_tokens = safe_int(item.get("completion_tokens"))
            total_tokens = safe_int(item.get("total_tokens")) or (prompt_tokens + completion_tokens)
            input_bytes = safe_int(item.get("input_bytes"))
            output_bytes = safe_int(item.get("output_bytes"))
            cache_read_tokens = safe_int(item.get("cache_read_tokens"))
            cache_write_tokens = safe_int(item.get("cache_write_tokens"))
            total_cost = safe_float(item.get("total_cost"))
            actual_cost = safe_float(item.get("actual_cost"))
            account_cost = safe_float(item.get("account_cost"))
            subscription_id = coerce_text(item.get("subscription_id"))
            plan_id = coerce_text(item.get("plan_id"))
            group_id = coerce_text(item.get("group_id"))
            account_id = coerce_text(item.get("consumer_id"))
            account_name = coerce_text(item.get("consumer_name")) or "未命名用户"
            plan_name = coerce_text(item.get("plan_name")) or "未关联计划"
            group_name = coerce_text(item.get("group_name")) or "未分组"
            plan_price_cents = max(0, safe_int(item.get("plan_price_cents")))

            amount_cents = 0
            related_orders = []
            if subscription_id:
                related_orders = orders_by_subscription.get(subscription_id, [])
            elif account_id and plan_id:
                related_orders = orders_by_account_plan.get((account_id, plan_id), [])
            if related_orders:
                paid_orders = [order for order in related_orders if coerce_text(order.get("status")) == "paid"]
                chosen_order = (paid_orders or related_orders)[-1]
                amount_cents = max(
                    0,
                    safe_int(chosen_order.get("final_price_cents"))
                    or safe_int(chosen_order.get("amount_cents"))
                    or plan_price_cents,
                )
                order_id = coerce_text(chosen_order.get("id"))
                if order_id:
                    order_entry = by_order.setdefault(
                        order_id,
                        {
                            "order_id": order_id,
                            "subscription_id": coerce_text(chosen_order.get("subscription_id")),
                            "account_id": coerce_text(chosen_order.get("account_id")),
                            "account_name": coerce_text(chosen_order.get("account_name")) or account_name,
                            "user_id": coerce_text(chosen_order.get("user_id") or chosen_order.get("account_id")),
                            "user_name": coerce_text(chosen_order.get("user_name") or chosen_order.get("account_name")) or account_name,
                            "plan_id": coerce_text(chosen_order.get("plan_id")) or plan_id,
                            "plan_name": coerce_text(chosen_order.get("plan_name")) or plan_name,
                            "group_id": coerce_text(chosen_order.get("group_id")) or group_id,
                            "group_name": coerce_text(chosen_order.get("group_name")) or group_name,
                            "channel_id": coerce_text(chosen_order.get("channel_id")),
                            "channel_name": coerce_text(chosen_order.get("channel_name")),
                            "provider": coerce_text(chosen_order.get("provider")),
                            "status": coerce_text(chosen_order.get("status")),
                            "amount_cents": max(
                                0,
                                safe_int(chosen_order.get("final_price_cents"))
                                or safe_int(chosen_order.get("amount_cents")),
                            ),
                            "total_cost": 0.0,
                            "actual_cost": 0.0,
                            "account_cost": 0.0,
                            "request_count": 0,
                            "error_count": 0,
                            "total_tokens": 0,
                            "input_bytes": 0,
                            "output_bytes": 0,
                        },
                    )
                    order_entry["request_count"] += request_count
                    order_entry["error_count"] += error_count
                    order_entry["total_tokens"] += total_tokens
                    order_entry["input_bytes"] += input_bytes
                    order_entry["output_bytes"] += output_bytes
                    order_entry["total_cost"] += total_cost
                    order_entry["actual_cost"] += actual_cost
                    order_entry["account_cost"] += account_cost
            elif subscription_id and plan_price_cents > 0:
                amount_cents = plan_price_cents

            summary["request_count"] += request_count
            summary["error_count"] += error_count
            summary["prompt_tokens"] += prompt_tokens
            summary["completion_tokens"] += completion_tokens
            summary["total_tokens"] += total_tokens
            summary["input_bytes"] += input_bytes
            summary["output_bytes"] += output_bytes
            summary["cache_read_tokens"] += cache_read_tokens
            summary["cache_write_tokens"] += cache_write_tokens
            summary["amount_cents"] += amount_cents
            summary["total_cost"] += total_cost
            summary["actual_cost"] += actual_cost
            summary["account_cost"] += account_cost
            if subscription_id:
                summary["covered_request_count"] += 1

            account_entry = by_account.setdefault(
                account_id or "anonymous",
                {
                    "account_id": account_id or "anonymous",
                    "account_name": account_name,
                    "user_id": account_id or "anonymous",
                    "user_name": account_name,
                    "consumer_type": coerce_text(item.get("consumer_type")),
                    "group_ids": set(),
                    "group_names": set(),
                    "plan_ids": set(),
                    "plan_names": set(),
                    "subscription_ids": set(),
                    "request_count": 0,
                    "error_count": 0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "input_bytes": 0,
                    "output_bytes": 0,
                    "cache_read_tokens": 0,
                    "cache_write_tokens": 0,
                    "amount_cents": 0,
                    "total_cost": 0.0,
                    "actual_cost": 0.0,
                    "account_cost": 0.0,
                },
            )
            account_entry["request_count"] += request_count
            account_entry["error_count"] += error_count
            account_entry["prompt_tokens"] += prompt_tokens
            account_entry["completion_tokens"] += completion_tokens
            account_entry["total_tokens"] += total_tokens
            account_entry["input_bytes"] += input_bytes
            account_entry["output_bytes"] += output_bytes
            account_entry["cache_read_tokens"] += cache_read_tokens
            account_entry["cache_write_tokens"] += cache_write_tokens
            account_entry["amount_cents"] += amount_cents
            account_entry["total_cost"] += total_cost
            account_entry["actual_cost"] += actual_cost
            account_entry["account_cost"] += account_cost
            if group_id:
                account_entry["group_ids"].add(group_id)
            if group_name:
                account_entry["group_names"].add(group_name)
            if plan_id:
                account_entry["plan_ids"].add(plan_id)
            if plan_name:
                account_entry["plan_names"].add(plan_name)
            if subscription_id:
                account_entry["subscription_ids"].add(subscription_id)

            group_entry = by_group.setdefault(
                group_id or "ungrouped",
                {
                    "group_id": group_id or "",
                    "group_name": group_name,
                    "account_ids": set(),
                    "user_ids": set(),
                    "plan_ids": set(),
                    "subscription_ids": set(),
                    "request_count": 0,
                    "error_count": 0,
                    "total_tokens": 0,
                    "input_bytes": 0,
                    "output_bytes": 0,
                    "amount_cents": 0,
                    "total_cost": 0.0,
                    "actual_cost": 0.0,
                    "account_cost": 0.0,
                },
            )
            group_entry["account_ids"].add(account_id or "anonymous")
            group_entry["user_ids"].add(account_id or "anonymous")
            if plan_id:
                group_entry["plan_ids"].add(plan_id)
            if subscription_id:
                group_entry["subscription_ids"].add(subscription_id)
            group_entry["request_count"] += request_count
            group_entry["error_count"] += error_count
            group_entry["total_tokens"] += total_tokens
            group_entry["input_bytes"] += input_bytes
            group_entry["output_bytes"] += output_bytes
            group_entry["amount_cents"] += amount_cents
            group_entry["total_cost"] += total_cost
            group_entry["actual_cost"] += actual_cost
            group_entry["account_cost"] += account_cost

            plan_entry = by_plan.setdefault(
                plan_id or "unplanned",
                {
                    "plan_id": plan_id or "",
                    "plan_name": plan_name,
                    "group_id": group_id,
                    "group_name": group_name,
                    "plan_price_cents": plan_price_cents,
                    "account_ids": set(),
                    "user_ids": set(),
                    "subscription_ids": set(),
                    "request_count": 0,
                    "error_count": 0,
                    "total_tokens": 0,
                    "input_bytes": 0,
                    "output_bytes": 0,
                    "amount_cents": 0,
                    "total_cost": 0.0,
                    "actual_cost": 0.0,
                    "account_cost": 0.0,
                },
            )
            plan_entry["account_ids"].add(account_id or "anonymous")
            plan_entry["user_ids"].add(account_id or "anonymous")
            if subscription_id:
                plan_entry["subscription_ids"].add(subscription_id)
            plan_entry["request_count"] += request_count
            plan_entry["error_count"] += error_count
            plan_entry["total_tokens"] += total_tokens
            plan_entry["input_bytes"] += input_bytes
            plan_entry["output_bytes"] += output_bytes
            plan_entry["amount_cents"] += amount_cents
            plan_entry["total_cost"] += total_cost
            plan_entry["actual_cost"] += actual_cost
            plan_entry["account_cost"] += account_cost

            if subscription_id:
                subscription = subscriptions.get(subscription_id, {})
                subscription_entry = by_subscription.setdefault(
                    subscription_id,
                    {
                        "subscription_id": subscription_id,
                        "status": coerce_text(subscription.get("status")) or "unknown",
                        "account_id": account_id,
                        "account_name": account_name,
                        "user_id": account_id,
                        "user_name": account_name,
                        "plan_id": plan_id,
                        "plan_name": plan_name,
                        "group_id": group_id,
                        "group_name": group_name,
                        "price_cents": max(
                            0,
                            safe_int(subscription.get("price_cents")) or plan_price_cents,
                        ),
                        "started_at": subscription.get("started_at"),
                        "expires_at": subscription.get("expires_at"),
                        "request_count": 0,
                        "error_count": 0,
                        "total_tokens": 0,
                        "input_bytes": 0,
                        "output_bytes": 0,
                        "amount_cents": 0,
                        "total_cost": 0.0,
                        "actual_cost": 0.0,
                        "account_cost": 0.0,
                    },
                )
                subscription_entry["request_count"] += request_count
                subscription_entry["error_count"] += error_count
                subscription_entry["total_tokens"] += total_tokens
                subscription_entry["input_bytes"] += input_bytes
                subscription_entry["output_bytes"] += output_bytes
                subscription_entry["amount_cents"] += amount_cents
                subscription_entry["total_cost"] += total_cost
                subscription_entry["actual_cost"] += actual_cost
                subscription_entry["account_cost"] += account_cost

        def _normalize(entries: dict[str, dict], *, set_fields: dict[str, str] | None = None, sort_keys: list[str] | None = None) -> list[dict]:
            items = []
            for entry in entries.values():
                normalized = dict(entry)
                for field, target in (set_fields or {}).items():
                    values = sorted(value for value in normalized.get(field, set()) if value)
                    normalized[target] = values
                    normalized[f"{target[:-4]}count" if target.endswith("_ids") else f"{target}_count"] = len(values)
                    normalized.pop(field, None)
                items.append(normalized)
            sort_keys = sort_keys or ["amount_cents", "total_tokens", "request_count"]
            items.sort(key=lambda item: tuple(-safe_int(item.get(key)) for key in sort_keys) + (coerce_text(item.get("user_name") or item.get("account_name") or item.get("group_name") or item.get("plan_name") or item.get("subscription_id")),))
            return items

        return {
            "ok": True,
            "summary": summary,
            "by_account": _normalize(
                by_account,
                set_fields={
                    "group_ids": "group_ids",
                    "group_names": "group_names",
                    "plan_ids": "plan_ids",
                    "plan_names": "plan_names",
                    "subscription_ids": "subscription_ids",
                },
            ),
            "by_group": _normalize(
                by_group,
                set_fields={
                    "account_ids": "account_ids",
                    "user_ids": "user_ids",
                    "plan_ids": "plan_ids",
                    "subscription_ids": "subscription_ids",
                },
            ),
            "by_plan": _normalize(
                by_plan,
                set_fields={
                    "account_ids": "account_ids",
                    "user_ids": "user_ids",
                    "subscription_ids": "subscription_ids",
                },
            ),
            "by_subscription": _normalize(by_subscription),
            "by_order": _normalize(by_order),
            "recent_request_total": len(rows),
            "started_after": started_after,
            "started_before": started_before,
        }

    def dashboard_summary(self) -> dict:
        accounts = self.list_accounts(limit=500).get("items", [])
        groups = self.list_groups().get("items", [])
        usage = self.list_usage(limit=500).get("items", [])
        protocols = self.list_protocol_profiles().get("items", [])
        return {
            "ok": True,
            "account_count": len(accounts),
            "group_count": len(groups),
            "protocol_count": len(protocols),
            "request_count": len(usage),
            "total_tokens": sum(safe_int(item.get("total_tokens")) for item in usage),
            "input_bytes": sum(safe_int(item.get("input_bytes")) for item in usage),
            "output_bytes": sum(safe_int(item.get("output_bytes")) for item in usage),
            "error_count": sum(1 for item in usage if safe_int(item.get("status_code")) >= 400 or item.get("error")),
            "top_accounts": accounts[:5],
            "top_groups": groups[:5],
        }
