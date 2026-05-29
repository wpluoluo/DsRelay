from __future__ import annotations

import json


HTML_SUCCESS_MARKERS = (
    "<!doctype html",
    "<html",
    "<head>",
    "<body>",
    "<title>",
)

STRUCTURED_ROUTE_MARKERS = (
    "chat/completions",
    "messages",
    "models",
    "responses",
    "embeddings",
    "images/generations",
    ":generatecontent",
    ":streamgeneratecontent",
)


def decode_body_text(body: bytes | None) -> str:
    if not body:
        return ""
    return body.decode("utf-8", errors="ignore")


def body_looks_like_html(text: str | None) -> bool:
    lowered = str(text or "").strip().lower()
    return any(marker in lowered for marker in HTML_SUCCESS_MARKERS)


def route_expects_structured_success(route_hint: str | None) -> bool:
    lowered = str(route_hint or "").strip("/").lower()
    return any(marker in lowered for marker in STRUCTURED_ROUTE_MARKERS)


def openai_choice_has_meaningful_output(choice: dict | None, *, include_reasoning: bool = False) -> bool:
    if not isinstance(choice, dict):
        return False

    message = choice.get("message") or {}
    content = message.get("content")
    if isinstance(content, str) and content.strip():
        return True
    if isinstance(content, list):
        for item in content:
            if not isinstance(item, dict):
                continue
            if item.get("text"):
                return True

    tool_calls = message.get("tool_calls") or []
    if isinstance(tool_calls, list) and tool_calls:
        return True
    if include_reasoning:
        reasoning = message.get("reasoning") or message.get("reasoning_content")
        if isinstance(reasoning, str) and reasoning.strip():
            return True

    delta = choice.get("delta") or {}
    if isinstance(delta.get("content"), str) and delta.get("content", "").strip():
        return True
    if include_reasoning:
        delta_reasoning = delta.get("reasoning") or delta.get("reasoning_content")
        if isinstance(delta_reasoning, str) and delta_reasoning.strip():
            return True
    delta_tool_calls = delta.get("tool_calls") or []
    return isinstance(delta_tool_calls, list) and bool(delta_tool_calls)


def openai_response_has_meaningful_output(response_body: dict | None, *, include_reasoning: bool = False) -> bool:
    if not isinstance(response_body, dict):
        return False

    if isinstance(response_body.get("error"), dict):
        return False

    choices = response_body.get("choices") or []
    if not isinstance(choices, list) or not choices:
        return False

    return any(openai_choice_has_meaningful_output(choice, include_reasoning=include_reasoning) for choice in choices)


def openai_stream_events_have_meaningful_output(
    response_events: list[dict] | None,
    *,
    include_reasoning: bool = False,
) -> bool:
    if not isinstance(response_events, list) or not response_events:
        return False
    for event in response_events:
        if not isinstance(event, dict):
            continue
        for choice in event.get("choices") or []:
            if openai_choice_has_meaningful_output(choice, include_reasoning=include_reasoning):
                return True
    return False


def inspect_success_payload(
    *,
    route_hint: str,
    content_type: str,
    body: bytes | None = None,
    json_body=None,
    response_body: dict | None = None,
    response_events: list[dict] | None = None,
    raw_error_lines: list[str] | None = None,
) -> dict | None:
    text = decode_body_text(body)
    preview = (text or json.dumps(response_body or json_body or {}, ensure_ascii=False)).replace("\n", "\\n")[:280]
    lowered_content_type = str(content_type or "").lower()
    normalized_route = str(route_hint or "").strip("/").lower()

    if route_expects_structured_success(normalized_route):
        if body is not None and not text.strip():
            return {
                "code": "empty_success_body",
                "message": "Upstream returned HTTP 200 with an empty success body.",
                "preview": preview,
            }
        if body_looks_like_html(text):
            return {
                "code": "html_success_body",
                "message": "Upstream returned an HTML gateway page instead of an API payload.",
                "preview": preview,
            }

    if normalized_route == "chat/completions":
        payload = response_body if isinstance(response_body, dict) else json_body
        if response_events is not None and not response_events and not (raw_error_lines or []):
            return {
                "code": "empty_sse_success",
                "message": "Upstream returned an empty streaming success payload.",
                "preview": preview,
            }
        if response_events is not None and not openai_stream_events_have_meaningful_output(response_events):
            return {
                "code": "empty_sse_success",
                "message": "Upstream returned a streaming success payload with no usable output.",
                "preview": preview,
            }
        if not isinstance(payload, dict):
            return {
                "code": "invalid_success_json",
                "message": "Upstream returned HTTP 200 but the chat completion body was not valid JSON.",
                "preview": preview,
            }
        if not openai_response_has_meaningful_output(payload):
            return {
                "code": "empty_chat_completion",
                "message": "Upstream returned HTTP 200 but the chat completion payload contained no usable output.",
                "preview": preview,
            }
        return None

    if "application/json" in lowered_content_type and body is not None and json_body is None:
        return {
            "code": "invalid_success_json",
            "message": "Upstream returned HTTP 200 with malformed JSON.",
            "preview": preview,
        }

    return None
