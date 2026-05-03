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
    request_snapshot = context["request_recorder_snapshot"]()
    route_health_snapshot = {
        route_url: dict(entry)
        for route_url, entry in (context.get("route_health") or {}).items()
    }

    return {
        "ok": True,
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "upstream_url": context["upstream_url"],
        "upstream_urls": list(context["upstream_urls"]),
        "upstream_url_count": len(context["upstream_urls"]),
        "pools_count": len(context["proxy_pools"]),
        "pools_enabled_count": sum(1 for p in context["proxy_pools"] if p.get("enabled", True)),
        "log_path": str(context["log_path"]),
        "runtime": context["build_runtime_snapshot"](),
        "config": context["build_runtime_config_payload"](),
        "stats": request_snapshot["stats"],
        "active_requests": request_snapshot["active_requests"],
        "recent_requests": request_snapshot["recent_requests"],
        "route_health": route_health_snapshot,
        "connection_pool": context["connection_pool_snapshot"](),
        "recent_logs": [line.rstrip("\n") for line in context["read_recent_log_lines"]()],
    }
