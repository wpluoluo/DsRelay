import unittest

from local_proxy.runtime.config_runtime import normalize_runtime_config_payload
from local_proxy.runtime.pools import ConnectionPoolState, normalize_proxy_pools


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

    def test_pool_state_keeps_same_url_pools_as_distinct_routes(self):
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
                    "priority": 99,
                    "urls": ["https://integrate.api.nvidia.com/v1"],
                    "keys": [{"key": "nv-key-2"}],
                },
                {
                    "name": "nv3",
                    "enabled": True,
                    "priority": 98,
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
        payload = {
            "pools": [
                {
                    "name": "responses-aware",
                    "enabled": True,
                    "priority": 100,
                    "urls": ["https://api.example.com/v1"],
                    "keys": [{"key": "sk-test-1"}],
                    "route_policy": {
                        "text_upstream_protocol": "responses",
                    },
                }
            ]
        }

        normalized = normalize_runtime_config_payload(payload, current=current_runtime_config())
        route_policy = normalized["proxy_pools"][0]["route_policy"]

        self.assertEqual(route_policy["text_upstream_protocol"], "responses")

    def test_pool_model_alias_text_is_preserved_when_normalized(self):
        pools = normalize_proxy_pools(
            [
                {
                    "name": "mapped-route",
                    "enabled": True,
                    "priority": 100,
                    "urls": ["https://integrate.api.nvidia.com/v1"],
                    "keys": [{"key": "nv-key-1"}],
                    "model_aliases_text": "deepseek-v4-flash-free=deepseek-ai/deepseek-v4-flash",
                }
            ]
        )

        self.assertEqual(
            pools[0]["model_aliases_text"],
            "deepseek-v4-flash-free=deepseek-ai/deepseek-v4-flash",
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

    def test_legacy_global_model_fields_migrate_into_each_pool(self):
        payload = {
            "supported_models_text": "deepseek-ai/deepseek-v4-flash",
            "model_aliases_text": "deepseek-v4-flash-free=deepseek-ai/deepseek-v4-flash",
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

        self.assertEqual(pool["supported_models_text"], "deepseek-ai/deepseek-v4-flash")
        self.assertEqual(pool["model_aliases_text"], "deepseek-v4-flash-free=deepseek-ai/deepseek-v4-flash")


if __name__ == "__main__":
    unittest.main()
