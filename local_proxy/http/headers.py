from __future__ import annotations

from flask import request


SENSITIVE_QUERY_KEYS = {
    "key",
    "api_key",
    "apikey",
    "access_token",
    "token",
    "authorization",
    "proxy-authorization",
    "x-forwarded-authorization",
    "x-api-key",
    "x-goog-api-key",
}

HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "content-encoding",
    "content-length",
}

RESPONSE_HEADER_BLOCKLIST = {
    "server",
}

REQUEST_HEADER_BLOCKLIST = {
    "host",
    "content-length",
    "accept-encoding",
    "connection",
    "authorization",
    "proxy-authorization",
    "x-forwarded-authorization",
    "cookie",
    "x-api-key",
    "x-goog-api-key",
    "anthropic-version",
    "anthropic-beta",
}


def sanitize_query_string(query_string: str | bytes | None, *, secret_masker) -> str:
    if isinstance(query_string, bytes):
        raw = query_string.decode("utf-8", errors="ignore")
    else:
        raw = str(query_string or "")
    if not raw:
        return ""

    sanitized_parts = []
    for part in raw.split("&"):
        if not part:
            continue
        key, separator, value = part.partition("=")
        if key.lower() in SENSITIVE_QUERY_KEYS:
            sanitized_parts.append(f"{key}{separator}{secret_masker(value) if value else '***'}")
        else:
            sanitized_parts.append(part)
    return "&".join(sanitized_parts)


def build_upstream_params() -> list[tuple[str, str]]:
    params = []
    for key, values in request.args.lists():
        if key.lower() in SENSITIVE_QUERY_KEYS:
            continue
        for value in values:
            params.append((key, value))
    return params


def build_upstream_headers(*, upstream_api_key: str) -> dict:
    headers = {}
    for key, value in request.headers.items():
        if key.lower() in REQUEST_HEADER_BLOCKLIST:
            continue
        headers[key] = value

    if "Content-Type" not in headers:
        headers["Content-Type"] = "application/json"

    headers.pop("Authorization", None)
    if upstream_api_key:
        if upstream_api_key.lower().startswith("bearer "):
            headers["Authorization"] = upstream_api_key
        else:
            headers["Authorization"] = f"Bearer {upstream_api_key}"

    return headers


def build_response_headers(upstream_headers) -> dict:
    return {
        key: value
        for key, value in upstream_headers.items()
        if key.lower() not in HOP_BY_HOP_HEADERS and key.lower() not in RESPONSE_HEADER_BLOCKLIST
    }


def apply_sse_response_headers(headers: dict) -> dict:
    headers["Content-Type"] = "text/event-stream; charset=utf-8"
    headers["Cache-Control"] = "no-cache, no-transform"
    headers["X-Accel-Buffering"] = "no"
    return headers
