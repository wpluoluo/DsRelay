import copy
import unittest

import requests

import local_proxy.server as server
from local_proxy.upstream.capabilities import (
    normalize_model_capabilities_text,
    parse_model_capabilities,
)


class ModelCapabilitySourceTests(unittest.TestCase):
    def setUp(self):
        self.original_cache = copy.deepcopy(server.model_route_cache)

    def tearDown(self):
        server.model_route_cache = self.original_cache

    def test_learned_model_capability_cache_is_disabled(self):
        server.model_route_cache = {"routes": {}, "model_lists": {}, "capabilities": {}}

        server.record_learned_model_capability(
            logical_model="gpt-5.5",
            route_url="https://api.example.com/v1#__route=test",
            model_candidate="gpt-5.5",
            max_output_tokens=4096,
            context_tokens=1050000,
        )

        self.assertEqual(server.model_route_cache["capabilities"], {})
        self.assertEqual(server.count_learned_model_capability_entries(), 0)
        self.assertIsNone(
            server.get_learned_model_capability(
                "gpt-5.5",
                "https://api.example.com/v1#__route=test",
                "gpt-5.5",
            )
        )

    def test_upstream_error_text_no_longer_produces_capability_learning(self):
        response = requests.Response()
        response.status_code = 400
        response._content = b"supports at most 8192 output tokens"
        response.encoding = "utf-8"

        self.assertIsNone(server.extract_completion_token_limit_from_response(response))
        self.assertEqual(server.extract_context_token_limit_from_response(response), (None, None))
        self.assertEqual(
            server.apply_learned_completion_limit_to_request_kwargs(
                {"json": {"max_completion_tokens": 16000}},
                logical_model="gpt-5.5",
                route_url="https://api.example.com/v1#__route=test",
                model_candidate="gpt-5.5",
            ),
            0,
        )

    def test_official_deepseek_v4_output_cap_is_enforced(self):
        capabilities = parse_model_capabilities(
            "deepseek-v4-flash=1048576,393216\n"
            "deepseek-v4-pro=1048576,393216\n"
            "deepseek-ai/deepseek-v4-flash=1048576,393216\n"
            "deepseek-ai/deepseek-v4-pro=1048576,393216\n"
        )

        self.assertEqual(capabilities["deepseek-v4-flash"]["max_output_tokens"], 262144)
        self.assertEqual(capabilities["deepseek-v4-pro"]["max_output_tokens"], 262144)
        self.assertEqual(capabilities["deepseek-ai/deepseek-v4-flash"]["max_output_tokens"], 262144)
        self.assertEqual(capabilities["deepseek-ai/deepseek-v4-pro"]["max_output_tokens"], 262144)

    def test_normalized_model_capabilities_text_deduplicates_default_block(self):
        normalized = normalize_model_capabilities_text(
            "# model=context_tokens,max_output_tokens\n"
            "# Prefer official provider docs or official Models APIs where available.\n"
            "deepseek-v4-flash=1048576,393216\n"
            "deepseek-v4-pro=1048576,393216\n"
            "gpt-5.5=1000000,128000\n"
        )

        lines = normalized.splitlines()
        self.assertEqual(lines.count("# model=context_tokens,max_output_tokens"), 1)
        self.assertEqual(lines.count("deepseek-v4-flash=1048576,262144"), 1)
        self.assertIn("deepseek-v4-flash=1048576,262144", normalized)


if __name__ == "__main__":
    unittest.main()
