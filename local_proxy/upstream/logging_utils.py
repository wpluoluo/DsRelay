from __future__ import annotations


def _stringify_attempt_url(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        parts = [str(item or "").strip() for item in value if str(item or "").strip()]
        return " | ".join(parts)
    return str(value or "").strip()


def summarize_attempt_routes(attempts: list[dict]) -> tuple[list[str], str]:
    attempt_urls = []
    for attempt in attempts or []:
        if not isinstance(attempt, dict):
            continue
        candidate = _stringify_attempt_url(attempt.get("upstream_url", ""))
        if candidate:
            attempt_urls.append(candidate)
    unique_urls = list(dict.fromkeys(attempt_urls))
    return unique_urls, " -> ".join(attempt_urls)


def summarize_attempts_for_log(attempts: list[dict]) -> str:
    parts = []
    for item in attempts or []:
        if not isinstance(item, dict):
            continue
        attempt_no = item.get("attempt")
        route = str(item.get("upstream_url") or "")
        route = route.replace("https://", "").replace("http://", "")
        if len(route) > 56:
            route = route[:56] + "..."
        model = str(item.get("model") or "")
        status = item.get("status_code")
        action = str(item.get("action") or item.get("kind") or "")
        key_id = str(item.get("api_key_id") or "")
        reason = str(item.get("reason") or item.get("error") or "")
        reason = reason.replace("\n", " ").strip()
        if len(reason) > 42:
            reason = reason[:42] + "..."
        fragment = f"第{attempt_no}次 {route}"
        if key_id:
            fragment += f" key={key_id}"
        if model:
            fragment += f" 模型={model}"
        if status is not None:
            fragment += f" 状态={status}"
        if action:
            fragment += f" 动作={action}"
        if reason:
            fragment += f" 原因={reason}"
        parts.append(fragment)
    return " | ".join(parts)
