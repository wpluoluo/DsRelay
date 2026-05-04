from __future__ import annotations

import os
import re
import time
from collections import deque


def read_recent_log_lines(*, log_path, app_started_at_epoch: float, limit: int) -> list[str]:
    if not log_path.exists():
        return []

    with log_path.open("r", encoding="utf-8", errors="ignore") as log_file:
        recent_candidates = list(deque(log_file, maxlen=max(limit * 4, limit)))

    filtered_lines = []
    for line in recent_candidates:
        lowered_line = line.lower()
        if "example.com" in lowered_line or "example domain" in lowered_line:
            continue
        if not re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", line):
            continue
        try:
            line_epoch = time.mktime(time.strptime(line[:19], "%Y-%m-%d %H:%M:%S"))
        except Exception:
            continue
        if line_epoch >= app_started_at_epoch:
            filtered_lines.append(line)

    return filtered_lines[-limit:]


def build_runtime_snapshot(context: dict) -> dict:
    uptime_seconds = max(0, int(time.time() - float(context["app_started_at_epoch"])))
    cooled_routes = 0
    route_health = context.get("route_health") or {}
    now = time.time()
    for entry in route_health.values():
        if float(entry.get("cooldown_until", 0.0) or 0.0) > now:
            cooled_routes += 1

    return {
        "pid": os.getpid(),
        "python_executable": context["python_executable"],
        "port": context["port"],
        "started_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(float(context["app_started_at_epoch"]))),
        "uptime_seconds": uptime_seconds,
        "request_timeout_seconds": context["request_timeout"],
        "request_normalization": context["enable_request_normalization"],
        "max_completion_tokens": context["max_completion_tokens"],
        "model_capability_count": context["model_capability_count"],
        "inject_zh_system_prompt": context["inject_zh_system_prompt"],
        "force_upstream_chat_stream": context["force_upstream_chat_stream"],
        "upstream_urls": list(context["upstream_urls"]),
        "upstream_url_count": len(context["upstream_urls"]),
        "upstream_api_key_configured": bool(context["upstream_api_key"]),
        "upstream_api_key_preview": context["mask_secret"](context["upstream_api_key"]),
        "proxy_api_key_configured": int(context.get("proxy_api_key_count") or 0) > 0,
        "proxy_api_key_count": int(context.get("proxy_api_key_count") or 0),
        "proxy_api_key_env_count": int(context.get("proxy_api_key_env_count") or 0),
        "proxy_api_key_managed_count": int(context.get("proxy_api_key_managed_count") or 0),
        "proxy_api_key_managed_enabled_count": int(context.get("proxy_api_key_managed_enabled_count") or 0),
        "model_alias_count": context["model_alias_count"],
        "model_aliases": dict(context["model_aliases"]),
        "model_routing": {
            "probe_enabled": context["enable_model_probe"],
            "probe_timeout_seconds": context["model_probe_timeout_seconds"],
            "probe_ttl_seconds": context["model_probe_ttl_seconds"],
            "route_cache_ttl_seconds": context["model_route_cache_ttl_seconds"],
            "interruption_resume_enabled": context["enable_interruption_resume"],
            "interruption_resume_ttl_seconds": context["interruption_resume_ttl_seconds"],
            "interruption_resume_max_chars": context["interruption_resume_max_chars"],
            "interruption_resume_min_chars": context["interruption_resume_min_chars"],
            "candidate_race_enabled": context["enable_model_candidate_race"],
            "candidate_race_limit": context["model_candidate_race_limit"],
            "candidate_race_timeout_seconds": context["model_candidate_race_timeout_seconds"],
            "route_cache_entries": context["count_model_route_cache_entries"](),
            "interrupted_response_entries": context["count_interrupted_response_entries"](),
            "learned_capability_entries": context["count_learned_model_capability_entries"](),
            "model_list_cache_entries": len(context["model_list_cache_entries"]),
            "cache_path": str(context["model_route_cache_path"]),
            "db_label": context["db_label"],
            "db_enabled": context["db_enabled"],
            "cache_stats": context["cache_stats_snapshot"](),
        },
        "config_path": str(context["config_path"]),
        "config_file_exists": context["config_file_exists"],
        "retry_config": {
            "max_retries": context["max_retries"],
            "backoff_ms": context["retry_backoff_ms"],
            "max_backoff_ms": context["retry_max_backoff_ms"],
            "route_failure_threshold": context["route_failure_threshold"],
            "route_cooldown_seconds": context["route_cooldown_seconds"],
            "route_switch_window_seconds": context["route_switch_window_seconds"],
            "randomize_endpoints": context["randomize_endpoints"],
            "retryable_status_codes": sorted(context["retryable_status_codes"]),
            "cooled_routes": cooled_routes,
        },
        "connection_pool": {
            "http_pool_connections": context["http_pool_connections"],
            "http_pool_maxsize": context["http_pool_maxsize"],
            "key_failure_threshold": context["pool_key_failure_threshold"],
            "key_cooldown_seconds": context["pool_key_cooldown_seconds"],
            "state": context["connection_pool_snapshot"](),
        },
        "image_generation": {
            "upstream_protocol": context["image_upstream_protocol"],
            "task_poll_timeout_seconds": context["image_task_poll_timeout_seconds"],
            "task_poll_interval_seconds": context["image_task_poll_interval_seconds"],
        },
        "capabilities": list(context["capabilities"]),
    }


