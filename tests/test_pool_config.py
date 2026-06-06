import time
import unittest
from unittest.mock import patch

import local_proxy.server as server_module
from local_proxy.runtime.config_runtime import normalize_runtime_config_payload
from local_proxy.runtime.pools import ConnectionPoolState, normalize_proxy_pools
from local_proxy.runtime.policies import get_pool_priority_for_url
from local_proxy.upstream.capabilities import DEFAULT_MODEL_CAPABILITIES_TEXT, normalize_model_capabilities_text
from local_proxy.upstream.models import normalize_model_alias_key


def current_runtime_config(**overrides):
    current = {
        "PROXY_POOLS": [],
        "MODEL_CAPABILITIES_TEXT": "",
        "REQUEST_TIMEOUT": 600,
        "STREAM_FIRST_EVENT_TIMEOUT_SECONDS": 600,
        "FORCE_UPSTREAM_CHAT_STREAM": True,
        "ENABLE_REQUEST_NORMALIZATION": True,
        "MAX_COMPLETION_TOKENS": 0,
        "INJECT_ZH_SYSTEM_PROMPT": True,
        "PROXY_SYSTEM_PROMPT_ZH": "默认提示",
        "DEFAULT_PROXY_SYSTEM_PROMPT_ZH": "默认提示",
        "MARKDOWN_OUTPUT_PROMPT_RULE": "Markdown 规则",
        "UPSTREAM_MAX_RETRIES": 3,
        "UPSTREAM_RETRY_BACKOFF_MS": 200,
        "UPSTREAM_RETRY_MAX_BACKOFF_MS": 1000,
        "UPSTREAM_ROUTE_SWITCH_WINDOW_SECONDS": 60,
        "UPSTREAM_RANDOMIZE_ENDPOINTS": True,
        "IMAGE_UPSTREAM_PROTOCOL": "auto",
        "IMAGE_TASK_POLL_TIMEOUT_SECONDS": 90,
        "IMAGE_TASK_POLL_INTERVAL_SECONDS": 2,
        "ENABLE_MODEL_PROBE": True,
        "MODEL_PROBE_TIMEOUT_SECONDS": 4,
        "MODEL_PROBE_TTL_SECONDS": 300,
        "MODEL_ROUTE_CACHE_TTL_SECONDS": 86400,
        "ENABLE_INTERRUPTION_RESUME": True,
        "INTERRUPTION_RESUME_TTL_SECONDS": 3600,
        "INTERRUPTION_RESUME_MAX_CHARS": 12000,
        "INTERRUPTION_RESUME_MIN_CHARS": 40,
        "ENABLE_MODEL_CANDIDATE_RACE": True,
        "MODEL_CANDIDATE_RACE_LIMIT": 3,
        "MODEL_CANDIDATE_RACE_TIMEOUT_SECONDS": 8,
    }
    current.update(overrides)
    return current


