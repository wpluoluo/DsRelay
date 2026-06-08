from __future__ import annotations

import json
import re
import time
import uuid

from .base import AdminServiceBase, coerce_text, safe_float, safe_int


class AdminAccountPortalMixin(AdminServiceBase):
    def account_redeem_profile(self, user_id: str) -> dict:
        account = self._require_account(user_id)
        history = self._account_redeem_history(account["id"])
        return {
            "ok": True,
            "user_id": account["id"],
            "balance_cents": safe_int(account.get("balance_cents")),
            "concurrency_limit": safe_int(account.get("concurrency_limit")),
            "history": history,
            "total": len(history),
        }

    def redeem_account_code(self, user_id: str, payload: dict) -> dict:
        if self.storage is None:
            raise RuntimeError("storage not configured")
        account = self._require_account(user_id)
        self._validate_account_active(account)
        code = coerce_text(payload.get("code"))
        if not code:
            raise ValueError("code is required")

        items = self._load_content_bucket("redeem-codes")
        matched = None
        matched_meta = None
        for item in items:
            meta = self._parse_redeem_code_item(item)
            if self._redeem_code_matches(meta, item, code):
                matched = item
                matched_meta = meta
                break
        if not matched or matched_meta is None:
            raise ValueError("redeem code not found")
        if coerce_text(matched.get("status")) != "active":
            raise ValueError("redeem code is not active")

        grant_type = coerce_text(matched_meta.get("type")) or "balance"
        now = time.time()
        result: dict = {
            "ok": True,
            "code": code,
            "type": grant_type,
            "message": "兑换成功",
        }
        if grant_type == "balance":
            amount_cents = safe_int(matched_meta.get("amount_cents"))
            if amount_cents <= 0:
                amount = safe_float(matched_meta.get("amount"))
                amount_cents = int(round(amount * 100))
            if amount_cents <= 0:
                raise ValueError("redeem code has no balance value")
            event = self.storage.adjust_admin_account_balance(
                account["id"],
                amount_cents,
                event_type="redeem",
                note=f"兑换码 {code}",
                actor_type="redeem",
                actor_id=coerce_text(matched.get("id")),
            )
            refreshed = self.storage.get_admin_account(account["id"]) or account
            result.update(
                {
                    "value": amount_cents,
                    "balance_cents": safe_int(refreshed.get("balance_cents")),
                    "event": event,
                }
            )
        elif grant_type == "concurrency":
            concurrency_delta = safe_int(matched_meta.get("concurrency") or matched_meta.get("value"))
            if concurrency_delta <= 0:
                raise ValueError("redeem code has no concurrency value")
            next_account = {
                **account,
                "concurrency_limit": safe_int(account.get("concurrency_limit")) + concurrency_delta,
            }
            saved = self.storage.upsert_admin_account(next_account)
            result.update(
                {
                    "value": concurrency_delta,
                    "concurrency_limit": safe_int(saved.get("concurrency_limit")),
                }
            )
        elif grant_type == "subscription":
            plan_id = coerce_text(matched_meta.get("plan_id"))
            if not plan_id:
                raise ValueError("redeem code has no subscription plan")
            plan = next((item for item in self.storage.list_admin_subscription_plans() if coerce_text(item.get("id")) == plan_id), None)
            if not plan:
                raise ValueError("subscription plan not found")
            validity_days = safe_int(matched_meta.get("validity_days")) or safe_int(plan.get("validity_days")) or 30
            subscription = self.assign_subscription(
                {
                    "user_id": account["id"],
                    "plan_id": plan_id,
                    "group_id": coerce_text(matched_meta.get("group_id")) or coerce_text(plan.get("group_id")),
                    "status": "active",
                    "started_at": now,
                    "expires_at": now + max(1, validity_days) * 86400,
                }
            ).get("item", {})
            result.update(
                {
                    "value": plan_id,
                    "plan_id": plan_id,
                    "plan_name": coerce_text(plan.get("name")),
                    "group_id": coerce_text(subscription.get("group_id")),
                    "validity_days": validity_days,
                    "subscription": subscription,
                }
            )
        else:
            raise ValueError(f"unsupported redeem code type: {grant_type}")

        next_items = []
        for item in items:
            if coerce_text(item.get("id")) == coerce_text(matched.get("id")):
                next_items.append(
                    {
                        **item,
                        "status": "used",
                        "note": self._append_redeem_note(item, account["id"], code, now),
                        "updated_at": now,
                    }
                )
            else:
                next_items.append(item)
        self._save_content_bucket("redeem-codes", next_items)
        return result

    def account_affiliate_detail(self, user_id: str) -> dict:
        account = self._require_account(user_id)
        aff_code = self._ensure_affiliate_code(account)
        invite_items = self._filter_affiliate_items("affiliate-invites", account["id"], aff_code)
        rebate_items = self._filter_affiliate_items("affiliate-rebates", account["id"], aff_code)
        transfer_items = self._filter_affiliate_items("affiliate-transfers", account["id"], aff_code)
        total_rebate_cents = sum(self._content_amount_cents(item) for item in rebate_items)
        transferred_cents = sum(self._content_amount_cents(item) for item in transfer_items)
        available_cents = max(0, total_rebate_cents - transferred_cents)
        return {
            "ok": True,
            "user_id": account["id"],
            "aff_code": aff_code,
            "effective_rebate_rate_percent": self._affiliate_rebate_rate(account),
            "aff_count": len(invite_items),
            "aff_quota_cents": available_cents,
            "aff_history_quota_cents": total_rebate_cents,
            "aff_frozen_quota_cents": 0,
            "invitees": invite_items,
            "rebates": rebate_items,
            "transfers": transfer_items,
        }

    def transfer_account_affiliate_quota(self, user_id: str) -> dict:
        if self.storage is None:
            raise RuntimeError("storage not configured")
        account = self._require_account(user_id)
        detail = self.account_affiliate_detail(account["id"])
        amount_cents = safe_int(detail.get("aff_quota_cents"))
        if amount_cents <= 0:
            raise ValueError("no affiliate quota available")
        event = self.storage.adjust_admin_account_balance(
            account["id"],
            amount_cents,
            event_type="affiliate_transfer",
            note="邀请返利转入余额",
            actor_type="affiliate",
            actor_id=coerce_text(detail.get("aff_code")),
        )
        items = self._load_content_bucket("affiliate-transfers")
        now = time.time()
        transfer = {
            "id": f"aff_transfer_{uuid.uuid4().hex[:16]}",
            "title": f"{coerce_text(detail.get('aff_code'))} transfer",
            "status": "active",
            "summary": f"{amount_cents}",
            "content": json.dumps(
                {
                    "user_id": account["id"],
                    "aff_code": coerce_text(detail.get("aff_code")),
                    "amount_cents": amount_cents,
                    "balance_event_id": coerce_text(event.get("id")),
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            "note": "",
            "created_at": now,
            "updated_at": now,
        }
        self._save_content_bucket("affiliate-transfers", [transfer, *items])
        return {
            "ok": True,
            "transferred_cents": amount_cents,
            "event": event,
            "item": transfer,
        }

    def _account_redeem_history(self, account_id: str) -> list[dict]:
        if self.storage is None:
            return []
        rows = self.storage.list_admin_balance_events(account_id, limit=100)
        history = []
        for row in rows:
            if coerce_text(row.get("event_type")) not in {"redeem", "affiliate_transfer"}:
                continue
            history.append(
                {
                    "id": coerce_text(row.get("id")),
                    "type": coerce_text(row.get("event_type")),
                    "amount_cents": safe_int(row.get("amount_cents")),
                    "before_balance_cents": safe_int(row.get("before_balance_cents")),
                    "after_balance_cents": safe_int(row.get("after_balance_cents")),
                    "note": coerce_text(row.get("note")),
                    "created_at": row.get("created_at"),
                }
            )
        return history

    def _parse_redeem_code_item(self, item: dict) -> dict:
        payload = self._content_payload(item)
        text = "\n".join(
            [
                coerce_text(item.get("title")),
                coerce_text(item.get("summary")),
                coerce_text(item.get("content")),
                coerce_text(item.get("note")),
            ]
        )
        meta = {
            "code": coerce_text(payload.get("code")) or coerce_text(item.get("title")),
            "type": coerce_text(payload.get("type")),
            "amount_cents": safe_int(payload.get("amount_cents")),
            "amount": payload.get("amount"),
            "concurrency": safe_int(payload.get("concurrency")),
            "value": payload.get("value"),
            "plan_id": coerce_text(payload.get("plan_id")),
            "group_id": coerce_text(payload.get("group_id")),
            "validity_days": safe_int(payload.get("validity_days")),
        }
        if not meta["type"]:
            type_match = re.search(r"(?:type|类型)\s*[:=]\s*([a-zA-Z_\-]+)", text)
            if type_match:
                meta["type"] = type_match.group(1).strip().lower()
        if not meta["amount_cents"]:
            cents_match = re.search(r"(?:amount_cents|金额分)\s*[:=]\s*(\d+)", text)
            if cents_match:
                meta["amount_cents"] = safe_int(cents_match.group(1))
        if not meta["amount"]:
            amount_match = re.search(r"(?:amount|金额)\s*[:=]\s*([0-9]+(?:\.[0-9]+)?)", text)
            if amount_match:
                meta["amount"] = amount_match.group(1)
        if not meta["plan_id"]:
            plan_match = re.search(r"(?:plan_id|套餐|计划)\s*[:=]\s*([a-zA-Z0-9_\-]+)", text)
            if plan_match:
                meta["plan_id"] = plan_match.group(1).strip()
        if not meta["concurrency"]:
            concurrency_match = re.search(r"(?:concurrency|并发)\s*[:=]\s*(\d+)", text)
            if concurrency_match:
                meta["concurrency"] = safe_int(concurrency_match.group(1))
        if not meta["type"]:
            if meta["plan_id"]:
                meta["type"] = "subscription"
            elif meta["concurrency"]:
                meta["type"] = "concurrency"
            else:
                meta["type"] = "balance"
        return meta

    def _content_payload(self, item: dict) -> dict:
        for field in ("content", "summary", "note"):
            text = coerce_text(item.get(field))
            if not text:
                continue
            try:
                payload = json.loads(text)
            except Exception:
                continue
            if isinstance(payload, dict):
                return payload
        return {}

    def _redeem_code_matches(self, meta: dict, item: dict, code: str) -> bool:
        wanted = code.strip().lower()
        candidates = {
            coerce_text(meta.get("code")).lower(),
            coerce_text(item.get("id")).lower(),
            coerce_text(item.get("title")).lower(),
        }
        return wanted in candidates

    def _append_redeem_note(self, item: dict, account_id: str, code: str, redeemed_at: float) -> str:
        note = coerce_text(item.get("note"))
        line = f"redeemed_by={account_id};code={code};at={redeemed_at}"
        return f"{note}\n{line}".strip() if note else line

    def _ensure_affiliate_code(self, account: dict) -> str:
        extra = account.get("extra") if isinstance(account.get("extra"), dict) else {}
        aff_code = coerce_text(extra.get("aff_code"))
        if aff_code:
            return aff_code
        seed = coerce_text(account.get("external_key")) or coerce_text(account.get("id"))
        suffix = re.sub(r"[^a-zA-Z0-9]", "", seed)[-8:].upper() or uuid.uuid4().hex[:8].upper()
        aff_code = f"AFF{suffix}"
        if self.storage is not None:
            self.storage.upsert_admin_account({**account, "extra": {**extra, "aff_code": aff_code}})
        return aff_code

    def _filter_affiliate_items(self, bucket: str, user_id: str, aff_code: str) -> list[dict]:
        user_key = user_id.lower()
        code_key = aff_code.lower()
        rows = []
        for item in self._load_content_bucket(bucket):
            payload = self._content_payload(item)
            text = " ".join(
                [
                    coerce_text(item.get("title")),
                    coerce_text(item.get("summary")),
                    coerce_text(item.get("content")),
                    coerce_text(item.get("note")),
                ]
            ).lower()
            owner = coerce_text(payload.get("user_id") or payload.get("account_id")).lower()
            code = coerce_text(payload.get("aff_code") or payload.get("code")).lower()
            if owner == user_key or code == code_key or user_key in text or code_key in text:
                rows.append({**item, "amount_cents": self._content_amount_cents(item)})
        return rows

    def _content_amount_cents(self, item: dict) -> int:
        payload = self._content_payload(item)
        amount_cents = safe_int(payload.get("amount_cents") or payload.get("quota_cents"))
        if amount_cents:
            return amount_cents
        amount = payload.get("amount") or payload.get("quota")
        if amount:
            return int(round(safe_float(amount) * 100))
        for field in ("summary", "note", "content"):
            match = re.search(r"[-+]?\d+(?:\.\d+)?", coerce_text(item.get(field)))
            if match:
                value = safe_float(match.group(0))
                if abs(value) >= 100 and "." not in match.group(0):
                    return int(value)
                return int(round(value * 100))
        return 0

    def _affiliate_rebate_rate(self, account: dict) -> float:
        extra = account.get("extra") if isinstance(account.get("extra"), dict) else {}
        rate = safe_float(extra.get("affiliate_rebate_rate_percent"))
        if rate <= 0:
            rate = 0.0
        return min(rate, 100.0)
