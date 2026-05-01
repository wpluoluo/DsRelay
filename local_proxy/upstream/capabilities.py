from __future__ import annotations

import json
import re
from typing import Any

from local_proxy.upstream.models import (
    build_related_model_name_candidates,
    normalize_model_alias_key,
    normalize_model_semantic_key,
)


DEFAULT_MODEL_CAPABILITIES_TEXT = """
# model=context_tokens,max_output_tokens
# Verified from public provider docs; route-level upstream errors can still learn stricter caps.
deepseek-v4-flash=1048576,393216
deepseek-v4-pro=1048576,393216
deepseek-ai/deepseek-v4-flash=1048576,393216
deepseek-ai/deepseek-v4-pro=1048576,393216
gpt-5.5=1000000,128000
gpt-5.4=1000000,128000
gpt-5.4-mini=400000,128000
gpt-5.4-codex=400000,128000
gpt-4.1=1047576,32768
gpt-4.1-mini=1047576,32768
gpt-4o=128000,16384
gpt-4o-mini=128000,16384
o3=200000,100000
o4-mini=200000,100000
gemini-2.5-pro=1048576,65536
gemini-2.5-flash=1048576,65536
gemini-2.0-flash=1048576,8192
qwen-max=32768,8192
qwen-plus=131072,16384
qwen-turbo=1000000,16384
qwen3-235b-a22b=131072,16384
qwen3-32b=131072,16384
glm-4.5=128000,16384
glm-4.5-air=128000,16384
glm-4-air=128000,8192
kimi-k2=128000,16384
kimi-latest=128000,16384
moonshot-v1-128k=128000,16384
moonshot-v1-32k=32768,8192
claude-opus-4-7=1000000,128000
claude-opus-4-6=1000000,128000
claude-sonnet-4-6=1000000,64000
claude-haiku-4-5=200000,64000
""".strip()


OUTPUT_TOKEN_LIMIT_PATTERNS = (
    re.compile(
        r"supports\s+at\s+most\s+([0-9][0-9,._\s]*)\s+(?:completion|output)\s+tokens?",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:max(?:imum)?|最多|上限)[^\n\r]{0,40}?(?:completion|output|输出)?[^\n\r]{0,20}?([0-9][0-9,._\s]*)\s*(?:tokens?|token|令牌)",
        re.IGNORECASE,
    ),
)


def normalize_model_capabilities_text(raw_capabilities: str | None) -> str:
    raw_text = str(raw_capabilities or "").strip()
    if not raw_text:
        return DEFAULT_MODEL_CAPABILITIES_TEXT
    return f"{DEFAULT_MODEL_CAPABILITIES_TEXT}\n{raw_text}".strip()


def _parse_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value) if int(value) >= 0 else None
    text = str(value).strip()
    if not text:
        return None
    text = re.sub(r"[\s,_]", "", text)
    try:
        parsed = int(float(text))
    except Exception:
        return None
    return parsed if parsed >= 0 else None


def _capability_from_value(value: Any) -> dict | None:
    if isinstance(value, dict):
        context_tokens = _parse_int(
            value.get("context_tokens")
            or value.get("input_tokens")
            or value.get("context")
            or value.get("input")
        )
        max_output_tokens = _parse_int(
            value.get("max_output_tokens")
            or value.get("output_tokens")
            or value.get("max_completion_tokens")
            or value.get("max_tokens")
            or value.get("output")
        )
    elif isinstance(value, list):
        context_tokens = _parse_int(value[0]) if len(value) > 0 else None
        max_output_tokens = _parse_int(value[1]) if len(value) > 1 else None
    else:
        context_tokens = None
        max_output_tokens = _parse_int(value)

    if not context_tokens and not max_output_tokens:
        return None
    return {
        "context_tokens": context_tokens,
        "max_output_tokens": max_output_tokens,
    }


def _parse_capability_line_value(raw_value: str) -> dict | None:
    text = str(raw_value or "").strip()
    if not text:
        return None

    named = {}
    for key, value in re.findall(r"([a-zA-Z_][a-zA-Z0-9_-]*)\s*[:=]\s*([0-9][0-9,._\s]*)", text):
        key = key.lower()
        if key in {"context", "context_tokens", "input", "input_tokens"}:
            named["context_tokens"] = _parse_int(value)
        elif key in {"output", "max_output", "max_output_tokens", "max_tokens", "max_completion_tokens"}:
            named["max_output_tokens"] = _parse_int(value)
    if named:
        return _capability_from_value(named)

    parts = [
        part.strip()
        for part in re.split(r"[,|/]+", text)
        if part.strip()
    ]
    numbers = parts if len(parts) >= 2 else re.findall(r"[0-9][0-9._]*", text)
    if len(numbers) >= 2:
        return _capability_from_value([numbers[0], numbers[1]])
    if len(numbers) == 1:
        return _capability_from_value(numbers[0])
    return None


