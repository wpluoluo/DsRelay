import json
import time
import unittest
from unittest import mock

import requests

from local_proxy.compat.protocols import (
    convert_anthropic_messages_to_openai,
    convert_openai_response_to_anthropic,
)
from local_proxy.http.validation import inspect_success_payload
from local_proxy.server import (
    _node_aware_request,
    app,
    bridge_openai_sse_response,
    classify_upstream_response,
    consume_openai_sse_events,
    execute_upstream_request,
    handle_anthropic_stream_response,
    handle_gemini_stream_response,
    openai_stream_response_with_connect_heartbeat,
    proxy_response,
    request_recorder,
    start_background_upstream_execution,
    wait_background_upstream_execution,
)


class SlowAfterTerminalResponse(requests.Response):
    def __init__(self, lines):
        super().__init__()
        self.status_code = 200
        self.headers["Content-Type"] = "text/event-stream"
        self.url = "https://upstream.example/v1/chat/completions"
        self._lines = list(lines)
        self.closed_by_proxy = False

    def iter_lines(self, decode_unicode=False):
        for line in self._lines:
            yield line.encode("utf-8") if isinstance(line, str) else line
        while not self.closed_by_proxy:
            time.sleep(0.01)
            yield b": late-upstream-line"

    def close(self):
        self.closed_by_proxy = True
        return super().close()


class FiniteStreamResponse(requests.Response):
    def __init__(self, lines):
        super().__init__()
        self.status_code = 200
        self.headers["Content-Type"] = "text/event-stream"
        self.url = "https://upstream.example/v1/chat/completions"
        self._lines = list(lines)
        self.closed_by_proxy = False

    def iter_lines(self, decode_unicode=False):
        for line in self._lines:
            yield line.encode("utf-8") if isinstance(line, str) else line

    def close(self):
        self.closed_by_proxy = True
        return super().close()


class ErrorAfterPartialStreamResponse(requests.Response):
    def __init__(self, lines, exc):
        super().__init__()
        self.status_code = 200
        self.headers["Content-Type"] = "text/event-stream"
        self.url = "https://upstream.example/v1/chat/completions"
        self._lines = list(lines)
        self._exc = exc
        self.closed_by_proxy = False

    def iter_lines(self, decode_unicode=False):
        for line in self._lines:
            yield line.encode("utf-8") if isinstance(line, str) else line
        raise self._exc

    def close(self):
        self.closed_by_proxy = True
        return super().close()


def make_json_response(payload: dict) -> requests.Response:
    response = requests.Response()
    response.status_code = 200
    response.url = "https://upstream.example/v1/chat/completions"
    response.headers["Content-Type"] = "application/json"
    response._content = json.dumps(payload).encode("utf-8")
    return response


def make_error_response(status_code: int, body: str, *, content_type: str = "text/plain") -> requests.Response:
    response = requests.Response()
    response.status_code = status_code
    response.url = "https://upstream.example/v1/chat/completions"
    response.headers["Content-Type"] = content_type
    response._content = body.encode("utf-8")
    return response


def openai_stream_lines(*, finish_reason="stop"):
    first = {
        "id": "chatcmpl-test",
        "object": "chat.completion.chunk",
        "created": 1,
        "model": "test-model",
        "choices": [{"index": 0, "delta": {"role": "assistant", "content": "ok"}, "finish_reason": None}],
    }
    terminal = {
        "id": "chatcmpl-test",
        "object": "chat.completion.chunk",
        "created": 1,
        "model": "test-model",
        "choices": [{"index": 0, "delta": {}, "finish_reason": finish_reason}],
    }
    return [
        "data: " + json.dumps(first, separators=(",", ":")),
        "",
        "data: " + json.dumps(terminal, separators=(",", ":")),
        "",
    ]


def collect_response_body(response):
    return b"".join(response.response)


def parse_sse_events(body: str) -> list[tuple[str | None, dict]]:
    events = []
    for packet in body.split("\n\n"):
        if not packet.strip():
            continue
        event_name = None
        data = None
        for line in packet.splitlines():
            if line.startswith("event: "):
                event_name = line[len("event: "):]
            elif line.startswith("data: "):
                data = line[len("data: "):]
        if data and data != "[DONE]":
            events.append((event_name, json.loads(data)))
    return events


def openai_stream_usage_events(body: str) -> list[dict]:
    return [
        payload
        for _, payload in parse_sse_events(body)
        if isinstance(payload, dict) and isinstance(payload.get("usage"), dict)
    ]


