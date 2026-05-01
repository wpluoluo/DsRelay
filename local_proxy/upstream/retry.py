from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError, as_completed
from threading import Event
from typing import Callable

import requests


def _race_timeout(base_timeout, race_timeout_seconds: int):
    if isinstance(base_timeout, (int, float)):
        return max(1, min(float(base_timeout), float(race_timeout_seconds)))
    return max(1, race_timeout_seconds)


def race_model_candidate_requests(
    *,
    request_kwargs: dict,
    route_url: str,
    candidates: list[str],
    logical_model: str | None,
    request_id: str,
    timeout_seconds: int,
    apply_candidate: Callable[[dict, str | None], dict],
    classify_response: Callable[[requests.Response], tuple[str, str]],
    extract_preview: Callable[[requests.Response], str],
    alias_differs: Callable[[str | None, str | None], bool],
    logger,
    request_sender: Callable[..., requests.Response] | None = None,
) -> dict:
    """Race several model-name variants and return the first accepted response.

    This only waits for response headers. The returned winner remains open for
    the caller; failed or late responses are closed here to reduce wasted stream
    work upstream.
    """

    candidates = [str(item or "").strip() for item in candidates if str(item or "").strip()]
    if not candidates:
        return {"winner_response": None, "attempts": [], "timed_out": False}

    stop_event = Event()
    started_at = time.perf_counter()

    sender = request_sender or requests.request

    def run_candidate(model_candidate: str):
        if stop_event.is_set():
            return {"model": model_candidate, "skipped": True}
        current_kwargs = apply_candidate(request_kwargs, model_candidate)
        current_kwargs["url"] = route_url
        current_kwargs["timeout"] = _race_timeout(current_kwargs.get("timeout"), timeout_seconds)
        response = sender(**current_kwargs)
        if stop_event.is_set():
            response.close()
        return {"model": model_candidate, "response": response}

    executor = ThreadPoolExecutor(max_workers=len(candidates), thread_name_prefix="model-race")
    future_to_model = {
        executor.submit(run_candidate, model_candidate): model_candidate
        for model_candidate in candidates
    }
    attempts = []
    winner_response = None
    timed_out = False

    try:
        for future in as_completed(future_to_model, timeout=timeout_seconds):
            model_candidate = future_to_model[future]
            try:
                result = future.result()
                response = result.get("response")
            except Exception as exc:
                attempts.append(
                    {
                        "upstream_url": route_url,
                        "model": model_candidate,
                        "model_alias_applied": alias_differs(logical_model, model_candidate),
                        "kind": "race_exception",
                        "error": str(exc),
                    }
                )
                continue

            if response is None:
                attempts.append(
                    {
                        "upstream_url": route_url,
                        "model": model_candidate,
                        "model_alias_applied": alias_differs(logical_model, model_candidate),
                        "kind": "race_skipped",
                    }
                )
                continue

            retry_action, reason = classify_response(response)
            preview = extract_preview(response) if response.status_code >= 400 else ""
            attempts.append(
                {
                    "upstream_url": route_url,
                    "model": model_candidate,
                    "model_alias_applied": alias_differs(logical_model, model_candidate),
                    "kind": "race_response",
                    "status_code": response.status_code,
                    "reason": reason,
                    "action": retry_action,
                    "preview": preview,
                    "race_ms": int((time.perf_counter() - started_at) * 1000),
                }
            )

            if response.status_code < 400:
                stop_event.set()
                winner_response = response
                break

            response.close()
    except TimeoutError:
        timed_out = True
        stop_event.set()
        pending_models = [
            model_candidate
            for future, model_candidate in future_to_model.items()
            if not future.done()
        ]
        for model_candidate in pending_models:
            attempts.append(
                {
                    "upstream_url": route_url,
                    "model": model_candidate,
                    "model_alias_applied": alias_differs(logical_model, model_candidate),
                    "kind": "race_timeout",
                    "error": f"candidate race timeout after {timeout_seconds}s",
                }
            )
    finally:
        for future, model_candidate in future_to_model.items():
            if future.done():
                try:
                    result = future.result()
                    response = result.get("response") if isinstance(result, dict) else None
                    if response is not None and response is not winner_response:
                        response.close()
                except Exception:
                    pass
            else:
                future.cancel()
        executor.shutdown(wait=False, cancel_futures=True)

    if logger:
        logger.info(
            "request_id=%s model_candidate_race route=%s candidates=%s winner=%s timed_out=%s attempts=%s",
            request_id,
            route_url,
            json.dumps(candidates, ensure_ascii=False),
            next((attempt.get("model") for attempt in attempts if attempt.get("status_code", 999) < 400), ""),
            str(timed_out).lower(),
            len(attempts),
        )

    return {
        "winner_response": winner_response,
        "attempts": attempts,
        "timed_out": timed_out,
    }
