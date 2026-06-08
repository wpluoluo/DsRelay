import unittest

from local_proxy.admin.service import AdminConsoleService


class FakeSub2AlignmentStorage:
    def load_app_config(self, key):
        if key != "runtime_config":
            return {}
        return {
            "pools": [
                {
                    "name": "nv",
                    "enabled": True,
                    "priority": 20,
                    "urls": ["https://a.example/v1", "https://b.example/v1"],
                    "keys": [{"key": "sk-a"}, {"key": ""}],
                    "route_policy": {
                        "text_upstream_protocol": "openai",
                        "route_cooldown_seconds": 30,
                        "rate_limit_retry_attempts": 3,
                    },
                    "supported_models_text": "deepseek-v4-flash",
                    "model_aliases_text": "deepseek-v4-flash=deepseek-ai/deepseek-v4-flash",
                }
            ]
        }

    def load_recent_requests(self, limit=5000):
        return [
            {
                "route_url": "https://a.example/v1",
                "pool_name": "nv",
                "status_code": 200,
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
                "input_bytes": 100,
                "bytes_sent": 50,
                "resolved_model": "deepseek-v4-flash",
                "started_at": "2026-06-08T01:00:00",
                "proxy_consumer_id": "user-a",
                "proxy_consumer_name": "User A",
                "proxy_consumer_type": "managed",
            },
            {
                "route_url": "https://b.example/v1",
                "pool_name": "nv",
                "status_code": 502,
                "error": "upstream reset",
                "prompt_tokens": 20,
                "completion_tokens": 0,
                "total_tokens": 20,
                "input_bytes": 200,
                "bytes_sent": 0,
                "resolved_model": "deepseek-v4-flash",
                "started_at": "2026-06-08T01:01:00",
                "proxy_consumer_id": "user-b",
                "proxy_consumer_name": "User B",
                "proxy_consumer_type": "managed",
            },
        ]

    def list_admin_accounts(self):
        return [
            {"id": "acct-a", "name": "Account A", "external_key": "user-a", "enabled": True, "status": "active", "extra": {}},
            {"id": "acct-b", "name": "Account B", "external_key": "user-b", "enabled": False, "status": "disabled", "extra": {}},
        ]

    def list_admin_groups(self):
        return [
            {
                "id": "group-a",
                "name": "Group A",
                "description": "",
                "platform": "openai",
                "is_exclusive": True,
                "rate_multiplier": 1.5,
                "extra": {"subscription_type": "subscription", "daily_limit_usd": 10, "rpm_limit": 60},
                "enabled": True,
                "sort_order": 0,
            }
        ]

    def list_admin_account_groups(self):
        return [
            {"account_id": "acct-a", "group_id": "group-a"},
            {"account_id": "acct-b", "group_id": "group-a"},
        ]

    def list_admin_account_subscriptions(self):
        return [
            {"id": "sub-a", "account_id": "acct-a", "group_id": "group-a", "status": "active"},
            {"id": "sub-b", "account_id": "acct-b", "group_id": "group-a", "status": "revoked"},
        ]


class AdminSub2AlignmentTests(unittest.TestCase):
    def test_provider_accounts_are_grouped_by_pool_not_route(self):
        service = AdminConsoleService(storage=FakeSub2AlignmentStorage())

        payload = service.list_provider_accounts()

        self.assertEqual(payload["total"], 1)
        item = payload["items"][0]
        self.assertEqual(item["pool_name"], "nv")
        self.assertEqual(item["route_count"], 2)
        self.assertEqual(item["request_count"], 2)
        self.assertEqual(item["error_count"], 1)
        self.assertEqual(item["key_count"], 1)
        self.assertEqual(item["protocol"], "openai")
        self.assertEqual(item["models"], ["deepseek-v4-flash"])

    def test_groups_expose_sub2_account_and_subscription_metrics(self):
        service = AdminConsoleService(storage=FakeSub2AlignmentStorage())

        payload = service.list_groups()

        item = payload["items"][0]
        self.assertEqual(item["id"], "group-a")
        self.assertEqual(item["subscription_type"], "subscription")
        self.assertEqual(item["daily_limit_usd"], 10)
        self.assertEqual(item["rpm_limit"], 60)
        self.assertEqual(item["account_count"], 2)
        self.assertEqual(item["active_account_count"], 1)
        self.assertEqual(item["rate_limited_account_count"], 1)
        self.assertEqual(item["subscription_count"], 2)
        self.assertEqual(item["active_subscription_count"], 1)


if __name__ == "__main__":
    unittest.main()
