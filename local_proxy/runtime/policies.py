from __future__ import annotations

from copy import deepcopy

from local_proxy.upstream.models import (
    dedupe_model_candidates,
    normalize_model_alias_key,
    parse_model_aliases,
    parse_supported_model_ids,
)


DEFAULT_ROUTE_POLICY = {
    "reasoning_effort": "medium",
    "prompt_cache_mode": "exact",
    "prompt_cache_hints_mode": "auto",
    "prompt_cache_provider": "auto",
    "text_upstream_protocol": "auto",
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


def normalize_text_upstream_protocol(value: object) -> str:
    candidate = str(value or "").strip().lower()
    if candidate in {"auto", "openai", "responses"}:
        return candidate
    return str(DEFAULT_ROUTE_POLICY["text_upstream_protocol"])


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
        policy["text_upstream_protocol"] = normalize_text_upstream_protocol(
            raw_policy.get("text_upstream_protocol")
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


def _route_lookup_parts(route_url: str, normalize_pool_url) -> tuple[str, str, str, bool]:
    route_text = str(route_url or "").strip()
    base_text, fragment = route_text.split("#", 1) if "#" in route_text else (route_text, "")
    normalized_base = normalize_pool_url(base_text)
    normalized_identity = f"{normalized_base}#{fragment}" if normalized_base and fragment.startswith("__route=") else ""
    return route_text, normalized_base, normalized_identity, bool(normalized_identity)


def _build_pool_route_urls(pool: dict, normalize_pool_url) -> list[str]:
    pool_name = str(pool.get("name") or "").strip()
    route_urls = []
    for route_ordinal, value in enumerate((pool.get("urls") or []), start=1):
        normalized_value = normalize_pool_url(value)
        route_urls.append(
            f"{normalized_value}#__route={__import__('hashlib').sha1(f'{pool_name}|{normalized_value}|{int(route_ordinal)}'.encode('utf-8')).hexdigest()[:12]}"
        )
    return route_urls


def get_route_policy_for_url(pools: list[dict], route_url: str, normalize_pool_url) -> dict:
    route_text, normalized_url, normalized_identity, route_has_identity = _route_lookup_parts(route_url, normalize_pool_url)
    for pool in pools or []:
        if not isinstance(pool, dict) or not pool.get("enabled", True):
            continue
        route_urls = _build_pool_route_urls(pool, normalize_pool_url)
        if route_has_identity and normalized_identity and normalized_identity in route_urls:
            return normalize_route_policy(pool.get("route_policy"))
        if route_text and route_text in route_urls:
            return normalize_route_policy(pool.get("route_policy"))
        urls = [normalize_pool_url(value) for value in (pool.get("urls") or [])]
        if not route_has_identity and normalized_url and normalized_url in urls:
            return normalize_route_policy(pool.get("route_policy"))
    return normalize_route_policy(None)


def get_pool_model_aliases_for_url(pools: list[dict], route_url: str, normalize_pool_url) -> dict[str, list[str]]:
    route_text, normalized_url, normalized_identity, route_has_identity = _route_lookup_parts(route_url, normalize_pool_url)
    for pool in pools or []:
        if not isinstance(pool, dict) or not pool.get("enabled", True):
            continue
        route_urls = _build_pool_route_urls(pool, normalize_pool_url)
        matches_route = bool((route_has_identity and normalized_identity and normalized_identity in route_urls) or (route_text and route_text in route_urls))
        urls = [normalize_pool_url(value) for value in (pool.get("urls") or [])]
        matches_base = bool((not route_has_identity) and normalized_url and normalized_url in urls)
        if matches_route or matches_base:
            return parse_model_aliases(pool.get("model_aliases_text"))
    return {}


def get_pool_supported_models_for_url(pools: list[dict], route_url: str, normalize_pool_url) -> list[str]:
    route_text, normalized_url, normalized_identity, route_has_identity = _route_lookup_parts(route_url, normalize_pool_url)
    for pool in pools or []:
        if not isinstance(pool, dict) or not pool.get("enabled", True):
            continue
        route_urls = _build_pool_route_urls(pool, normalize_pool_url)
        matches_route = bool((route_has_identity and normalized_identity and normalized_identity in route_urls) or (route_text and route_text in route_urls))
        urls = [normalize_pool_url(value) for value in (pool.get("urls") or [])]
        matches_base = bool((not route_has_identity) and normalized_url and normalized_url in urls)
        if matches_route or matches_base:
            supported_models = parse_supported_model_ids(pool.get("supported_models_text"))
            route_aliases = parse_model_aliases(pool.get("model_aliases_text"))
            expanded_supported_models = []
            for model_id in supported_models:
                expanded_supported_models.append(model_id)
                for alias_target in route_aliases.get(normalize_model_alias_key(model_id), []):
                    expanded_supported_models.append(alias_target)
            return dedupe_model_candidates(expanded_supported_models)
    return []


def get_pool_priority_for_url(pools: list[dict], route_url: str, normalize_pool_url) -> int:
    route_text, normalized_url, normalized_identity, route_has_identity = _route_lookup_parts(route_url, normalize_pool_url)
    for pool in pools or []:
        if not isinstance(pool, dict) or not pool.get("enabled", True):
            continue
        try:
            priority = int(pool.get("priority", 100) or 100)
        except Exception:
            priority = 100
        route_urls = _build_pool_route_urls(pool, normalize_pool_url)
        matches_route = bool((route_has_identity and normalized_identity and normalized_identity in route_urls) or (route_text and route_text in route_urls))
        urls = [normalize_pool_url(value) for value in (pool.get("urls") or [])]
        matches_base = bool((not route_has_identity) and normalized_url and normalized_url in urls)
        if matches_route or matches_base:
            return priority
    return 0