class StreamCompletionTests(unittest.TestCase):
    def test_bridge_openai_sse_response_streams_success_chunks_lazily(self):
        observed = []

        class StepwiseBody:
            def __iter__(self):
                observed.append("iter-start")
                yield b"chunk-1"
                observed.append("after-chunk-1")
                yield b"chunk-2"
                observed.append("after-chunk-2")

        response = requests.Response()
        response.status_code = 200
        response.response = StepwiseBody()

        bridged = iter(bridge_openai_sse_response(response))

        self.assertEqual(next(bridged), b"chunk-1")
        self.assertEqual(observed, ["iter-start"])
        self.assertEqual(next(bridged), b"chunk-2")
        self.assertEqual(observed, ["iter-start", "after-chunk-1"])
        with self.assertRaises(StopIteration):
            next(bridged)
        self.assertEqual(observed, ["iter-start", "after-chunk-1", "after-chunk-2"])

    def test_classify_404_page_not_found_as_route_switch(self):
        response = make_error_response(404, "404 page not found")

        action, reason = classify_upstream_response(response)

        self.assertEqual(action, "switch_route")
        self.assertEqual(reason, "route_not_found_404")

    def test_node_aware_request_does_not_consume_streaming_opencode_response_body(self):
        class StreamingSentinelResponse:
            status_code = 200

            @property
            def content(self):
                raise AssertionError("streaming response body should not be consumed for logging")

        sentinel = StreamingSentinelResponse()

        with mock.patch("local_proxy.server.UPSTREAM_SESSION.request", return_value=sentinel) as request_mock:
            response = _node_aware_request(
                "POST",
                "https://opencode.ai/zen/v1/chat/completions",
                stream=True,
                json={"model": "demo", "stream": True},
                headers={"Content-Type": "application/json"},
            )

        self.assertIs(response, sentinel)
        request_mock.assert_called_once()
        self.assertEqual(
            request_mock.call_args.args[:2],
            ("POST", "http://127.0.0.1:18766/zen/v1/chat/completions"),
        )

    def test_openai_stream_exhausts_candidate_routes_until_success(self):
        terminal = {
            "id": "chatcmpl-empty",
            "object": "chat.completion.chunk",
            "created": 1,
            "model": "test-model",
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        }
        route_pool = [
            "https://bad1.example/v1/chat/completions",
            "https://bad2.example/v1/chat/completions",
            "https://bad3.example/v1/chat/completions",
            "https://good.example/v1/chat/completions",
        ]
        request_payload = {"model": "test-model", "stream": True, "messages": [{"role": "user", "content": "hello"}]}
        initial_response = FiniteStreamResponse(
            [
                "data: " + json.dumps(terminal, separators=(",", ":")),
                "",
            ]
        )
        initial_response.url = route_pool[0]
        fallback_executions = [
            {
                "upstream_response": FiniteStreamResponse(
                    [
                        "data: " + json.dumps(terminal, separators=(",", ":")),
                        "",
                    ]
                ),
                "upstream_url": route_pool[1],
                "route_url": route_pool[1],
                "tool_schemas": {},
                "retry_count": 1,
                "upstream_url_pool": list(route_pool),
                "route_pool_size": len(route_pool),
                "request_context": {},
            },
            {
                "upstream_response": FiniteStreamResponse(
                    [
                        "data: " + json.dumps(terminal, separators=(",", ":")),
                        "",
                    ]
                ),
                "upstream_url": route_pool[2],
                "route_url": route_pool[2],
                "tool_schemas": {},
                "retry_count": 2,
                "upstream_url_pool": list(route_pool),
                "route_pool_size": len(route_pool),
                "request_context": {},
            },
            {
                "upstream_response": make_json_response(
                    {
                        "id": "chatcmpl-ok",
                        "object": "chat.completion",
                        "created": 1,
                        "model": "test-model",
                        "choices": [
                            {
                                "index": 0,
                                "message": {"role": "assistant", "content": "ok"},
                                "finish_reason": "stop",
                            }
                        ],
                        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                    }
                ),
                "upstream_url": route_pool[3],
                "route_url": route_pool[3],
                "tool_schemas": {},
                "retry_count": 3,
                "upstream_url_pool": list(route_pool),
                "route_pool_size": len(route_pool),
                "request_context": {},
            },
        ]
        fallback_executions[0]["upstream_response"].url = route_pool[1]
        fallback_executions[1]["upstream_response"].url = route_pool[2]
        fallback_executions[2]["upstream_response"].url = route_pool[3]

        with mock.patch("local_proxy.server.execute_upstream_request", side_effect=fallback_executions) as execute_mock:
            response = proxy_response(
                initial_response,
                sanitize_dsml=True,
                request_id="stream-failover-budget",
                upstream_url=route_pool[0],
                started_at=time.perf_counter(),
                requested_stream=True,
                route_hint="chat/completions",
                tool_schemas={},
                retry_count=0,
                protocol="openai_chat_completions",
                request_payload=request_payload,
                execution={
                    "route_url": route_pool[0],
                    "upstream_url_pool": list(route_pool),
                    "route_pool_size": len(route_pool),
                    "request_context": {},
                },
            )
            body = collect_response_body(response).decode("utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertIn('"content":"ok"', body)
        self.assertIn("data: [DONE]\n\n", body)
        self.assertEqual(execute_mock.call_count, 3)

    def test_openai_stream_stops_after_finish_reason_and_adds_done(self):
        upstream = SlowAfterTerminalResponse(openai_stream_lines())
        request_payload = {"model": "test-model", "stream": True, "messages": [{"role": "user", "content": "hello"}]}
        response = proxy_response(
            upstream,
            sanitize_dsml=True,
            request_id="streamtest",
            upstream_url=upstream.url,
            started_at=time.perf_counter(),
            requested_stream=True,
            route_hint="chat/completions",
            tool_schemas={},
            retry_count=0,
            protocol="openai_chat_completions",
            request_payload=request_payload,
            execution={},
        )

        body = collect_response_body(response).decode("utf-8")
        usage_events = openai_stream_usage_events(body)

        self.assertIn('"content":"ok"', body)
        self.assertIn('"finish_reason":"stop"', body)
        self.assertIn("data: [DONE]\n\n", body)
        self.assertEqual(len(usage_events), 1)
        self.assertGreater(usage_events[0]["usage"]["prompt_tokens"], 0)
        self.assertGreater(usage_events[0]["usage"]["completion_tokens"], 0)
        self.assertTrue(upstream.closed_by_proxy)

    def test_openai_stream_read_exception_after_partial_output_fails_over_and_completes(self):
        initial_upstream = ErrorAfterPartialStreamResponse(
            [
                "data: " + json.dumps(
                    {
                        "id": "chatcmpl-partial",
                        "object": "chat.completion.chunk",
                        "created": 1,
                        "model": "test-model",
                        "choices": [
                            {
                                "index": 0,
                                "delta": {"role": "assistant", "content": "ok"},
                                "finish_reason": None,
                            }
                        ],
                    },
                    separators=(",", ":"),
                ),
                "",
            ],
            requests.exceptions.ChunkedEncodingError("peer closed stream"),
        )
        fallback_upstream = FiniteStreamResponse(openai_stream_lines())
        request_payload = {"model": "test-model", "stream": True, "messages": [{"role": "user", "content": "hello"}]}

        captured_retry_payloads = []

        def fake_execute(*args, **kwargs):
            captured_retry_payloads.append(args[1])
            return {
                "upstream_response": fallback_upstream,
                "upstream_url": fallback_upstream.url,
                "route_url": fallback_upstream.url,
                "tool_schemas": {},
                "retry_count": 1,
                "upstream_url_pool": [
                    initial_upstream.url,
                    fallback_upstream.url,
                ],
                "route_pool_size": 2,
                "request_context": {},
            }

        with mock.patch("local_proxy.server.execute_upstream_request", side_effect=fake_execute) as execute_mock:
            response = proxy_response(
                initial_upstream,
                sanitize_dsml=True,
                request_id="stream-read-failover",
                upstream_url=initial_upstream.url,
                started_at=time.perf_counter(),
                requested_stream=True,
                route_hint="chat/completions",
                tool_schemas={},
                retry_count=0,
                protocol="openai_chat_completions",
                request_payload=request_payload,
                execution={
                    "route_url": initial_upstream.url,
                    "upstream_url_pool": [initial_upstream.url, fallback_upstream.url],
                    "route_pool_size": 2,
                    "request_context": {},
                },
            )
            body = collect_response_body(response).decode("utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertIn('"content":"ok"', body)
        self.assertIn('"finish_reason":"stop"', body)
        self.assertIn("data: [DONE]\n\n", body)
        self.assertEqual(execute_mock.call_count, 1)
        self.assertTrue(initial_upstream.closed_by_proxy)
        self.assertTrue(fallback_upstream.closed_by_proxy)
        self.assertTrue(any("已输出片段末尾" in json.dumps(payload, ensure_ascii=False) for payload in captured_retry_payloads))

    def test_openai_stream_read_exception_after_partial_output_still_closes_cleanly_without_failover(self):
        upstream = ErrorAfterPartialStreamResponse(
            [
                "data: " + json.dumps(
                    {
                        "id": "chatcmpl-partial-local",
                        "object": "chat.completion.chunk",
                        "created": 1,
                        "model": "test-model",
                        "choices": [
                            {
                                "index": 0,
                                "delta": {"role": "assistant", "content": "ok"},
                                "finish_reason": None,
                            }
                        ],
                    },
                    separators=(",", ":"),
                ),
                "",
            ],
            requests.exceptions.ReadTimeout("mid-stream timeout"),
        )
        request_payload = {"model": "test-model", "stream": True, "messages": [{"role": "user", "content": "hello"}]}

        with mock.patch("local_proxy.server.execute_upstream_request", return_value=None) as execute_mock:
            response = proxy_response(
                upstream,
                sanitize_dsml=True,
                request_id="stream-read-clean-close",
                upstream_url=upstream.url,
                started_at=time.perf_counter(),
                requested_stream=True,
                route_hint="chat/completions",
                tool_schemas={},
                retry_count=0,
                protocol="openai_chat_completions",
                request_payload=request_payload,
                execution={
                    "route_url": upstream.url,
                    "upstream_url_pool": [upstream.url, "https://fallback.example/v1/chat/completions"],
                    "route_pool_size": 2,
                    "request_context": {},
                },
            )
            body = collect_response_body(response).decode("utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertIn('"content":"ok"', body)
        self.assertIn('"finish_reason":"stop"', body)
        self.assertIn("data: [DONE]\n\n", body)
        self.assertEqual(execute_mock.call_count, 1)
        self.assertTrue(upstream.closed_by_proxy)

    def test_openai_stream_wraps_bare_json_chunks_into_sse_frames(self):
        first = {
            "id": "chatcmpl-bare",
            "object": "chat.completion.chunk",
            "created": 1,
            "model": "test-model",
            "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}],
        }
        second = {
            "id": "chatcmpl-bare",
            "object": "chat.completion.chunk",
            "created": 1,
            "model": "test-model",
            "choices": [{"index": 0, "delta": {"content": "好的"}, "finish_reason": None}],
        }
        terminal = {
            "id": "chatcmpl-bare",
            "object": "chat.completion.chunk",
            "created": 1,
            "model": "test-model",
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        }
        upstream = FiniteStreamResponse(
            [
                json.dumps(first, separators=(",", ":")),
                "",
                json.dumps(second, separators=(",", ":")),
                "",
                "data: " + json.dumps(terminal, separators=(",", ":")),
                "",
            ]
        )
        response = proxy_response(
            upstream,
            sanitize_dsml=True,
            request_id="barejsonstream",
            upstream_url=upstream.url,
            started_at=time.perf_counter(),
            requested_stream=True,
            route_hint="chat/completions",
            tool_schemas={},
            retry_count=0,
            protocol="openai_chat_completions",
            request_payload={"model": "test-model", "stream": True, "messages": [{"role": "user", "content": "hello"}]},
            execution={},
        )

        body = collect_response_body(response).decode("utf-8")
        events = parse_sse_events(body)

        self.assertEqual(events[0][1]["choices"][0]["delta"]["role"], "assistant")
        self.assertEqual(events[1][1]["choices"][0]["delta"]["content"], "好的")
        self.assertEqual(events[2][1]["choices"][0]["finish_reason"], "stop")
        self.assertNotIn('\n{"choices":[{"delta":{"content":"好的"},"index":0}]', body)
        self.assertIn("data: [DONE]\n\n", body)
        self.assertTrue(upstream.closed_by_proxy)

    def test_openai_non_stream_fills_usage_when_upstream_omits_usage(self):
        upstream = make_json_response(
            {
                "id": "chatcmpl-test",
                "object": "chat.completion",
                "created": 1,
                "model": "test-model",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "ok"},
                        "finish_reason": "stop",
                    }
                ],
            }
        )
        response = proxy_response(
            upstream,
            sanitize_dsml=True,
            request_id="jsonusage",
            upstream_url=upstream.url,
            started_at=time.perf_counter(),
            requested_stream=False,
            route_hint="chat/completions",
            tool_schemas={},
            retry_count=0,
            protocol="openai_chat_completions",
            request_payload={"model": "test-model", "messages": [{"role": "user", "content": "hello"}]},
            execution={},
        )

        payload = json.loads(collect_response_body(response).decode("utf-8"))

        self.assertEqual(payload["choices"][0]["message"]["content"], "ok")
        self.assertGreater(payload["usage"]["prompt_tokens"], 0)
        self.assertGreater(payload["usage"]["completion_tokens"], 0)
        self.assertEqual(payload["usage"]["total_tokens"], payload["usage"]["prompt_tokens"] + payload["usage"]["completion_tokens"])

    def test_openai_json_to_stream_fills_usage_when_upstream_omits_usage(self):
        upstream = make_json_response(
            {
                "id": "chatcmpl-test",
                "object": "chat.completion",
                "created": 1,
                "model": "test-model",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "ok"},
                        "finish_reason": "stop",
                    }
                ],
            }
        )
        response = proxy_response(
            upstream,
            sanitize_dsml=True,
            request_id="jsonstreamusage",
            upstream_url=upstream.url,
            started_at=time.perf_counter(),
            requested_stream=True,
            route_hint="chat/completions",
            tool_schemas={},
            retry_count=0,
            protocol="openai_chat_completions",
            request_payload={"model": "test-model", "stream": True, "messages": [{"role": "user", "content": "hello"}]},
            execution={},
        )

        body = collect_response_body(response).decode("utf-8")
        usage_events = openai_stream_usage_events(body)

        self.assertIn("data: [DONE]\n\n", body)
        self.assertEqual(len(usage_events), 1)
        self.assertGreater(usage_events[0]["usage"]["prompt_tokens"], 0)
        self.assertGreater(usage_events[0]["usage"]["completion_tokens"], 0)

    def test_openai_stream_preserves_upstream_usage(self):
        usage_event = {
            "id": "chatcmpl-test",
            "object": "chat.completion.chunk",
            "created": 1,
            "model": "test-model",
            "choices": [],
            "usage": {
                "prompt_tokens": 123,
                "completion_tokens": 45,
                "total_tokens": 168,
                "prompt_tokens_details": {"cached_tokens": 77},
            },
        }
        upstream = SlowAfterTerminalResponse(
            [
                openai_stream_lines()[0],
                openai_stream_lines()[1],
                "data: " + json.dumps(usage_event, separators=(",", ":")),
                "",
                openai_stream_lines()[2],
                openai_stream_lines()[3],
            ]
        )
        response = proxy_response(
            upstream,
            sanitize_dsml=True,
            request_id="streamusagepreserve",
            upstream_url=upstream.url,
            started_at=time.perf_counter(),
            requested_stream=True,
            route_hint="chat/completions",
            tool_schemas={},
            retry_count=0,
            protocol="openai_chat_completions",
            request_payload={"model": "test-model", "stream": True, "messages": [{"role": "user", "content": "hello"}]},
            execution={},
        )

        body = collect_response_body(response).decode("utf-8")
        usage_events = openai_stream_usage_events(body)

        self.assertEqual(len(usage_events), 1)
        self.assertEqual(usage_events[0]["usage"]["prompt_tokens"], 123)
        self.assertEqual(usage_events[0]["usage"]["completion_tokens"], 45)
        self.assertEqual(usage_events[0]["usage"]["total_tokens"], 168)
        self.assertEqual(usage_events[0]["usage"]["prompt_tokens_details"]["cached_tokens"], 77)
        self.assertEqual(usage_events[0]["usage"]["cache_read_input_tokens"], 77)
        recent = next(item for item in request_recorder.snapshot()["recent_requests"] if item["request_id"] == "streamusagepreserve")
        self.assertEqual(recent["prompt_tokens"], 123)
        self.assertEqual(recent["completion_tokens"], 45)
        self.assertEqual(recent["total_tokens"], 168)
        self.assertEqual(recent["cache_read_input_tokens"], 77)

    def test_openai_stream_maps_prompt_cache_hit_tokens(self):
        usage_event = {
            "id": "chatcmpl-test",
            "object": "chat.completion.chunk",
            "created": 1,
            "model": "test-model",
            "choices": [],
            "usage": {
                "completion_tokens": 45,
                "total_tokens": 168,
                "prompt_cache_hit_tokens": 77,
                "prompt_cache_miss_tokens": 46,
            },
        }
        upstream = SlowAfterTerminalResponse(
            [
                openai_stream_lines()[0],
                openai_stream_lines()[1],
                "data: " + json.dumps(usage_event, separators=(",", ":")),
                "",
                openai_stream_lines()[2],
                openai_stream_lines()[3],
            ]
        )
        response = proxy_response(
            upstream,
            sanitize_dsml=True,
            request_id="streamusagecachehit",
            upstream_url=upstream.url,
            started_at=time.perf_counter(),
            requested_stream=True,
            route_hint="chat/completions",
            tool_schemas={},
            retry_count=0,
            protocol="openai_chat_completions",
            request_payload={"model": "test-model", "stream": True, "messages": [{"role": "user", "content": "hello"}]},
            execution={},
        )

        body = collect_response_body(response).decode("utf-8")
        usage_events = openai_stream_usage_events(body)

        self.assertGreaterEqual(len(usage_events), 1)
        last_usage = usage_events[-1]["usage"]
        self.assertEqual(last_usage["prompt_tokens"], 123)
        self.assertEqual(last_usage["completion_tokens"], 45)
        self.assertEqual(last_usage["prompt_tokens_details"]["cached_tokens"], 77)
        self.assertEqual(last_usage["cache_read_input_tokens"], 77)
        self.assertEqual(last_usage["prompt_cache_hit_tokens"], 77)
        self.assertEqual(last_usage["prompt_cache_miss_tokens"], 46)

    def test_openai_stream_repairs_zero_completion_usage_when_output_exists(self):
        content_event = {
            "id": "chatcmpl-test",
            "object": "chat.completion.chunk",
            "created": 1,
            "model": "test-model",
            "choices": [
                {
                    "index": 0,
                    "delta": {"content": "visible reply"},
                    "finish_reason": None,
                }
            ],
            "usage": None,
        }
        usage_event = {
            "id": "chatcmpl-test",
            "object": "chat.completion.chunk",
            "created": 1,
            "model": "test-model",
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            "usage": {
                "prompt_tokens": 6552,
                "completion_tokens": 0,
                "total_tokens": 6552,
                "prompt_tokens_details": {"cached_tokens": 6500},
            },
        }
        upstream = SlowAfterTerminalResponse(
            [
                "data: " + json.dumps(content_event, separators=(",", ":")),
                "",
                "data: " + json.dumps(usage_event, separators=(",", ":")),
                "",
            ]
        )
        response = proxy_response(
            upstream,
            sanitize_dsml=True,
            request_id="streamzerooutputusage",
            upstream_url=upstream.url,
            started_at=time.perf_counter(),
            requested_stream=True,
            route_hint="chat/completions",
            tool_schemas={},
            retry_count=0,
            protocol="openai_chat_completions",
            request_payload={"model": "test-model", "stream": True, "messages": [{"role": "user", "content": "hello"}]},
            execution={},
        )

        body = collect_response_body(response).decode("utf-8")
        usage_events = openai_stream_usage_events(body)
        last_usage = usage_events[-1]["usage"]

        self.assertEqual(last_usage["prompt_tokens"], 6552)
        self.assertGreater(last_usage["completion_tokens"], 0)
        self.assertEqual(last_usage["total_tokens"], 6552 + last_usage["completion_tokens"])
        self.assertEqual(last_usage["cache_read_input_tokens"], 6500)
        recent = next(item for item in request_recorder.snapshot()["recent_requests"] if item["request_id"] == "streamzerooutputusage")
        self.assertGreater(recent["completion_tokens"], 0)
        self.assertEqual(recent["total_tokens"], 6552 + recent["completion_tokens"])

    def test_consume_openai_sse_events_does_not_wait_for_upstream_close_after_finish(self):
        upstream = SlowAfterTerminalResponse(openai_stream_lines())

        consumed = consume_openai_sse_events(upstream, {})

        self.assertEqual(len(consumed["response_events"]), 2)
        self.assertEqual(
            consumed["response_events"][-1]["choices"][0]["finish_reason"],
            "stop",
        )

    def test_consume_openai_sse_events_captures_stream_read_exception(self):
        upstream = ErrorAfterPartialStreamResponse(
            [": upstream-opened"],
            requests.ConnectionError("Read timed out."),
        )

        consumed = consume_openai_sse_events(upstream, {})

        self.assertEqual(consumed["response_events"], [])
        self.assertTrue(
            any(line.startswith("stream_read_exception:ConnectionError") for line in consumed["raw_error_lines"])
        )

    def test_anthropic_stream_sends_message_stop_after_openai_finish_reason(self):
        upstream = SlowAfterTerminalResponse(openai_stream_lines())
        request_payload = {"model": "test-model", "stream": True, "messages": [{"role": "user", "content": "hello"}]}
        response = handle_anthropic_stream_response(
            upstream_response=upstream,
            request_id="anthstream",
            upstream_url=upstream.url,
            started_at=time.perf_counter(),
            request_payload=request_payload,
            tool_schemas={},
            retry_count=0,
            observability_meta={"_upstream_openai_payload": request_payload},
        )

        body = collect_response_body(response).decode("utf-8")
        events = parse_sse_events(body)
        message_start = next(payload for name, payload in events if name == "message_start")
        message_delta = next(payload for name, payload in events if name == "message_delta")

        self.assertIn("event: message_start", body)
        self.assertIn("event: content_block_delta", body)
        self.assertIn('"stop_reason":"end_turn"', body)
        self.assertIn("event: message_stop", body)
        self.assertGreater(message_start["message"]["usage"]["input_tokens"], 0)
        self.assertGreater(message_delta["usage"]["output_tokens"], 0)
        self.assertTrue(upstream.closed_by_proxy)

    def test_anthropic_stream_does_not_emit_thinking_by_default(self):
        first = {
            "id": "chatcmpl-thinking",
            "object": "chat.completion.chunk",
            "created": 1,
            "model": "test-model",
            "choices": [{"index": 0, "delta": {"reasoning_content": "trace", "content": "ok"}, "finish_reason": None}],
        }
        terminal = {
            "id": "chatcmpl-thinking",
            "object": "chat.completion.chunk",
            "created": 1,
            "model": "test-model",
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        }
        upstream = SlowAfterTerminalResponse(
            [
                "data: " + json.dumps(first, separators=(",", ":")),
                "",
                "data: " + json.dumps(terminal, separators=(",", ":")),
                "",
            ]
        )
        request_payload = {"model": "test-model", "stream": True, "messages": [{"role": "user", "content": "hello"}]}

        response = handle_anthropic_stream_response(
            upstream_response=upstream,
            request_id="anthstream-nothinking",
            upstream_url=upstream.url,
            started_at=time.perf_counter(),
            request_payload=request_payload,
            tool_schemas={},
            retry_count=0,
            observability_meta={"_upstream_openai_payload": request_payload},
        )

        body = collect_response_body(response).decode("utf-8")

        self.assertIn('"text_delta"', body)
        self.assertNotIn('"thinking_delta"', body)
        self.assertNotIn('"type":"thinking"', body)
        self.assertTrue(upstream.closed_by_proxy)

    def test_anthropic_inbound_thinking_blocks_are_ignored_during_conversion(self):
        messages = [
            {
                "role": "assistant",
                "content": [
                    {"type": "thinking", "thinking": "internal trace", "signature": "sig"},
                    {"type": "text", "text": "done"},
                ],
            },
            {
                "role": "user",
                "content": [
                    {"type": "thinking", "thinking": "echoed trace", "signature": "sig"},
                    {"type": "text", "text": "next"},
                ],
            },
        ]

        converted = convert_anthropic_messages_to_openai(messages)

        self.assertEqual(
            converted,
            [
                {"role": "assistant", "content": "done"},
                {"role": "user", "content": "next"},
            ],
        )

    def test_anthropic_non_stream_does_not_emit_thinking_by_default(self):
        anthropic_body = convert_openai_response_to_anthropic(
            {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "ok",
                            "reasoning": "internal trace",
                        },
                        "finish_reason": "stop",
                    }
                ]
            },
            {},
            {"model": "test-model", "messages": [{"role": "user", "content": "hello"}]},
        )

        self.assertEqual(anthropic_body["content"], [{"type": "text", "text": "ok"}])

    def test_anthropic_non_stream_emits_thinking_when_explicitly_enabled(self):
        anthropic_body = convert_openai_response_to_anthropic(
            {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "ok",
                            "reasoning": "internal trace",
                        },
                        "finish_reason": "stop",
                    }
                ]
            },
            {},
            {
                "model": "test-model",
                "messages": [{"role": "user", "content": "hello"}],
                "thinking": {"type": "enabled", "budget_tokens": 1024},
            },
        )

        self.assertEqual(anthropic_body["content"][0], {"type": "text", "text": "ok"})
        self.assertEqual(anthropic_body["content"][1]["type"], "thinking")
        self.assertEqual(anthropic_body["content"][1]["thinking"], "internal trace")

    def test_gemini_stream_sends_terminal_chunk_after_openai_finish_reason(self):
        upstream = SlowAfterTerminalResponse(openai_stream_lines())
        response = handle_gemini_stream_response(
            upstream_response=upstream,
            request_id="gemstream",
            upstream_url=upstream.url,
            started_at=time.perf_counter(),
            tool_schemas={},
            retry_count=0,
            observability_meta={"_upstream_openai_payload": {"model": "test-model", "stream": True}},
        )

        body = collect_response_body(response).decode("utf-8")

        self.assertIn('"text":"ok"', body)
        self.assertIn('"finishReason":"STOP"', body)
        self.assertTrue(upstream.closed_by_proxy)

    def test_openai_stream_blank_success_returns_malformed_error_not_empty_token(self):
        upstream = FiniteStreamResponse([": upstream-comment", ""])
        response = proxy_response(
            upstream,
            sanitize_dsml=True,
            request_id="blankstream",
            upstream_url=upstream.url,
            started_at=time.perf_counter(),
            requested_stream=True,
            route_hint="chat/completions",
            tool_schemas={},
            retry_count=0,
            protocol="openai_chat_completions",
            request_payload={"model": "test-model", "stream": True},
            execution={"empty_sse_fallbacks": 2},
        )

        body = collect_response_body(response).decode("utf-8")

        self.assertIn("empty_sse_success", body)
        self.assertNotIn('"content":""', body)
        self.assertNotIn('"content": ""', body)
        self.assertTrue(upstream.closed_by_proxy)

    def test_finish_reason_without_content_is_not_meaningful_output(self):
        issue = inspect_success_payload(
            route_hint="chat/completions",
            content_type="application/json",
            response_body={
                "id": "chatcmpl-empty",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": None},
                        "finish_reason": "stop",
                    }
                ],
            },
        )

        self.assertIsNotNone(issue)
        self.assertEqual(issue["code"], "empty_chat_completion")

    def test_reasoning_only_completion_is_not_meaningful_output(self):
        issue = inspect_success_payload(
            route_hint="chat/completions",
            content_type="application/json",
            response_body={
                "id": "chatcmpl-reasoning-only",
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "reasoning": "I should call a tool next.",
                        },
                        "finish_reason": "stop",
                    }
                ],
            },
        )

        self.assertIsNotNone(issue)
        self.assertEqual(issue["code"], "empty_chat_completion")

    def test_stream_finish_reason_without_content_is_not_forwarded_as_success(self):
        terminal_only = {
            "id": "chatcmpl-empty",
            "object": "chat.completion.chunk",
            "created": 1,
            "model": "test-model",
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        }
        upstream = FiniteStreamResponse(["data: " + json.dumps(terminal_only, separators=(",", ":")), ""])
        response = proxy_response(
            upstream,
            sanitize_dsml=True,
            request_id="terminalempty",
            upstream_url=upstream.url,
            started_at=time.perf_counter(),
            requested_stream=True,
            route_hint="chat/completions",
            tool_schemas={},
            retry_count=0,
            protocol="openai_chat_completions",
            request_payload={"model": "test-model", "stream": True},
            execution={"empty_sse_fallbacks": 2},
        )

        body = collect_response_body(response).decode("utf-8")

        self.assertIn("empty_sse_success", body)
        self.assertIn("no usable output", body)
        self.assertNotIn('"finish_reason":"stop"', body)
        self.assertTrue(upstream.closed_by_proxy)

    def test_stream_reasoning_only_finish_is_not_forwarded_as_success(self):
        reasoning_only = {
            "id": "chatcmpl-reasoning-only",
            "object": "chat.completion.chunk",
            "created": 1,
            "model": "test-model",
            "choices": [
                {
                    "index": 0,
                    "delta": {"reasoning_content": "Let me call a tool next."},
                    "finish_reason": None,
                }
            ],
        }
        terminal_only = {
            "id": "chatcmpl-reasoning-only",
            "object": "chat.completion.chunk",
            "created": 1,
            "model": "test-model",
            "choices": [
                {
                    "index": 0,
                    "delta": {},
                    "finish_reason": "stop",
                    "matched_stop": 1,
                    "reasoning": "Let me call a tool next.",
                }
            ],
        }
        upstream = FiniteStreamResponse(
            [
                "data: " + json.dumps(reasoning_only, separators=(",", ":")),
                "",
                "data: " + json.dumps(terminal_only, separators=(",", ":")),
                "",
            ]
        )
        response = proxy_response(
            upstream,
            sanitize_dsml=True,
            request_id="reasoningonly",
            upstream_url=upstream.url,
            started_at=time.perf_counter(),
            requested_stream=True,
            route_hint="chat/completions",
            tool_schemas={},
            retry_count=0,
            protocol="openai_chat_completions",
            request_payload={"model": "test-model", "stream": True},
            execution={"empty_sse_fallbacks": 2},
        )

        body = collect_response_body(response).decode("utf-8")

        self.assertIn("empty_sse_success", body)
        self.assertIn("no usable output", body)
        self.assertNotIn('"finish_reason":"stop"', body)
        self.assertTrue(upstream.closed_by_proxy)

    def test_openai_stream_heartbeat_only_preflight_switches_route_quickly(self):
        upstream = FiniteStreamResponse([])
        fallback_upstream = FiniteStreamResponse(openai_stream_lines())
        request_payload = {"model": "test-model", "stream": True, "messages": [{"role": "user", "content": "hello"}]}

        def fake_iter_response_lines_with_heartbeat(response, heartbeat_seconds):
            if response is upstream:
                return iter([None, None, None])
            return iter(
                [
                    line.encode("utf-8") if isinstance(line, str) else line
                    for line in openai_stream_lines()
                ]
            )

        with mock.patch("local_proxy.server.STREAM_FIRST_EVENT_TIMEOUT_SECONDS", 0), \
            mock.patch(
                "local_proxy.server.iter_response_lines_with_heartbeat",
                side_effect=fake_iter_response_lines_with_heartbeat,
            ), \
            mock.patch(
                "local_proxy.server.execute_upstream_request",
                return_value={
                    "upstream_response": fallback_upstream,
                    "upstream_url": fallback_upstream.url,
                    "tool_schemas": {},
                    "retry_count": 1,
                    "attempts": [{"route_url": "https://fallback.example/v1/chat/completions"}],
                    "upstream_url_pool": [
                        "https://primary.example/v1/chat/completions",
                        "https://fallback.example/v1/chat/completions",
                    ],
                    "route_pool_size": 2,
                    "request_context": {},
                    "route_url": "https://fallback.example/v1/chat/completions",
                },
            ) as execute_mock:
            response = proxy_response(
                upstream,
                sanitize_dsml=True,
                request_id="heartbeatfallback",
                upstream_url=upstream.url,
                started_at=time.perf_counter(),
                requested_stream=True,
                route_hint="chat/completions",
                tool_schemas={},
                retry_count=0,
                protocol="openai_chat_completions",
                request_payload=request_payload,
                execution={
                    "empty_sse_fallbacks": 0,
                    "request_context": {},
                    "route_url": "https://primary.example/v1/chat/completions",
                    "upstream_url_pool": [
                        "https://primary.example/v1/chat/completions",
                        "https://fallback.example/v1/chat/completions",
                    ],
                    "route_pool_size": 2,
                },
            )

        body = collect_response_body(response).decode("utf-8")

        self.assertIn('"content":"ok"', body)
        self.assertIn("data: [DONE]\n\n", body)
        execute_mock.assert_called_once()
        self.assertTrue(upstream.closed_by_proxy)
        self.assertTrue(fallback_upstream.closed_by_proxy)

    def test_openai_connect_heartbeat_retries_terminal_404_before_emitting_error(self):
        initial_error = make_error_response(404, "404 page not found")
        fallback_upstream = FiniteStreamResponse(openai_stream_lines())
        request_payload = {"model": "test-model", "stream": True, "messages": [{"role": "user", "content": "hello"}]}

        class ReadyBackgroundExecution:
            def wait(self, timeout_seconds):
                return (
                    "result",
                    {
                        "upstream_response": initial_error,
                        "upstream_url": initial_error.url,
                        "tool_schemas": {},
                        "retry_count": 0,
                        "attempts": [{"route_url": "https://primary.example/v1/chat/completions", "reason": "route_not_found_404"}],
                        "upstream_url_pool": [
                            "https://primary.example/v1/chat/completions",
                            "https://fallback.example/v1/chat/completions",
                        ],
                        "route_pool_size": 2,
                        "request_context": {},
                        "route_url": "https://primary.example/v1/chat/completions",
                    },
                )

            def cancel(self):
                return None

        with mock.patch(
            "local_proxy.server.execute_upstream_request",
            return_value={
                "upstream_response": fallback_upstream,
                "upstream_url": fallback_upstream.url,
                "tool_schemas": {},
                "retry_count": 1,
                "attempts": [{"route_url": "https://fallback.example/v1/chat/completions"}],
                "upstream_url_pool": [
                    "https://primary.example/v1/chat/completions",
                    "https://fallback.example/v1/chat/completions",
                ],
                "route_pool_size": 2,
                "request_context": {},
                "route_url": "https://fallback.example/v1/chat/completions",
            },
        ) as execute_mock:
            response = openai_stream_response_with_connect_heartbeat(
                background_execution=ReadyBackgroundExecution(),
                request_id="heartbeat404fallback",
                started_at=time.perf_counter(),
                sanitize_dsml=True,
                route_hint="chat/completions",
                request_payload=request_payload,
            )
            body = collect_response_body(response).decode("utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertIn('"content":"ok"', body)
        self.assertIn("data: [DONE]\n\n", body)
        self.assertNotIn("404 page not found", body)
        execute_mock.assert_called_once()
        self.assertTrue(fallback_upstream.closed_by_proxy)

    def test_openai_non_stream_returns_proxy_502_instead_of_upstream_404(self):
        upstream = make_error_response(404, "404 page not found")
        response = proxy_response(
            upstream,
            sanitize_dsml=True,
            request_id="json404",
            upstream_url=upstream.url,
            started_at=time.perf_counter(),
            requested_stream=False,
            route_hint="chat/completions",
            tool_schemas={},
            retry_count=0,
            protocol="openai_chat_completions",
            request_payload={"model": "test-model", "messages": [{"role": "user", "content": "hello"}]},
            execution={"route_url": upstream.url, "upstream_url_pool": [upstream.url], "route_pool_size": 1},
        )

        payload = json.loads(collect_response_body(response).decode("utf-8"))

        self.assertEqual(response.status_code, 502)
        self.assertEqual(payload["error"]["upstream_status"], 404)
        self.assertEqual(payload["error"]["message"], "Upstream returned an error.")
        self.assertIn("404 page not found", payload["error"]["upstream_preview"])

    def test_openai_connect_heartbeat_emits_sse_error_packets_when_all_routes_fail(self):
        initial_error = make_error_response(404, "404 page not found")

        class ReadyBackgroundExecution:
            def wait(self, timeout_seconds):
                return (
                    "result",
                    {
                        "upstream_response": initial_error,
                        "upstream_url": initial_error.url,
                        "tool_schemas": {},
                        "retry_count": 0,
                        "attempts": [{"route_url": initial_error.url, "reason": "route_not_found_404"}],
                        "upstream_url_pool": [initial_error.url],
                        "route_pool_size": 1,
                        "request_context": {},
                        "route_url": initial_error.url,
                    },
                )

            def cancel(self):
                return None

        response = openai_stream_response_with_connect_heartbeat(
            background_execution=ReadyBackgroundExecution(),
            request_id="heartbeat404terminal",
            started_at=time.perf_counter(),
            sanitize_dsml=True,
            route_hint="chat/completions",
            request_payload={"model": "test-model", "stream": True, "messages": [{"role": "user", "content": "hello"}]},
        )
        body = collect_response_body(response).decode("utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertIn('data: {"error"', body)
        self.assertIn('"upstream_status": 404', body)
        self.assertIn("data: [DONE]\n\n", body)
        self.assertNotIn('\n{"error":', body)

    def test_openai_connect_heartbeat_retries_request_exception_before_emitting_error(self):
        fallback_upstream = FiniteStreamResponse(openai_stream_lines())
        request_payload = {"model": "test-model", "stream": True, "messages": [{"role": "user", "content": "hello"}]}

        class ReadyBackgroundExecution:
            def wait(self, timeout_seconds):
                return (
                    "result",
                    {
                        "upstream_response": None,
                        "upstream_url": "https://primary.example/v1/chat/completions",
                        "tool_schemas": {},
                        "retry_count": 0,
                        "attempts": [{"route_url": "https://primary.example/v1/chat/completions", "error": "Read timed out"}],
                        "upstream_url_pool": [
                            "https://primary.example/v1/chat/completions",
                            "https://fallback.example/v1/chat/completions",
                        ],
                        "route_pool_size": 2,
                        "request_context": {},
                        "route_url": "https://primary.example/v1/chat/completions",
                        "request_exception": requests.exceptions.ReadTimeout("Read timed out. (read timeout=10)"),
                    },
                )

            def cancel(self):
                return None

        with mock.patch(
            "local_proxy.server.execute_upstream_request",
            return_value={
                "upstream_response": fallback_upstream,
                "upstream_url": fallback_upstream.url,
                "tool_schemas": {},
                "retry_count": 1,
                "attempts": [{"route_url": "https://fallback.example/v1/chat/completions"}],
                "upstream_url_pool": [
                    "https://primary.example/v1/chat/completions",
                    "https://fallback.example/v1/chat/completions",
                ],
                "route_pool_size": 2,
                "request_context": {},
                "route_url": "https://fallback.example/v1/chat/completions",
            },
        ) as execute_mock:
            response = openai_stream_response_with_connect_heartbeat(
                background_execution=ReadyBackgroundExecution(),
                request_id="heartbeat-exception-fallback",
                started_at=time.perf_counter(),
                sanitize_dsml=True,
                route_hint="chat/completions",
                request_payload=request_payload,
            )
            body = collect_response_body(response).decode("utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertIn('"content":"ok"', body)
        self.assertIn("data: [DONE]\n\n", body)
        self.assertNotIn('data: {"error"', body)
        execute_mock.assert_called_once()
        self.assertTrue(fallback_upstream.closed_by_proxy)

    def test_openai_connect_heartbeat_reconstructs_route_pool_for_request_exception_fallback(self):
        fallback_upstream = FiniteStreamResponse(openai_stream_lines())
        request_payload = {"model": "test-model", "stream": True, "messages": [{"role": "user", "content": "hello"}]}
        seen = {}

        class ReadyBackgroundExecution:
            def wait(self, timeout_seconds):
                return (
                    "result",
                    {
                        "upstream_response": None,
                        "upstream_url": "https://primary.example/v1/chat/completions",
                        "tool_schemas": {},
                        "retry_count": 0,
                        "attempts": [{"route_url": "https://primary.example/v1/chat/completions", "error": "Read timed out"}],
                        "request_context": {},
                        "route_url": "https://primary.example/v1/chat/completions",
                        "request_exception": requests.exceptions.ReadTimeout("Read timed out. (read timeout=10)"),
                    },
                )

            def cancel(self):
                return None

        with mock.patch(
            "local_proxy.server.build_candidate_upstream_urls_for_request",
            return_value=[
                "https://primary.example/v1/chat/completions",
                "https://fallback.example/v1/chat/completions",
            ],
        ), mock.patch(
            "local_proxy.server.execute_upstream_request",
            side_effect=lambda *args, **kwargs: (
                seen.setdefault("kwargs", dict(kwargs)),
                {
                    "upstream_response": fallback_upstream,
                    "upstream_url": fallback_upstream.url,
                    "tool_schemas": {},
                    "retry_count": 1,
                    "attempts": [{"route_url": "https://fallback.example/v1/chat/completions"}],
                    "upstream_url_pool": [
                        "https://primary.example/v1/chat/completions",
                        "https://fallback.example/v1/chat/completions",
                    ],
                    "route_pool_size": 2,
                    "request_context": {},
                    "route_url": "https://fallback.example/v1/chat/completions",
                },
            )[1],
        ) as execute_mock:
            response = openai_stream_response_with_connect_heartbeat(
                background_execution=ReadyBackgroundExecution(),
                request_id="heartbeat-exception-reconstruct-fallback",
                started_at=time.perf_counter(),
                sanitize_dsml=True,
                route_hint="chat/completions",
                request_payload=request_payload,
            )
            body = collect_response_body(response).decode("utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertIn('"content":"ok"', body)
        self.assertIn("data: [DONE]\n\n", body)
        self.assertNotIn('data: {"error"', body)
        execute_mock.assert_called_once()
        self.assertEqual(
            seen["kwargs"]["initial_blocked_urls"],
            {"https://primary.example/v1/chat/completions"},
        )
        self.assertTrue(fallback_upstream.closed_by_proxy)

    def test_background_execution_wraps_exception_with_route_context_for_stream_failover(self):
        request_payload = {"model": "test-model", "stream": True, "messages": [{"role": "user", "content": "hello"}]}

        with app.test_request_context(
            "/v1/chat/completions",
            method="POST",
            json=request_payload,
        ), mock.patch(
            "local_proxy.server.execute_upstream_request",
            side_effect=RuntimeError("boom"),
        ), mock.patch(
            "local_proxy.server.build_candidate_route_targets_for_request",
            return_value=[
                (
                    "https://primary.example/v1#__route=one",
                    "https://primary.example/v1/chat/completions#__route=one",
                ),
                (
                    "https://fallback.example/v1#__route=two",
                    "https://fallback.example/v1/chat/completions#__route=two",
                ),
            ],
        ):
            background_execution = start_background_upstream_execution(
                "chat/completions",
                request_payload,
                "background-error-wrap",
            )
            ready, execution, error = wait_background_upstream_execution(background_execution, 1)

        self.assertTrue(ready)
        self.assertIsNone(error)
        self.assertIsInstance(execution, dict)
        self.assertEqual(str(execution.get("request_exception")), "boom")
        self.assertEqual(
            execution.get("route_url"),
            "https://primary.example/v1/chat/completions#__route=one",
        )
        self.assertEqual(
            execution.get("upstream_url"),
            "https://primary.example/v1/chat/completions",
        )
        self.assertEqual(
            execution.get("upstream_url_pool"),
            [
                "https://primary.example/v1/chat/completions#__route=one",
                "https://fallback.example/v1/chat/completions#__route=two",
            ],
        )
        self.assertEqual(execution.get("route_pool_size"), 2)
        self.assertEqual(
            execution.get("attempts"),
            [
                {
                    "attempt": 1,
                    "route_url": "https://primary.example/v1/chat/completions#__route=one",
                    "upstream_url": "https://primary.example/v1/chat/completions",
                    "kind": "exception",
                    "error": "boom",
                }
            ],
        )

    def test_background_execution_prefers_last_selected_route_when_execute_upstream_request_raises(self):
        request_payload = {"model": "test-model", "stream": True, "messages": [{"role": "user", "content": "hello"}]}

        def raise_after_route_selection(*args, **kwargs):
            exc = RuntimeError("boom")
            setattr(exc, "_proxy_route_selection_debug", {
                "request_id": "background-debug-selected",
                "selected_url": "https://fallback.example/v1/chat/completions#__route=two",
                "ordered_urls": [
                    "https://fallback.example/v1/chat/completions#__route=two",
                    "https://primary.example/v1/chat/completions#__route=one",
                ],
            })
            raise exc

        with app.test_request_context(
            "/v1/chat/completions",
            method="POST",
            json=request_payload,
        ), mock.patch(
            "local_proxy.server.execute_upstream_request",
            side_effect=raise_after_route_selection,
        ), mock.patch(
            "local_proxy.server.build_candidate_route_targets_for_request",
            return_value=[
                (
                    "https://primary.example/v1/chat/completions#__route=one",
                    "https://primary.example/v1/chat/completions#__route=one",
                ),
                (
                    "https://fallback.example/v1/chat/completions#__route=two",
                    "https://fallback.example/v1/chat/completions#__route=two",
                ),
            ],
        ):
            background_execution = start_background_upstream_execution(
                "chat/completions",
                request_payload,
                "background-debug-selected",
            )
            ready, execution, error = wait_background_upstream_execution(background_execution, 1)

        self.assertTrue(ready)
        self.assertIsNone(error)
        self.assertIsInstance(execution, dict)
        self.assertEqual(
            execution.get("route_url"),
            "https://fallback.example/v1/chat/completions#__route=two",
        )
        self.assertEqual(
            execution.get("upstream_url"),
            "https://fallback.example/v1/chat/completions",
        )
        self.assertEqual(execution.get("selected_route_index"), 1)
        self.assertEqual(
            execution.get("attempts"),
            [
                {
                    "attempt": 1,
                    "route_url": "https://fallback.example/v1/chat/completions#__route=two",
                    "upstream_url": "https://fallback.example/v1/chat/completions",
                    "kind": "exception",
                    "error": "boom",
                }
            ],
        )

    def test_background_execution_uses_generic_upstream_candidates_when_model_filtered_routes_are_empty(self):
        request_payload = {"model": "test-model", "stream": True, "messages": [{"role": "user", "content": "hello"}]}

        with app.test_request_context(
            "/v1/chat/completions",
            method="POST",
            json=request_payload,
        ), mock.patch(
            "local_proxy.server.execute_upstream_request",
            side_effect=RuntimeError("boom"),
        ), mock.patch(
            "local_proxy.server.build_candidate_route_targets_for_request",
            return_value=[],
        ), mock.patch(
            "local_proxy.server.build_upstream_url_candidates",
            return_value=[
                "https://primary.example/v1/chat/completions#__route=one",
                "https://fallback.example/v1/chat/completions#__route=two",
            ],
        ):
            background_execution = start_background_upstream_execution(
                "chat/completions",
                request_payload,
                "background-error-generic-fallback",
            )
            ready, execution, error = wait_background_upstream_execution(background_execution, 1)

        self.assertTrue(ready)
        self.assertIsNone(error)
        self.assertIsInstance(execution, dict)
        self.assertEqual(
            execution.get("route_url"),
            "https://primary.example/v1/chat/completions#__route=one",
        )
        self.assertEqual(
            execution.get("upstream_url"),
            "https://primary.example/v1/chat/completions",
        )
        self.assertEqual(
            execution.get("upstream_url_pool"),
            [
                "https://primary.example/v1/chat/completions#__route=one",
                "https://fallback.example/v1/chat/completions#__route=two",
            ],
        )
        self.assertEqual(
            execution.get("attempts"),
            [
                {
                    "attempt": 1,
                    "route_url": "https://primary.example/v1/chat/completions#__route=one",
                    "upstream_url": "https://primary.example/v1/chat/completions",
                    "kind": "exception",
                    "error": "boom",
                }
            ],
        )

    def test_execute_upstream_request_clears_inflight_cache_on_exception(self):
        with mock.patch("local_proxy.server.UPSTREAM_URL_POOL", ["https://primary.example/v1#__route=one"]), \
             mock.patch("local_proxy.server.build_route_policy", return_value={}), \
             mock.patch("local_proxy.server.resolve_upstream_text_subpath", return_value="chat/completions"), \
             mock.patch(
                 "local_proxy.server.router_build_upstream_url_candidates",
                 return_value=["https://primary.example/v1/chat/completions#__route=one"],
             ), \
             mock.patch(
                 "local_proxy.server.build_upstream_json_payload",
                 return_value=(
                     {"model": "test-model", "messages": [{"role": "user", "content": "hello"}], "stream": True},
                     True,
                     0,
                     ["test-model"],
                 ),
             ), \
             mock.patch("local_proxy.server.build_session_affinity_key", return_value="session-1"), \
             mock.patch(
                 "local_proxy.server.apply_route_policy_to_payload",
                 return_value=(
                     {"model": "test-model", "messages": [{"role": "user", "content": "hello"}], "stream": True},
                     0,
                     {},
                 ),
             ), \
             mock.patch("local_proxy.server.check_payload_against_model_capability", return_value=None), \
             mock.patch("local_proxy.server.choose_api_key_for_url", return_value={}), \
             mock.patch("local_proxy.server.request_upstream_with_retries", side_effect=RuntimeError("boom")):
            with self.assertRaisesRegex(RuntimeError, "boom"):
                execute_upstream_request(
                    "chat/completions",
                    {"model": "test-model", "messages": [{"role": "user", "content": "hello"}], "stream": True},
                    "raise-once",
                    request_context={},
                )

        self.assertEqual(
            len([key for key in getattr(__import__("local_proxy.server", fromlist=["inflight_request_cache"]), "inflight_request_cache").keys() if key]),
            0,
        )

if __name__ == "__main__":
    unittest.main()
