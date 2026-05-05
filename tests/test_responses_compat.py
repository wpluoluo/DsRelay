import unittest
from unittest.mock import patch

import local_proxy.server as server


class ResponsesCompatTests(unittest.TestCase):
    def setUp(self):
        self.original_pools = server.PROXY_POOLS
        self.original_upstream_pool = server.UPSTREAM_URL_POOL
        server.PROXY_POOLS = [
            {
                "name": "openai-line",
                "enabled": True,
                "priority": 100,
                "urls": ["https://line-openai.example/v1"],
                "keys": [{"key": "sk-openai"}],
                "route_policy": {"text_upstream_protocol": "openai"},
            },
            {
                "name": "responses-line",
                "enabled": True,
                "priority": 99,
                "urls": ["https://line-responses.example/v1"],
                "keys": [{"key": "sk-responses"}],
                "route_policy": {"text_upstream_protocol": "responses"},
            },
        ]
        server.UPSTREAM_URL_POOL = [
            "https://line-openai.example/v1#__route=openai",
            "https://line-responses.example/v1#__route=responses",
        ]

    def tearDown(self):
        server.PROXY_POOLS = self.original_pools
        server.UPSTREAM_URL_POOL = self.original_upstream_pool

    def test_responses_request_uses_route_specific_upstream_subpath(self):
        seen = {}

        def fake_request_upstream_with_retries(request_kwargs, **kwargs):
            seen["request_kwargs"] = dict(request_kwargs)
            seen["kwargs"] = dict(kwargs)
            return None, [], None

        with server.app.test_request_context("/v1/responses", method="POST", json={"model": "demo", "input": "hi", "stream": False}):
            with patch.object(server, "request_upstream_with_retries", side_effect=fake_request_upstream_with_retries):
                result = server.execute_upstream_request(
                    "responses",
                    {"model": "demo", "input": "hi", "stream": False},
                    "req-openai",
                )

        self.assertEqual(result["upstream_subpath"], "chat/completions")
        self.assertEqual(seen["kwargs"]["subpath"], "chat/completions")
        self.assertEqual(
            seen["kwargs"]["upstream_urls"],
            [
                "https://line-openai.example/v1/chat/completions#__route=openai",
                "https://line-responses.example/v1/responses#__route=responses",
            ],
        )
        self.assertEqual(seen["request_kwargs"]["url"], "https://line-openai.example/v1/chat/completions")
        self.assertIn("messages", seen["request_kwargs"]["json"])
        meta = server.build_request_observability_meta(result, {"model": "demo"})
        self.assertEqual(meta["upstream_subpath"], "chat/completions")

    def test_convert_openai_response_to_responses_payload(self):
        openai_body = {
            "id": "chatcmpl_1",
            "object": "chat.completion",
            "created": 1710000000,
            "model": "demo-model",
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": "ok",
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 11,
                "completion_tokens": 3,
                "total_tokens": 14,
            },
        }

        response_body = server.convert_openai_response_to_responses(
            openai_body,
            {"model": "demo-model", "input": "hello"},
        )

        self.assertEqual(response_body["object"], "response")
        self.assertEqual(response_body["status"], "completed")
        self.assertEqual(response_body["output"][0]["content"][0]["type"], "output_text")
        self.assertEqual(response_body["output"][0]["content"][0]["text"], "ok")
        self.assertEqual(response_body["usage"]["input_tokens"], 11)
        self.assertEqual(response_body["usage"]["output_tokens"], 3)


if __name__ == "__main__":
    unittest.main()
