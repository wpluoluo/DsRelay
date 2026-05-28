import copy
import unittest

import requests

import local_proxy.server as server


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


if __name__ == "__main__":
    unittest.main()
