import unittest

from local_proxy.runtime.request_cache import build_cache_key, build_coalescing_key, is_cacheable_request


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


if __name__ == "__main__":
    unittest.main()
