from __future__ import annotations

from .models import AdminProtocolProfile


PROTOCOL_PROFILES: dict[str, AdminProtocolProfile] = {
    "openai": AdminProtocolProfile(
        key="openai",
        label="OpenAI Chat Completions",
        supports_tools=True,
        supports_stream=True,
        supports_system_prompt=True,
        supports_images=True,
    ),
    "responses": AdminProtocolProfile(
        key="responses",
        label="OpenAI Responses",
        supports_tools=True,
        supports_stream=True,
        supports_system_prompt=True,
        supports_images=False,
    ),
    "anthropic": AdminProtocolProfile(
        key="anthropic",
        label="Anthropic Messages",
        supports_tools=True,
        supports_stream=True,
        supports_system_prompt=True,
        supports_images=False,
    ),
    "gemini": AdminProtocolProfile(
        key="gemini",
        label="Gemini Generate Content",
        supports_tools=True,
        supports_stream=True,
        supports_system_prompt=False,
        supports_images=True,
    ),
}
