from __future__ import annotations

import json
import random
import time
from typing import Any, Callable

import requests

from local_proxy.upstream.models import (
    dedupe_model_candidates,
    discover_model_candidates_from_models,
    extract_model_ids_from_models_payload,
    model_list_url_from_endpoint,
    normalize_model_alias_key,
)


MODEL_UNAVAILABLE_UPSTREAM_ERROR_MARKERS = (
    "model_not_found",
    "model not found",
    "invalid model",
    "model does not exist",
    "requested model does not exist",
    "no available channel for model",
    "unsupported_model",
    "model is not supported",
    "model not exist",
    "模型不存在",
    "模型未找到",
    "模型不支持",
    "无可用渠道",
)


def build_upstream_url_candidates(upstream_url_pool: list[str], upstream_url: str, subpath: str) -> list[str]:
    normalized_subpath = str(subpath or "").strip("/")
    deduped = []
    seen = set()

    for base_url in upstream_url_pool:
        full_url = f"{base_url.rstrip('/')}/{normalized_subpath}" if normalized_subpath else base_url.rstrip("/")
        if full_url in seen:
            continue
        seen.add(full_url)
        deduped.append(full_url)

    if deduped:
        return deduped
    if upstream_url:
        return [f"{upstream_url.rstrip('/')}/{normalized_subpath}"]
    return []


def remaining_retry_window_ms(deadline_monotonic: float) -> int:
    return max(0, int((deadline_monotonic - time.monotonic()) * 1000))


def get_route_health_entry(route_health: dict, state_lock, route_url: str) -> dict:
    with state_lock:
        return route_health.setdefault(
            route_url,
            {
                "consecutive_failures": 0,
                "cooldown_until": 0.0,
                "last_reason": "",
                "last_failure_at": 0.0,
            },
        )


def is_route_in_cooldown(route_health: dict, state_lock, route_url: str) -> bool:
    if not route_url:
        return False
    entry = get_route_health_entry(route_health, state_lock, route_url)
    return float(entry.get("cooldown_until", 0.0) or 0.0) > time.time()


def mark_route_success(route_health: dict, state_lock, route_url: str) -> None:
    if not route_url:
        return
    with state_lock:
        entry = route_health.setdefault(
            route_url,
            {
                "consecutive_failures": 0,
                "cooldown_until": 0.0,
                "last_reason": "",
                "last_failure_at": 0.0,
            },
        )
        entry["consecutive_failures"] = 0
        entry["cooldown_until"] = 0.0
        entry["last_reason"] = ""


def mark_route_failure(
    route_health: dict,
    state_lock,
    route_url: str,
    reason: str,
    *,
    route_cooldown_seconds: int,
    route_switch_window_seconds: int,
    route_failure_threshold: int,
) -> None:
    if not route_url:
        return
    now = time.time()
    cooldown_seconds = max(route_cooldown_seconds, route_switch_window_seconds)
    with state_lock:
        entry = route_health.setdefault(
            route_url,
            {
                "consecutive_failures": 0,
                "cooldown_until": 0.0,
                "last_reason": "",
                "last_failure_at": 0.0,
            },
        )
        entry["consecutive_failures"] = int(entry.get("consecutive_failures", 0) or 0) + 1
        entry["last_reason"] = reason or ""
        entry["last_failure_at"] = now
        if entry["consecutive_failures"] >= route_failure_threshold:
            entry["cooldown_until"] = max(
                float(entry.get("cooldown_until", 0.0) or 0.0),
                now + cooldown_seconds,
            )


