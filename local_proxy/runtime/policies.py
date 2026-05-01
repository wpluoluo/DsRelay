from __future__ import annotations

from copy import deepcopy


DEFAULT_ROUTE_POLICY = {
    "reasoning_effort": "medium",
    "prompt_cache_mode": "exact",
    "compression_mode": "balanced",
    "max_history_messages": 24,
    "max_tool_chars": 24000,
    "max_input_chars": 180000,
    "max_output_tokens": 0,
}


def normalize_reasoning_effort(value: object) -> str:
    candidate = str(value or "").strip().lower()
    if candidate in {"low", "medium", "high"}:
        return candidate
    return str(DEFAULT_ROUTE_POLICY["reasoning_effort"])


def normalize_prompt_cache_mode(value: object) -> str:
    candidate = str(value or "").strip().lower()
    if candidate in {"off", "exact"}:
        return candidate
    return str(DEFAULT_ROUTE_POLICY["prompt_cache_mode"])


def normalize_compression_mode(value: object) -> str:
    candidate = str(value or "").strip().lower()
    if candidate in {"off", "light", "balanced", "aggressive"}:
        return candidate
    return str(DEFAULT_ROUTE_POLICY["compression_mode"])


def normalize_positive_int(value: object, default: int, *, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = int(default)
    if parsed < minimum:
        return minimum
    if parsed > maximum:
        return maximum
    return parsed


def normalize_route_policy(raw_policy: object) -> dict:
    policy = deepcopy(DEFAULT_ROUTE_POLICY)
    if isinstance(raw_policy, dict):
        policy["reasoning_effort"] = normalize_reasoning_effort(raw_policy.get("reasoning_effort"))
        policy["prompt_cache_mode"] = normalize_prompt_cache_mode(raw_policy.get("prompt_cache_mode"))
        policy["compression_mode"] = normalize_compression_mode(raw_policy.get("compression_mode"))
        policy["max_history_messages"] = normalize_positive_int(
            raw_policy.get("max_history_messages", policy["max_history_messages"]),
            int(policy["max_history_messages"]),
            minimum=2,
            maximum=200,
        )
        policy["max_tool_chars"] = normalize_positive_int(
            raw_policy.get("max_tool_chars", policy["max_tool_chars"]),
            int(policy["max_tool_chars"]),
            minimum=1000,
            maximum=500000,
        )
        policy["max_input_chars"] = normalize_positive_int(
            raw_policy.get("max_input_chars", policy["max_input_chars"]),
            int(policy["max_input_chars"]),
            minimum=2000,
            maximum=2000000,
        )
        policy["max_output_tokens"] = normalize_positive_int(
            raw_policy.get("max_output_tokens", policy["max_output_tokens"]),
            int(policy["max_output_tokens"]),
            minimum=0,
            maximum=10000000,
        )
    return policy


def normalize_pool_route_policies(raw_pools: object) -> list[dict]:
    if not isinstance(raw_pools, list):
        return []
    normalized = []
    for item in raw_pools:
        if not isinstance(item, dict):
            continue
        pool = dict(item)
        pool["route_policy"] = normalize_route_policy(item.get("route_policy"))
        normalized.append(pool)
    return normalized


def get_route_policy_for_url(pools: list[dict], route_url: str, normalize_pool_url) -> dict:
    normalized_url = normalize_pool_url(route_url)
    for pool in pools or []:
        if not isinstance(pool, dict) or not pool.get("enabled", True):
            continue
        urls = [normalize_pool_url(value) for value in (pool.get("urls") or [])]
        if normalized_url and normalized_url in urls:
            return normalize_route_policy(pool.get("route_policy"))
    return normalize_route_policy(None)
