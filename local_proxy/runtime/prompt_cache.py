from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy

from local_proxy.compat.tools import normalize_openai_tool_definition, openai_tool_sort_key


PROMPT_CACHE_SENSITIVE_HOST_MARKERS = (
    "api.openai.com",
    "openai.azure.com",
    "openrouter.ai",
    "deepseek.com",
    "nvidia.com",
    "opencode.ai",
    "anthropic.com",
    "generativelanguage.googleapis.com",
    "googleapis.com",
)


def route_is_prompt_cache_sensitive(route_url: str | None) -> bool:
    route_text = str(route_url or "").strip().lower()
    return bool(route_text and any(marker in route_text for marker in PROMPT_CACHE_SENSITIVE_HOST_MARKERS))


def should_force_prompt_cache_affinity(candidate_urls: list[str] | None) -> bool:
    urls = [str(item or "").strip() for item in (candidate_urls or []) if str(item or "").strip()]
    return bool(urls) and any(route_is_prompt_cache_sensitive(url) for url in urls)


def ensure_stream_usage_options_for_prompt_cache(payload: dict | None, *, upstream_url: str | None) -> tuple[dict | None, int, dict]:
    if not isinstance(payload, dict):
        return payload, 0, {"stream_usage_included": False}
    if not payload.get("stream") or not route_is_prompt_cache_sensitive(upstream_url):
        return payload, 0, {"stream_usage_included": False}

    next_payload = dict(payload)
    stream_options = next_payload.get("stream_options")
    if not isinstance(stream_options, dict):
        stream_options = {}
    else:
        stream_options = dict(stream_options)

    if stream_options.get("include_usage") is True:
        return next_payload, 0, {"stream_usage_included": True, "stream_usage_include_source": "existing"}

    stream_options["include_usage"] = True
    next_payload["stream_options"] = stream_options
    return next_payload, 1, {"stream_usage_included": True, "stream_usage_include_source": "proxy"}


def stable_prompt_cache_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def stable_prompt_cache_hash(value, *, length: int = 16) -> str:
    digest = hashlib.sha256(stable_prompt_cache_json(value).encode("utf-8")).hexdigest()
    return digest[: max(8, min(64, int(length or 16)))]


def _normalize_message_content_for_prefix(content):
    if isinstance(content, str):
        return re.sub(r"\s+", " ", content).strip()
    return deepcopy(content)


def build_prompt_prefix_observability(payload: dict | None, *, prefix_messages: int = 4) -> dict:
    if not isinstance(payload, dict):
        return {
            "prompt_prefix_hash": "",
            "prompt_messages_hash": "",
            "prompt_tools_hash": "",
            "prompt_prefix_message_count": 0,
            "prompt_tool_count": 0,
        }

    messages = payload.get("messages") if isinstance(payload.get("messages"), list) else []
    prefix = []
    for message in messages[: max(1, int(prefix_messages or 4))]:
        if not isinstance(message, dict):
            prefix.append(message)
            continue
        normalized = {}
        for key in sorted(message.keys()):
            if key in {"id", "created", "timestamp"}:
                continue
            value = message.get(key)
            if key == "content":
                value = _normalize_message_content_for_prefix(value)
            normalized[key] = value
        prefix.append(normalized)

    tools = []
    raw_tools = payload.get("tools")
    if isinstance(raw_tools, list):
        for tool in raw_tools:
            normalized_tool, _ = normalize_openai_tool_definition(tool)
            tools.append(normalized_tool)
        tools = sorted(tools, key=openai_tool_sort_key)

    messages_hash = stable_prompt_cache_hash(
        {
            "model": str(payload.get("model") or ""),
            "messages": prefix,
        }
    )
    tools_hash = stable_prompt_cache_hash(tools)
    prefix_hash = stable_prompt_cache_hash(
        {
            "messages": messages_hash,
            "tools": tools_hash,
        }
    )
    return {
        "prompt_prefix_hash": prefix_hash,
        "prompt_messages_hash": messages_hash,
        "prompt_tools_hash": tools_hash,
        "prompt_prefix_message_count": len(prefix),
        "prompt_tool_count": len(tools),
    }
