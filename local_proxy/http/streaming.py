from __future__ import annotations

import json
import queue
import time
from threading import Thread
import uuid

import requests


CLIENT_GONE_MARKERS = (
    "client_gone",
    "client gone",
    "client disconnected",
    "context canceled",
    "context cancelled",
    "request canceled",
    "request cancelled",
    "connection reset",
    "broken pipe",
    "write failed",
)


def is_text_response(content_type: str) -> bool:
    content_type = (content_type or "").lower()
    return (
        "application/json" in content_type
        or "text/" in content_type
        or "event-stream" in content_type
    )


def text_indicates_client_gone(text: str | None) -> bool:
    searchable = str(text or "").lower()
    return any(marker in searchable for marker in CLIENT_GONE_MARKERS)


def is_client_gone_exception(exc: BaseException | None) -> bool:
    return isinstance(exc, (GeneratorExit, BrokenPipeError, ConnectionResetError)) or text_indicates_client_gone(str(exc or ""))


def close_response_quietly(response: requests.Response | None) -> None:
    if response is None:
        return
    try:
        response.close()
    except Exception:
        pass


def format_sse_event(event_name: str, payload: dict) -> bytes:
    return (
        f"event: {event_name}\n"
        f"data: {json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}\n\n"
    ).encode("utf-8")


def format_openai_sse_payload(payload) -> bytes:
    if isinstance(payload, str):
        body = payload
    else:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return f"data: {body}\n\n".encode("utf-8")


def build_openai_stream_packets_from_chat_completion(response_body: dict) -> list[bytes]:
    if not isinstance(response_body, dict):
        response_body = {}

    chunk_id = response_body.get("id") or f"chatcmpl-{uuid.uuid4().hex[:16]}"
    created = int(response_body.get("created") or time.time())
    model = response_body.get("model")

    content_chunk = {
        "id": chunk_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [],
    }

    for fallback_index, choice in enumerate(response_body.get("choices") or []):
        message = choice.get("message") or {}
        delta = {
            "role": message.get("role") or "assistant",
        }
        content = message.get("content")
        if isinstance(content, str):
            delta["content"] = content
        elif isinstance(content, list):
            text = "".join(
                str(item.get("text", ""))
                for item in content
                if isinstance(item, dict) and item.get("type") == "text"
            )
            if text:
                delta["content"] = text
        reasoning = message.get("reasoning")
        if isinstance(reasoning, str) and reasoning:
            delta["reasoning_content"] = reasoning
        if message.get("tool_calls"):
            delta["tool_calls"] = message.get("tool_calls")

        content_chunk["choices"].append(
            {
                "index": int(choice.get("index", fallback_index) or 0),
                "delta": delta,
                "finish_reason": None,
            }
        )

    if not content_chunk["choices"]:
        content_chunk["choices"].append(
            {
                "index": 0,
                "delta": {"role": "assistant"},
                "finish_reason": None,
            }
        )

    finish_chunk = {
        "id": chunk_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [],
    }
    for fallback_index, choice in enumerate(response_body.get("choices") or []):
        finish_chunk["choices"].append(
            {
                "index": int(choice.get("index", fallback_index) or 0),
                "delta": (
                    {"reasoning_content": reasoning}
                    if isinstance((choice.get("message") or {}).get("reasoning"), str)
                    and (choice.get("message") or {}).get("reasoning")
                    else {}
                ),
                "finish_reason": choice.get("finish_reason", "stop"),
            }
        )

    if not finish_chunk["choices"]:
        finish_chunk["choices"].append(
            {
                "index": 0,
                "delta": {},
                "finish_reason": "stop",
            }
        )

    packets = [format_openai_sse_payload(content_chunk), format_openai_sse_payload(finish_chunk)]

    usage = response_body.get("usage")
    if isinstance(usage, dict) and usage:
        packets.append(
            format_openai_sse_payload(
                {
                    "id": chunk_id,
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": model,
                    "choices": [],
                    "usage": usage,
                }
            )
        )

    packets.append(format_openai_sse_payload("[DONE]"))
    return packets


