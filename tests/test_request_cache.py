import unittest

from local_proxy.runtime.request_cache import (
    build_cache_key,
    build_cached_execution,
    build_coalescing_key,
    is_cache_lookup_eligible_request,
    is_cache_storable_response,
    is_cacheable_request,
    response_tool_calls_are_read_only,
)
from local_proxy.server import build_request_observability_meta, save_request_cache_entry
import local_proxy.server as server


class RequestCacheTests(unittest.TestCase):
    def test_cache_key_ignores_stream_transport_flags(self):
        base_payload = {
            "model": "demo-model",
            "messages": [{"role": "user", "content": "hello"}],
        }
        route_policy = {"prompt_cache_mode": "exact"}

        non_stream_key = build_cache_key(
            protocol="openai_chat_completions",
            path="chat/completions",
            payload={**base_payload, "stream": False},
            route_policy=route_policy,
        )
        stream_key = build_cache_key(
            protocol="openai_chat_completions",
            path="chat/completions",
            payload={
                **base_payload,
                "stream": True,
                "stream_options": {"include_usage": True},
            },
            route_policy=route_policy,
        )

        self.assertEqual(non_stream_key, stream_key)

    def test_cache_key_ignores_upstream_prompt_cache_hint_fields(self):
        base_payload = {
            "model": "demo-model",
            "messages": [{"role": "user", "content": "hello"}],
        }
        route_policy = {"prompt_cache_mode": "exact"}

        plain_key = build_cache_key(
            protocol="openai_chat_completions",
            path="chat/completions",
            payload=base_payload,
            route_policy=route_policy,
        )
        hinted_key = build_cache_key(
            protocol="openai_chat_completions",
            path="chat/completions",
            payload={
                **base_payload,
                "prompt_cache_key": "session-a",
                "prompt_cache_retention": "24h",
            },
            route_policy=route_policy,
        )

        self.assertEqual(plain_key, hinted_key)

    def test_cache_key_ignores_non_semantic_request_metadata(self):
        base_payload = {
            "model": "demo-model",
            "messages": [{"role": "user", "content": "hello"}],
            "temperature": 0.2,
        }
        route_policy = {"prompt_cache_mode": "exact"}

        plain_key = build_cache_key(
            protocol="openai_chat_completions",
            path="chat/completions",
            payload=base_payload,
            route_policy=route_policy,
        )
        metadata_key = build_cache_key(
            protocol="openai_chat_completions",
            path="chat/completions",
            payload={
                **base_payload,
                "metadata": {"request_id": "abc"},
                "user": "user-a",
                "request_id": "req-1",
                "trace_id": "trace-1",
                "session_id": "session-1",
                "conversation_id": "conversation-1",
            },
            route_policy=route_policy,
        )

        self.assertEqual(plain_key, metadata_key)

    def test_cache_key_is_stable_after_openai_tool_normalization(self):
        from local_proxy.compat.tools import normalize_openai_request_payload

        payload_a = {
            "model": "demo-model",
            "messages": [{"role": "user", "content": "hello"}],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "Write",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "path": {"type": "string"},
                                "content": {"type": "string"},
                            },
                            "required": ["content", "path"],
                        },
                    },
                },
                {
                    "type": "function",
                    "function": {
                        "name": "Read",
                        "parameters": {
                            "required": ["path"],
                            "properties": {"path": {"type": "string"}},
                            "type": "object",
                        },
                    },
                },
            ],
        }
        payload_b = {**payload_a, "tools": list(reversed(payload_a["tools"]))}
        normalized_a, _ = normalize_openai_request_payload(payload_a)
        normalized_b, _ = normalize_openai_request_payload(payload_b)

        self.assertEqual(
            build_cache_key(
                protocol="openai_chat_completions",
                path="chat/completions",
                payload=normalized_a,
                route_policy={"prompt_cache_mode": "exact"},
            ),
            build_cache_key(
                protocol="openai_chat_completions",
                path="chat/completions",
                payload=normalized_b,
                route_policy={"prompt_cache_mode": "exact"},
            ),
        )

    def test_cache_key_stabilizes_tools_without_full_request_normalization(self):
        payload_a = {
            "model": "demo-model",
            "messages": [{"role": "user", "content": "hello"}],
            "tools": [
                {
                    "name": "Search",
                    "description": "search files",
                    "input_schema": {
                        "required": ["query", "path"],
                        "properties": {
                            "query": {"type": "string"},
                            "path": {"type": "string"},
                        },
                        "type": "object",
                    },
                },
                {
                    "type": "function",
                    "function": {
                        "name": "Read",
                        "parameters": {
                            "properties": {"file_path": {"type": "string"}},
                            "required": ["file_path"],
                            "type": "object",
                        },
                    },
                },
            ],
            "tool_choice": {"type": "tool", "name": "Read"},
        }
        payload_b = {
            **payload_a,
            "tools": list(reversed(payload_a["tools"])),
            "tool_choice": {"name": "Read"},
        }

        self.assertEqual(
            build_cache_key(
                protocol="openai_chat_completions",
                path="chat/completions",
                payload=payload_a,
                route_policy={"prompt_cache_mode": "exact"},
            ),
            build_cache_key(
                protocol="openai_chat_completions",
                path="chat/completions",
                payload=payload_b,
                route_policy={"prompt_cache_mode": "exact"},
            ),
        )

    def test_stream_request_can_use_prompt_cache_when_payload_supported(self):
        payload = {
            "model": "demo-model",
            "messages": [{"role": "user", "content": "hello"}],
            "stream": True,
        }

        self.assertTrue(
            is_cacheable_request(
                request_payload=payload,
                route_policy={"prompt_cache_mode": "exact"},
                stream=True,
            )
        )

    def test_tool_request_lookup_can_cache_plain_text_response(self):
        payload = {
            "model": "demo-model",
            "messages": [{"role": "user", "content": "hello"}],
            "tools": [
                {"type": "function", "function": {"name": "ToolSearch", "parameters": {}}},
            ],
        }
        response_body = {
            "choices": [{"message": {"content": "ok"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 1, "total_tokens": 11},
        }
        route_policy = {"prompt_cache_mode": "exact"}

        self.assertTrue(
            is_cache_lookup_eligible_request(
                request_payload=payload,
                route_policy=route_policy,
                stream=True,
            )
        )
        self.assertTrue(
            is_cache_storable_response(
                request_payload=payload,
                route_policy=route_policy,
                response_body=response_body,
            )
        )

    def test_tool_call_response_is_not_stored(self):
        payload = {
            "model": "demo-model",
            "messages": [{"role": "user", "content": "hello"}],
            "tools": [
                {"type": "function", "function": {"name": "Write", "parameters": {}}},
            ],
        }
        response_body = {
            "choices": [
                {
                    "message": {
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "type": "function",
                                "function": {"name": "Write", "arguments": "{\"path\":\"a.txt\",\"content\":\"x\"}"},
                            }
                        ]
                    }
                }
            ]
        }

        self.assertFalse(
            is_cache_storable_response(
                request_payload=payload,
                route_policy={"prompt_cache_mode": "exact"},
                response_body=response_body,
            )
        )

    def test_read_only_tool_call_response_is_storable(self):
        payload = {
            "model": "demo-model",
            "messages": [{"role": "user", "content": "hello"}],
            "tools": [
                {"type": "function", "function": {"name": "Read", "parameters": {}}},
            ],
        }
        response_body = {
            "choices": [
                {
                    "message": {
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "type": "function",
                                "function": {"name": "Read", "arguments": "{\"file_path\":\"a.txt\"}"},
                            }
                        ]
                    },
                    "finish_reason": "tool_calls",
                }
            ]
        }

        self.assertTrue(response_tool_calls_are_read_only(response_body))
        self.assertTrue(
            is_cache_storable_response(
                request_payload=payload,
                route_policy={"prompt_cache_mode": "exact"},
                response_body=response_body,
            )
        )

    def test_reasoning_only_openai_response_is_not_storable(self):
        payload = {
            "model": "demo-model",
            "messages": [{"role": "user", "content": "hello"}],
        }
        response_body = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "",
                        "reasoning": "internal only",
                    },
                    "finish_reason": "length",
                }
            ],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 160,
                "completion_tokens_details": {"reasoning_tokens": 160},
                "total_tokens": 170,
            },
        }

        self.assertFalse(
            is_cache_storable_response(
                request_payload=payload,
                route_policy={"prompt_cache_mode": "exact"},
                response_body=response_body,
                protocol="openai_chat_completions",
            )
        )

    def test_gemini_text_response_is_storable(self):
        payload = {
            "model": "demo-model",
            "messages": [{"role": "user", "content": "hello"}],
        }
        response_body = {
            "candidates": [
                {
                    "content": {
                        "role": "model",
                        "parts": [{"text": "ok"}],
                    },
                    "finishReason": "STOP",
                }
            ],
            "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 1, "totalTokenCount": 11},
        }

        self.assertTrue(
            is_cache_storable_response(
                request_payload=payload,
                route_policy={"prompt_cache_mode": "exact"},
                response_body=response_body,
                protocol="gemini_generate_content",
            )
        )

    def test_anthropic_text_response_is_storable(self):
        payload = {
            "model": "demo-model",
            "messages": [{"role": "user", "content": "hello"}],
        }
        response_body = {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "text", "text": "ok"}],
            "stop_reason": "end_turn",
        }

        self.assertTrue(
            is_cache_storable_response(
                request_payload=payload,
                route_policy={"prompt_cache_mode": "exact"},
                response_body=response_body,
                protocol="anthropic_messages",
            )
        )

    def test_openai_responses_text_response_is_storable(self):
        payload = {
            "model": "demo-model",
            "messages": [{"role": "user", "content": "hello"}],
        }
        response_body = {
            "id": "resp_1",
            "object": "response",
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "ok"}],
                }
            ],
        }

        self.assertTrue(
            is_cache_storable_response(
                request_payload=payload,
                route_policy={"prompt_cache_mode": "exact"},
                response_body=response_body,
                protocol="openai_responses",
            )
        )

    def test_save_request_cache_uses_execution_upstream_payload_key(self):
        class FakeStorage:
            def __init__(self):
                self.saved = None

            def save_request_cache(self, payload):
                self.saved = payload

        fake_storage = FakeStorage()
        original_storage = server.storage
        try:
            server.storage = fake_storage
            upstream_payload = {
                "model": "upstream-model",
                "messages": [{"role": "user", "content": "hello"}],
                "reasoning_effort": "medium",
                "prompt_cache_key": "pcache:v1:test",
            }
            cache_key = build_cache_key(
                protocol="openai_chat_completions",
                path="chat/completions",
                payload=upstream_payload,
                route_policy={"prompt_cache_mode": "exact"},
            )
            save_request_cache_entry(
                execution={
                    "cache_key": cache_key,
                    "upstream_payload": upstream_payload,
                    "route_policy": {"prompt_cache_mode": "exact"},
                    "route_url": "https://good.example/v1/chat/completions#__route=good",
                },
                protocol="openai_chat_completions",
                path="chat/completions",
                request_payload={
                    "model": "logical-model",
                    "messages": [{"role": "user", "content": "hello"}],
                },
                response_body={"choices": [{"message": {"content": "ok"}}]},
                upstream_url="https://good.example/v1/chat/completions",
            )
        finally:
            server.storage = original_storage

        self.assertIsNotNone(fake_storage.saved)
        self.assertEqual(fake_storage.saved["cache_key"], cache_key)
        self.assertEqual(fake_storage.saved["request_payload"]["model"], "upstream-model")
        self.assertEqual(fake_storage.saved["request_fingerprint"], cache_key)

    def test_save_request_cache_prefers_base_cache_payload_over_resume_payload(self):
        class FakeStorage:
            def __init__(self):
                self.saved = None

            def save_request_cache(self, payload):
                self.saved = payload

        fake_storage = FakeStorage()
        original_storage = server.storage
        base_payload = {
            "model": "demo-model",
            "messages": [{"role": "user", "content": "hello"}],
        }
        resume_payload = {
            **base_payload,
            "messages": [
                {"role": "system", "content": "上一段续接文本"},
                {"role": "user", "content": "hello"},
            ],
        }
        cache_key = build_cache_key(
            protocol="openai_chat_completions",
            path="chat/completions",
            payload=base_payload,
            route_policy={"prompt_cache_mode": "exact"},
        )
        try:
            server.storage = fake_storage
            save_request_cache_entry(
                execution={
                    "cache_key": cache_key,
                    "cache_payload": base_payload,
                    "upstream_payload": resume_payload,
                    "route_policy": {"prompt_cache_mode": "exact"},
                },
                protocol="openai_chat_completions",
                path="chat/completions",
                request_payload=resume_payload,
                response_body={"choices": [{"message": {"content": "ok"}}]},
                upstream_url="https://good.example/v1/chat/completions",
            )
        finally:
            server.storage = original_storage

        self.assertIsNotNone(fake_storage.saved)
        self.assertEqual(fake_storage.saved["cache_key"], cache_key)
        self.assertEqual(fake_storage.saved["request_payload"], base_payload)
        self.assertNotIn("上一段续接文本", str(fake_storage.saved["request_payload"]))

    def test_coalescing_key_matches_exact_payload_except_transport_flags(self):
        base_payload = {
            "model": "demo-model",
            "messages": [{"role": "user", "content": "hello"}],
            "temperature": 0.2,
        }

        first_key = build_coalescing_key(
            protocol="anthropic_messages",
            path="chat/completions",
            payload={**base_payload, "stream": True},
        )
        second_key = build_coalescing_key(
            protocol="anthropic_messages",
            path="chat/completions",
            payload={**base_payload, "stream": False, "stream_options": {"include_usage": True}},
        )

        self.assertEqual(first_key, second_key)

    def test_cached_execution_preserves_upstream_path_metadata_for_observability(self):
        execution = build_cached_execution(
            cached_payload={
                "response_body": {"id": "resp_1", "model": "demo-model"},
                "created_at": 1.0,
                "source": "sqlite",
                "upstream_url": "https://good.example/v1/chat/completions",
                "route_url": "https://good.example/v1/chat/completions#__route=good",
                "pool_name": "good",
                "key_index": 1,
                "model_name": "demo-model",
                "path": "chat/completions",
            },
            request_payload={
                "model": "demo-model",
                "messages": [{"role": "user", "content": "hello"}],
            },
            request_repairs=0,
            model_candidates=["demo-model"],
            route_policy={"prompt_cache_mode": "exact"},
            cache_key="cache-key",
        )

        self.assertEqual(execution["upstream_url"], "https://good.example/v1/chat/completions")
        self.assertEqual(execution["route_url"], "https://good.example/v1/chat/completions#__route=good")
        self.assertEqual(execution["upstream_subpath"], "chat/completions")
        self.assertEqual(execution["upstream_url_pool"], ["https://good.example/v1/chat/completions#__route=good"])
        self.assertEqual(execution["route_pool_size"], 1)
        self.assertEqual(execution["attempt_route_count"], 1)

    def test_execute_upstream_request_uses_downstream_protocol_for_cached_gemini_response(self):
        payload = {
            "model": "demo-model",
            "messages": [{"role": "user", "content": "hello"}],
        }
        route_policy = {"prompt_cache_mode": "exact"}
        cache_key = build_cache_key(
            protocol="gemini_generate_content",
            path="chat/completions",
            payload=payload,
            route_policy=route_policy,
        )

        class FakeStorage:
            def load_request_cache(self, requested_key):
                self.requested_key = requested_key
                return {
                    "response_body": {
                        "candidates": [
                            {
                                "content": {
                                    "role": "model",
                                    "parts": [{"text": "ok"}],
                                },
                                "finishReason": "STOP",
                            }
                        ],
                    },
                    "created_at": 1.0,
                    "source": "mysql",
                    "upstream_url": "https://good.example/v1/chat/completions",
                    "route_url": "https://good.example/v1/chat/completions#__route=good",
                    "pool_name": "good",
                    "key_index": 1,
                    "model_name": "demo-model",
                    "path": "chat/completions",
                }

        fake_storage = FakeStorage()
        original_storage = server.storage
        with server.app.test_request_context("/v1beta/models/demo:generateContent", method="POST"):
            try:
                server.storage = fake_storage
                with (
                    unittest.mock.patch.object(
                        server,
                        "build_candidate_route_targets_for_request",
                        return_value=[
                            (
                                "https://good.example/v1#__route=good",
                                "https://good.example/v1/chat/completions#__route=good",
                            )
                        ],
                    ),
                    unittest.mock.patch.object(server, "build_route_policy", return_value=route_policy),
                    unittest.mock.patch.object(server, "resolve_upstream_text_subpath", return_value="chat/completions"),
                    unittest.mock.patch.object(
                        server,
                        "build_upstream_json_payload",
                        return_value=(payload, False, 0, ["demo-model"]),
                    ),
                    unittest.mock.patch.object(
                        server,
                        "apply_route_policy_to_payload",
                        return_value=(payload, 0, {}),
                    ),
                    unittest.mock.patch.object(server, "check_payload_against_model_capability", return_value=None),
                    unittest.mock.patch.object(
                        server,
                        "request_upstream_with_retries",
                        side_effect=AssertionError("cache hit should not request upstream"),
                    ),
                ):
                    execution = server.execute_upstream_request(
                        "chat/completions",
                        payload,
                        "req-gemini-cache",
                        cache_protocol="gemini_generate_content",
                    )
            finally:
                server.storage = original_storage

        self.assertEqual(fake_storage.requested_key, cache_key)
        self.assertTrue(execution["cache_hit"])
        self.assertEqual(execution["cached_response_body"]["candidates"][0]["content"]["parts"][0]["text"], "ok")

    def test_observability_does_not_mark_tool_choice_only_request_as_bypassed(self):
        payload = {
            "model": "demo-model",
            "messages": [{"role": "user", "content": "hello"}],
            "tool_choice": "auto",
        }
        meta = build_request_observability_meta(
            {
                "route_policy": {"prompt_cache_mode": "exact"},
                "upstream_payload": payload,
                "response_body": {
                    "choices": [{"message": {"content": "ok"}}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12},
                },
                "route_policy_metrics": {
                    "prompt_cache_hints_mode": "auto",
                    "prompt_cache_provider": "observe",
                },
            },
            payload,
        )

        self.assertEqual(meta["local_response_cache_status"], "miss")
        self.assertEqual(meta["local_response_cache_note"], "本次未命中")
        self.assertEqual(meta["upstream_prompt_cache_status"], "miss")
        self.assertEqual(meta["upstream_prompt_cache_note"], "本次未返回缓存命中")

    def test_save_request_cache_rejects_reasoning_only_success_body(self):
        class FakeStorage:
            def __init__(self):
                self.saved = None

            def save_request_cache(self, payload):
                self.saved = payload

        fake_storage = FakeStorage()
        original_storage = server.storage
        try:
            server.storage = fake_storage
            save_request_cache_entry(
                execution={
                    "upstream_payload": {
                        "model": "demo-model",
                        "messages": [{"role": "user", "content": "hello"}],
                    },
                    "route_policy": {"prompt_cache_mode": "exact"},
                },
                protocol="openai_chat_completions",
                path="chat/completions",
                request_payload={
                    "model": "demo-model",
                    "messages": [{"role": "user", "content": "hello"}],
                },
                response_body={
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": "",
                                "reasoning": "internal only",
                            },
                            "finish_reason": "length",
                        }
                    ],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 1, "total_tokens": 11},
                },
                upstream_url="https://good.example/v1/chat/completions",
            )
        finally:
            server.storage = original_storage

        self.assertIsNone(fake_storage.saved)

    def test_save_request_cache_rejects_reasoning_only_success_body_with_versioned_path(self):
        class FakeStorage:
            def __init__(self):
                self.saved = None

            def save_request_cache(self, payload):
                self.saved = payload

        fake_storage = FakeStorage()
        original_storage = server.storage
        try:
            server.storage = fake_storage
            save_request_cache_entry(
                execution={
                    "upstream_payload": {
                        "model": "demo-model",
                        "messages": [{"role": "user", "content": "hello"}],
                    },
                    "route_policy": {"prompt_cache_mode": "exact"},
                },
                protocol="openai_chat_completions",
                path="v1/chat/completions",
                request_payload={
                    "model": "demo-model",
                    "messages": [{"role": "user", "content": "hello"}],
                },
                response_body={
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": "",
                                "reasoning": "internal only",
                            },
                            "finish_reason": "length",
                        }
                    ],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 1, "total_tokens": 11},
                },
                upstream_url="https://good.example/v1/chat/completions",
            )
        finally:
            server.storage = original_storage

        self.assertIsNone(fake_storage.saved)

    def test_save_request_cache_stores_gemini_text_response(self):
        class FakeStorage:
            def __init__(self):
                self.saved = None

            def save_request_cache(self, payload):
                self.saved = payload

        fake_storage = FakeStorage()
        original_storage = server.storage
        try:
            server.storage = fake_storage
            save_request_cache_entry(
                execution={
                    "upstream_payload": {
                        "model": "demo-model",
                        "messages": [{"role": "user", "content": "hello"}],
                    },
                    "route_policy": {"prompt_cache_mode": "exact"},
                },
                protocol="gemini_generate_content",
                path="chat/completions",
                request_payload={
                    "model": "demo-model",
                    "messages": [{"role": "user", "content": "hello"}],
                },
                response_body={
                    "candidates": [
                        {
                            "content": {
                                "role": "model",
                                "parts": [{"text": "ok"}],
                            },
                            "finishReason": "STOP",
                        }
                    ],
                    "usageMetadata": {
                        "promptTokenCount": 10,
                        "candidatesTokenCount": 1,
                        "totalTokenCount": 11,
                    },
                },
                upstream_url="https://good.example/v1/chat/completions",
            )
        finally:
            server.storage = original_storage

        self.assertIsNotNone(fake_storage.saved)
        self.assertEqual(fake_storage.saved["protocol"], "gemini_generate_content")
        self.assertEqual(fake_storage.saved["response_body"]["candidates"][0]["content"]["parts"][0]["text"], "ok")

    def test_save_request_cache_counts_miss_only_when_response_is_stored(self):
        class FakeStorage:
            def __init__(self):
                self.saved = None

            def save_request_cache(self, payload):
                self.saved = payload

        fake_storage = FakeStorage()
        original_storage = server.storage
        before = server.cache_stats.snapshot()
        try:
            server.storage = fake_storage
            save_request_cache_entry(
                execution={
                    "upstream_payload": {
                        "model": "demo-model",
                        "messages": [{"role": "user", "content": "hello"}],
                    },
                    "route_policy": {"prompt_cache_mode": "exact"},
                },
                protocol="openai_chat_completions",
                path="chat/completions",
                request_payload={
                    "model": "demo-model",
                    "messages": [{"role": "user", "content": "hello"}],
                },
                response_body={"choices": [{"message": {"content": "ok"}}]},
                upstream_url="https://good.example/v1/chat/completions",
            )
        finally:
            server.storage = original_storage
        after = server.cache_stats.snapshot()

        self.assertIsNotNone(fake_storage.saved)
        self.assertEqual(
            int(after.get("prompt_cache_misses") or 0),
            int(before.get("prompt_cache_misses") or 0) + 1,
        )
        self.assertEqual(
            int(after.get("prompt_cache_writes") or 0),
            int(before.get("prompt_cache_writes") or 0) + 1,
        )


if __name__ == "__main__":
    unittest.main()
