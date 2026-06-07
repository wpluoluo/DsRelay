from __future__ import annotations

from local_proxy.platform import PROTOCOL_PROFILES
from local_proxy.upstream.protocol_capabilities import get_protocol_parameter_keys

from .base import AdminServiceBase


class AdminProtocolsMixin(AdminServiceBase):
    def list_protocol_profiles(self) -> dict:
        items = []
        for key, profile in PROTOCOL_PROFILES.items():
            items.append(
                {
                    "key": profile.key,
                    "label": profile.label,
                    "supports_tools": profile.supports_tools,
                    "supports_stream": profile.supports_stream,
                    "supports_system_prompt": profile.supports_system_prompt,
                    "supports_images": profile.supports_images,
                    "parameter_keys": sorted(get_protocol_parameter_keys(key)),
                }
            )
        items.sort(key=lambda item: item["key"])
        return {"ok": True, "items": items, "total": len(items)}
