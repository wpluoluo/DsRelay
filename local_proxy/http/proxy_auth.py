from __future__ import annotations

import hmac
import re
import secrets
import string
import uuid
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256


AUTH_QUERY_KEYS = ("key", "api_key", "apikey")
AUTH_HEADER_KEYS = (
    "X-API-Key",
    "X-Goog-API-Key",
    "Api-Key",
    "X-Proxy-API-Key",
    "Proxy-Authorization",
)
MANAGED_KEY_PREFIX = "sk-"
MANAGED_KEY_RANDOM_LENGTH = 48
MANAGED_KEY_ALPHABET = string.ascii_letters + string.digits


@dataclass(frozen=True)
class ProxyApiAuthResult:
    ok: bool
    reason: str = ""
    source: str = ""
    key_id: str = ""


def parse_proxy_api_keys(raw_value: str | None) -> tuple[str, ...]:
    """Parse the independent NEWAPI -> local proxy shared secrets."""

    tokens = [
        part.strip()
        for part in re.split(r"[\s,;]+", str(raw_value or ""))
        if part.strip()
    ]
    return tuple(dict.fromkeys(tokens))


def utc_now_text() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")


def generate_proxy_api_key() -> str:
    token = "".join(secrets.choice(MANAGED_KEY_ALPHABET) for _ in range(MANAGED_KEY_RANDOM_LENGTH))
    return f"{MANAGED_KEY_PREFIX}{token}"


def hash_proxy_api_key(key: str) -> str:
    return sha256(str(key or "").encode("utf-8")).hexdigest()


def preview_proxy_api_key(key: str) -> str:
    value = str(key or "").strip()
    if not value:
        return ""
    if len(value) <= 14:
        return value[:4] + "*" * max(0, len(value) - 8) + value[-4:]
    return f"{value[:8]}...{value[-6:]}"


def make_proxy_api_key_record(name: str | None = None) -> tuple[dict, str]:
    key = generate_proxy_api_key()
    now = utc_now_text()
    record = {
        "id": f"pak_{uuid.uuid4().hex[:16]}",
        "name": str(name or "").strip() or "NEWAPI",
        "key": key,
        "key_hash": hash_proxy_api_key(key),
        "key_preview": preview_proxy_api_key(key),
        "enabled": True,
        "created_at": now,
        "updated_at": now,
    }
    return record, key


def normalize_proxy_api_key_records(records) -> list[dict]:
    normalized = []
    seen_ids = set()
    for raw in records or []:
        if not isinstance(raw, dict):
            continue
        raw_key = str(raw.get("key") or "").strip()
        key_hash = str(raw.get("key_hash") or "").strip().lower()
        if raw_key:
            key_hash = hash_proxy_api_key(raw_key)
        if not re.fullmatch(r"[a-f0-9]{64}", key_hash):
            continue

        key_id = str(raw.get("id") or "").strip()
        if not key_id or key_id in seen_ids:
            key_id = f"pak_{uuid.uuid4().hex[:16]}"
        seen_ids.add(key_id)

        name = str(raw.get("name") or "").strip() or "NEWAPI"
        now = utc_now_text()
        created_at = str(raw.get("created_at") or "").strip() or now
        updated_at = str(raw.get("updated_at") or "").strip() or created_at
        preview = str(raw.get("key_preview") or "").strip()
        if raw_key:
            preview = preview_proxy_api_key(raw_key)

        item = {
            "id": key_id,
            "name": name[:80],
            "key_hash": key_hash,
            "key_preview": preview,
            "enabled": raw.get("enabled") is not False,
            "created_at": created_at,
            "updated_at": updated_at,
        }
        if raw_key:
            item["key"] = raw_key
        normalized.append(item)
    return normalized


def public_proxy_api_key_record(record: dict) -> dict:
    return {
        "id": str(record.get("id") or ""),
        "name": str(record.get("name") or ""),
        "key": str(record.get("key") or ""),
        "key_preview": str(record.get("key_preview") or ""),
        "enabled": record.get("enabled") is not False,
        "created_at": str(record.get("created_at") or ""),
        "updated_at": str(record.get("updated_at") or ""),
    }


def extract_proxy_api_key(request) -> tuple[str, str]:
    for header_name in AUTH_HEADER_KEYS:
        value = str(request.headers.get(header_name) or "").strip()
        if value:
            if header_name.lower() == "proxy-authorization" and value.lower().startswith("bearer "):
                return value[7:].strip(), header_name.lower()
            return value, header_name.lower()

    auth_header = str(request.headers.get("Authorization") or "").strip()
    if auth_header:
        if auth_header.lower().startswith("bearer "):
            return auth_header[7:].strip(), "authorization"
        if not any(ch.isspace() for ch in auth_header):
            return auth_header, "authorization"
        return "", "authorization"

    for query_key in AUTH_QUERY_KEYS:
        value = str(request.args.get(query_key) or "").strip()
        if value:
            return value, query_key

    return "", ""


def verify_proxy_api_key(
    request,
    configured_keys: tuple[str, ...],
    managed_records: list[dict] | tuple[dict, ...] = (),
) -> ProxyApiAuthResult:
    enabled_records = [
        record
        for record in (managed_records or [])
        if isinstance(record, dict) and record.get("enabled") is not False and record.get("key_hash")
    ]
    if not configured_keys and not enabled_records:
        return ProxyApiAuthResult(False, "proxy_api_key_not_configured")

    candidate, source = extract_proxy_api_key(request)
    if not candidate:
        return ProxyApiAuthResult(False, "proxy_api_key_missing")

    for expected in configured_keys:
        if hmac.compare_digest(candidate, expected):
            return ProxyApiAuthResult(True, source=source)

    candidate_hash = hash_proxy_api_key(candidate)
    for record in enabled_records:
        if hmac.compare_digest(candidate_hash, str(record.get("key_hash") or "")):
            return ProxyApiAuthResult(True, source=source, key_id=str(record.get("id") or ""))

    return ProxyApiAuthResult(False, "proxy_api_key_invalid", source=source)


def build_proxy_api_key_failure_diagnostics(
    request,
    configured_keys: tuple[str, ...],
    managed_records: list[dict] | tuple[dict, ...] = (),
) -> dict:
    enabled_records = [
        record
        for record in (managed_records or [])
        if isinstance(record, dict) and record.get("enabled") is not False and record.get("key_hash")
    ]
    candidate, source = extract_proxy_api_key(request)
    candidate_hash = hash_proxy_api_key(candidate)[:12] if candidate else ""
    return {
        "source": source or "",
        "candidate_present": bool(candidate),
        "candidate_preview": preview_proxy_api_key(candidate) if candidate else "",
        "candidate_hash_prefix": candidate_hash,
        "env_key_count": len(tuple(configured_keys or ())),
        "managed_key_count": len(enabled_records),
        "managed_key_ids": [str(record.get("id") or "") for record in enabled_records],
        "managed_key_previews": [str(record.get("key_preview") or "") for record in enabled_records],
    }
