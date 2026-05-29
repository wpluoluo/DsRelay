from __future__ import annotations

import json
import time
from typing import Any, Callable

import requests

from local_proxy.upstream.models import dedupe_model_candidates, normalize_model_alias_key
from local_proxy.upstream.retry import race_model_candidate_requests


ROUTE_FAILOVER_STATUS_CODES = {408, 425, 429, 500, 502, 503, 504, 524}
DETERMINISTIC_ROUTE_FAILURE_STATUS_CODES = {401, 402, 403}
DETERMINISTIC_FAILURE_MARKERS = (
    "auth",
    "unauthorized",
    "invalid_api_key",
    "authentication",
    "permission_denied",
    "quota",
    "balance",
    "payment required",
    "billing",
    "account disabled",
    "account suspended",
    "service disabled",
    "service unavailable for account",
    "channel disabled",
    "channel unavailable",
    "欠费",
    "余额不足",
    "停机",
    "停服",
    "服务停用",
    "账号停用",
    "渠道停用",
)


def clamp_stream_timeout_to_retry_window(timeout_value, remaining_window_ms: int):
    if not (isinstance(timeout_value, tuple) and len(timeout_value) == 2):
        return timeout_value
    try:
        connect_timeout = int(timeout_value[0])
        read_timeout = int(timeout_value[1])
    except Exception:
        return timeout_value

    budget_ms = max(0, int(remaining_window_ms or 0))
    budget_seconds = max(1, (budget_ms + 999) // 1000)
    connect_timeout = max(1, min(connect_timeout, budget_seconds))
    read_timeout = max(connect_timeout, min(read_timeout, budget_seconds))
    return (connect_timeout, read_timeout)


def _is_deterministic_upstream_failure(status_code: int, reason: str, preview: str) -> bool:
    searchable = f"{reason or ''} {preview or ''}".lower()
    return status_code in DETERMINISTIC_ROUTE_FAILURE_STATUS_CODES or any(
        marker in searchable for marker in DETERMINISTIC_FAILURE_MARKERS
    )


def _set_authorization_header(request_kwargs: dict, api_key: str) -> None:
    headers = dict(request_kwargs.get("headers") or {})
    headers.pop("Authorization", None)
    headers.pop("authorization", None)
    key = str(api_key or "").strip()
    if key:
        headers["Authorization"] = key if key.lower().startswith("bearer ") else f"Bearer {key}"
    request_kwargs["headers"] = headers


def _base_request_url(route_url: str) -> str:
    marker = "#__route="
    text = str(route_url or "").strip()
    if marker in text:
        return text.split(marker, 1)[0]
    return text


def request_upstream_with_retries(
    request_kwargs: dict,
    *,
    subpath: str,
    request_id: str,
    upstream_urls: list[str] | None,
    model_candidates: list[str] | None,
    should_retry_request: Callable[[str, str], bool],
    max_retries: int,
    should_enforce_route_switch_window: Callable[[list[str], bool], bool],
    route_switch_window_seconds: int,
    build_attempt_url_cycle: Callable[[list[str], set[str]], list[str]],
    build_model_candidate_order_for_route: Callable[[str, list[str], dict, str], dict],
    should_race_model_candidates_for_route: Callable[..., bool],
    get_api_keys_for_url: Callable[[str], list[str]],
    choose_api_key_for_url: Callable[[str], dict],
    mark_api_key_success: Callable[[str, dict | None], None],
    mark_api_key_failure: Callable[[str, dict | None, str], None],
    mark_route_success: Callable[[str], None],
    mark_route_failure: Callable[[str, str], None],
    response_indicates_model_unavailable: Callable[[requests.Response], bool],
    classify_upstream_response: Callable[[requests.Response], tuple[str, str]],
    extract_error_preview_from_response: Callable[[requests.Response], str],
    apply_model_candidate_to_request_kwargs: Callable[[dict, str | None], dict],
    apply_learned_completion_limit_to_request_kwargs: Callable[..., int],
    extract_completion_token_limit_from_response: Callable[[requests.Response], int | None],
    extract_context_token_limit_from_response: Callable[[requests.Response], tuple[int | None, int | None]],
    clamp_payload_output_tokens: Callable[[dict | None, int | None], int],
    record_learned_model_capability: Callable[..., None],
    record_model_candidate_result: Callable[..., None],
    compute_retry_delay_ms: Callable[[int, requests.Response | None], int],
    remaining_retry_window_ms: Callable[[float], int],
    append_race_attempts: Callable[[list[dict], list[dict]], set[str]],
    model_candidate_differs_from_logical: Callable[[str | None, str | None], bool],
    logger,
    cache_stat_bump: Callable[[str], None],
    model_candidate_race_limit: int,
    model_candidate_race_timeout_seconds: int,
    enable_model_candidate_race: bool,
    request_sender: Any,
    initial_blocked_urls: set[str] | None = None,
) -> tuple[requests.Response | None, list[dict], Exception | None]:
    request_kwargs = dict(request_kwargs or {})
    request_kwargs.pop("meta", None)
    retry_allowed = should_retry_request(subpath, str(request_kwargs.get("method", "GET")))
    model_candidates = [
        str(item or "").strip()
        for item in (model_candidates or [])
        if str(item or "").strip()
    ]
    model_candidates = dedupe_model_candidates(model_candidates)
    model_variant_count = max(1, len(model_candidates) + 6)
    max_attempts = (1 + (max_retries if retry_allowed else 0)) * model_variant_count
    candidate_urls = list(dict.fromkeys(upstream_urls or [str(request_kwargs.get("url", "")).strip()]))
    candidate_urls = [url for url in candidate_urls if url]
    enforce_route_window = should_enforce_route_switch_window(candidate_urls, retry_allowed)
    attempts = []
    last_exception = None
    last_response = None
    blocked_urls = {
        str(url)
        for url in (initial_blocked_urls or set())
        if str(url) in candidate_urls
    }
    if len(blocked_urls) >= len(candidate_urls):
        blocked_urls = set()
    route_model_index = {}
    route_model_orders = {}
    raced_routes = set()
    route_key_failures: dict[str, set[str]] = {}
    route_cycle = build_attempt_url_cycle(candidate_urls, blocked_urls)
    last_logged_route_debug = None
    deadline_monotonic = (
        time.monotonic() + route_switch_window_seconds
        if enforce_route_window
        else time.monotonic()
    )
    immediate_followup_available = False
    immediate_followup_consumed = False

    for attempt_number in range(1, max_attempts + 1):
        if attempt_number > 1 and enforce_route_window and remaining_retry_window_ms(deadline_monotonic) <= 0:
            if immediate_followup_available and not immediate_followup_consumed:
                immediate_followup_available = False
                immediate_followup_consumed = True
            else:
                break

        if not route_cycle:
            route_cycle = build_attempt_url_cycle(candidate_urls, blocked_urls)
        if not route_cycle:
            break

        route_debug = None
        if hasattr(build_attempt_url_cycle, "__globals__"):
            route_debug = build_attempt_url_cycle.__globals__.get("route_selection_state", {}).get("__last_route_selection_debug__")
        if logger and isinstance(route_debug, dict):
            current_debug = json.dumps(route_debug, ensure_ascii=False, sort_keys=True)
            if current_debug != last_logged_route_debug:
                logger.info(
                    "request_id=%s 线路选路 session_affinity_type=%s affinity_applied=%s reason=%s randomize=%s selected=%s ordered=%s blocked=%s cooldown=%s",
                    request_id,
                    route_debug.get("session_affinity_type", ""),
                    str(bool(route_debug.get("session_affinity_applied"))).lower(),
                    route_debug.get("rotation_reason", ""),
                    str(bool(route_debug.get("randomize_endpoints"))).lower(),
                    route_debug.get("selected_url", ""),
                    json.dumps(route_debug.get("ordered_urls", []), ensure_ascii=False),
                    json.dumps(route_debug.get("blocked_urls", []), ensure_ascii=False),
                    json.dumps(route_debug.get("cooldown_urls", []), ensure_ascii=False),
                )
                last_logged_route_debug = current_debug

        attempt_url = route_cycle.pop(0)
        request_url = _base_request_url(attempt_url)
        order_info = route_model_orders.setdefault(
            attempt_url,
            build_model_candidate_order_for_route(
                attempt_url,
                model_candidates,
                request_kwargs,
                request_id,
            ),
        )
        ordered_model_candidates = list(order_info.get("candidates") or [])
        logical_model = model_candidates[0] if model_candidates else None
        if logical_model and not ordered_model_candidates:
            blocked_urls.add(attempt_url)
            attempts.append(
                {
                    "attempt": len(attempts) + 1,
                    "route_url": attempt_url,
                    "upstream_url": request_url,
                    "model": logical_model,
                    "model_alias_applied": False,
                    "pool_name": "",
                    "api_key_index": None,
                    "api_key_count": len(get_api_keys_for_url(attempt_url)),
                    "api_key_id": "",
                    "kind": "skipped",
                    "reason": "no_supported_model_candidates",
                    "action": "switch_route",
                    "preview": "route has no explicit supported candidate for the requested model",
                }
            )
            logger.warning(
                "request_id=%s 切换线路 次数=%s 线路=%s 原因=当前线路未显式支持请求模型 剩余线路=%s 模型=%s",
                request_id,
                len(attempts),
                attempt_url,
                max(0, len(candidate_urls) - len(blocked_urls)),
                logical_model,
            )
            if len(blocked_urls) >= len(candidate_urls):
                break
            route_cycle = build_attempt_url_cycle(candidate_urls, blocked_urls)
            continue

        if (
            attempt_url not in raced_routes
            and should_race_model_candidates_for_route(
                subpath=subpath,
                method=str(request_kwargs.get("method", "GET")),
                order_info=order_info,
                ordered_model_candidates=ordered_model_candidates,
            )
        ):
            raced_routes.add(attempt_url)
            race_candidates = ordered_model_candidates[:model_candidate_race_limit]
            if enable_model_candidate_race and len(race_candidates) > 1:
                cache_stat_bump("model_candidate_race_attempts")
                race_key_choice = choose_api_key_for_url(attempt_url, exclude=route_key_failures.get(attempt_url, set()))
                race_key = str(race_key_choice.get("key") or "")
                if race_key:
                    race_request_kwargs = dict(request_kwargs)
                    _set_authorization_header(race_request_kwargs, race_key)
                else:
                    race_request_kwargs = request_kwargs
                race_outcome = race_model_candidate_requests(
                    request_kwargs=race_request_kwargs,
                    route_url=request_url,
                    candidates=race_candidates,
                    logical_model=logical_model,
                    request_id=request_id,
                    timeout_seconds=model_candidate_race_timeout_seconds,
                    apply_candidate=apply_model_candidate_to_request_kwargs,
                    classify_response=classify_upstream_response,
                    extract_preview=extract_error_preview_from_response,
                    alias_differs=model_candidate_differs_from_logical,
                    logger=logger,
                    request_sender=request_sender,
                )
                if race_outcome.get("timed_out"):
                    cache_stat_bump("model_candidate_race_timeouts")
                failed_model_keys = append_race_attempts(
                    attempts,
                    race_outcome.get("attempts") or [],
                    logical_model=logical_model,
                    route_url=attempt_url,
                )
                winner_response = race_outcome.get("winner_response")
                if winner_response is not None:
                    mark_api_key_success(attempt_url, race_key_choice)
                    cache_stat_bump("model_candidate_race_hits")
                    last_response = winner_response
                    return winner_response, attempts, None

                next_model_index = 0
                while (
                    next_model_index < len(ordered_model_candidates)
                    and normalize_model_alias_key(ordered_model_candidates[next_model_index]) in failed_model_keys
                ):
                    next_model_index += 1
                if next_model_index:
                    route_model_index[attempt_url] = max(route_model_index.get(attempt_url, 0), next_model_index)

        model_index = route_model_index.get(attempt_url, 0)
        model_candidate = ordered_model_candidates[model_index] if model_index < len(ordered_model_candidates) else None
        current_request_kwargs = apply_model_candidate_to_request_kwargs(request_kwargs, model_candidate)
        current_request_kwargs["url"] = request_url
        if enforce_route_window:
            current_request_kwargs["timeout"] = clamp_stream_timeout_to_retry_window(
                current_request_kwargs.get("timeout"),
                remaining_retry_window_ms(deadline_monotonic),
            )
        key_choice = choose_api_key_for_url(attempt_url, exclude=route_key_failures.get(attempt_url, set()))
        attempt_key = str(key_choice.get("key") or "")
        available_keys_for_route = get_api_keys_for_url(attempt_url)
        if available_keys_for_route and not attempt_key:
            blocked_urls.add(attempt_url)
            attempts.append(
                {
                    "attempt": len(attempts) + 1,
                    "route_url": attempt_url,
                    "upstream_url": request_url,
                    "model": model_candidate,
                    "model_alias_applied": model_candidate_differs_from_logical(logical_model, model_candidate),
                    "pool_name": "",
                    "api_key_index": None,
                    "api_key_count": len(available_keys_for_route),
                    "api_key_id": "",
                    "kind": "skipped",
                    "reason": "all_keys_cooling",
                    "action": "switch_route",
                    "preview": "all available keys are cooling down",
                }
            )
            logger.warning(
                "request_id=%s 切换线路 次数=%s 线路=%s 原因=当前线路全部Key冷却中 剩余线路=%s",
                request_id,
                len(attempts),
                attempt_url,
                max(0, len(candidate_urls) - len(blocked_urls)),
            )
            if len(blocked_urls) >= len(candidate_urls):
                break
            route_cycle = build_attempt_url_cycle(candidate_urls, blocked_urls)
            continue
        if attempt_key:
            _set_authorization_header(current_request_kwargs, attempt_key)
        learned_request_repairs = apply_learned_completion_limit_to_request_kwargs(
            current_request_kwargs,
            logical_model=logical_model,
            route_url=attempt_url,
            model_candidate=model_candidate,
        )
        current_attempt_number = len(attempts) + 1
        try:
            response = request_sender(**current_request_kwargs)
        except requests.RequestException as exc:
            last_exception = exc
            attempts.append(
                {
                    "attempt": current_attempt_number,
                    "route_url": attempt_url,
                    "upstream_url": request_url,
                    "model": model_candidate,
                    "model_alias_applied": model_candidate_differs_from_logical(logical_model, model_candidate),
                    "pool_name": key_choice.get("pool_name"),
                    "api_key_index": key_choice.get("key_index"),
                    "api_key_count": key_choice.get("key_count"),
                    "api_key_id": key_choice.get("key_id"),
                    "kind": "exception",
                    "error": str(exc),
                }
            )
            mark_route_failure(attempt_url, "request_exception")
            record_model_candidate_result(
                logical_model=logical_model,
                route_url=attempt_url,
                model_candidate=model_candidate,
                success=False,
            )
            if len(candidate_urls) - len(blocked_urls) > 1:
                blocked_urls.add(attempt_url)
                if not immediate_followup_consumed:
                    immediate_followup_available = True
                logger.warning(
                    "request_id=%s 切换线路 次数=%s 线路=%s 原因=请求异常 剩余线路=%s 错误=%s",
                    request_id,
                    current_attempt_number,
                    attempt_url,
                    max(0, len(candidate_urls) - len(blocked_urls)),
                    str(exc),
                )
                route_cycle = build_attempt_url_cycle(candidate_urls, blocked_urls)
                continue
            if attempt_number >= max_attempts or not retry_allowed:
                break

            delay_ms = compute_retry_delay_ms(current_attempt_number)
            if enforce_route_window:
                delay_ms = min(delay_ms, remaining_retry_window_ms(deadline_monotonic))
            logger.warning(
                "request_id=%s 上游重试 次数=%s 线路=%s 原因=请求异常 延迟毫秒=%s 错误=%s",
                request_id,
                current_attempt_number,
                attempt_url,
                delay_ms,
                str(exc),
            )
            if delay_ms <= 0:
                break
            time.sleep(delay_ms / 1000)
            continue
        except Exception as exc:
            last_exception = exc
            attempts.append(
                {
                    "attempt": current_attempt_number,
                    "route_url": attempt_url,
                    "upstream_url": request_url,
                    "model": model_candidate,
                    "model_alias_applied": model_candidate_differs_from_logical(logical_model, model_candidate),
                    "pool_name": key_choice.get("pool_name"),
                    "api_key_index": key_choice.get("key_index"),
                    "api_key_count": key_choice.get("key_count"),
                    "api_key_id": key_choice.get("key_id"),
                    "kind": "exception",
                    "error": str(exc),
                }
            )
            mark_route_failure(attempt_url, "request_exception")
            record_model_candidate_result(
                logical_model=logical_model,
                route_url=attempt_url,
                model_candidate=model_candidate,
                success=False,
            )
            if len(candidate_urls) - len(blocked_urls) > 1:
                blocked_urls.add(attempt_url)
                if not immediate_followup_consumed:
                    immediate_followup_available = True
                logger.warning(
                    "request_id=%s 切换线路 次数=%s 线路=%s 原因=请求异常 剩余线路=%s 错误=%s",
                    request_id,
                    current_attempt_number,
                    attempt_url,
                    max(0, len(candidate_urls) - len(blocked_urls)),
                    str(exc),
                )
                route_cycle = build_attempt_url_cycle(candidate_urls, blocked_urls)
                continue
            if attempt_number >= max_attempts or not retry_allowed:
                break

            delay_ms = compute_retry_delay_ms(current_attempt_number)
            if enforce_route_window:
                delay_ms = min(delay_ms, remaining_retry_window_ms(deadline_monotonic))
            logger.warning(
                "request_id=%s 上游重试 次数=%s 线路=%s 原因=请求异常 延迟毫秒=%s 错误=%s",
                request_id,
                current_attempt_number,
                attempt_url,
                delay_ms,
                str(exc),
            )
            if delay_ms <= 0:
                break
            time.sleep(delay_ms / 1000)
            continue

        defer_stream_success_evaluation = bool(current_request_kwargs.get("stream")) and response.status_code < 400
        if defer_stream_success_evaluation:
            retry_action, reason = ("return", f"stream_success_deferred_{response.status_code}")
            preview = ""
        else:
            retry_action, reason = classify_upstream_response(response)
            preview = extract_error_preview_from_response(response) if response.status_code >= 400 else ""
        attempts.append(
            {
                "attempt": current_attempt_number,
                "route_url": attempt_url,
                "upstream_url": request_url,
                "model": model_candidate,
                "model_alias_applied": model_candidate_differs_from_logical(logical_model, model_candidate),
                "learned_request_repairs": learned_request_repairs,
                "pool_name": key_choice.get("pool_name"),
                "api_key_index": key_choice.get("key_index"),
                "api_key_count": key_choice.get("key_count"),
                "api_key_id": key_choice.get("key_id"),
                "kind": "response",
                "status_code": response.status_code,
                "reason": reason,
                "action": retry_action,
                "preview": preview,
            }
        )
        last_response = response

        client_gone_response = reason.startswith("client_gone")
        model_unavailable_response = (
            False if defer_stream_success_evaluation else response_indicates_model_unavailable(response)
        )
        learned_output_limit = extract_completion_token_limit_from_response(response) if response.status_code >= 400 else None
        learned_input_tokens = None
        learned_context_limit = None
        if not defer_stream_success_evaluation and response.status_code >= 400:
            learned_input_tokens, learned_context_limit = extract_context_token_limit_from_response(response)
        token_limit_adjustable = bool(
            (learned_output_limit and learned_output_limit > 0)
            or (learned_context_limit and learned_context_limit > 0)
        )
        if response.status_code < 400:
            mark_api_key_success(attempt_url, key_choice)
            mark_route_success(attempt_url)
            record_model_candidate_result(
                logical_model=logical_model,
                route_url=attempt_url,
                model_candidate=model_candidate,
                success=True,
            )
        deterministic_failure = _is_deterministic_upstream_failure(
            response.status_code,
            reason,
            preview,
        )
        route_should_cooldown = deterministic_failure or response.status_code == 429 or (
            retry_action == "switch_route" and not client_gone_response
        )
        if route_should_cooldown:
            mark_route_failure(attempt_url, reason)

        key_retry_reason = deterministic_failure
        if response.status_code >= 400 and deterministic_failure:
            mark_api_key_failure(
                attempt_url,
                key_choice,
                reason,
                force_cooldown=True,
            )

        if token_limit_adjustable and retry_allowed and len(attempts) < max_attempts:
            retry_probe_kwargs = apply_model_candidate_to_request_kwargs(request_kwargs, model_candidate)
            retry_probe_kwargs["url"] = request_url
            adjusted = clamp_payload_output_tokens(retry_probe_kwargs.get("json"), learned_output_limit) if isinstance(retry_probe_kwargs.get("json"), dict) else 0
            if adjusted or (learned_context_limit and learned_context_limit > 0):
                record_learned_model_capability(
                    logical_model=logical_model,
                    route_url=attempt_url,
                    model_candidate=model_candidate,
                    max_output_tokens=learned_output_limit,
                    context_tokens=learned_context_limit,
                )
            if adjusted:
                attempts[-1]["action"] = "adjust_tokens"
                attempts[-1]["learned_max_output_tokens"] = learned_output_limit
                logger.warning(
                    "request_id=%s 输出上限回退 次数=%s 线路=%s 模型=%s 学习到的最大输出=%s 状态=%s 预览=%s",
                    request_id,
                    current_attempt_number,
                    attempt_url,
                    model_candidate or "",
                    learned_output_limit,
                    response.status_code,
                    preview,
                )
                response.close()
                if not immediate_followup_consumed:
                    immediate_followup_available = True
                route_cycle.insert(0, attempt_url)
                continue
            if learned_context_limit and learned_context_limit > 0:
                attempts[-1]["learned_context_tokens"] = learned_context_limit
                attempts[-1]["learned_input_tokens"] = learned_input_tokens

        current_failed_keys = route_key_failures.setdefault(attempt_url, set())
        if (
            key_choice.get("from_pool")
            and response.status_code >= 400
            and key_retry_reason
            and len(current_failed_keys) < len(available_keys_for_route)
        ):
            current_failed_keys.add(str(key_choice.get("key") or ""))
            next_key_choice = choose_api_key_for_url(attempt_url, exclude=current_failed_keys)
            if next_key_choice and str(next_key_choice.get("key") or "") not in current_failed_keys:
                cache_stat_bump("pool_key_switches")
                attempts[-1]["action"] = "switch_api_key"
                attempts[-1]["next_api_key_index"] = next_key_choice.get("key_index")
                logger.warning(
                    "request_id=%s 切换Key 次数=%s 线路=%s 连接池=%s %s->%s 状态=%s 原因=%s",
                    request_id,
                    current_attempt_number,
                    attempt_url,
                    key_choice.get("pool_name") or "global",
                    key_choice.get("key_id") or "global",
                    next_key_choice.get("key_id") or "global",
                    response.status_code,
                    reason,
                )
                response.close()
                if not immediate_followup_consumed:
                    immediate_followup_available = True
                route_cycle.insert(0, attempt_url)
                continue

        has_alternate_route = len(candidate_urls) - len(blocked_urls) > 1
        route_failover_response = (
            retry_allowed
            and has_alternate_route
            and (
                retry_action == "switch_route"
                or response.status_code in ROUTE_FAILOVER_STATUS_CODES
            )
        )
        if route_failover_response:
            blocked_urls.add(attempt_url)
            attempts[-1]["action"] = "switch_route"
            logger.warning(
                "request_id=%s 切换线路 次数=%s 线路=%s 状态=%s 原因=%s 剩余线路=%s",
                request_id,
                current_attempt_number,
                attempt_url,
                response.status_code,
                reason,
                max(0, len(candidate_urls) - len(blocked_urls)),
            )
            response.close()
            if not immediate_followup_consumed:
                immediate_followup_available = True
            route_cycle = build_attempt_url_cycle(candidate_urls, blocked_urls)
            continue

        if (
            retry_action == "retry"
            and len(candidate_urls) - len(blocked_urls) > 1
            and len(current_failed_keys) >= len(available_keys_for_route)
        ):
            blocked_urls.add(attempt_url)
            attempts[-1]["action"] = "switch_route"
            logger.warning(
                "request_id=%s 切换线路 次数=%s 线路=%s 状态=%s 原因=%s 剩余线路=%s",
                request_id,
                current_attempt_number,
                attempt_url,
                response.status_code,
                reason,
                max(0, len(candidate_urls) - len(blocked_urls)),
            )
            response.close()
            if not immediate_followup_consumed:
                immediate_followup_available = True
            route_cycle = build_attempt_url_cycle(candidate_urls, blocked_urls)
            continue

        if retry_action == "return" or not retry_allowed or len(attempts) >= max_attempts:
            return response, attempts, None

        if model_unavailable_response and model_index + 1 < len(ordered_model_candidates):
            record_model_candidate_result(
                logical_model=logical_model,
                route_url=attempt_url,
                model_candidate=model_candidate,
                success=False,
            )
            next_model = ordered_model_candidates[model_index + 1]
            route_model_index[attempt_url] = model_index + 1
            logger.warning(
                "request_id=%s 切换模型别名 次数=%s 线路=%s %s->%s 状态=%s",
                request_id,
                current_attempt_number,
                attempt_url,
                model_candidate or "",
                next_model,
                response.status_code,
            )
            response.close()
            if not immediate_followup_consumed:
                immediate_followup_available = True
            route_cycle.insert(0, attempt_url)
            continue

        if retry_action == "switch_route":
            blocked_urls.add(attempt_url)
            logger.warning(
                "request_id=%s 切换线路 次数=%s 线路=%s 状态=%s 原因=%s 剩余线路=%s",
                request_id,
                current_attempt_number,
                attempt_url,
                response.status_code,
                reason,
                max(0, len(candidate_urls) - len(blocked_urls)),
            )
            if len(blocked_urls) >= len(candidate_urls):
                return response, attempts, None
            response.close()
            if not immediate_followup_consumed:
                immediate_followup_available = True
            route_cycle = build_attempt_url_cycle(candidate_urls, blocked_urls)
            continue

        delay_ms = compute_retry_delay_ms(current_attempt_number, response)
        if enforce_route_window:
            delay_ms = min(delay_ms, remaining_retry_window_ms(deadline_monotonic))
        logger.warning(
            "request_id=%s 上游重试 次数=%s 线路=%s 状态=%s 原因=%s 延迟毫秒=%s",
            request_id,
            current_attempt_number,
            attempt_url,
            response.status_code,
            reason,
            delay_ms,
        )
        response.close()
        if delay_ms <= 0:
            return response, attempts, None
        time.sleep(delay_ms / 1000)

    if last_response is not None:
        return last_response, attempts, None

    return None, attempts, last_exception
