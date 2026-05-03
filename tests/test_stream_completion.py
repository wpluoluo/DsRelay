import json
import time
import unittest

import requests

from local_proxy.http.validation import inspect_success_payload
from local_proxy.server import (
    consume_openai_sse_events,
    handle_anthropic_stream_response,
    handle_gemini_stream_response,
    proxy_response,
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


class StreamCompletionTests(unittest.TestCase):
    def test_openai_stream_stops_after_finish_reason_and_adds_done(self):
        upstream = SlowAfterTerminalResponse(openai_stream_lines())
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
            request_payload={"model": "test-model", "stream": True},
            execution={},
        )

        body = collect_response_body(response).decode("utf-8")

        self.assertIn('"content":"ok"', body)
        self.assertIn('"finish_reason":"stop"', body)
        self.assertIn("data: [DONE]\n\n", body)
        self.assertTrue(upstream.closed_by_proxy)

    def test_consume_openai_sse_events_does_not_wait_for_upstream_close_after_finish(self):
        upstream = SlowAfterTerminalResponse(openai_stream_lines())

        consumed = consume_openai_sse_events(upstream, {})

        self.assertEqual(len(consumed["response_events"]), 2)
        self.assertEqual(
            consumed["response_events"][-1]["choices"][0]["finish_reason"],
            "stop",
        )

    def test_anthropic_stream_sends_message_stop_after_openai_finish_reason(self):
        upstream = SlowAfterTerminalResponse(openai_stream_lines())
        response = handle_anthropic_stream_response(
            upstream_response=upstream,
            request_id="anthstream",
            upstream_url=upstream.url,
            started_at=time.perf_counter(),
            request_payload={"model": "test-model", "stream": True},
            tool_schemas={},
            retry_count=0,
            observability_meta={"_upstream_openai_payload": {"model": "test-model", "stream": True}},
        )

        body = collect_response_body(response).decode("utf-8")

        self.assertIn("event: message_start", body)
        self.assertIn("event: content_block_delta", body)
        self.assertIn('"stop_reason":"end_turn"', body)
        self.assertIn("event: message_stop", body)
        self.assertTrue(upstream.closed_by_proxy)

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


if __name__ == "__main__":
    unittest.main()