def build_anthropic_stream_packets_from_message(message_body: dict) -> list[bytes]:
    if not isinstance(message_body, dict):
        message_body = {}

    usage = message_body.get("usage") or {}
    packets = [
        format_sse_event(
            "message_start",
            {
                "type": "message_start",
                "message": {
                    "id": message_body.get("id") or f"msg_{uuid.uuid4().hex[:24]}",
                    "type": "message",
                    "role": "assistant",
                    "model": message_body.get("model"),
                    "content": [],
                    "stop_reason": None,
                    "stop_sequence": None,
                    "usage": {
                        "input_tokens": int(usage.get("input_tokens", 0) or 0),
                        "output_tokens": 0,
                    },
                },
            },
        )
    ]

    for block_index, block in enumerate(message_body.get("content") or []):
        if not isinstance(block, dict):
            continue
        block_type = block.get("type")
        if block_type == "text":
            packets.append(
                format_sse_event(
                    "content_block_start",
                    {
                        "type": "content_block_start",
                        "index": block_index,
                        "content_block": {
                            "type": "text",
                            "text": "",
                        },
                    },
                )
            )
            if block.get("text"):
                packets.append(
                    format_sse_event(
                        "content_block_delta",
                        {
                            "type": "content_block_delta",
                            "index": block_index,
                            "delta": {
                                "type": "text_delta",
                                "text": str(block.get("text") or ""),
                            },
                        },
                    )
                )
            packets.append(
                format_sse_event(
                    "content_block_stop",
                    {
                        "type": "content_block_stop",
                        "index": block_index,
                    },
                )
            )
            continue

        if block_type == "tool_use":
            packets.append(
                format_sse_event(
                    "content_block_start",
                    {
                        "type": "content_block_start",
                        "index": block_index,
                        "content_block": {
                            "type": "tool_use",
                            "id": block.get("id") or f"toolu_{uuid.uuid4().hex[:24]}",
                            "name": block.get("name", ""),
                            "input": {},
                        },
                    },
                )
            )
            payload = json.dumps(block.get("input") or {}, ensure_ascii=False, separators=(",", ":"))
            if payload:
                packets.append(
                    format_sse_event(
                        "content_block_delta",
                        {
                            "type": "content_block_delta",
                            "index": block_index,
                            "delta": {
                                "type": "input_json_delta",
                                "partial_json": payload,
                            },
                        },
                    )
                )
            packets.append(
                format_sse_event(
                    "content_block_stop",
                    {
                        "type": "content_block_stop",
                        "index": block_index,
                    },
                )
            )

    packets.append(
        format_sse_event(
            "message_delta",
            {
                "type": "message_delta",
                "delta": {
                    "stop_reason": message_body.get("stop_reason"),
                    "stop_sequence": message_body.get("stop_sequence"),
                },
                "usage": {
                    "output_tokens": int(usage.get("output_tokens", 0) or 0),
                },
            },
        )
    )
    packets.append(format_sse_event("message_stop", {"type": "message_stop"}))
    return packets


def iter_response_lines(upstream_response: requests.Response):
    try:
        yield from upstream_response.iter_lines(decode_unicode=False)
        return
    except AttributeError:
        pass

    for raw_line in upstream_response.content.splitlines():
        yield raw_line


def iter_response_lines_with_heartbeat(upstream_response: requests.Response, heartbeat_seconds: int):
    if heartbeat_seconds <= 0:
        yield from iter_response_lines(upstream_response)
        return

    sentinel = object()
    line_queue = queue.Queue()

    def pump_lines() -> None:
        try:
            for raw_line in iter_response_lines(upstream_response):
                line_queue.put(raw_line)
        except BaseException as exc:  # pragma: no cover
            line_queue.put(exc)
        finally:
            line_queue.put(sentinel)

    Thread(target=pump_lines, name="upstream-sse-pump", daemon=True).start()
    while True:
        try:
            item = line_queue.get(timeout=heartbeat_seconds)
        except queue.Empty:
            yield None
            continue
        if item is sentinel:
            break
        if isinstance(item, BaseException):
            raise item
        yield item
