import unittest

from local_proxy.server import apply_route_policy_to_payload


class PromptCacheHintTests(unittest.TestCase):
    def test_auto_mode_injects_openai_prompt_cache_hint(self):
        payload = {
            "model": "gpt-test",
            "messages": [{"role": "user", "content": "hello"}],
        }
        route_policy = {
            "reasoning_effort": "medium",
            "prompt_cache_mode": "exact",
            "prompt_cache_hints_mode": "auto",
            "prompt_cache_provider": "openai",
            "prompt_cache_retention": "24h",
            "max_output_tokens": 0,
        }

        updated, repairs, metrics = apply_route_policy_to_payload(
            "chat/completions",
            payload,
            route_policy,
            upstream_url="https://api.openai.com/v1/chat/completions",
            session_affinity_key="session:v1:test",
        )

        self.assertEqual(repairs, 3)
        self.assertEqual(updated["reasoning_effort"], "medium")
        self.assertTrue(str(updated.get("prompt_cache_key", "")).startswith("pcache:v1:"))
        self.assertEqual(updated.get("prompt_cache_retention"), "24h")
        self.assertTrue(metrics["prompt_cache_hint_applied"])
        self.assertEqual(metrics["prompt_cache_provider"], "openai")
        self.assertEqual(metrics["prompt_cache_retention"], "24h")

    def test_passthrough_mode_preserves_client_hint_without_injection(self):
        payload = {
            "model": "gpt-test",
            "messages": [{"role": "user", "content": "hello"}],
            "prompt_cache_key": "client-key",
            "prompt_cache_retention": "in_memory",
        }
        route_policy = {
            "reasoning_effort": "medium",
            "prompt_cache_mode": "exact",
            "prompt_cache_hints_mode": "passthrough",
            "prompt_cache_provider": "openai",
            "prompt_cache_retention": "",
            "max_output_tokens": 0,
        }

        updated, repairs, metrics = apply_route_policy_to_payload(
            "chat/completions",
            payload,
            route_policy,
            upstream_url="https://api.openai.com/v1/chat/completions",
            session_affinity_key="session:v1:test",
        )

        self.assertEqual(repairs, 1)
        self.assertEqual(updated.get("prompt_cache_key"), "client-key")
        self.assertEqual(updated.get("prompt_cache_retention"), "in_memory")
        self.assertFalse(metrics["prompt_cache_hint_applied"])
        self.assertTrue(metrics["prompt_cache_hint_passthrough"])

    def test_auto_mode_skips_unknown_provider(self):
        payload = {
            "model": "gpt-test",
            "messages": [{"role": "user", "content": "hello"}],
        }
        route_policy = {
            "reasoning_effort": "medium",
            "prompt_cache_mode": "exact",
            "prompt_cache_hints_mode": "auto",
            "prompt_cache_provider": "auto",
            "prompt_cache_retention": "24h",
            "max_output_tokens": 0,
        }

        updated, repairs, metrics = apply_route_policy_to_payload(
            "chat/completions",
            payload,
            route_policy,
            upstream_url="https://unknown.example/v1/chat/completions",
            session_affinity_key="session:v1:test",
        )

        self.assertEqual(repairs, 1)
        self.assertNotIn("prompt_cache_key", updated)
        self.assertEqual(metrics["prompt_cache_provider"], "none")
        self.assertFalse(metrics["prompt_cache_hint_applied"])


if __name__ == "__main__":
    unittest.main()
