from __future__ import annotations

import hashlib
import json
import time
from copy import deepcopy


DEFAULT_REQUEST_CACHE_TTL_SECONDS = 900

READ_ONLY_TOOL_NAME_KEYWORDS = (
    "read",
    "list",
    "ls",
    "dir",
    "search",
    "grep",
    "glob",
    "find",
    "query",
    "fetch",
    "get",
    "view",
    "show",
    "stat",
    "inspect",
)

MUTATING_TOOL_NAME_KEYWORDS = (
    "write",
    "edit",
    "replace",
    "delete",
    "remove",
    "rename",
    "move",
    "copy",
    "create",
    "insert",
    "update",
    "patch",
    "exec",
    "execute",
    "run",
    "bash",
    "shell",
    "command",
    "terminal",
    "todo",
    "dispatch",
    "submit",
    "send",
    "apply",
)


def canonical_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def canonicalize_tool_name(tool_name: str | None) -> str:
    return "".join(ch.lower() for ch in str(tool_name or "") if ch.isalnum())


def get_tool_name(tool: dict | None) -> str:
    if not isinstance(tool, dict):
        return ""
    if isinstance(tool.get("function"), dict):
        return str((tool.get("function") or {}).get("name") or "")
    return str(tool.get("name") or "")


def is_read_only_tool_name(tool_name: str | None) -> bool:
    canonical_name = canonicalize_tool_name(tool_name)
    if not canonical_name:
        return False
    if any(marker in canonical_name for marker in MUTATING_TOOL_NAME_KEYWORDS):
        return False
    return any(marker in canonical_name for marker in READ_ONLY_TOOL_NAME_KEYWORDS)


def all_tools_read_only(tools) -> bool:
    if not isinstance(tools, list) or not tools:
        return False
    tool_names = [get_tool_name(tool) for tool in tools if isinstance(tool, dict)]
    if not tool_names or len(tool_names) != len(tools):
        return False
    return all(is_read_only_tool_name(name) for name in tool_names)


def normalize_cache_payload(payload: dict | None) -> dict:
    if not isinstance(payload, dict):
        return {}
    normalized = deepcopy(payload)
    normalized.pop("stream", None)
    normalized.pop("stream_options", None)
    return normalized


def build_cache_key(*, protocol: str, path: str, payload: dict | None, route_policy: dict | None) -> str:
    canonical_payload = canonical_json(normalize_cache_payload(payload))
    policy = dict(route_policy or {})
    cache_relevant_policy = {
        "prompt_cache_mode": policy.get("prompt_cache_mode"),
    }
    canonical_policy = canonical_json(cache_relevant_policy)
    base = "|".join(
        [
            str(protocol or "").strip().lower(),
            str(path or "").strip().lower(),
            canonical_policy,
            canonical_payload,
        ]
    )
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def build_coalescing_key(*, protocol: str, path: str, payload: dict | None) -> str:
    canonical_payload = canonical_json(normalize_cache_payload(payload))
    base = "|".join(
        [
            str(protocol or "").strip().lower(),
            str(path or "").strip().lower(),
            canonical_payload,
        ]
    )
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def is_cacheable_request(*, request_payload: dict | None, route_policy: dict | None, stream: bool) -> bool:
    if not isinstance(request_payload, dict):
        return False
    if str((route_policy or {}).get("prompt_cache_mode") or "off") != "exact":
        return False
    tools = request_payload.get("tools")
    if tools:
        if not all_tools_read_only(tools):
            return False
        tool_choice = request_payload.get("tool_choice")
        if isinstance(tool_choice, dict):
            choice_type = str(tool_choice.get("type") or "").strip().lower()
            if choice_type not in {"", "function"}:
                return False
            if choice_type == "function" and not is_read_only_tool_name(
                ((tool_choice.get("function") or {}).get("name"))
            ):
                return False
        elif str(tool_choice or "").strip().lower() not in {"", "auto", "required"}:
            return False
    if request_payload.get("response_format"):
        return False
    messages = request_payload.get("messages")
    if not isinstance(messages, list) or not messages:
        return False
    return True


def build_cached_execution(
    *,
    cached_payload: dict,
    request_payload: dict | None,
    request_repairs: int,
    model_candidates: list[str],
    route_policy: dict,
    cache_key: str,
    route_policy_metrics: dict | None = None,
) -> dict:
    cached_body = deepcopy(cached_payload.get("response_body") or {})
    return {
        "cache_hit": True,
        "cache_key": cache_key,
        "cached_at": float(cached_payload.get("created_at", 0.0) or 0.0),
        "cache_source": str(cached_payload.get("source") or "sqlite"),
        "upstream_url": str(cached_payload.get("upstream_url") or ""),
        "upstream_pool_name": str(cached_payload.get("pool_name") or ""),
        "upstream_key_index": cached_payload.get("key_index"),
        "resolved_model": str(cached_payload.get("model_name") or ""),
        "upstream_url_pool": [],
        "attempted_pool_names": [str(cached_payload.get("pool_name") or "")] if str(cached_payload.get("pool_name") or "") else [],
        "route_pool_size": 0,
        "tool_schemas": {},
        "upstream_payload": request_payload if isinstance(request_payload, dict) else None,
        "upstream_stream": bool((request_payload or {}).get("stream")) if isinstance(request_payload, dict) else False,
        "upstream_response": None,
        "attempts": [],
        "request_exception": None,
        "retry_count": 0,
        "request_repairs": request_repairs,
        "model_candidates": model_candidates,
        "initial_key_choice": {},
        "logical_model": model_candidates[0] if model_candidates else str((request_payload or {}).get("model") or ""),
        "selected_pool_name": str(cached_payload.get("pool_name") or ""),
        "selected_key_index": cached_payload.get("key_index"),
        "route_policy": route_policy,
        "route_policy_metrics": deepcopy(route_policy_metrics or {}),
        "cached_response_body": cached_body,
    }


def build_cache_record(
    *,
    cache_key: str,
    protocol: str,
    path: str,
    request_payload: dict | None,
    route_policy: dict | None,
    response_body: dict,
    upstream_url: str,
    model_name: str | None,
    pool_name: str | None = None,
    key_index: int | None = None,
    ttl_seconds: int = DEFAULT_REQUEST_CACHE_TTL_SECONDS,
) -> dict:
    now = time.time()
    return {
        "cache_key": cache_key,
        "protocol": str(protocol or ""),
        "path": str(path or ""),
        "request_fingerprint": build_cache_key(
            protocol=protocol,
            path=path,
            payload=request_payload,
            route_policy=route_policy,
        ),
        "request_payload": deepcopy(request_payload or {}),
        "route_policy": deepcopy(route_policy or {}),
        "response_body": deepcopy(response_body or {}),
        "upstream_url": str(upstream_url or ""),
        "model_name": str(model_name or ""),
        "pool_name": str(pool_name or ""),
        "key_index": key_index,
        "created_at": now,
        "expires_at": now + max(60, int(ttl_seconds or DEFAULT_REQUEST_CACHE_TTL_SECONDS)),
        "source": "sqlite",
    }
