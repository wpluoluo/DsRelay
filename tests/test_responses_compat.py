import unittest
from unittest.mock import patch

import local_proxy.server as server
from local_proxy.upstream.router import build_model_candidate_order_for_route


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

    def test_normalize_downstream_subpath_strips_version_and_openai_prefixes(self):
        self.assertEqual(server.normalize_downstream_subpath("v1/messages"), "messages")
        self.assertEqual(server.normalize_downstream_subpath("/v1/v1/chat/completions"), "chat/completions")
        self.assertEqual(server.normalize_downstream_subpath("openai/chat/completions"), "chat/completions")
        self.assertEqual(server.normalize_downstream_subpath("/v1/openai/responses"), "responses")

    def test_detect_inbound_protocol_uses_normalized_subpath(self):
        with server.app.test_request_context("/v1/messages", method="POST", json={"messages": [{"role": "user", "content": "hi"}]}):
            self.assertEqual(server.detect_inbound_protocol("v1/messages", {"messages": [{"role": "user", "content": "hi"}]}), "anthropic_messages")
        with server.app.test_request_context("/v1/openai/chat/completions", method="POST", json={"messages": [{"role": "user", "content": "hi"}]}):
            self.assertEqual(server.detect_inbound_protocol("openai/chat/completions", {"messages": [{"role": "user", "content": "hi"}]}), "openai_chat_completions")
        with server.app.test_request_context("/v1/responses", method="POST", json={"input": "hi"}):
            self.assertEqual(server.detect_inbound_protocol("v1/responses", {"input": "hi"}), "openai_responses")

    def test_resolve_upstream_text_subpath_uses_normalized_subpath(self):
        self.assertEqual(
            server.resolve_upstream_text_subpath("v1/responses", {"text_upstream_protocol": "openai"}, {"input": "hi"}),
            "chat/completions",
        )
        self.assertEqual(
            server.resolve_upstream_text_subpath("/v1/openai/responses", {"text_upstream_protocol": "responses"}, {"input": "hi"}),
            "responses",
        )

    def test_build_model_candidates_uses_only_configured_alias_targets_when_mapping_hits(self):
        original_aliases = server.MODEL_ALIASES
        try:
            server.MODEL_ALIASES = {
                "deepseek-v4-flash": ["deepseek-ai/deepseek-v4-flash"],
            }
            candidates = server.build_model_candidates_from_payload({"model": "deepseek-v4-flash"})
        finally:
            server.MODEL_ALIASES = original_aliases

        self.assertEqual(candidates, ["deepseek-ai/deepseek-v4-flash"])

    def test_build_model_candidates_locks_deepseek_v4_pro_to_configured_alias_first(self):
        original_aliases = server.MODEL_ALIASES
        try:
            server.MODEL_ALIASES = {
                "deepseek-v4-pro": ["deepseek-ai/deepseek-v4-pro"],
            }
            candidates = server.build_model_candidates_from_payload({"model": "deepseek-v4-pro"})
        finally:
            server.MODEL_ALIASES = original_aliases

        self.assertEqual(candidates, ["deepseek-ai/deepseek-v4-pro"])

    def test_build_model_candidates_passthroughs_original_model_when_mapping_misses(self):
        original_aliases = server.MODEL_ALIASES
        try:
            server.MODEL_ALIASES = {}
            candidates = server.build_model_candidates_from_payload({"model": "deepseek-v4-flash"})
        finally:
            server.MODEL_ALIASES = original_aliases

        self.assertEqual(candidates, ["deepseek-v4-flash"])

    def test_route_model_order_keeps_alias_target_locked_when_request_model_differs(self):
        order_info = build_model_candidate_order_for_route(
            route_url="https://integrate.api.nvidia.com/v1/chat/completions#__route=test",
            model_candidates=["deepseek-ai/deepseek-v4-flash"],
            request_kwargs={"json": {"model": "deepseek-v4-flash"}},
            request_id="req-locked-alias",
            get_cached_route_candidates=lambda logical_model, route_url: ["deepseek-v4-flash"],
            fetch_model_list=lambda route_url, request_kwargs, request_id: [
                "deepseek-v4-flash",
                "deepseek-ai/deepseek-v4-flash",
            ],
            get_model_candidate_score=lambda logical_model, route_url, model_candidate: 0,
            logger=type("NullLogger", (), {"info": lambda *args, **kwargs: None})(),
        )

        self.assertEqual(order_info["candidates"], ["deepseek-ai/deepseek-v4-flash"])

    def test_proxy_entrypoint_normalizes_duplicate_v1_prefix_before_upstream_request(self):
        seen = {}

        def fake_execute_upstream_request(subpath, request_payload, request_id, **kwargs):
            seen["subpath"] = subpath
            return {
                "upstream_url": "https://line-openai.example/v1/chat/completions",
                "route_url": "https://line-openai.example/v1/chat/completions#__route=openai",
                "upstream_subpath": subpath,
                "upstream_url_pool": ["https://line-openai.example/v1/chat/completions#__route=openai"],
                "route_pool_size": 1,
                "tool_schemas": {},
                "upstream_payload": request_payload,
                "upstream_stream": False,
                "upstream_response": None,
                "attempts": [],
                "request_exception": RuntimeError("skip"),
                "retry_count": 0,
                "request_repairs": 0,
                "model_candidates": [],
                "initial_key_choice": {},
                "forced_error_payload": {"error": {"message": "skip"}},
                "forced_error_status": 502,
            }

        with server.app.test_request_context(
            "/v1/v1/chat/completions",
            method="POST",
            json={"model": "demo", "messages": [{"role": "user", "content": "hi"}]},
            headers={"Authorization": "Bearer proxy-secret"},
        ):
            with patch.object(server, "require_proxy_api_key", return_value=None):
                with patch.object(server, "execute_upstream_request", side_effect=fake_execute_upstream_request):
                    response = server.proxy_entrypoint("v1/chat/completions")

        self.assertEqual(seen["subpath"], "chat/completions")
        self.assertEqual(response.status_code, 502)

    def test_proxy_entrypoint_normalizes_duplicate_v1_messages_into_anthropic_handler(self):
        with server.app.test_request_context(
            "/v1/v1/messages",
            method="POST",
            json={"model": "demo", "messages": [{"role": "user", "content": "hi"}]},
            headers={"x-api-key": "proxy-secret", "anthropic-version": "2023-06-01"},
        ):
            with patch.object(server, "require_proxy_api_key", return_value=None):
                with patch.object(server, "anthropic_messages", return_value=server.Response("ok", status=200)) as anthropic_mock:
                    response = server.proxy_entrypoint("v1/messages")

        anthropic_mock.assert_called_once()
        self.assertEqual(response.status_code, 200)

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
