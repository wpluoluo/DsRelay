from __future__ import annotations


def _handler(handlers: dict, name: str):
    try:
        return handlers[name]
    except KeyError as exc:  # pragma: no cover
        raise KeyError(f"missing route handler: {name}") from exc


def register_http_routes(app, handlers: dict) -> None:
    """Register Flask routes outside of the main server module."""

    app.after_request(_handler(handlers, "add_cors_headers"))
    app.add_url_rule("/health", endpoint="health", view_func=_handler(handlers, "health"), methods=["GET"])
    app.add_url_rule("/debug/state", endpoint="debug_state", view_func=_handler(handlers, "debug_state"), methods=["GET"])
    app.add_url_rule(
        "/debug/config",
        endpoint="debug_config",
        view_func=_handler(handlers, "debug_config"),
        methods=["GET", "POST", "OPTIONS"],
    )
    app.add_url_rule(
        "/debug/pools/test",
        endpoint="debug_pool_test",
        view_func=_handler(handlers, "debug_pool_test"),
        methods=["POST", "OPTIONS"],
    )
    app.add_url_rule(
        "/debug/requests/clear",
        endpoint="debug_requests_clear",
        view_func=_handler(handlers, "debug_requests_clear"),
        methods=["POST", "OPTIONS"],
    )
    app.add_url_rule(
        "/debug/proxy-keys",
        endpoint="debug_proxy_api_keys",
        view_func=_handler(handlers, "debug_proxy_api_keys"),
        methods=["GET", "POST", "OPTIONS"],
    )
    app.add_url_rule("/v1", endpoint="v1_root", view_func=_handler(handlers, "v1_root"), methods=["GET", "OPTIONS"])
    app.add_url_rule(
        "/v1beta",
        endpoint="gemini_version_root_v1beta",
        view_func=_handler(handlers, "gemini_version_root"),
        methods=["GET", "OPTIONS"],
    )
    app.add_url_rule(
        "/v1alpha",
        endpoint="gemini_version_root_v1alpha",
        view_func=_handler(handlers, "gemini_version_root"),
        methods=["GET", "OPTIONS"],
    )
    app.add_url_rule(
        "/v1/messages",
        endpoint="anthropic_messages",
        view_func=_handler(handlers, "anthropic_messages"),
        methods=["POST", "OPTIONS"],
    )
    app.add_url_rule(
        "/v1/<path:subpath>",
        endpoint="proxy",
        view_func=_handler(handlers, "proxy"),
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    )
    app.add_url_rule(
        "/v1beta/<path:subpath>",
        endpoint="proxy_gemini_versioned_v1beta",
        view_func=_handler(handlers, "proxy_gemini_versioned"),
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    )
    app.add_url_rule(
        "/v1alpha/<path:subpath>",
        endpoint="proxy_gemini_versioned_v1alpha",
        view_func=_handler(handlers, "proxy_gemini_versioned"),
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    )