def build_dashboard_state(context: dict) -> dict:
    runtime_snapshot = context["build_runtime_snapshot"]()
    request_snapshot = context["request_recorder_snapshot"]()
    route_health_snapshot = {
        route_url: dict(entry)
        for route_url, entry in (context.get("route_health") or {}).items()
    }
    recent_requests = request_snapshot["recent_requests"]
    cache_stats = (runtime_snapshot.get("model_routing") or {}).get("cache_stats") or {}
    local_response_cache_hits = int(cache_stats.get("prompt_cache_hits", 0) or 0)
    local_response_cache_misses = int(cache_stats.get("prompt_cache_misses", 0) or 0)
    total_local_cache_attempts = local_response_cache_hits + local_response_cache_misses
    local_response_cache_hit_rate = (
        local_response_cache_hits / total_local_cache_attempts
        if total_local_cache_attempts > 0 else 0.0
    )
    upstream_prompt_cache_requests = 0
    upstream_prompt_cache_hits = 0
    prompt_hint_requests = 0

    cache_read_samples = [
        int(item.get("cache_read_input_tokens") or 0)
        for item in recent_requests
        if int(item.get("cache_read_input_tokens") or 0) > 0
    ]
    avg_cache_read_tokens = (
        sum(cache_read_samples) / len(cache_read_samples)
        if cache_read_samples else 0.0
    )

    session_route_map: dict[str, set[str]] = {}
    route_sessions: dict[str, set[str]] = {}
    sticky_sessions = 0
    for item in recent_requests:
        if bool(item.get("upstream_prompt_cache_eligible")):
            upstream_prompt_cache_requests += 1
        if bool(item.get("upstream_prompt_cache_hit")):
            upstream_prompt_cache_hits += 1
        if bool(item.get("prompt_cache_hint_applied")) or bool(item.get("prompt_cache_hint_passthrough")):
            prompt_hint_requests += 1
        affinity_key = str(item.get("session_affinity_key") or "").strip()
        route_url = str(item.get("upstream_url") or "").strip()
        if not affinity_key or not route_url:
            continue
        session_route_map.setdefault(affinity_key, set()).add(route_url)
        route_sessions.setdefault(route_url, set()).add(affinity_key)
    for routes in session_route_map.values():
        if len(routes) == 1:
            sticky_sessions += 1
    sticky_total = len(session_route_map)
    sticky_rate = (sticky_sessions / sticky_total) if sticky_total > 0 else 0.0
    active_affinity_keys = context.get("active_session_affinity_keys")
    active_affinity_keys = int(active_affinity_keys()) if callable(active_affinity_keys) else 0

    route_observability = {}
    for route_url in set(list(context["upstream_urls"]) + list(route_health_snapshot.keys())):
        route_observability[str(route_url)] = {
            "route_url": str(route_url),
            "pool_name": "",
            "request_count": 0,
            "success_count": 0,
            "error_count": 0,
            "status_429_count": 0,
            "local_cache_hit_count": 0,
            "upstream_prompt_cache_hit_count": 0,
            "upstream_prompt_cache_request_count": 0,
            "cache_read_input_tokens": 0,
            "cache_read_samples": 0,
            "hint_applied_count": 0,
            "session_count": 0,
            "sticky_session_count": 0,
            "active_affinity_count": 0,
            "cooling": False,
            "consecutive_failures": 0,
            "last_reason": "",
        }
    connection_pool = context["connection_pool_snapshot"]() or {}
    for route_url, info in (connection_pool.get("urls") or {}).items():
        entry = route_observability.setdefault(
            str(route_url),
            {
                "route_url": str(route_url),
                "pool_name": "",
                "request_count": 0,
                "success_count": 0,
                "error_count": 0,
                "status_429_count": 0,
                "local_cache_hit_count": 0,
                "upstream_prompt_cache_hit_count": 0,
                "upstream_prompt_cache_request_count": 0,
                "cache_read_input_tokens": 0,
                "cache_read_samples": 0,
                "hint_applied_count": 0,
                "session_count": 0,
                "sticky_session_count": 0,
                "active_affinity_count": 0,
                "cooling": False,
                "consecutive_failures": 0,
                "last_reason": "",
            },
        )
        entry["pool_name"] = str((info or {}).get("pool_name") or "")
    for item in recent_requests:
        route_url = str(item.get("upstream_url") or "").strip()
        if not route_url:
            continue
        entry = route_observability.setdefault(
            route_url,
            {
                "route_url": route_url,
                "pool_name": str(item.get("pool_name") or ""),
                "request_count": 0,
                "success_count": 0,
                "error_count": 0,
                "status_429_count": 0,
                "local_cache_hit_count": 0,
                "upstream_prompt_cache_hit_count": 0,
                "upstream_prompt_cache_request_count": 0,
                "cache_read_input_tokens": 0,
                "cache_read_samples": 0,
                "hint_applied_count": 0,
                "session_count": 0,
                "sticky_session_count": 0,
                "active_affinity_count": 0,
                "cooling": False,
                "consecutive_failures": 0,
                "last_reason": "",
            },
        )
        entry["request_count"] += 1
        status_code = int(item.get("status_code") or 0)
        if status_code == 429:
            entry["status_429_count"] += 1
        if item.get("error") or (status_code >= 400 and status_code != 429):
            entry["error_count"] += 1
        elif status_code > 0 and status_code < 400:
            entry["success_count"] += 1
        if bool(item.get("local_response_cache_hit")):
            entry["local_cache_hit_count"] += 1
        if bool(item.get("upstream_prompt_cache_eligible")):
            entry["upstream_prompt_cache_request_count"] += 1
        if bool(item.get("upstream_prompt_cache_hit")):
            entry["upstream_prompt_cache_hit_count"] += 1
        cache_read_tokens = int(item.get("cache_read_input_tokens") or 0)
        if cache_read_tokens > 0:
            entry["cache_read_input_tokens"] += cache_read_tokens
            entry["cache_read_samples"] += 1
        if bool(item.get("prompt_cache_hint_applied")):
            entry["hint_applied_count"] += 1
        if not entry["pool_name"]:
            entry["pool_name"] = str(item.get("pool_name") or "")
    for route_url, sessions in route_sessions.items():
        entry = route_observability.setdefault(
            route_url,
            {
                "route_url": route_url,
                "pool_name": "",
                "request_count": 0,
                "success_count": 0,
                "error_count": 0,
                "status_429_count": 0,
                "local_cache_hit_count": 0,
                "upstream_prompt_cache_hit_count": 0,
                "upstream_prompt_cache_request_count": 0,
                "cache_read_input_tokens": 0,
                "cache_read_samples": 0,
                "hint_applied_count": 0,
                "session_count": 0,
                "sticky_session_count": 0,
                "active_affinity_count": 0,
                "cooling": False,
                "consecutive_failures": 0,
                "last_reason": "",
            },
        )
        entry["session_count"] = len(sessions)
        entry["sticky_session_count"] = sum(
            1
            for affinity_key in sessions
            if len(session_route_map.get(affinity_key) or ()) == 1
        )
    active_route_affinity_counts = context.get("active_route_affinity_counts")
    active_route_affinity_counts = active_route_affinity_counts() if callable(active_route_affinity_counts) else {}
    for route_url, count in (active_route_affinity_counts or {}).items():
        if route_url in route_observability:
            route_observability[route_url]["active_affinity_count"] = int(count or 0)
    now_epoch = time.time()
    for route_url, health in route_health_snapshot.items():
        entry = route_observability.setdefault(
            str(route_url),
            {
                "route_url": str(route_url),
                "pool_name": "",
                "request_count": 0,
                "success_count": 0,
                "error_count": 0,
                "status_429_count": 0,
                "local_cache_hit_count": 0,
                "upstream_prompt_cache_hit_count": 0,
                "upstream_prompt_cache_request_count": 0,
                "cache_read_input_tokens": 0,
                "cache_read_samples": 0,
                "hint_applied_count": 0,
                "session_count": 0,
                "sticky_session_count": 0,
                "active_affinity_count": 0,
                "cooling": False,
                "consecutive_failures": 0,
                "last_reason": "",
            },
        )
        entry["cooling"] = float((health or {}).get("cooldown_until", 0.0) or 0.0) > now_epoch
        entry["consecutive_failures"] = int((health or {}).get("consecutive_failures", 0) or 0)
        entry["last_reason"] = str((health or {}).get("last_reason") or "")

    route_observability_rows = []
    for entry in route_observability.values():
        request_count = int(entry.get("request_count") or 0)
        cache_read_samples = int(entry.get("cache_read_samples") or 0)
        session_count = int(entry.get("session_count") or 0)
        sticky_session_count = int(entry.get("sticky_session_count") or 0)
        route_observability_rows.append(
            {
                "route_url": entry["route_url"],
                "pool_name": entry["pool_name"],
                "request_count": request_count,
                "success_count": int(entry.get("success_count") or 0),
                "error_count": int(entry.get("error_count") or 0),
                "status_429_count": int(entry.get("status_429_count") or 0),
                "local_cache_hit_count": int(entry.get("local_cache_hit_count") or 0),
                "local_cache_hit_rate": (
                    int(entry.get("local_cache_hit_count") or 0) / request_count
                    if request_count > 0 else 0.0
                ),
                "upstream_prompt_cache_hit_count": int(entry.get("upstream_prompt_cache_hit_count") or 0),
                "upstream_prompt_cache_request_count": int(entry.get("upstream_prompt_cache_request_count") or 0),
                "upstream_prompt_cache_hit_rate": (
                    int(entry.get("upstream_prompt_cache_hit_count") or 0) / int(entry.get("upstream_prompt_cache_request_count") or 0)
                    if int(entry.get("upstream_prompt_cache_request_count") or 0) > 0 else 0.0
                ),
                "avg_cache_read_input_tokens": (
                    float(entry.get("cache_read_input_tokens") or 0) / cache_read_samples
                    if cache_read_samples > 0 else 0.0
                ),
                "hint_applied_count": int(entry.get("hint_applied_count") or 0),
                "hint_applied_rate": (int(entry.get("hint_applied_count") or 0) / request_count) if request_count > 0 else 0.0,
                "session_count": session_count,
                "sticky_session_count": sticky_session_count,
                "sticky_session_rate": (sticky_session_count / session_count) if session_count > 0 else 0.0,
                "active_affinity_count": int(entry.get("active_affinity_count") or 0),
                "cooling": bool(entry.get("cooling")),
                "consecutive_failures": int(entry.get("consecutive_failures") or 0),
                "last_reason": str(entry.get("last_reason") or ""),
            }
        )
    route_observability_rows.sort(
        key=lambda item: (
            -int(item.get("request_count") or 0),
            -int(item.get("status_429_count") or 0),
            str(item.get("route_url") or ""),
        )
    )

    return {
        "ok": True,
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "upstream_url": context["upstream_url"],
        "upstream_urls": list(context["upstream_urls"]),
        "upstream_url_count": len(context["upstream_urls"]),
        "pools_count": len(context["proxy_pools"]),
        "pools_enabled_count": sum(1 for p in context["proxy_pools"] if p.get("enabled", True)),
        "log_path": str(context["log_path"]),
        "runtime": runtime_snapshot,
        "config": context["build_runtime_config_payload"](),
        "stats": request_snapshot["stats"],
        "active_requests": request_snapshot["active_requests"],
        "recent_requests": recent_requests,
        "route_health": route_health_snapshot,
        "connection_pool": context["connection_pool_snapshot"](),
        "route_observability": route_observability_rows,
        "cache_observability": {
            "local_response_cache_hits": local_response_cache_hits,
            "local_response_cache_misses": local_response_cache_misses,
            "local_response_cache_hit_rate": local_response_cache_hit_rate,
            "upstream_prompt_cache_requests": upstream_prompt_cache_requests,
            "upstream_prompt_cache_hits": upstream_prompt_cache_hits,
            "upstream_prompt_cache_hit_rate": (
                upstream_prompt_cache_hits / upstream_prompt_cache_requests
                if upstream_prompt_cache_requests > 0 else 0.0
            ),
            "prompt_hint_requests": prompt_hint_requests,
            "avg_cache_read_input_tokens": avg_cache_read_tokens,
            "sticky_session_count": sticky_sessions,
            "sticky_session_total": sticky_total,
            "sticky_session_rate": sticky_rate,
            "active_affinity_keys": active_affinity_keys,
        },
        "recent_logs": [line.rstrip("\n") for line in context["read_recent_log_lines"]()],
    }