def build_attempt_url_cycle(
    candidate_urls: list[str],
    blocked_urls: set[str],
    *,
    route_health: dict,
    route_selection_state: dict,
    state_lock,
    randomize_endpoints: bool,
    route_score_provider: Callable[[str], float] | None = None,
) -> list[str]:
    active_urls = [
        url
        for url in candidate_urls
        if url not in blocked_urls and not is_route_in_cooldown(route_health, state_lock, url)
    ]
    if not active_urls:
        active_urls = [url for url in candidate_urls if url not in blocked_urls]
    if len(active_urls) <= 1:
        return active_urls

    now = time.time()
    with state_lock:
        ranked_urls = []
        for url in active_urls:
            entry = route_health.setdefault(
                url,
                {
                    "consecutive_failures": 0,
                    "cooldown_until": 0.0,
                    "last_reason": "",
                    "last_failure_at": 0.0,
                },
            )
            ranked_urls.append(
                (
                    -float(route_score_provider(url) if callable(route_score_provider) else 0.0),
                    int(entry.get("consecutive_failures", 0) or 0),
                    -float(entry.get("last_failure_at", 0.0) or 0.0),
                    url,
                )
            )

        ranked_urls.sort()
        ordered = [item[-1] for item in ranked_urls]

        group_key = "|".join(ordered)
        cursor_entry = route_selection_state.get(group_key, {})
        cursor_value = int(cursor_entry.get("cursor", 0) or 0) % len(ordered)
        last_used_at = float(cursor_entry.get("last_used_at", 0.0) or 0.0)

        # If route health changed materially, reset to the healthiest route first.
        if now - last_used_at > 300:
            cursor_value = 0

        if randomize_endpoints:
            jitter_seed = int(now // 15)
            jitter = (hash(f"{group_key}:{jitter_seed}") % len(ordered)) if len(ordered) > 1 else 0
            cursor_value = (cursor_value + jitter) % len(ordered)

        rotated = ordered[cursor_value:] + ordered[:cursor_value]
        route_selection_state[group_key] = {
            "cursor": (cursor_value + 1) % len(ordered),
            "last_used_at": now,
        }

    if randomize_endpoints and len(rotated) > 1:
        if len(rotated) == 2:
            if random.random() < 0.5:
                return [rotated[1], rotated[0]]
            return rotated
        head = rotated[:1]
        tail = rotated[1:]
        random.shuffle(tail)
        return head + tail
    return rotated


def should_enforce_route_switch_window(candidate_urls: list[str], retry_allowed: bool) -> bool:
    return retry_allowed and len(candidate_urls) > 1


def response_indicates_model_unavailable(extract_searchable_text: Callable[[requests.Response], str], response: requests.Response) -> bool:
    searchable = extract_searchable_text(response)
    return any(marker in searchable for marker in MODEL_UNAVAILABLE_UPSTREAM_ERROR_MARKERS)


def get_cached_model_list(model_route_cache: dict, cache_stats_bump: Callable[[str], None], route_url: str) -> list[str] | None:
    model_lists = model_route_cache.setdefault("model_lists", {})
    cache_key = model_list_url_from_endpoint(route_url)
    entry = model_lists.get(cache_key)
    if not isinstance(entry, dict):
        cache_stats_bump("model_list_misses")
        return None
    if float(entry.get("expires_at", 0.0) or 0.0) <= time.time():
        cache_stats_bump("model_list_misses")
        return None
    models = entry.get("models")
    if isinstance(models, list):
        cache_stats_bump("model_list_hits")
        return list(models)
    cache_stats_bump("model_list_misses")
    return None


def cache_model_list(
    model_route_cache: dict,
    state_lock,
    save_cache: Callable[[], None],
    route_url: str,
    models: list[str],
    *,
    model_probe_ttl_seconds: int,
) -> None:
    cache_key = model_list_url_from_endpoint(route_url)
    now = time.time()
    with state_lock:
        model_route_cache.setdefault("model_lists", {})[cache_key] = {
            "models": list(dict.fromkeys(models)),
            "fetched_at": now,
            "expires_at": now + model_probe_ttl_seconds,
        }
        save_cache()


def fetch_upstream_model_list(
    *,
    route_url: str,
    request_kwargs: dict,
    request_id: str,
    get_cached: Callable[[str], list[str] | None],
    cache_list: Callable[[str, list[str]], None],
    enabled: bool,
    request_timeout: int,
    probe_timeout_seconds: int,
    session: Any,
    logger,
    extract_error_preview: Callable[[requests.Response], str],
    json_body_from_response: Callable[[requests.Response], dict],
) -> list[str]:
    cached_models = get_cached(route_url)
    if cached_models is not None:
        return cached_models
    if not enabled:
        return []

    models_url = model_list_url_from_endpoint(route_url)
    headers = dict(request_kwargs.get("headers") or {})
    headers.pop("Content-Length", None)
    headers.pop("content-length", None)
    headers.pop("Content-Type", None)
    headers.pop("content-type", None)
    try:
        response = session.get(
            models_url,
            headers=headers,
            params=request_kwargs.get("params"),
            timeout=min(request_timeout, probe_timeout_seconds),
        )
    except requests.RequestException as exc:
        logger.warning(
            "request_id=%s upstream_model_probe_exception route=%s models_url=%s error=%s",
            request_id,
            route_url,
            models_url,
            str(exc),
        )
        cache_list(route_url, [])
        return []

    if response.status_code >= 400:
        logger.warning(
            "request_id=%s upstream_model_probe_failed route=%s models_url=%s status=%s preview=%s",
            request_id,
            route_url,
            models_url,
            response.status_code,
            extract_error_preview(response),
        )
        cache_list(route_url, [])
        return []

    models = extract_model_ids_from_models_payload(json_body_from_response(response))
    cache_list(route_url, models)
    logger.info(
        "request_id=%s upstream_model_probe route=%s models=%s",
        request_id,
        route_url,
        len(models),
    )
    return models


def build_model_candidate_order_for_route(
    *,
    route_url: str,
    model_candidates: list[str],
    request_kwargs: dict,
    request_id: str,
    get_cached_route_candidates: Callable[[str, str], list[str]],
    fetch_model_list: Callable[[str, dict, str], list[str]],
    get_model_candidate_score: Callable[[str, str, str], float | int],
    logger,
) -> dict:
    if not model_candidates:
        return {
            "candidates": [],
            "cache_hit": False,
            "probed": False,
            "exact_available": False,
            "discovered_count": 0,
        }

    logical_model = model_candidates[0]
    candidates = dedupe_model_candidates(model_candidates)
    def compact(items: list[str], limit: int = 4) -> str:
        values = list(items or [])
        if len(values) <= limit:
            return ", ".join(values)
        return ", ".join(values[:limit]) + f" ... +{len(values) - limit}"
    cached_candidates = get_cached_route_candidates(logical_model, route_url)
    if cached_candidates:
        ordered = dedupe_model_candidates(cached_candidates + candidates)
        logger.info(
            "request_id=%s 模型候选 线路=%s 逻辑模型=%s 顺序=%s 已探测=%s 命中缓存=%s",
            request_id,
            route_url,
            logical_model,
            compact(ordered),
            False,
            True,
        )
        return {
            "candidates": ordered,
            "cache_hit": True,
            "probed": False,
            "exact_available": False,
            "discovered_count": 0,
        }

    available_models = fetch_model_list(route_url, request_kwargs, request_id)
    discovered = discover_model_candidates_from_models(logical_model, candidates, available_models)

    available_by_key = {}
    for model_id in available_models:
        available_by_key.setdefault(normalize_model_alias_key(model_id), model_id)
    available_keys = set(available_by_key)
    exact_available = [
        available_by_key[normalize_model_alias_key(candidate)]
        for candidate in candidates
        if normalize_model_alias_key(candidate) in available_keys
    ]
    unavailable_known = bool(available_models) and not exact_available

    if unavailable_known and discovered:
        candidates = discovered + candidates
    else:
        candidates = exact_available + candidates + discovered
    candidates = dedupe_model_candidates(candidates)

    indexed = list(enumerate(candidates))
    indexed.sort(
        key=lambda item: (
            -get_model_candidate_score(logical_model, route_url, item[1]),
            0 if normalize_model_alias_key(item[1]) in available_keys else 1,
            item[0],
        )
    )
    ordered = [candidate for _, candidate in indexed]
    logger.info(
        "request_id=%s 模型候选 线路=%s 逻辑模型=%s 顺序=%s 已探测=%s",
        request_id,
        route_url,
        logical_model,
        compact(ordered),
        bool(available_models),
    )
    return {
        "candidates": ordered,
        "cache_hit": False,
        "probed": bool(available_models),
        "exact_available": bool(exact_available),
        "discovered_count": len(discovered),
    }


def order_model_candidates_for_route(**kwargs) -> list[str]:
    return build_model_candidate_order_for_route(**kwargs)["candidates"]


def apply_model_candidate_to_request_kwargs(request_kwargs: dict, model_candidate: str | None) -> dict:
    current_request_kwargs = dict(request_kwargs)
    if not model_candidate:
        return current_request_kwargs

    json_payload = current_request_kwargs.get("json")
    if isinstance(json_payload, dict) and isinstance(json_payload.get("model"), str):
        variant_payload = dict(json_payload)
        variant_payload["model"] = model_candidate
        current_request_kwargs["json"] = variant_payload

    return current_request_kwargs


def model_candidate_differs_from_logical(logical_model: str | None, model_candidate: str | None) -> bool:
    if not logical_model or not model_candidate:
        return False
    return normalize_model_alias_key(logical_model) != normalize_model_alias_key(model_candidate)


def should_race_model_candidates_for_route(
    *,
    subpath: str,
    method: str,
    order_info: dict,
    ordered_model_candidates: list[str],
    enable_model_candidate_race: bool,
) -> bool:
    if not enable_model_candidate_race:
        return False
    if str(method or "").upper() != "POST":
        return False
    if subpath not in {"chat/completions", "images/generations"}:
        return False
    if len(ordered_model_candidates) <= 1:
        return False
    if order_info.get("cache_hit"):
        return False
    if order_info.get("exact_available") or int(order_info.get("discovered_count", 0) or 0) > 0:
        return False
    return True


def append_race_attempts(
    attempts: list[dict],
    race_attempts: list[dict],
    *,
    logical_model: str | None,
    route_url: str,
    mark_route_success_fn: Callable[[str], None],
    record_model_candidate_result_fn: Callable[..., None],
) -> set[str]:
    failed_model_keys = set()
    for race_attempt in race_attempts:
        race_attempt = dict(race_attempt)
        race_attempt["attempt"] = len(attempts) + 1
        attempts.append(race_attempt)

        model_candidate = race_attempt.get("model")
        status_code = int(race_attempt.get("status_code", 0) or 0)
        reason = str(race_attempt.get("reason") or "")
        if status_code and status_code < 400:
            mark_route_success_fn(route_url)
            record_model_candidate_result_fn(
                logical_model=logical_model,
                route_url=route_url,
                model_candidate=model_candidate,
                success=True,
            )
            continue
        if reason.startswith("model_unavailable"):
            failed_model_keys.add(normalize_model_alias_key(model_candidate))
            record_model_candidate_result_fn(
                logical_model=logical_model,
                route_url=route_url,
                model_candidate=model_candidate,
                success=False,
            )
    return failed_model_keys
