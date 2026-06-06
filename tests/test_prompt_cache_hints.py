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
            "prompt_cache_provider": "auto",
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

    def test_auto_mode_observes_opencode_route_without_injection(self):
        payload = {
            "model": "deepseek-v4-flash-free",
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
            upstream_url="https://opencode.ai/zen/v1/chat/completions",
            session_affinity_key="session:v1:test",
        )

        self.assertEqual(repairs, 1)
        self.assertNotIn("prompt_cache_key", updated)
        self.assertNotIn("prompt_cache_retention", updated)
        self.assertFalse(metrics["prompt_cache_hint_applied"])
        self.assertEqual(metrics["prompt_cache_provider"], "observe")

    def test_opencode_stream_requests_include_usage_for_cache_observability(self):
        payload = {
            "model": "deepseek-v4-flash-free",
            "messages": [{"role": "user", "content": "hello"}],
            "stream": True,
        }
        route_policy = {
            "reasoning_effort": "medium",
            "prompt_cache_mode": "exact",
            "prompt_cache_hints_mode": "auto",
            "prompt_cache_provider": "auto",
            "prompt_cache_retention": "",
            "max_output_tokens": 0,
        }

        updated, repairs, metrics = apply_route_policy_to_payload(
            "chat/completions",
            payload,
            route_policy,
            upstream_url="https://opencode.ai/zen/v1/chat/completions",
            session_affinity_key="session:v1:test",
        )

        self.assertEqual(repairs, 2)
        self.assertEqual(updated["stream_options"], {"include_usage": True})
        self.assertTrue(metrics["stream_usage_included"])
        self.assertEqual(metrics["stream_usage_include_source"], "proxy")

    def test_non_cache_sensitive_stream_requests_do_not_force_include_usage(self):
        payload = {
            "model": "unknown",
            "messages": [{"role": "user", "content": "hello"}],
            "stream": True,
        }
        route_policy = {
            "reasoning_effort": "medium",
            "prompt_cache_mode": "exact",
            "prompt_cache_hints_mode": "off",
            "prompt_cache_provider": "none",
            "prompt_cache_retention": "",
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
        self.assertNotIn("stream_options", updated)
        self.assertFalse(metrics["stream_usage_included"])

    def test_opencode_tool_choice_skips_reasoning_effort(self):
        payload = {
            "model": "deepseek-v4-flash-free",
            "messages": [{"role": "user", "content": "hello"}],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "Read",
                        "parameters": {"type": "object", "properties": {}},
                    },
                }
            ],
            "tool_choice": "auto",
        }
        route_policy = {
            "reasoning_effort": "high",
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
            upstream_url="https://opencode.ai/zen/v1/chat/completions",
            session_affinity_key="session:v1:test",
        )

        self.assertEqual(repairs, 0)
        self.assertNotIn("reasoning_effort", updated)
        self.assertTrue(metrics["reasoning_disabled_for_tool_choice"])
        self.assertEqual(metrics["reasoning_compat_provider"], "deepseek")
        self.assertEqual(metrics["prompt_cache_provider"], "observe")

    def test_opencode_tool_choice_removes_existing_reasoning_fields(self):
        payload = {
            "model": "deepseek-v4-flash-free",
            "messages": [{"role": "user", "content": "hello"}],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "Read",
                        "parameters": {"type": "object", "properties": {}},
                    },
                }
            ],
            "tool_choice": {"type": "function", "function": {"name": "Read"}},
            "reasoning_effort": "high",
            "thinking": {"type": "enabled"},
        }
        route_policy = {
            "reasoning_effort": "high",
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
            upstream_url="https://opencode.ai/zen/v1/chat/completions",
            session_affinity_key="session:v1:test",
        )

        self.assertEqual(repairs, 2)
        self.assertNotIn("reasoning_effort", updated)
        self.assertNotIn("thinking", updated)
        self.assertTrue(metrics["reasoning_disabled_for_tool_choice"])
        self.assertEqual(set(metrics["reasoning_removed_fields"]), {"reasoning_effort", "thinking"})

    def test_openai_tool_choice_keeps_reasoning_effort(self):
        payload = {
            "model": "gpt-test",
            "messages": [{"role": "user", "content": "hello"}],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "Read",
                        "parameters": {"type": "object", "properties": {}},
                    },
                }
            ],
            "tool_choice": "auto",
        }
        route_policy = {
            "reasoning_effort": "medium",
            "prompt_cache_mode": "exact",
            "prompt_cache_hints_mode": "off",
            "prompt_cache_provider": "none",
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
        self.assertEqual(updated["reasoning_effort"], "medium")
        self.assertFalse(metrics["reasoning_disabled_for_tool_choice"])

    def test_auto_mode_observes_nvidia_route_without_injection(self):
        payload = {
            "model": "gpt-test",
            "messages": [{"role": "user", "content": "hello"}],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "Read",
                        "parameters": {"type": "object", "properties": {}},
                    },
                }
            ],
            "tool_choice": "auto",
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
            upstream_url="https://integrate.api.nvidia.com/v1/chat/completions",
            session_affinity_key="session:v1:test",
        )

        self.assertEqual(repairs, 1)
        self.assertNotIn("prompt_cache_key", updated)
        self.assertNotIn("prompt_cache_retention", updated)
        self.assertFalse(metrics["prompt_cache_hint_applied"])
        self.assertEqual(metrics["prompt_cache_provider"], "observe")

    def test_legacy_openai_provider_on_observe_only_host_does_not_inject(self):
        payload = {
            "model": "deepseek-v4-flash-free",
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
            upstream_url="https://opencode.ai/zen/v1/chat/completions",
            session_affinity_key="session:v1:test",
        )

        self.assertEqual(repairs, 1)
        self.assertNotIn("prompt_cache_key", updated)
        self.assertNotIn("prompt_cache_retention", updated)
        self.assertFalse(metrics["prompt_cache_hint_applied"])
        self.assertEqual(metrics["prompt_cache_provider"], "observe")

    def test_explicit_openrouter_provider_injects_prompt_cache_hint(self):
        payload = {
            "model": "gpt-test",
            "messages": [{"role": "user", "content": "hello"}],
        }
        route_policy = {
            "reasoning_effort": "medium",
            "prompt_cache_mode": "exact",
            "prompt_cache_hints_mode": "auto",
            "prompt_cache_provider": "openrouter",
            "prompt_cache_retention": "24h",
            "max_output_tokens": 0,
        }

        updated, repairs, metrics = apply_route_policy_to_payload(
            "chat/completions",
            payload,
            route_policy,
            upstream_url="https://openrouter.ai/api/v1/chat/completions",
            session_affinity_key="session:v1:test",
        )

        self.assertGreaterEqual(repairs, 2)
        self.assertTrue(str(updated.get("prompt_cache_key", "")).startswith("pcache:v1:"))
        self.assertEqual(updated.get("prompt_cache_retention"), "24h")
        self.assertTrue(metrics["prompt_cache_hint_applied"])
        self.assertEqual(metrics["prompt_cache_provider"], "openrouter")


if __name__ == "__main__":
    unittest.main()
