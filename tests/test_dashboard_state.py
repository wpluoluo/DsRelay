import unittest

from local_proxy.runtime.snapshots import build_dashboard_state, build_runtime_snapshot
from local_proxy.runtime.request_cache import build_cached_execution
import local_proxy.server as server


class DashboardStateTests(unittest.TestCase):
    def test_runtime_snapshot_exposes_stream_first_event_timeout_seconds(self):
        runtime = build_runtime_snapshot(
            {
                "app_started_at_epoch": 1.0,
                "python_executable": "python",
                "port": 18765,
                "request_timeout": 30,
                "stream_first_event_timeout_seconds": 45,
                "enable_request_normalization": True,
                "max_completion_tokens": 0,
                "model_capability_count": 1,
                "inject_zh_system_prompt": True,
                "force_upstream_chat_stream": True,
                "upstream_urls": ["https://integrate.api.nvidia.com/v1#__route=a"],
                "upstream_api_key": "",
                "proxy_api_key_count": 1,
                "proxy_api_key_env_count": 0,
                "proxy_api_key_managed_count": 1,
                "proxy_api_key_managed_enabled_count": 1,
                "mask_secret": lambda value: str(value),
                "model_alias_count": 1,
                "model_aliases": {"deepseek-v4-pro": ["deepseek-ai/deepseek-v4-pro"]},
                "enable_model_probe": True,
                "model_probe_timeout_seconds": 4,
                "model_probe_ttl_seconds": 300,
                "model_route_cache_ttl_seconds": 86400,
                "enable_interruption_resume": True,
                "interruption_resume_ttl_seconds": 3600,
                "interruption_resume_max_chars": 12000,
                "interruption_resume_min_chars": 40,
                "enable_model_candidate_race": True,
                "model_candidate_race_limit": 3,
                "model_candidate_race_timeout_seconds": 3,
                "count_model_route_cache_entries": lambda: 0,
                "count_interrupted_response_entries": lambda: 0,
                "count_learned_model_capability_entries": lambda: 0,
                "model_list_cache_entries": {},
                "model_route_cache_path": "cache.json",
                "db_label": "mysql://demo",
                "db_enabled": True,
                "cache_stats_snapshot": lambda: {},
                "config_path": "config/proxy-config.json",
                "config_file_exists": True,
                "primary_config_path": "config/proxy-config.json",
                "config_candidate_paths": [],
                "config_source": "storage",
                "max_retries": 3,
                "retry_backoff_ms": 200,
                "retry_max_backoff_ms": 300,
                "route_failure_threshold": 3,
                "route_cooldown_seconds": 90,
                "route_switch_window_seconds": 10,
                "randomize_endpoints": True,
                "retryable_status_codes": {408, 429, 500, 502, 503, 504},
                "http_pool_connections": 64,
                "http_pool_maxsize": 128,
                "pool_key_failure_threshold": 2,
                "pool_key_cooldown_seconds": 180,
                "connection_pool_snapshot": lambda: {},
                "image_upstream_protocol": "auto",
                "image_task_poll_timeout_seconds": 90,
                "image_task_poll_interval_seconds": 2,
                "route_health": {},
                "capabilities": ["OpenAI Chat Completions"],
            }
        )

        self.assertEqual(runtime["stream_first_event_timeout_seconds"], 45)

    def test_recent_requests_are_tagged_against_current_routes(self):
        state = build_dashboard_state(
            {
                "build_runtime_snapshot": lambda: {
                    "model_routing": {
                        "cache_stats": {},
                        "db_label": "mysql://demo",
                    },
                    "config_source": "storage",
                },
                "request_recorder_snapshot": lambda: {
                    "stats": {},
                    "active_requests": [],
                    "recent_requests": [
                        {
                            "request_id": "req-current",
                            "upstream_url": "https://integrate.api.nvidia.com/v1/chat/completions",
                            "pool_name": "nv-1",
                            "status_code": 200,
                        },
                        {
                            "request_id": "req-old",
                            "upstream_url": "https://open.juece.cloud/v1/chat/completions",
                            "pool_name": "juece",
                            "status_code": 200,
                        },
                    ],
                },
                "route_health": {},
                "upstream_url": "https://integrate.api.nvidia.com/v1#__route=a",
                "upstream_urls": [
                    "https://integrate.api.nvidia.com/v1#__route=a",
                    "https://integrate.api.nvidia.com/v1#__route=b",
                ],
                "proxy_pools": [
                    {"name": "nv-1", "enabled": True},
                    {"name": "nv-2", "enabled": True},
                ],
                "log_path": "proxy.log",
                "build_runtime_config_payload": lambda: {
                    "config_source": "storage",
                    "db_label": "mysql://demo",
                },
                "connection_pool_snapshot": lambda: {
                    "urls": {
                        "https://integrate.api.nvidia.com/v1#__route=a": {"pool_name": "nv-1"},
                        "https://integrate.api.nvidia.com/v1#__route=b": {"pool_name": "nv-2"},
                    }
                },
                "active_session_affinity_keys": lambda: 0,
                "active_route_affinity_counts": lambda: {},
                "read_recent_log_lines": lambda: [],
                "config_source": "storage",
            }
        )

        recent = state["recent_requests"]
        self.assertEqual(len(recent), 2)
        self.assertTrue(recent[0]["matches_current_route"])
        self.assertFalse(recent[1]["matches_current_route"])
        self.assertIn(
            recent[0]["current_route_url"],
            {
                "https://integrate.api.nvidia.com/v1#__route=a",
                "https://integrate.api.nvidia.com/v1#__route=b",
            },
        )
        self.assertEqual(recent[1]["current_route_url"], "https://open.juece.cloud/v1/chat/completions")

        routes = {item["route_url"]: item for item in state["route_observability"]}
        self.assertIn("https://integrate.api.nvidia.com/v1#__route=a", routes)
        self.assertIn("https://open.juece.cloud/v1/chat/completions", routes)
        self.assertFalse(routes["https://integrate.api.nvidia.com/v1#__route=a"]["historical_only"])
        self.assertTrue(routes["https://open.juece.cloud/v1/chat/completions"]["historical_only"])
        self.assertEqual(state["config_source"], "storage")

    def test_cached_execution_observability_exposes_upstream_subpath(self):
        execution = build_cached_execution(
            cached_payload={
                "response_body": {"id": "resp_1", "model": "demo"},
                "created_at": 1.0,
                "source": "sqlite",
                "upstream_url": "https://good.example/v1/chat/completions",
                "pool_name": "good",
                "key_index": 1,
                "model_name": "demo",
                "path": "chat/completions",
            },
            request_payload={
                "model": "demo",
                "messages": [{"role": "user", "content": "hi"}],
            },
            request_repairs=0,
            model_candidates=["demo"],
            route_policy={"prompt_cache_mode": "exact"},
            cache_key="cache-key",
        )

        meta = server.build_request_observability_meta(
            execution,
            {"model": "demo", "messages": [{"role": "user", "content": "hi"}]},
        )

        self.assertEqual(meta["upstream_subpath"], "chat/completions")

    def test_dashboard_filters_reserved_example_requests_from_recent_rows(self):
        state = build_dashboard_state(
            {
                "build_runtime_snapshot": lambda: {
                    "model_routing": {
                        "cache_stats": {},
                        "db_label": "mysql://demo",
                    },
                    "config_source": "storage",
                },
                "request_recorder_snapshot": lambda: {
                    "stats": {},
                    "active_requests": [],
                    "recent_requests": [
                        {
                            "request_id": "req-test",
                            "upstream_url": "https://good.example/v1/chat/completions",
                            "pool_name": "good",
                            "status_code": 200,
                        },
                        {
                            "request_id": "req-real",
                            "upstream_url": "https://integrate.api.nvidia.com/v1/chat/completions",
                            "pool_name": "nv",
                            "status_code": 200,
                        },
                    ],
                },
                "route_health": {},
                "upstream_url": "https://integrate.api.nvidia.com/v1#__route=a",
                "upstream_urls": ["https://integrate.api.nvidia.com/v1#__route=a"],
                "proxy_pools": [{"name": "nv", "enabled": True}],
                "log_path": "proxy.log",
                "build_runtime_config_payload": lambda: {
                    "config_source": "storage",
                    "db_label": "mysql://demo",
                },
                "connection_pool_snapshot": lambda: {
                    "urls": {
                        "https://integrate.api.nvidia.com/v1#__route=a": {"pool_name": "nv"},
                    }
                },
                "active_session_affinity_keys": lambda: 0,
                "active_route_affinity_counts": lambda: {},
                "read_recent_log_lines": lambda: [],
                "config_source": "storage",
            }
        )

        recent = state["recent_requests"]
        self.assertEqual(len(recent), 1)
        self.assertEqual(recent[0]["request_id"], "req-real")


if __name__ == "__main__":
    unittest.main()
