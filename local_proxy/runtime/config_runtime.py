from __future__ import annotations

import json

from local_proxy.runtime.helpers import ensure_proxy_prompt_rules, parse_bool, parse_int
from local_proxy.runtime.policies import normalize_pool_route_policies
from local_proxy.runtime.pools import apply_legacy_pool_text_defaults, normalize_proxy_pools
from local_proxy.http.proxy_auth import normalize_proxy_api_key_records
from local_proxy.upstream.capabilities import (
    normalize_model_capabilities_text,
    parse_model_capabilities,
)


def normalize_runtime_config_payload(
    config_payload: dict | None,
    *,
    current: dict,
) -> dict:
    config_payload = dict(config_payload or {})

    next_proxy_api_key_records = current.get("PROXY_API_KEY_RECORDS", [])
    if "proxy_api_key_records" in config_payload:
        next_proxy_api_key_records = normalize_proxy_api_key_records(config_payload.get("proxy_api_key_records"))

    next_model_capabilities_text = normalize_model_capabilities_text(
        config_payload.get("model_capabilities_text", current["MODEL_CAPABILITIES_TEXT"])
    )
    next_model_capabilities = parse_model_capabilities(next_model_capabilities_text)

    next_request_timeout = parse_int(
        config_payload.get("request_timeout", current["REQUEST_TIMEOUT"]),
        current["REQUEST_TIMEOUT"],
        minimum=30,
        maximum=3600,
    )
    next_stream_first_event_timeout_seconds = parse_int(
        config_payload.get(
            "stream_first_event_timeout_seconds",
            max(next_request_timeout, current["STREAM_FIRST_EVENT_TIMEOUT_SECONDS"]),
        ),
        max(next_request_timeout, current["STREAM_FIRST_EVENT_TIMEOUT_SECONDS"]),
        minimum=1,
        maximum=3600,
    )
    next_force_stream = parse_bool(
        config_payload.get("force_upstream_chat_stream", current["FORCE_UPSTREAM_CHAT_STREAM"]),
        current["FORCE_UPSTREAM_CHAT_STREAM"],
    )
    next_request_normalization = parse_bool(
        config_payload.get("enable_request_normalization", current["ENABLE_REQUEST_NORMALIZATION"]),
        current["ENABLE_REQUEST_NORMALIZATION"],
    )
    next_max_completion_tokens = parse_int(
        config_payload.get("max_completion_tokens", current["MAX_COMPLETION_TOKENS"]),
        current["MAX_COMPLETION_TOKENS"],
        minimum=0,
        maximum=10000000,
    )
    next_inject_zh_prompt = parse_bool(
        config_payload.get("inject_zh_system_prompt", current["INJECT_ZH_SYSTEM_PROMPT"]),
        current["INJECT_ZH_SYSTEM_PROMPT"],
    )
    next_proxy_prompt = ensure_proxy_prompt_rules(
        str(config_payload.get("proxy_system_prompt_zh", current["PROXY_SYSTEM_PROMPT_ZH"]) or current["DEFAULT_PROXY_SYSTEM_PROMPT_ZH"]).strip()
        or current["DEFAULT_PROXY_SYSTEM_PROMPT_ZH"],
        current["DEFAULT_PROXY_SYSTEM_PROMPT_ZH"],
        current["MARKDOWN_OUTPUT_PROMPT_RULE"],
    )
    next_max_retries = parse_int(
        config_payload.get("max_retries", current["UPSTREAM_MAX_RETRIES"]),
        current["UPSTREAM_MAX_RETRIES"],
        minimum=0,
        maximum=30,
    )
    next_retry_backoff_ms = parse_int(
        config_payload.get("retry_backoff_ms", current["UPSTREAM_RETRY_BACKOFF_MS"]),
        current["UPSTREAM_RETRY_BACKOFF_MS"],
        minimum=0,
        maximum=60000,
    )
    next_retry_max_backoff_ms = parse_int(
        config_payload.get("retry_max_backoff_ms", current["UPSTREAM_RETRY_MAX_BACKOFF_MS"]),
        current["UPSTREAM_RETRY_MAX_BACKOFF_MS"],
        minimum=next_retry_backoff_ms,
        maximum=120000,
    )
    next_route_switch_window_seconds = parse_int(
        config_payload.get("route_switch_window_seconds", current["UPSTREAM_ROUTE_SWITCH_WINDOW_SECONDS"]),
        current["UPSTREAM_ROUTE_SWITCH_WINDOW_SECONDS"],
        minimum=1,
        maximum=600,
    )
    next_randomize_endpoints = parse_bool(
        config_payload.get("randomize_endpoints", current["UPSTREAM_RANDOMIZE_ENDPOINTS"]),
        current["UPSTREAM_RANDOMIZE_ENDPOINTS"],
    )
    next_image_upstream_protocol = str(
        config_payload.get("image_upstream_protocol", current["IMAGE_UPSTREAM_PROTOCOL"])
        or current["IMAGE_UPSTREAM_PROTOCOL"]
    ).strip().lower()
    if next_image_upstream_protocol not in {"auto", "openai", "google", "dashscope"}:
        next_image_upstream_protocol = current["IMAGE_UPSTREAM_PROTOCOL"]
    next_image_task_poll_timeout_seconds = parse_int(
        config_payload.get("image_task_poll_timeout_seconds", current["IMAGE_TASK_POLL_TIMEOUT_SECONDS"]),
        current["IMAGE_TASK_POLL_TIMEOUT_SECONDS"],
        minimum=0,
        maximum=600,
    )
    next_image_task_poll_interval_seconds = parse_int(
        config_payload.get("image_task_poll_interval_seconds", current["IMAGE_TASK_POLL_INTERVAL_SECONDS"]),
        current["IMAGE_TASK_POLL_INTERVAL_SECONDS"],
        minimum=1,
        maximum=30,
    )
    next_enable_model_probe = parse_bool(
        config_payload.get("enable_model_probe", current["ENABLE_MODEL_PROBE"]),
        current["ENABLE_MODEL_PROBE"],
    )
    next_model_probe_timeout_seconds = parse_int(
        config_payload.get("model_probe_timeout_seconds", current["MODEL_PROBE_TIMEOUT_SECONDS"]),
        current["MODEL_PROBE_TIMEOUT_SECONDS"],
        minimum=1,
        maximum=30,
    )
    next_model_probe_ttl_seconds = parse_int(
        config_payload.get("model_probe_ttl_seconds", current["MODEL_PROBE_TTL_SECONDS"]),
        current["MODEL_PROBE_TTL_SECONDS"],
        minimum=10,
        maximum=3600,
    )
    next_model_route_cache_ttl_seconds = parse_int(
        config_payload.get("model_route_cache_ttl_seconds", current["MODEL_ROUTE_CACHE_TTL_SECONDS"]),
        current["MODEL_ROUTE_CACHE_TTL_SECONDS"],
        minimum=60,
        maximum=604800,
    )
    next_enable_interruption_resume = parse_bool(
        config_payload.get("enable_interruption_resume", current["ENABLE_INTERRUPTION_RESUME"]),
        current["ENABLE_INTERRUPTION_RESUME"],
    )
    next_interruption_resume_ttl_seconds = parse_int(
        config_payload.get("interruption_resume_ttl_seconds", current["INTERRUPTION_RESUME_TTL_SECONDS"]),
        current["INTERRUPTION_RESUME_TTL_SECONDS"],
        minimum=60,
        maximum=604800,
    )
    next_interruption_resume_max_chars = parse_int(
        config_payload.get("interruption_resume_max_chars", current["INTERRUPTION_RESUME_MAX_CHARS"]),
        current["INTERRUPTION_RESUME_MAX_CHARS"],
        minimum=500,
        maximum=200000,
    )
    next_interruption_resume_min_chars = parse_int(
        config_payload.get("interruption_resume_min_chars", current["INTERRUPTION_RESUME_MIN_CHARS"]),
        current["INTERRUPTION_RESUME_MIN_CHARS"],
        minimum=1,
        maximum=10000,
    )
    next_enable_model_candidate_race = parse_bool(
        config_payload.get("enable_model_candidate_race", current["ENABLE_MODEL_CANDIDATE_RACE"]),
        current["ENABLE_MODEL_CANDIDATE_RACE"],
    )
    next_model_candidate_race_limit = parse_int(
        config_payload.get("model_candidate_race_limit", current["MODEL_CANDIDATE_RACE_LIMIT"]),
        current["MODEL_CANDIDATE_RACE_LIMIT"],
        minimum=1,
        maximum=6,
    )
    next_model_candidate_race_timeout_seconds = parse_int(
        config_payload.get("model_candidate_race_timeout_seconds", current["MODEL_CANDIDATE_RACE_TIMEOUT_SECONDS"]),
        current["MODEL_CANDIDATE_RACE_TIMEOUT_SECONDS"],
        minimum=1,
        maximum=60,
    )

    next_pools = current["PROXY_POOLS"]
    incoming_pools = config_payload.get("pools")
    if isinstance(incoming_pools, list):
        incoming_pools = apply_legacy_pool_text_defaults(
            incoming_pools,
            legacy_model_aliases_text=config_payload.get("model_aliases_text"),
            legacy_supported_models_text=config_payload.get("supported_models_text"),
        )
        next_pools = normalize_pool_route_policies(normalize_proxy_pools(incoming_pools))

    return {
        "proxy_api_key_records": next_proxy_api_key_records,
        "proxy_pools": next_pools,
        "model_capabilities_text": next_model_capabilities_text,
        "model_capabilities": next_model_capabilities,
        "request_timeout": next_request_timeout,
        "stream_first_event_timeout_seconds": max(
            next_request_timeout,
            next_stream_first_event_timeout_seconds,
        ),
        "force_upstream_chat_stream": next_force_stream,
        "enable_request_normalization": next_request_normalization,
        "max_completion_tokens": next_max_completion_tokens,
        "inject_zh_system_prompt": next_inject_zh_prompt,
        "proxy_system_prompt_zh": next_proxy_prompt,
        "max_retries": next_max_retries,
        "retry_backoff_ms": next_retry_backoff_ms,
        "retry_max_backoff_ms": max(next_retry_backoff_ms, next_retry_max_backoff_ms),
        "route_switch_window_seconds": next_route_switch_window_seconds,
        "randomize_endpoints": next_randomize_endpoints,
        "image_upstream_protocol": next_image_upstream_protocol,
        "image_task_poll_timeout_seconds": next_image_task_poll_timeout_seconds,
        "image_task_poll_interval_seconds": next_image_task_poll_interval_seconds,
        "enable_model_probe": next_enable_model_probe,
        "model_probe_timeout_seconds": next_model_probe_timeout_seconds,
        "model_probe_ttl_seconds": next_model_probe_ttl_seconds,
        "model_route_cache_ttl_seconds": next_model_route_cache_ttl_seconds,
        "enable_interruption_resume": next_enable_interruption_resume,
        "interruption_resume_ttl_seconds": next_interruption_resume_ttl_seconds,
        "interruption_resume_max_chars": next_interruption_resume_max_chars,
        "interruption_resume_min_chars": next_interruption_resume_min_chars,
        "enable_model_candidate_race": next_enable_model_candidate_race,
        "model_candidate_race_limit": next_model_candidate_race_limit,
        "model_candidate_race_timeout_seconds": next_model_candidate_race_timeout_seconds,
    }


