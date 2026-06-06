from __future__ import annotations


TEXT_UPSTREAM_PROTOCOLS = ("auto", "openai", "responses", "anthropic", "gemini")


PROTOCOL_PARAMETER_KEYS = {
    "openai": {
        "frequency_penalty",
        "max_completion_tokens",
        "max_tokens",
        "metadata",
        "modalities",
        "n",
        "parallel_tool_calls",
        "presence_penalty",
        "prompt_cache_key",
        "prompt_cache_retention",
        "reasoning_effort",
        "response_format",
        "seed",
        "service_tier",
        "stop",
        "stream",
        "stream_options",
        "temperature",
        "tool_choice",
        "tools",
        "top_p",
    },
    "responses": {
        "include",
        "instructions",
        "max_output_tokens",
        "metadata",
        "parallel_tool_calls",
        "prompt_cache_key",
        "prompt_cache_retention",
        "reasoning",
        "service_tier",
        "stream",
        "temperature",
        "text",
        "tool_choice",
        "tools",
        "top_p",
        "truncation",
    },
    "anthropic": {
        "cache_control",
        "container",
        "context_management",
        "max_tokens",
        "metadata",
        "service_tier",
        "stop_sequences",
        "stream",
        "system",
        "temperature",
        "thinking",
        "tool_choice",
        "tools",
        "top_k",
        "top_p",
    },
    "gemini": {
        "cachedContent",
        "contents",
        "generationConfig",
        "safetySettings",
        "systemInstruction",
        "toolConfig",
        "tools",
    },
}


def normalize_text_protocol(value: object) -> str:
    protocol = str(value or "").strip().lower()
    if protocol in TEXT_UPSTREAM_PROTOCOLS:
        return protocol
    return "auto"


def get_protocol_parameter_keys(protocol: object) -> set[str]:
    normalized = normalize_text_protocol(protocol)
    if normalized == "auto":
        return set().union(*PROTOCOL_PARAMETER_KEYS.values())
    return set(PROTOCOL_PARAMETER_KEYS.get(normalized, set()))
