import importlib
import json
import os
import unittest

import requests


class FiniteStreamResponse(requests.Response):
    def __init__(self, url: str, lines: list[str]):
        super().__init__()
        self.status_code = 200
        self.url = url
        self.headers["Content-Type"] = "text/event-stream"
        self._lines = list(lines)
        self.closed_by_proxy = False

    def iter_lines(self, decode_unicode=False):
        for line in self._lines:
            yield line.encode("utf-8")

    def close(self):
        self.closed_by_proxy = True
        return super().close()


def make_json_response(url: str, payload: dict) -> requests.Response:
    response = requests.Response()
    response.status_code = 200
    response.url = url
    response.headers["Content-Type"] = "application/json"
    response._content = json.dumps(payload).encode("utf-8")
    return response


def make_error_response(url: str, status_code: int, body: str, *, content_type: str = "text/plain; charset=utf-8") -> requests.Response:
    response = requests.Response()
    response.status_code = status_code
    response.url = url
    response.headers["Content-Type"] = content_type
    response._content = body.encode("utf-8")
    return response


class AnthropicMalformedSuccessRetryTests(unittest.TestCase):
    def load_server(self):
        os.environ["PROXY_API_KEYS"] = "proxy-secret"
        os.environ["UPSTREAM_URL"] = "https://bad.example/v1"
        os.environ["UPSTREAM_URL_POOL"] = "https://bad.example/v1,https://good.example/v1"
        os.environ["UPSTREAM_API_KEY"] = "upstream-secret"
        os.environ["UPSTREAM_RANDOMIZE_ENDPOINTS"] = "0"

        import local_proxy.server as server

        server = importlib.reload(server)
        self.addCleanup(lambda: os.environ.pop("PROXY_API_KEYS", None))
        self.addCleanup(lambda: os.environ.pop("UPSTREAM_URL", None))
        self.addCleanup(lambda: os.environ.pop("UPSTREAM_URL_POOL", None))
        self.addCleanup(lambda: os.environ.pop("UPSTREAM_API_KEY", None))
        self.addCleanup(lambda: os.environ.pop("UPSTREAM_RANDOMIZE_ENDPOINTS", None))
        return server

    def test_anthropic_messages_retries_empty_stream_success_on_alternate_route(self):
        server = self.load_server()
        server.ENABLE_MODEL_PROBE = False
        server.UPSTREAM_RANDOMIZE_ENDPOINTS = False
        server.PROXY_POOLS[:] = [
            {
                "name": "bad",
                "enabled": True,
                "priority": 200,
                "urls": ["https://bad.example/v1"],
                "keys": [{"key": "bad-key"}],
                "route_policy": {},
            },
            {
                "name": "good",
                "enabled": True,
                "priority": 100,
                "urls": ["https://good.example/v1"],
                "keys": [{"key": "good-key"}],
                "route_policy": {},
            },
        ]
        server.rebuild_pool_state()
        server.route_health.clear()
        server.route_selection_state.clear()
        server.model_route_cache["routes"] = {}
        sent_urls = []

        terminal_only = {
            "id": "chatcmpl-empty",
            "object": "chat.completion.chunk",
            "created": 1,
            "model": "demo",
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        }
        healthy_body = {
            "id": "chatcmpl-ok",
            "object": "chat.completion",
            "created": 1,
            "model": "demo",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "ok"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }

        def fake_request(**kwargs):
            url = kwargs["url"]
            sent_urls.append(url)
            if "bad.example" in url:
                return FiniteStreamResponse(
                    url,
                    [
                        "data: " + json.dumps(terminal_only, separators=(",", ":")),
                        "",
                    ],
                )
            return make_json_response(url, healthy_body)

        server.UPSTREAM_SESSION.request = fake_request
        client = server.app.test_client()

        response = client.post(
            "/v1/messages",
            headers={
                "Authorization": "Bearer proxy-secret",
                "anthropic-version": "2023-06-01",
            },
            json={
                "model": "demo",
                "max_tokens": 64,
                "messages": [{"role": "user", "content": "hi"}],
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["content"][0]["text"], "ok")
        self.assertEqual(
            sent_urls,
            [
                "https://bad.example/v1/chat/completions",
                "https://good.example/v1/chat/completions",
            ],
        )
        self.assertEqual(response.headers.get("X-Proxy-Retries"), "1")

    def test_anthropic_messages_retries_empty_stream_success_on_same_url_distinct_route(self):
        server = self.load_server()
        server.ENABLE_MODEL_PROBE = False
        server.UPSTREAM_RANDOMIZE_ENDPOINTS = False
        server.UPSTREAM_ROUTE_FAILURE_THRESHOLD = 3
        server.PROXY_POOLS[:] = [
            {
                "name": "nv1",
                "enabled": True,
                "priority": 200,
                "urls": ["https://integrate.api.nvidia.com/v1"],
                "keys": [{"key": "nv-key-1"}],
                "route_policy": {},
            },
            {
                "name": "nv2",
                "enabled": True,
                "priority": 100,
                "urls": ["https://integrate.api.nvidia.com/v1"],
                "keys": [{"key": "nv-key-2"}],
                "route_policy": {},
            },
        ]
        server.rebuild_pool_state()
        server.route_health.clear()
        server.route_selection_state.clear()
        server.model_route_cache["routes"] = {}
        seen = []

        terminal_only = {
            "id": "chatcmpl-empty",
            "object": "chat.completion.chunk",
            "created": 1,
            "model": "demo",
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        }
        healthy_body = {
            "id": "chatcmpl-ok",
            "object": "chat.completion",
            "created": 1,
            "model": "demo",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "ok"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }

        def fake_request(**kwargs):
            auth = kwargs.get("headers", {}).get("Authorization", "")
            seen.append((kwargs["url"], auth))
            if len(seen) == 1:
                return FiniteStreamResponse(
                    kwargs["url"],
                    [
                        "data: " + json.dumps(terminal_only, separators=(",", ":")),
                        "",
                    ],
                )
            return make_json_response(kwargs["url"], healthy_body)

        server.UPSTREAM_SESSION.request = fake_request
        client = server.app.test_client()

        response = client.post(
            "/v1/messages",
            headers={
                "Authorization": "Bearer proxy-secret",
                "anthropic-version": "2023-06-01",
            },
            json={
                "model": "demo",
                "max_tokens": 64,
                "messages": [{"role": "user", "content": "hi"}],
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["content"][0]["text"], "ok")
        self.assertEqual(len(seen), 2)
        self.assertEqual(seen[0][0], "https://integrate.api.nvidia.com/v1/chat/completions")
        self.assertEqual(seen[1][0], "https://integrate.api.nvidia.com/v1/chat/completions")
        self.assertNotEqual(seen[0][1], seen[1][1])
        self.assertTrue(any("nv-key-1" in auth for _, auth in seen))
        self.assertTrue(any("nv-key-2" in auth for _, auth in seen))
        self.assertEqual(response.headers.get("X-Proxy-Retries"), "1")

    def test_anthropic_messages_returns_proxy_502_instead_of_upstream_404(self):
        server = self.load_server()
        server.ENABLE_MODEL_PROBE = False
        server.UPSTREAM_RANDOMIZE_ENDPOINTS = False
        server.PROXY_POOLS[:] = [
            {
                "name": "bad",
                "enabled": True,
                "priority": 100,
                "urls": ["https://bad.example/v1"],
                "keys": [{"key": "bad-key"}],
                "route_policy": {},
            },
        ]
        server.rebuild_pool_state()
        server.route_health.clear()
        server.route_selection_state.clear()
        server.model_route_cache["routes"] = {}

        server.UPSTREAM_SESSION.request = lambda **kwargs: make_error_response(
            kwargs["url"],
            404,
            "404 page not found",
        )
        client = server.app.test_client()

        response = client.post(
            "/v1/messages",
            headers={
                "Authorization": "Bearer proxy-secret",
                "anthropic-version": "2023-06-01",
            },
            json={
                "model": "demo",
                "max_tokens": 64,
                "messages": [{"role": "user", "content": "hi"}],
            },
        )

        payload = response.get_json()

        self.assertEqual(response.status_code, 502)
        self.assertEqual(payload["error"]["type"], "api_error")
        self.assertEqual(payload["error"]["message"], "Upstream returned HTTP 404.")
        self.assertEqual(payload["upstream_status"], 404)
        self.assertIn("404 page not found", payload["upstream_preview"])

    def test_anthropic_messages_retries_route_not_found_before_stream_success(self):
        server = self.load_server()
        server.ENABLE_MODEL_PROBE = False
        server.UPSTREAM_RANDOMIZE_ENDPOINTS = False
        server.PROXY_POOLS[:] = [
            {
                "name": "bad",
                "enabled": True,
                "priority": 200,
                "urls": ["https://bad.example/v1"],
                "keys": [{"key": "bad-key"}],
                "route_policy": {},
            },
            {
                "name": "good",
                "enabled": True,
                "priority": 100,
                "urls": ["https://good.example/v1"],
                "keys": [{"key": "good-key"}],
                "route_policy": {},
            },
        ]
        server.rebuild_pool_state()
        server.route_health.clear()
        server.route_selection_state.clear()
        server.model_route_cache["routes"] = {}
        sent_urls = []

        healthy_body = {
            "id": "chatcmpl-ok",
            "object": "chat.completion",
            "created": 1,
            "model": "demo",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "ok"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }

        def fake_request(**kwargs):
            url = kwargs["url"]
            sent_urls.append(url)
            if "bad.example" in url:
                return make_error_response(url, 404, "404 page not found")
            return make_json_response(url, healthy_body)

        server.UPSTREAM_SESSION.request = fake_request
        client = server.app.test_client()

        response = client.post(
            "/v1/messages",
            headers={
                "Authorization": "Bearer proxy-secret",
                "anthropic-version": "2023-06-01",
            },
            json={
                "model": "demo",
                "stream": True,
                "max_tokens": 64,
                "messages": [{"role": "user", "content": "hi"}],
            },
        )

        body = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn('"text":"ok"', body)
        self.assertEqual(
            sent_urls,
            [
                "https://bad.example/v1/chat/completions",
                "https://good.example/v1/chat/completions",
            ],
        )
        self.assertEqual(response.headers.get("X-Proxy-Retries"), "1")

    def test_anthropic_messages_exhausts_candidate_routes_until_stream_success(self):
        server = self.load_server()
        server.ENABLE_MODEL_PROBE = False
        server.UPSTREAM_RANDOMIZE_ENDPOINTS = False
        server.PROXY_POOLS[:] = [
            {
                "name": "bad1",
                "enabled": True,
                "priority": 400,
                "urls": ["https://bad1.example/v1"],
                "keys": [{"key": "bad1-key"}],
                "route_policy": {},
            },
            {
                "name": "bad2",
                "enabled": True,
                "priority": 300,
                "urls": ["https://bad2.example/v1"],
                "keys": [{"key": "bad2-key"}],
                "route_policy": {},
            },
            {
                "name": "bad3",
                "enabled": True,
                "priority": 200,
                "urls": ["https://bad3.example/v1"],
                "keys": [{"key": "bad3-key"}],
                "route_policy": {},
            },
            {
                "name": "good",
                "enabled": True,
                "priority": 100,
                "urls": ["https://good.example/v1"],
                "keys": [{"key": "good-key"}],
                "route_policy": {},
            },
        ]
        server.rebuild_pool_state()
        server.route_health.clear()
        server.route_selection_state.clear()
        server.model_route_cache["routes"] = {}
        sent_urls = []

        terminal_only = {
            "id": "chatcmpl-empty",
            "object": "chat.completion.chunk",
            "created": 1,
            "model": "demo",
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        }
        healthy_body = {
            "id": "chatcmpl-ok",
            "object": "chat.completion",
            "created": 1,
            "model": "demo",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "ok"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }

        def fake_request(**kwargs):
            url = kwargs["url"]
            sent_urls.append(url)
            if "good.example" in url:
                return make_json_response(url, healthy_body)
            return FiniteStreamResponse(
                url,
                [
                    "data: " + json.dumps(terminal_only, separators=(",", ":")),
                    "",
                ],
            )

        server.UPSTREAM_SESSION.request = fake_request
        client = server.app.test_client()

        response = client.post(
            "/v1/messages",
            headers={
                "Authorization": "Bearer proxy-secret",
                "anthropic-version": "2023-06-01",
            },
            json={
                "model": "demo",
                "stream": True,
                "max_tokens": 64,
                "messages": [{"role": "user", "content": "hi"}],
            },
        )

        body = response.get_data(as_text=True)
        recent_requests = server.request_recorder.snapshot()["recent_requests"]

        self.assertEqual(response.status_code, 200)
        self.assertIn('"text":"ok"', body)
        self.assertEqual(
            sent_urls,
            [
                "https://bad1.example/v1/chat/completions",
                "https://bad2.example/v1/chat/completions",
                "https://bad3.example/v1/chat/completions",
                "https://good.example/v1/chat/completions",
            ],
        )
        self.assertEqual(len(recent_requests), 1)
        self.assertEqual(recent_requests[0]["status_code"], 200)
        self.assertEqual(recent_requests[0]["bytes_sent"] > 0, True)

    def test_anthropic_messages_preserves_thinking_stream_blocks_when_enabled(self):
        server = self.load_server()
        server.ENABLE_MODEL_PROBE = False
        server.UPSTREAM_RANDOMIZE_ENDPOINTS = False
        server.PROXY_POOLS[:] = [
            {
                "name": "good",
                "enabled": True,
                "priority": 100,
                "urls": ["https://good.example/v1"],
                "keys": [{"key": "good-key"}],
                "route_policy": {},
            },
        ]
        server.rebuild_pool_state()
        server.route_health.clear()
        server.route_selection_state.clear()
        server.model_route_cache["routes"] = {}

        first = {
            "id": "chatcmpl-thinking",
            "object": "chat.completion.chunk",
            "created": 1,
            "model": "demo",
            "choices": [{"index": 0, "delta": {"reasoning_content": "trace", "content": "ok"}, "finish_reason": None}],
        }
        terminal = {
            "id": "chatcmpl-thinking",
            "object": "chat.completion.chunk",
            "created": 1,
            "model": "demo",
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        }

        server.UPSTREAM_SESSION.request = lambda **kwargs: FiniteStreamResponse(
            kwargs["url"],
            [
                "data: " + json.dumps(first, separators=(",", ":")),
                "",
                "data: " + json.dumps(terminal, separators=(",", ":")),
                "",
            ],
        )
        client = server.app.test_client()

        response = client.post(
            "/v1/messages",
            headers={
                "Authorization": "Bearer proxy-secret",
                "anthropic-version": "2023-06-01",
            },
            json={
                "model": "demo",
                "stream": True,
                "thinking": {"type": "enabled", "budget_tokens": 1024},
                "max_tokens": 64,
                "messages": [{"role": "user", "content": "hi"}],
            },
        )

        body = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn('"thinking_delta"', body)
        self.assertIn('"text_delta"', body)
        self.assertIn('"thinking":"trace"', body)
        self.assertIn('"text":"ok"', body)

    def test_anthropic_messages_fills_usage_when_upstream_omits_usage(self):
        server = self.load_server()
        server.ENABLE_MODEL_PROBE = False
        server.PROXY_POOLS[:] = [
            {
                "name": "good",
                "enabled": True,
                "priority": 100,
                "urls": ["https://good.example/v1"],
                "keys": [{"key": "good-key"}],
                "route_policy": {},
            },
        ]
        server.rebuild_pool_state()
        server.route_health.clear()
        server.route_selection_state.clear()
        healthy_body = {
            "id": "chatcmpl-ok",
            "object": "chat.completion",
            "created": 1,
            "model": "demo",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "ok"},
                    "finish_reason": "stop",
                }
            ],
        }

        def fake_request(**kwargs):
            return make_json_response(kwargs["url"], healthy_body)

        server.UPSTREAM_SESSION.request = fake_request
        client = server.app.test_client()

        response = client.post(
            "/v1/messages",
            headers={
                "Authorization": "Bearer proxy-secret",
                "anthropic-version": "2023-06-01",
            },
            json={
                "model": "demo",
                "max_tokens": 64,
                "messages": [{"role": "user", "content": "hi"}],
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["content"][0]["text"], "ok")
        self.assertGreater(payload["usage"]["input_tokens"], 0)
        self.assertGreater(payload["usage"]["output_tokens"], 0)

    def test_anthropic_messages_preserves_upstream_usage(self):
        server = self.load_server()
        server.ENABLE_MODEL_PROBE = False
        server.PROXY_POOLS[:] = [
            {
                "name": "good",
                "enabled": True,
                "priority": 100,
                "urls": ["https://good.example/v1"],
                "keys": [{"key": "good-key"}],
                "route_policy": {},
            },
        ]
        server.rebuild_pool_state()
        server.route_health.clear()
        server.route_selection_state.clear()
        healthy_body = {
            "id": "chatcmpl-ok",
            "object": "chat.completion",
            "created": 1,
            "model": "demo",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "ok"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 123, "completion_tokens": 45, "total_tokens": 168},
        }

        def fake_request(**kwargs):
            return make_json_response(kwargs["url"], healthy_body)

        server.UPSTREAM_SESSION.request = fake_request
        client = server.app.test_client()

        response = client.post(
            "/v1/messages",
            headers={
                "Authorization": "Bearer proxy-secret",
                "anthropic-version": "2023-06-01",
            },
            json={
                "model": "demo",
                "max_tokens": 64,
                "messages": [{"role": "user", "content": "hi"}],
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["usage"], {"input_tokens": 123, "output_tokens": 45})

    def test_anthropic_messages_maps_cached_usage_fields(self):
        server = self.load_server()
        server.ENABLE_MODEL_PROBE = False
        server.PROXY_POOLS[:] = [
            {
                "name": "good",
                "enabled": True,
                "priority": 100,
                "urls": ["https://good.example/v1"],
                "keys": [{"key": "good-key"}],
                "route_policy": {},
            },
        ]
        server.rebuild_pool_state()
        server.route_health.clear()
        server.route_selection_state.clear()
        healthy_body = {
            "id": "chatcmpl-ok",
            "object": "chat.completion",
            "created": 1,
            "model": "demo",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "ok"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 123,
                "completion_tokens": 45,
                "total_tokens": 168,
                "prompt_tokens_details": {"cached_tokens": 88},
            },
        }

        def fake_request(**kwargs):
            return make_json_response(kwargs["url"], healthy_body)

        server.UPSTREAM_SESSION.request = fake_request
        client = server.app.test_client()

        response = client.post(
            "/v1/messages",
            headers={
                "Authorization": "Bearer proxy-secret",
                "anthropic-version": "2023-06-01",
            },
            json={
                "model": "demo",
                "max_tokens": 64,
                "messages": [{"role": "user", "content": "hi"}],
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["usage"]["input_tokens"], 123)
        self.assertEqual(payload["usage"]["output_tokens"], 45)
        self.assertEqual(payload["usage"]["cache_read_input_tokens"], 88)

    def test_anthropic_messages_maps_prompt_cache_hit_tokens(self):
        server = self.load_server()
        server.ENABLE_MODEL_PROBE = False
        server.PROXY_POOLS[:] = [
            {
                "name": "good",
                "enabled": True,
                "priority": 100,
                "urls": ["https://good.example/v1"],
                "keys": [{"key": "good-key"}],
                "route_policy": {},
            },
        ]
        server.rebuild_pool_state()
        server.route_health.clear()
        server.route_selection_state.clear()
        healthy_body = {
            "id": "chatcmpl-ok",
            "object": "chat.completion",
            "created": 1,
            "model": "demo",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "ok"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "completion_tokens": 45,
                "total_tokens": 168,
                "prompt_cache_hit_tokens": 88,
                "prompt_cache_miss_tokens": 35,
            },
        }

        def fake_request(**kwargs):
            return make_json_response(kwargs["url"], healthy_body)

        server.UPSTREAM_SESSION.request = fake_request
        client = server.app.test_client()

        response = client.post(
            "/v1/messages",
            headers={
                "Authorization": "Bearer proxy-secret",
                "anthropic-version": "2023-06-01",
            },
            json={
                "model": "demo",
                "max_tokens": 64,
                "messages": [{"role": "user", "content": "hi"}],
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["usage"]["input_tokens"], 123)
        self.assertEqual(payload["usage"]["output_tokens"], 45)
        self.assertEqual(payload["usage"]["cache_read_input_tokens"], 88)


if __name__ == "__main__":
    unittest.main()
