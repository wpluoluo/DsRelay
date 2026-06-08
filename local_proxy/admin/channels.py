from __future__ import annotations

import time
import uuid

from .base import AdminServiceBase, coerce_text, safe_float, safe_int


CHANNELS_CONFIG_KEY = "admin_channels"


def _normalize_channel_payload(payload: dict, *, current: dict | None = None) -> dict:
    current = current if isinstance(current, dict) else {}
    now = time.time()
    raw_group_ids = payload.get("group_ids") if isinstance(payload.get("group_ids"), list) else []
    raw_pricing = (
        payload.get("model_pricing")
        if isinstance(payload.get("model_pricing"), list)
        else current.get("model_pricing") if isinstance(current.get("model_pricing"), list) else []
    )
    pricing_rows = []
    for row in raw_pricing:
        if not isinstance(row, dict):
            continue
        model = coerce_text(row.get("model"))
        if not model:
            continue
        pricing_rows.append(
            {
                "model": model,
                "input_price": safe_float(row.get("input_price")),
                "output_price": safe_float(row.get("output_price")),
                "unit": coerce_text(row.get("unit")) or "1M tokens",
            }
        )

    return {
        "id": coerce_text(payload.get("id")) or coerce_text(current.get("id")) or f"channel_{uuid.uuid4().hex[:16]}",
        "name": coerce_text(payload.get("name")) if "name" in payload else coerce_text(current.get("name")),
        "description": coerce_text(payload.get("description")) if "description" in payload else coerce_text(current.get("description")),
        "platform": coerce_text(payload.get("platform")) if "platform" in payload else coerce_text(current.get("platform")),
        "billing_model_source": (
            coerce_text(payload.get("billing_model_source"))
            if "billing_model_source" in payload
            else coerce_text(current.get("billing_model_source"))
        ) or "channel_mapped",
        "group_ids": [coerce_text(item) for item in raw_group_ids if coerce_text(item)] if "group_ids" in payload else current.get("group_ids", []),
        "model_pricing": pricing_rows,
        "features_config": payload.get("features_config") if isinstance(payload.get("features_config"), dict) else current.get("features_config", {}),
        "enabled": payload.get("enabled", current.get("enabled", True)) is not False,
        "sort_order": safe_int(payload.get("sort_order") if "sort_order" in payload else current.get("sort_order")),
        "created_at": current.get("created_at") or now,
        "updated_at": now,
    }


class AdminChannelsMixin(AdminServiceBase):
    def _load_admin_channels(self) -> list[dict]:
        if self.storage is None:
            return []
        payload = self.storage.load_app_config(CHANNELS_CONFIG_KEY)
        rows = payload.get("items") if isinstance(payload.get("items"), list) else []
        items = []
        for row in rows:
            if isinstance(row, dict):
                items.append(_normalize_channel_payload(row, current=row))
        items.sort(key=lambda item: (safe_int(item.get("sort_order")), coerce_text(item.get("name"))))
        return items

    def _save_admin_channels(self, items: list[dict]) -> None:
        if self.storage is None:
            raise RuntimeError("storage not configured")
        self.storage.save_app_config({"items": items}, CHANNELS_CONFIG_KEY)

    def list_channels(self) -> dict:
        items = self._load_admin_channels()
        groups = self._group_policy_map()
        plan_count_by_group: dict[str, int] = {}
        if self.storage is not None:
            for plan in self.storage.list_admin_subscription_plans():
                group_id = coerce_text(plan.get("group_id"))
                if group_id:
                    plan_count_by_group[group_id] = plan_count_by_group.get(group_id, 0) + 1

        enriched = []
        for item in items:
            group_ids = [coerce_text(group_id) for group_id in item.get("group_ids", []) if coerce_text(group_id)]
            group_names = [coerce_text(groups.get(group_id, {}).get("name")) or group_id for group_id in group_ids]
            plan_count = sum(plan_count_by_group.get(group_id, 0) for group_id in group_ids)
            enriched.append(
                {
                    **item,
                    "group_names": group_names,
                    "group_count": len(group_ids),
                    "plan_count": plan_count,
                    "pricing_count": len(item.get("model_pricing") or []),
                }
            )
        return {"ok": True, "items": enriched, "total": len(enriched)}

    def upsert_channel(self, payload: dict) -> dict:
        if self.storage is None:
            raise RuntimeError("storage not configured")
        items = self._load_admin_channels()
        channel_id = coerce_text(payload.get("id"))
        current = next((item for item in items if coerce_text(item.get("id")) == channel_id), {})
        item = _normalize_channel_payload(payload, current=current)
        if not item["name"]:
            raise ValueError("channel name is required")
        self._validate_group_ids_exist(item["group_ids"])

        next_items = []
        replaced = False
        for existing in items:
            if coerce_text(existing.get("id")) == item["id"]:
                next_items.append(item)
                replaced = True
            else:
                next_items.append(existing)
        if not replaced:
            next_items.append(item)
        self._save_admin_channels(next_items)
        return {"ok": True, "item": item}

    def delete_channel(self, channel_id: str) -> dict:
        if self.storage is None:
            raise RuntimeError("storage not configured")
        target = coerce_text(channel_id)
        if not target:
            raise ValueError("channel_id is required")
        items = self._load_admin_channels()
        next_items = [item for item in items if coerce_text(item.get("id")) != target]
        if len(next_items) == len(items):
            raise ValueError("channel not found")
        self._save_admin_channels(next_items)
        return {"ok": True, "id": target}
