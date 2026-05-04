from __future__ import annotations

from copy import deepcopy


DEFAULT_ROUTE_POLICY = {
    "reasoning_effort": "medium",
    "prompt_cache_mode": "exact",
    "prompt_cache_hints_mode": "auto",
    "prompt_cache_provider": "auto",
    "prompt_cache_retention": "",
    "max_output_tokens": 0,
    "route_cooldown_seconds": 90,
    "route_cooldown_multiplier": 2,
    "route_cooldown_max_seconds": 900,
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


def normalize_prompt_cache_hints_mode(value: object) -> str:
    candidate = str(value or "").strip().lower()
    if candidate in {"off", "passthrough", "auto"}:
        return candidate
    return str(DEFAULT_ROUTE_POLICY["prompt_cache_hints_mode"])


def normalize_prompt_cache_provider(value: object) -> str:
    candidate = str(value or "").strip().lower()
    if candidate in {"auto", "openai", "none"}:
        return candidate
    return str(DEFAULT_ROUTE_POLICY["prompt_cache_provider"])


def normalize_prompt_cache_retention(value: object) -> str:
    candidate = str(value or "").strip().lower()
    if candidate in {"", "default", "off", "none"}:
        return ""
    if candidate in {"in_memory", "24h"}:
        return candidate
    return str(DEFAULT_ROUTE_POLICY["prompt_cache_retention"])


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


def normalize_positive_float(value: object, default: float, *, minimum: float, maximum: float) -> float:
    try:
        parsed = float(value)
    except Exception:
        parsed = float(default)
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
        policy["prompt_cache_hints_mode"] = normalize_prompt_cache_hints_mode(
            raw_policy.get("prompt_cache_hints_mode")
        )
        policy["prompt_cache_provider"] = normalize_prompt_cache_provider(
            raw_policy.get("prompt_cache_provider")
        )
        policy["prompt_cache_retention"] = normalize_prompt_cache_retention(
            raw_policy.get("prompt_cache_retention")
        )
        policy["max_output_tokens"] = normalize_positive_int(
            raw_policy.get("max_output_tokens", policy["max_output_tokens"]),
            int(policy["max_output_tokens"]),
            minimum=0,
            maximum=10000000,
        )
        policy["route_cooldown_seconds"] = normalize_positive_int(
            raw_policy.get("route_cooldown_seconds", policy["route_cooldown_seconds"]),
            int(policy["route_cooldown_seconds"]),
            minimum=1,
            maximum=86400,
        )
        policy["route_cooldown_multiplier"] = normalize_positive_float(
            raw_policy.get("route_cooldown_multiplier", policy["route_cooldown_multiplier"]),
            float(policy["route_cooldown_multiplier"]),
            minimum=1.0,
            maximum=8.0,
        )
        policy["route_cooldown_max_seconds"] = normalize_positive_int(
            raw_policy.get("route_cooldown_max_seconds", policy["route_cooldown_max_seconds"]),
            int(policy["route_cooldown_max_seconds"]),
            minimum=1,
            maximum=604800,
        )
        if policy["route_cooldown_max_seconds"] < policy["route_cooldown_seconds"]:
            policy["route_cooldown_max_seconds"] = int(policy["route_cooldown_seconds"])
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
