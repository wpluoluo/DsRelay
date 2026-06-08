from __future__ import annotations

import time
import uuid

from .base import AdminServiceBase, coerce_text


CONTENT_BUCKETS = {
    "announcements": "公告",
    "redeem-codes": "兑换码",
    "promo-codes": "Promo Codes",
    "affiliate-invites": "邀请记录",
    "affiliate-rebates": "返利记录",
    "affiliate-transfers": "提取记录",
    "risk-rules": "风控规则",
}


class AdminContentMixin(AdminServiceBase):
    def _content_storage_key(self, bucket: str) -> str:
        return f"admin_content:{bucket}"

    def _load_content_bucket(self, bucket: str) -> list[dict]:
        if self.storage is None:
            return []
        payload = self.storage.load_app_config(self._content_storage_key(bucket))
        rows = payload.get("items") if isinstance(payload.get("items"), list) else []
        items = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            items.append(
                {
                    "id": coerce_text(row.get("id")),
                    "title": coerce_text(row.get("title")),
                    "status": coerce_text(row.get("status")) or "active",
                    "summary": coerce_text(row.get("summary")),
                    "content": coerce_text(row.get("content")),
                    "note": coerce_text(row.get("note")),
                    "created_at": row.get("created_at"),
                    "updated_at": row.get("updated_at"),
                }
            )
        items.sort(
            key=lambda item: (
                0 if coerce_text(item.get("status")) == "active" else 1,
                -(float(item.get("updated_at") or 0)),
                coerce_text(item.get("title")),
            )
        )
        return items

    def _save_content_bucket(self, bucket: str, items: list[dict]) -> None:
        if self.storage is None:
            raise RuntimeError("storage not configured")
        self.storage.save_app_config({"items": items}, self._content_storage_key(bucket))

    def list_content_bucket(self, bucket: str) -> dict:
        if bucket not in CONTENT_BUCKETS:
            raise ValueError("unsupported content bucket")
        items = self._load_content_bucket(bucket)
        return {"ok": True, "bucket": bucket, "label": CONTENT_BUCKETS[bucket], "items": items, "total": len(items)}

    def upsert_content_bucket_item(self, bucket: str, payload: dict) -> dict:
        if bucket not in CONTENT_BUCKETS:
            raise ValueError("unsupported content bucket")
        items = self._load_content_bucket(bucket)
        item_id = coerce_text(payload.get("id")) or f"content_{uuid.uuid4().hex[:16]}"
        now = time.time()
        item = {
            "id": item_id,
            "title": coerce_text(payload.get("title")),
            "status": coerce_text(payload.get("status")) or "active",
            "summary": coerce_text(payload.get("summary")),
            "content": coerce_text(payload.get("content")),
            "note": coerce_text(payload.get("note")),
            "created_at": now,
            "updated_at": now,
        }
        if not item["title"]:
            raise ValueError("title is required")
        next_items = []
        replaced = False
        for current in items:
            if coerce_text(current.get("id")) == item_id:
                item["created_at"] = current.get("created_at") or now
                next_items.append(item)
                replaced = True
            else:
                next_items.append(current)
        if not replaced:
            next_items.append(item)
        self._save_content_bucket(bucket, next_items)
        return {"ok": True, "bucket": bucket, "item": item}

    def delete_content_bucket_item(self, bucket: str, item_id: str) -> dict:
        if bucket not in CONTENT_BUCKETS:
            raise ValueError("unsupported content bucket")
        target = coerce_text(item_id)
        if not target:
            raise ValueError("content id is required")
        items = self._load_content_bucket(bucket)
        next_items = [item for item in items if coerce_text(item.get("id")) != target]
        if len(next_items) == len(items):
            raise ValueError("content item not found")
        self._save_content_bucket(bucket, next_items)
        return {"ok": True, "bucket": bucket, "id": target}
