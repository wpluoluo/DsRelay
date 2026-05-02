import unittest

from local_proxy.runtime.config_runtime import normalize_runtime_config_payload
from local_proxy.runtime.pools import ConnectionPoolState, normalize_proxy_pools


def current_runtime_config(**overrides):
    current = {
        "PROXY_POOLS": [],
        "MODEL_ALIASES_TEXT": "",
        "MODEL_CAPABILITIES_TEXT": "",
        "REQUEST_TIMEOUT": 600,
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
                    "route_policy": {"reasoning_effort": "high"},
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
        self.assertEqual(pools[0]["route_policy"]["reasoning_effort"], "high")
        self.assertEqual(pools[0]["route_policy"]["prompt_cache_mode"], "exact")

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

        self.assertEqual(urls, ["https://api.example.com/v1"])
        self.assertEqual(state.get_api_keys_for_url("https://api.example.com/v1"), ["sk-a", "sk-b"])
        self.assertEqual(choice["key"], "sk-a")
        self.assertEqual(choice["pool_name"], "pool")


if __name__ == "__main__":
    unittest.main()