class PoolConfigTests(unittest.TestCase):
    def test_request_timeout_is_no_longer_clamped_to_30_or_3600(self):
        normalized = normalize_runtime_config_payload(
            {"request_timeout": 5},
            current=current_runtime_config(),
        )

        self.assertEqual(normalized["request_timeout"], 5)

        normalized = normalize_runtime_config_payload(
            {"request_timeout": 7200},
            current=current_runtime_config(),
        )

        self.assertEqual(normalized["request_timeout"], 7200)

    def test_model_probe_timeout_is_no_longer_clamped_to_30(self):
        normalized = normalize_runtime_config_payload(
            {"model_probe_timeout_seconds": 45},
            current=current_runtime_config(),
        )

        self.assertEqual(normalized["model_probe_timeout_seconds"], 45)

    def test_stream_first_event_timeout_can_be_lower_than_request_timeout(self):
        normalized = normalize_runtime_config_payload(
            {
                "request_timeout": 180,
                "stream_first_event_timeout_seconds": 20,
            },
            current=current_runtime_config(),
        )

        self.assertEqual(normalized["request_timeout"], 180)
        self.assertEqual(normalized["stream_first_event_timeout_seconds"], 20)

    def test_new_pool_payload_keeps_route_and_key(self):
        payload = {
            "pools": [
                {
                    "name": " new pool ",
                    "enabled": True,
                    "priority": "120",
                    "urls": [" https://api.example.com/v1/chat/completions ", ""],
                    "keys": [{"key": " sk-test-1 "}, {"key": ""}],
                    "supported_models_text": "demo-model\nprovider/demo",
                    "model_aliases_text": "demo=provider/demo",
                    "route_policy": {
                        "reasoning_effort": "high",
                        "route_cooldown_seconds": 45,
                        "route_cooldown_multiplier": 1.5,
                        "route_cooldown_max_seconds": 300,
                        "rate_limit_retry_attempts": 3,
                        "rate_limit_backoff_initial_ms": 1000,
                        "rate_limit_backoff_multiplier": 2,
                        "rate_limit_backoff_max_ms": 4000,
                    },
                }
            ]
        }

        normalized = normalize_runtime_config_payload(payload, current=current_runtime_config())
        pools = normalized["proxy_pools"]

        self.assertEqual(len(pools), 1)
        self.assertEqual(pools[0]["name"], "new pool")
        self.assertEqual(pools[0]["priority"], 120)
        self.assertEqual(pools[0]["urls"], ["https://api.example.com/v1"])
        self.assertEqual(pools[0]["keys"], [{"key": "sk-test-1"}])
        self.assertEqual(pools[0]["supported_models_text"], "demo-model\nprovider/demo")
        self.assertEqual(pools[0]["model_aliases_text"], "demo=provider/demo")
        self.assertEqual(pools[0]["route_policy"]["reasoning_effort"], "high")
        self.assertEqual(pools[0]["route_policy"]["text_upstream_protocol"], "auto")
        self.assertEqual(pools[0]["route_policy"]["prompt_cache_mode"], "exact")
        self.assertEqual(pools[0]["route_policy"]["prompt_cache_hints_mode"], "auto")
        self.assertEqual(pools[0]["route_policy"]["prompt_cache_provider"], "auto")
        self.assertEqual(pools[0]["route_policy"]["prompt_cache_retention"], "")
        self.assertEqual(pools[0]["route_policy"]["route_cooldown_seconds"], 45)
        self.assertEqual(pools[0]["route_policy"]["route_cooldown_multiplier"], 1.5)
        self.assertEqual(pools[0]["route_policy"]["route_cooldown_max_seconds"], 300)
        self.assertEqual(pools[0]["route_policy"]["rate_limit_retry_attempts"], 3)
        self.assertEqual(pools[0]["route_policy"]["rate_limit_backoff_initial_ms"], 1000)
        self.assertEqual(pools[0]["route_policy"]["rate_limit_backoff_multiplier"], 2)
        self.assertEqual(pools[0]["route_policy"]["rate_limit_backoff_max_ms"], 4000)
        self.assertNotIn("compression_mode", pools[0]["route_policy"])
        self.assertNotIn("max_history_messages", pools[0]["route_policy"])
        self.assertNotIn("max_tool_chars", pools[0]["route_policy"])
        self.assertNotIn("max_input_chars", pools[0]["route_policy"])


    def test_pool_state_rebuild_uses_saved_keys(self):
        pools = normalize_proxy_pools(
            [
                {
                    "name": "pool",
                    "enabled": True,
                    "priority": 100,
                    "urls": ["https://api.example.com/v1"],
                    "keys": [{"key": "sk-a"}, {"key": "sk-b"}],
                }
            ]
        )
        state = ConnectionPoolState()

        urls = state.rebuild(pools)
        choice = state.choose_key("https://api.example.com/v1/chat/completions")

        self.assertEqual(len(urls), 1)
        self.assertTrue(urls[0].startswith("https://api.example.com/v1#__route="))
        self.assertEqual(state.get_api_keys_for_url("https://api.example.com/v1"), ["sk-a", "sk-b"])
        self.assertEqual(choice["key"], "sk-a")
        self.assertEqual(choice["pool_name"], "pool")

    def test_pool_state_rebuild_keeps_keyless_route(self):
        pools = normalize_proxy_pools(
            [
                {
                    "name": "zen-no-key",
                    "enabled": True,
                    "priority": 100,
                    "urls": ["https://opencode.ai/zen/v1"],
                    "keys": [],
                }
            ]
        )
        state = ConnectionPoolState()

        urls = state.rebuild(pools)

        self.assertEqual(len(urls), 1)
        self.assertTrue(urls[0].startswith("https://opencode.ai/zen/v1#__route="))
        self.assertEqual(state.get_api_keys_for_url("https://opencode.ai/zen/v1"), [])
        self.assertIsNone(state.choose_key("https://opencode.ai/zen/v1/chat/completions"))

    def test_pool_state_rebuild_orders_lower_priority_number_first(self):
        pools = normalize_proxy_pools(
            [
                {
                    "name": "nv1",
                    "enabled": True,
                    "priority": 100,
                    "urls": ["https://integrate.api.nvidia.com/v1"],
                    "keys": [{"key": "nv-key-1"}],
                },
                {
                    "name": "nv2",
                    "enabled": True,
                    "priority": 101,
                    "urls": ["https://integrate.api.nvidia.com/v1"],
                    "keys": [{"key": "nv-key-2"}],
                },
                {
                    "name": "nv3",
                    "enabled": True,
                    "priority": 102,
                    "urls": ["https://integrate.api.nvidia.com/v1"],
                    "keys": [{"key": "nv-key-3"}],
                },
            ]
        )
        state = ConnectionPoolState()

        urls = state.rebuild(pools)

        self.assertEqual(len(urls), 3)
        self.assertEqual(len(set(urls)), 3)
        self.assertTrue(all(url.startswith("https://integrate.api.nvidia.com/v1#__route=") for url in urls))
        self.assertEqual(state.get_api_keys_for_url(urls[0]), ["nv-key-1"])
        self.assertEqual(state.get_api_keys_for_url(urls[1]), ["nv-key-2"])
        self.assertEqual(state.get_api_keys_for_url(urls[2]), ["nv-key-3"])

    def test_pool_route_policy_keeps_prompt_cache_hint_settings(self):
        payload = {
            "pools": [
                {
                    "name": "cache-aware",
                    "enabled": True,
                    "priority": 100,
                    "urls": ["https://api.openai.com/v1"],
                    "keys": [{"key": "sk-test-1"}],
                    "route_policy": {
                        "prompt_cache_hints_mode": "passthrough",
                        "prompt_cache_provider": "openai",
                        "prompt_cache_retention": "24h",
                    },
                }
            ]
        }

        normalized = normalize_runtime_config_payload(payload, current=current_runtime_config())
        route_policy = normalized["proxy_pools"][0]["route_policy"]

        self.assertEqual(route_policy["prompt_cache_hints_mode"], "passthrough")
        self.assertEqual(route_policy["prompt_cache_provider"], "openai")
        self.assertEqual(route_policy["prompt_cache_retention"], "24h")

    def test_pool_route_policy_keeps_text_upstream_protocol(self):
        for protocol in ("responses", "anthropic", "gemini"):
            with self.subTest(protocol=protocol):
                payload = {
                    "pools": [
                        {
                            "name": "protocol-aware",
                            "enabled": True,
                            "priority": 100,
                            "urls": ["https://api.example.com/v1"],
                            "keys": [{"key": "sk-test-1"}],
                            "route_policy": {
                                "text_upstream_protocol": protocol,
                            },
                        }
                    ]
                }

                normalized = normalize_runtime_config_payload(payload, current=current_runtime_config())
                route_policy = normalized["proxy_pools"][0]["route_policy"]

                self.assertEqual(route_policy["text_upstream_protocol"], protocol)

    def test_runtime_config_ignores_manual_model_capability_text(self):
        normalized = normalize_runtime_config_payload(
            {
                "model_capabilities_text": "custom-only-model=1,1",
            },
            current=current_runtime_config(MODEL_CAPABILITIES_TEXT="custom-only-model=1,1"),
        )

        expected = normalize_model_capabilities_text(DEFAULT_MODEL_CAPABILITIES_TEXT)
        self.assertEqual(normalized["model_capabilities_text"], expected)
        self.assertNotIn("custom-only-model", normalized["model_capabilities"])

    def test_runtime_config_storage_export_omits_model_capability_text(self):
        exported = server_module.export_runtime_config_for_storage()

        self.assertNotIn("model_capabilities_text", exported)

    def test_pool_model_alias_text_is_preserved_when_normalized(self):
        pools = normalize_proxy_pools(
            [
                {
                    "name": "mapped-route",
                    "enabled": True,
                    "priority": 100,
                    "urls": ["https://integrate.api.nvidia.com/v1"],
                    "keys": [{"key": "nv-key-1"}],
                    "model_aliases_text": "deepseek-v4-flash=deepseek-ai/deepseek-v4-flash",
                }
            ]
        )

        self.assertEqual(
            pools[0]["model_aliases_text"],
            "deepseek-v4-flash=deepseek-ai/deepseek-v4-flash",
        )

    def test_pool_supported_models_text_is_preserved_when_normalized(self):
        pools = normalize_proxy_pools(
            [
                {
                    "name": "nv-route",
                    "enabled": True,
                    "priority": 100,
                    "urls": ["https://integrate.api.nvidia.com/v1"],
                    "keys": [{"key": "nv-key-1"}],
                    "supported_models_text": "deepseek-ai/deepseek-v4-flash\ndeepseek-ai/deepseek-v4-pro",
                }
            ]
        )

        self.assertEqual(
            pools[0]["supported_models_text"],
            "deepseek-ai/deepseek-v4-flash\ndeepseek-ai/deepseek-v4-pro",
        )

    def test_legacy_global_model_fields_no_longer_migrate_into_each_pool(self):
        payload = {
            "supported_models_text": "deepseek-ai/deepseek-v4-flash",
            "model_aliases_text": "deepseek-v4-flash=deepseek-ai/deepseek-v4-flash",
            "pools": [
                {
                    "name": "nv-route",
                    "enabled": True,
                    "priority": 100,
                    "urls": ["https://integrate.api.nvidia.com/v1"],
                    "keys": [{"key": "nv-key-1"}],
                }
            ],
        }

        normalized = normalize_runtime_config_payload(payload, current=current_runtime_config())
        pool = normalized["proxy_pools"][0]

        self.assertEqual(pool["supported_models_text"], "")
        self.assertEqual(pool["model_aliases_text"], "")

    def test_route_selection_score_prefers_lower_priority_number_over_learned_route_score(self):
        priority_100_url = ConnectionPoolState.route_id_for("priority-100", "https://opencode.ai/zen/v1", 1)
        priority_103_url = ConnectionPoolState.route_id_for("priority-103", "https://integrate.api.nvidia.com/v1", 1)
        pools = normalize_proxy_pools(
            [
                {
                    "name": "priority-100",
                    "enabled": True,
                    "priority": 100,
                    "urls": ["https://opencode.ai/zen/v1"],
                    "keys": [],
                },
                {
                    "name": "priority-103",
                    "enabled": True,
                    "priority": 103,
                    "urls": ["https://integrate.api.nvidia.com/v1"],
                    "keys": [{"key": "nv-key"}],
                },
            ]
        )
        expires_at = time.time() + 300
        cache_payload = {
            "routes": {
                normalize_model_alias_key("demo-model"): {
                    priority_100_url: {
                        "demo-model": {
                            "model": "demo-model",
                            "score": 0.0,
                            "successes": 0,
                            "failures": 0,
                            "expires_at": expires_at,
                            "cooldown_until": 0.0,
                            "last_success_at": 0.0,
                        }
                    },
                    priority_103_url: {
                        "demo-model": {
                            "model": "demo-model",
                            "score": 500.0,
                            "successes": 20,
                            "failures": 0,
                            "expires_at": expires_at,
                            "cooldown_until": 0.0,
                            "last_success_at": expires_at - 10,
                        }
                    },
                }
            }
        }

        with patch.object(server_module, "PROXY_POOLS", pools), patch.dict(server_module.model_route_cache, cache_payload, clear=True):
            self.assertGreater(
                server_module.get_route_selection_score("demo-model", priority_100_url),
                server_module.get_route_selection_score("demo-model", priority_103_url),
            )

    def test_get_pool_priority_for_route_url_with_subpath_keeps_route_identity(self):
        pools = normalize_proxy_pools(
            [
                {
                    "name": "nv1",
                    "enabled": True,
                    "priority": 102,
                    "urls": ["https://integrate.api.nvidia.com/v1"],
                    "keys": [{"key": "nv-key-1"}],
                },
                {
                    "name": "nv",
                    "enabled": True,
                    "priority": 100,
                    "urls": ["https://integrate.api.nvidia.com/v1"],
                    "keys": [{"key": "nv-key-2"}],
                },
            ]
        )
        route_url = ConnectionPoolState.route_id_for("nv1", "https://integrate.api.nvidia.com/v1", 1)
        route_with_subpath = route_url.replace("/v1#__route=", "/v1/chat/completions#__route=")

        self.assertEqual(
            get_pool_priority_for_url(pools, route_with_subpath, server_module.normalize_pool_url),
            102,
        )


if __name__ == "__main__":
    unittest.main()