def log_runtime_config_update(*, logger, upstream_url_pool: list[str], model_capabilities: dict, state: dict, persisted: bool) -> None:
    logger.info(
        "运行配置已更新 上游线路=%s 模型能力数=%s 超时秒=%s 重试次数=%s 随机轮询=%s 流式透传=%s 请求归一化=%s 默认输出上限=%s 中文提示=%s 图片协议=%s 已持久化=%s",
        json.dumps(upstream_url_pool, ensure_ascii=False),
        len(model_capabilities),
        state["REQUEST_TIMEOUT"],
        state["UPSTREAM_MAX_RETRIES"],
        state["UPSTREAM_RANDOMIZE_ENDPOINTS"],
        state["FORCE_UPSTREAM_CHAT_STREAM"],
        state["ENABLE_REQUEST_NORMALIZATION"],
        state["MAX_COMPLETION_TOKENS"],
        state["INJECT_ZH_SYSTEM_PROMPT"],
        state["IMAGE_UPSTREAM_PROTOCOL"],
        persisted,
    )


def apply_runtime_globals(target_globals: dict, normalized_config: dict) -> None:
    target_globals["UPSTREAM_API_KEY"] = ""
    target_globals["PROXY_API_KEY_RECORDS"] = normalized_config["proxy_api_key_records"]
    target_globals["MODEL_CAPABILITIES_TEXT"] = normalized_config["model_capabilities_text"]
    target_globals["MODEL_CAPABILITIES"] = normalized_config["model_capabilities"]
    target_globals["REQUEST_TIMEOUT"] = normalized_config["request_timeout"]
    target_globals["STREAM_FIRST_EVENT_TIMEOUT_SECONDS"] = normalized_config["stream_first_event_timeout_seconds"]
    target_globals["FORCE_UPSTREAM_CHAT_STREAM"] = normalized_config["force_upstream_chat_stream"]
    target_globals["ENABLE_REQUEST_NORMALIZATION"] = normalized_config["enable_request_normalization"]
    target_globals["MAX_COMPLETION_TOKENS"] = normalized_config["max_completion_tokens"]
    target_globals["INJECT_ZH_SYSTEM_PROMPT"] = normalized_config["inject_zh_system_prompt"]
    target_globals["PROXY_SYSTEM_PROMPT_ZH"] = normalized_config["proxy_system_prompt_zh"]
    target_globals["UPSTREAM_MAX_RETRIES"] = normalized_config["max_retries"]
    target_globals["UPSTREAM_RETRY_BACKOFF_MS"] = normalized_config["retry_backoff_ms"]
    target_globals["UPSTREAM_RETRY_MAX_BACKOFF_MS"] = normalized_config["retry_max_backoff_ms"]
    target_globals["UPSTREAM_ROUTE_SWITCH_WINDOW_SECONDS"] = normalized_config["route_switch_window_seconds"]
    target_globals["UPSTREAM_RANDOMIZE_ENDPOINTS"] = normalized_config["randomize_endpoints"]
    target_globals["IMAGE_UPSTREAM_PROTOCOL"] = normalized_config["image_upstream_protocol"]
    target_globals["IMAGE_TASK_POLL_TIMEOUT_SECONDS"] = normalized_config["image_task_poll_timeout_seconds"]
    target_globals["IMAGE_TASK_POLL_INTERVAL_SECONDS"] = normalized_config["image_task_poll_interval_seconds"]
    target_globals["ENABLE_MODEL_PROBE"] = normalized_config["enable_model_probe"]
    target_globals["MODEL_PROBE_TIMEOUT_SECONDS"] = normalized_config["model_probe_timeout_seconds"]
    target_globals["MODEL_PROBE_TTL_SECONDS"] = normalized_config["model_probe_ttl_seconds"]
    target_globals["MODEL_ROUTE_CACHE_TTL_SECONDS"] = normalized_config["model_route_cache_ttl_seconds"]
    target_globals["ENABLE_INTERRUPTION_RESUME"] = normalized_config["enable_interruption_resume"]
    target_globals["INTERRUPTION_RESUME_TTL_SECONDS"] = normalized_config["interruption_resume_ttl_seconds"]
    target_globals["INTERRUPTION_RESUME_MAX_CHARS"] = normalized_config["interruption_resume_max_chars"]
    target_globals["INTERRUPTION_RESUME_MIN_CHARS"] = normalized_config["interruption_resume_min_chars"]
    target_globals["ENABLE_MODEL_CANDIDATE_RACE"] = normalized_config["enable_model_candidate_race"]
    target_globals["MODEL_CANDIDATE_RACE_LIMIT"] = normalized_config["model_candidate_race_limit"]
    target_globals["MODEL_CANDIDATE_RACE_TIMEOUT_SECONDS"] = normalized_config["model_candidate_race_timeout_seconds"]


def apply_pool_runtime_state(
    *,
    normalized_pools: list[dict],
    rebuild_pool_state,
    connection_pool_state,
    save_pool_runtime_state_to_storage,
    target_globals: dict,
) -> None:
    target_globals["PROXY_POOLS"][:] = normalized_pools
    if normalized_pools:
        rebuild_pool_state()
        return
    connection_pool_state.rebuild([])
    target_globals["UPSTREAM_URL_POOL"] = []
    target_globals["UPSTREAM_URL"] = ""
    target_globals["URL_POOL_KEY_MAP"] = {}
    save_pool_runtime_state_to_storage()
