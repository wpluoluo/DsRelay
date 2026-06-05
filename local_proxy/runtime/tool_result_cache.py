from __future__ import annotations

from copy import deepcopy

from local_proxy.runtime.request_cache import (
    build_cached_tool_result_messages,
    build_tool_result_cache_key,
    extract_tool_result_cache_updates,
    response_tool_call_entries,
    response_tool_calls_are_read_only,
)


def observe_tool_result_cache_from_request(
    *,
    storage,
    request_payload: dict | None,
    protocol: str,
    tool_schemas: dict | None = None,
    ttl_seconds: int,
    bump_cache_stat,
    logger,
) -> dict:
    meta = {
        "tool_result_cache_writes": 0,
        "tool_result_cache_invalidations": 0,
    }
    if storage is None or not isinstance(request_payload, dict):
        return meta
    updates = extract_tool_result_cache_updates(
        request_payload=request_payload,
        protocol=protocol,
        tool_schemas=tool_schemas or {},
        ttl_seconds=ttl_seconds,
    )
    try:
        if updates.get("invalidate") and hasattr(storage, "clear_tool_result_cache"):
            storage.clear_tool_result_cache()
            meta["tool_result_cache_invalidations"] = 1
            bump_cache_stat("tool_result_cache_invalidations")
            logger.info(
                "工具结果缓存失效 mutating_tools=%s",
                ",".join(str(item) for item in (updates.get("mutating_tools") or [])[:8]),
            )
        writes = updates.get("writes") if isinstance(updates.get("writes"), list) else []
        if writes and hasattr(storage, "save_tool_result_cache"):
            saved = int(storage.save_tool_result_cache(writes) or 0)
            if saved > 0:
                meta["tool_result_cache_writes"] = saved
                bump_cache_stat("tool_result_cache_writes", saved)
                logger.info("工具结果缓存写入 数量=%s 协议=%s", saved, protocol)
    except Exception as exc:  # pragma: no cover
        logger.warning("tool_result_cache_observe_failed protocol=%s error=%s", protocol, str(exc))
    return meta


def load_cached_tool_results_for_response(
    *,
    storage,
    response_body: dict | None,
    protocol: str,
    tool_schemas: dict | None = None,
    logger,
) -> dict:
    if storage is None or not isinstance(response_body, dict) or not hasattr(storage, "load_tool_result_cache_many"):
        return {}
    entries = response_tool_call_entries(response_body, tool_schemas=tool_schemas or {})
    cache_keys = [
        build_tool_result_cache_key(
            protocol=protocol,
            tool_name=str(entry.get("tool_name") or ""),
            arguments=entry.get("arguments", {}),
        )
        for entry in entries
        if str(entry.get("tool_name") or "")
    ]
    if not cache_keys:
        return {}
    try:
        return storage.load_tool_result_cache_many(cache_keys)
    except Exception as exc:  # pragma: no cover
        logger.warning("tool_result_cache_load_failed protocol=%s error=%s", protocol, str(exc))
        return {}


def continue_with_cached_tool_results_once(
    *,
    storage,
    route_hint: str,
    request_id: str,
    upstream_url: str,
    request_payload: dict | None,
    execution: dict | None,
    response_body: dict | None,
    protocol: str | None,
    request_context: dict | None = None,
    execute_upstream_request,
    carry_same_request_execution_history,
    bump_cache_stat,
    logger,
) -> dict | None:
    normalized_protocol = str(protocol or "openai_chat_completions")
    if not isinstance(request_payload, dict) or not isinstance(response_body, dict):
        return None
    replay_depth = int((execution or {}).get("tool_result_cache_replay_depth") or 0)
    if replay_depth > 0:
        return None
    if not response_tool_calls_are_read_only(response_body):
        return None

    tool_schemas = (execution or {}).get("tool_schemas") if isinstance((execution or {}).get("tool_schemas"), dict) else {}
    cached_results = load_cached_tool_results_for_response(
        storage=storage,
        response_body=response_body,
        protocol=normalized_protocol,
        tool_schemas=tool_schemas,
        logger=logger,
    )
    tool_messages = build_cached_tool_result_messages(
        response_body=response_body,
        cached_results=cached_results,
        protocol=normalized_protocol,
        tool_schemas=tool_schemas,
    )
    entries = response_tool_call_entries(response_body, tool_schemas=tool_schemas)
    if not entries:
        return None
    if not tool_messages or len(tool_messages) != len(entries):
        bump_cache_stat("tool_result_cache_misses")
        if isinstance(execution, dict):
            execution["tool_result_cache_status"] = "miss"
            execution["tool_result_cache_note"] = "只读工具结果未命中"
        return None

    choices = response_body.get("choices") if isinstance(response_body.get("choices"), list) else []
    first_choice = choices[0] if choices and isinstance(choices[0], dict) else {}
    assistant_message = deepcopy(first_choice.get("message") if isinstance(first_choice.get("message"), dict) else {})
    if not assistant_message.get("tool_calls"):
        return None
    assistant_message["role"] = "assistant"
    continued_payload = deepcopy(request_payload)
    messages = continued_payload.get("messages")
    if not isinstance(messages, list):
        return None
    continued_payload["messages"] = list(messages) + [assistant_message] + tool_messages
    continued_payload["stream"] = False

    bump_cache_stat("tool_result_cache_hits", len(tool_messages))
    logger.info(
        "request_id=%s 工具结果缓存命中 数量=%s 协议=%s 上游=%s",
        request_id,
        len(tool_messages),
        normalized_protocol,
        upstream_url,
    )
    next_execution = execute_upstream_request(
        route_hint,
        continued_payload,
        request_id,
        cache_protocol=normalized_protocol,
        request_context=request_context or (execution.get("request_context") if isinstance(execution, dict) else None),
        bypass_inflight_coalescing=True,
    )
    if isinstance(next_execution, dict):
        next_execution["tool_result_cache_replay_depth"] = replay_depth + 1
        next_execution["tool_result_cache_status"] = "hit"
        next_execution["tool_result_cache_hits"] = len(tool_messages)
        next_execution["tool_result_cache_note"] = f"复用只读工具结果 {len(tool_messages)} 条"
        if isinstance(execution, dict):
            next_execution = carry_same_request_execution_history(execution, next_execution)
    return next_execution if isinstance(next_execution, dict) else None
