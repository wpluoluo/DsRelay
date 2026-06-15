from __future__ import annotations

REASONING_PAYLOAD_FIELDS = ("reasoning_effort", "reasoning", "thinking")


def route_is_deepseek_tool_choice_sensitive(upstream_url: str | None, payload: dict | None) -> bool:
    route_text = str(upstream_url or "").strip().lower()
    model_text = str((payload or {}).get("model") or "").strip().lower() if isinstance(payload, dict) else ""
    if any(marker in route_text for marker in ("opencode.ai", "deepseek.com", "deepseek")):
        return True
    return "deepseek" in model_text


def payload_uses_tool_choice(payload: dict | None) -> bool:
    if not isinstance(payload, dict):
        return False
    if "tool_choice" in payload:
        tool_choice = payload.get("tool_choice")
        if tool_choice is None:
            return False
        if isinstance(tool_choice, str):
            return bool(tool_choice.strip())
        return True
    return bool(payload.get("tools"))


def apply_deepseek_tool_choice_reasoning_compat(
    payload: dict | None,
    *,
    upstream_url: str = "",
) -> tuple[dict | None, int, dict]:
    metrics = {
        "reasoning_disabled_for_tool_choice": False,
        "reasoning_compat_provider": "",
        "reasoning_removed_fields": [],
        "tool_choice_downgraded": False,
    }
    if not isinstance(payload, dict):
        return payload, 0, metrics
    if not payload_uses_tool_choice(payload):
        return payload, 0, metrics
    if not route_is_deepseek_tool_choice_sensitive(upstream_url, payload):
        return payload, 0, metrics

    next_payload = dict(payload)
    removed_fields = []
    for field in REASONING_PAYLOAD_FIELDS:
        if field in next_payload:
            next_payload.pop(field, None)
            removed_fields.append(field)
    tool_choice = next_payload.get("tool_choice")
    if isinstance(tool_choice, str) and tool_choice.strip().lower() == "required":
        next_payload["tool_choice"] = "auto"
        metrics["tool_choice_downgraded"] = True
    metrics["reasoning_disabled_for_tool_choice"] = True
    metrics["reasoning_compat_provider"] = "deepseek"
    metrics["reasoning_removed_fields"] = removed_fields
    return next_payload, len(removed_fields) + (1 if metrics["tool_choice_downgraded"] else 0), metrics


def should_skip_reasoning_effort_for_tool_choice(
    payload: dict | None,
    *,
    upstream_url: str = "",
) -> bool:
    return payload_uses_tool_choice(payload) and route_is_deepseek_tool_choice_sensitive(upstream_url, payload)