def parse_model_capabilities(raw_capabilities: str | dict | None) -> dict[str, dict]:
    if isinstance(raw_capabilities, dict):
        raw_items = raw_capabilities.items()
    else:
        raw_text = str(raw_capabilities or "").strip()
        if not raw_text:
            return {}
        try:
            parsed = json.loads(raw_text)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict):
            raw_items = parsed.items()
        else:
            raw_items = []
            pairs = []
            for raw_line in re.split(r"[\r\n;]+", raw_text):
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                for separator in ("=>", "->", "="):
                    if separator in line:
                        model, value = line.split(separator, 1)
                        pairs.append((model, _parse_capability_line_value(value)))
                        break
            raw_items = pairs

    capabilities = {}
    for model, value in raw_items:
        model_name = str(model or "").strip()
        capability = value if isinstance(value, dict) and "max_output_tokens" in value else _capability_from_value(value)
        if not model_name or not capability:
            continue
        capabilities[normalize_model_alias_key(model_name)] = {
            "model": model_name,
            "context_tokens": capability.get("context_tokens"),
            "max_output_tokens": capability.get("max_output_tokens"),
        }
    return capabilities


def find_model_capability(model_name: str | None, capabilities: dict[str, dict]) -> dict | None:
    if not model_name or not isinstance(capabilities, dict):
        return None

    candidate_names = build_related_model_name_candidates(model_name)
    candidate_names.append(str(model_name or "").strip())
    for candidate in candidate_names:
        entry = capabilities.get(normalize_model_alias_key(candidate))
        if isinstance(entry, dict):
            return entry

    semantic_key = normalize_model_semantic_key(model_name)
    if not semantic_key:
        return None
    for key, entry in capabilities.items():
        if normalize_model_semantic_key(key) == semantic_key and isinstance(entry, dict):
            return entry
        entry_model = entry.get("model") if isinstance(entry, dict) else None
        if normalize_model_semantic_key(entry_model) == semantic_key:
            return entry
    return None


def extract_completion_token_limit_from_text(text: str | None) -> int | None:
    searchable = str(text or "")
    if not searchable:
        return None
    for pattern in OUTPUT_TOKEN_LIMIT_PATTERNS:
        match = pattern.search(searchable)
        if match:
            return _parse_int(match.group(1))
    return None


def parse_token_limit_value(value) -> tuple[int | None, bool]:
    parsed = _parse_int(value)
    if parsed is None:
        return None, False
    return parsed, not isinstance(value, int) or isinstance(value, bool)


def clamp_payload_output_tokens(payload: dict, max_output_tokens: int | None) -> int:
    limit = _parse_int(max_output_tokens)
    if not isinstance(payload, dict) or not limit or limit <= 0:
        return 0

    repairs = 0
    for key in ("max_completion_tokens", "max_tokens"):
        if key not in payload:
            continue
        parsed, coerced = parse_token_limit_value(payload.get(key))
        if parsed is None:
            continue
        normalized = min(parsed, limit)
        if normalized != payload.get(key):
            payload[key] = normalized
            repairs += 1
        elif coerced:
            payload[key] = normalized
            repairs += 1
    return repairs


CONTEXT_TOKEN_LIMIT_PATTERNS = (
    re.compile(
        r"input\s*\(\s*([0-9][0-9,._\s]*)\s+tokens?\s*\)\s+is\s+longer\s+than\s+the\s+model'?s\s+context\s+length\s*\(\s*([0-9][0-9,._\s]*)\s+tokens?\s*\)",
        re.IGNORECASE,
    ),
    re.compile(
        r"context\s+length[^\n\r]{0,40}?([0-9][0-9,._\s]*)\s+tokens?",
        re.IGNORECASE,
    ),
)


def estimate_payload_tokens(payload: dict | None) -> int:
    if not isinstance(payload, dict):
        return 0

    try:
        serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    except Exception:
        serialized = str(payload)

    if not serialized:
        return 0

    char_count = len(serialized)
    ascii_count = sum(1 for ch in serialized if ord(ch) < 128)
    non_ascii_count = max(0, char_count - ascii_count)
    estimated = (ascii_count / 4.0) + (non_ascii_count / 1.6)
    return max(1, int(estimated))


def find_context_window_overflow(payload: dict | None, capability: dict | None) -> dict | None:
    if not isinstance(payload, dict) or not isinstance(capability, dict):
        return None

    context_limit = _parse_int(capability.get("context_tokens"))
    if not context_limit or context_limit <= 0:
        return None

    requested_output = None
    for key in ("max_completion_tokens", "max_tokens"):
        parsed = _parse_int(payload.get(key))
        if parsed is not None:
            requested_output = max(requested_output or 0, parsed)

    estimated_total = estimate_payload_tokens(payload)
    reserved_output = max(0, requested_output or 0)
    if estimated_total <= context_limit:
        return None

    allowed_input = max(0, context_limit - reserved_output)
    return {
        "estimated_total_tokens": estimated_total,
        "context_tokens": context_limit,
        "requested_output_tokens": reserved_output,
        "allowed_input_tokens": allowed_input,
    }


def extract_context_token_limit_from_text(text: str | None) -> tuple[int | None, int | None]:
    searchable = str(text or "")
    if not searchable:
        return None, None

    for index, pattern in enumerate(CONTEXT_TOKEN_LIMIT_PATTERNS):
        match = pattern.search(searchable)
        if not match:
            continue
        if index == 0:
            return _parse_int(match.group(1)), _parse_int(match.group(2))
        return None, _parse_int(match.group(1))
    return None, None
