import unittest

from local_proxy.runtime.request_cache import (
    build_cache_key,
    build_cached_execution,
    build_coalescing_key,
    is_cacheable_request,
)
from local_proxy.server import build_request_observability_meta


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


if __name__ == "__main__":
    unittest.main()
