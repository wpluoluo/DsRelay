import unittest

from local_proxy.account.service import AccountPortalService
from local_proxy.admin.service import AdminConsoleService


class FakeAccountPortalStorage:
    def __init__(self):
        self.accounts = {
            "acct_a": {
                "id": "acct_a",
                "name": "Account A",
                "external_key": "user-a",
                "source_type": "managed",
                "role": "user",
                "status": "active",
                "balance_cents": 1000,
                "concurrency_limit": 2,
                "allowed_group_ids": ["group_a"],
                "extra": {},
                "enabled": True,
                "note": "",
            },
            "acct_b": {
                "id": "acct_b",
                "name": "Account B",
                "external_key": "user-b",
                "source_type": "managed",
                "role": "user",
                "status": "active",
                "balance_cents": 2000,
                "concurrency_limit": 1,
                "allowed_group_ids": ["group_b"],
                "extra": {},
                "enabled": True,
                "note": "",
            }
        }
        self.app_config = {
            "admin_channels": {
                "items": [
                    {
                        "id": "channel_a",
                        "name": "Channel A",
                        "description": "",
                        "platform": "openai",
                        "group_ids": ["group_a"],
                        "model_pricing": [{"model": "model-a", "input_price": 1, "output_price": 2}],
                        "enabled": True,
                    },
                    {
                        "id": "channel_b",
                        "name": "Channel B",
                        "description": "",
                        "platform": "openai",
                        "group_ids": ["group_b"],
                        "model_pricing": [{"model": "model-b", "input_price": 1, "output_price": 2}],
                        "enabled": True,
                    },
                    {
                        "id": "channel_public",
                        "name": "Public Channel",
                        "description": "",
                        "platform": "openai",
                        "group_ids": [],
                        "model_pricing": [{"model": "model-public", "input_price": 1, "output_price": 2}],
                        "enabled": True,
                    },
                ],
            },
            "admin_content:redeem-codes": {
                "items": [
                    {
                        "id": "redeem_a",
                        "title": "CODE100",
                        "status": "active",
                        "summary": '{"type":"balance","amount_cents":500}',
                        "content": "",
                        "note": "",
                        "created_at": 1.0,
                        "updated_at": 1.0,
                    }
                ]
            },
            "admin_content:affiliate-rebates": {
                "items": [
                    {
                        "id": "rebate_a",
                        "title": "AFFUSERA rebate",
                        "status": "active",
                        "summary": "250",
                        "content": '{"account_id":"acct_a","aff_code":"AFFUSERA","amount_cents":250}',
                        "note": "",
                        "created_at": 1.0,
                        "updated_at": 1.0,
                    }
                ]
            },
            "admin_content:affiliate-invites": {"items": []},
            "admin_content:affiliate-transfers": {"items": []},
        }
        self.balance_events = []
        self.api_keys = {
            "key_a": {"id": "key_a", "account_id": "acct_a", "name": "Key A", "key_preview": "sk-a", "enabled": True},
            "key_b": {"id": "key_b", "account_id": "acct_b", "name": "Key B", "key_preview": "sk-b", "enabled": True},
        }
        self.payment_orders = {
            "order_a": {"id": "order_a", "account_id": "acct_a", "plan_id": "plan_a", "amount_cents": 1000, "status": "pending"},
            "order_b": {"id": "order_b", "account_id": "acct_b", "plan_id": "plan_b", "amount_cents": 2000, "status": "pending"},
        }
        self.recent_requests = [
            {
                "request_id": "req_a",
                "proxy_consumer_id": "user-a",
                "proxy_consumer_name": "Account A",
                "proxy_consumer_type": "managed",
                "proxy_api_key_id": "key_a",
                "logical_model": "model-a",
                "prompt_tokens": 10,
                "completion_tokens": 3,
            },
            {
                "request_id": "req_b",
                "proxy_consumer_id": "user-b",
                "proxy_consumer_name": "Account B",
                "proxy_consumer_type": "managed",
                "proxy_api_key_id": "key_b",
                "logical_model": "model-b",
                "prompt_tokens": 20,
                "completion_tokens": 4,
            },
        ]

    def get_admin_account(self, account_id):
        return dict(self.accounts.get(account_id, {}))

    def upsert_admin_account(self, payload):
        self.accounts[payload["id"]] = dict(payload)
        return dict(payload)

    def list_admin_accounts(self):
        return list(self.accounts.values())

    def list_admin_groups(self):
        return [
            {
                "id": "group_a",
                "name": "Group A",
                "description": "",
                "platform": "openai",
                "is_exclusive": False,
                "rate_multiplier": 1,
                "extra": {},
                "enabled": True,
                "sort_order": 0,
            },
            {
                "id": "group_b",
                "name": "Group B",
                "description": "",
                "platform": "openai",
                "is_exclusive": False,
                "rate_multiplier": 1,
                "extra": {},
                "enabled": True,
                "sort_order": 0,
            }
        ]

    def list_admin_account_groups(self):
        return [{"account_id": "acct_a", "group_id": "group_a"}, {"account_id": "acct_b", "group_id": "group_b"}]

    def list_admin_subscription_plans(self):
        return []

    def list_admin_account_subscriptions(self):
        return []

    def list_admin_api_keys(self):
        return list(self.api_keys.values())

    def get_admin_api_key(self, key_id):
        return dict(self.api_keys.get(key_id, {}))

    def upsert_admin_api_key(self, payload):
        item = dict(payload)
        group_id = item.get("group_id") or ""
        group_name = ""
        for group in self.list_admin_groups():
            if group.get("id") == group_id:
                group_name = group.get("name", "")
                break
        item["group_name"] = group_name
        self.api_keys[item["id"]] = item
        return dict(item)

    def list_admin_payment_orders(self):
        return list(self.payment_orders.values())

    def get_admin_payment_order(self, order_id):
        return dict(self.payment_orders.get(order_id, {}))

    def list_payment_fulfillment_logs(self, order_id):
        return []

    def list_admin_payment_channels(self):
        return []

    def load_recent_requests(self, limit=5000):
        return self.recent_requests[:limit]

    def get_active_subscription_context_for_account(self, account_id, group_id=""):
        return {}

    def load_app_config(self, key):
        return self.app_config.get(key, {})

    def save_app_config(self, payload, key="runtime_config"):
        self.app_config[key] = payload

    def adjust_admin_account_balance(self, account_id, amount_cents, **kwargs):
        account = self.accounts[account_id]
        before = int(account.get("balance_cents") or 0)
        after = before + int(amount_cents)
        account["balance_cents"] = after
        event = {
            "id": f"bal_{len(self.balance_events) + 1}",
            "account_id": account_id,
            "event_type": kwargs.get("event_type"),
            "amount_cents": amount_cents,
            "before_balance_cents": before,
            "after_balance_cents": after,
            "note": kwargs.get("note", ""),
            "actor_type": kwargs.get("actor_type", ""),
            "actor_id": kwargs.get("actor_id", ""),
            "created_at": 2.0 + len(self.balance_events),
        }
        self.balance_events.append(event)
        return dict(event)

    def list_admin_balance_events(self, account_id=None, limit=200):
        return [item for item in self.balance_events if not account_id or item["account_id"] == account_id][:limit]


class AdminAccountPortalTests(unittest.TestCase):
    def test_redeem_code_adds_balance_and_marks_code_used(self):
        storage = FakeAccountPortalStorage()
        service = AdminConsoleService(storage=storage)

        result = service.redeem_account_code("acct_a", {"code": "CODE100"})
        profile = service.account_redeem_profile("acct_a")
        code_items = storage.app_config["admin_content:redeem-codes"]["items"]

        self.assertTrue(result["ok"])
        self.assertEqual(result["balance_cents"], 1500)
        self.assertEqual(profile["history"][0]["amount_cents"], 500)
        self.assertEqual(code_items[0]["status"], "used")

    def test_affiliate_transfer_moves_available_quota_to_balance(self):
        storage = FakeAccountPortalStorage()
        storage.accounts["acct_a"]["extra"] = {"aff_code": "AFFUSERA"}
        service = AdminConsoleService(storage=storage)

        detail = service.account_affiliate_detail("acct_a")
        result = service.transfer_account_affiliate_quota("acct_a")
        refreshed = service.account_affiliate_detail("acct_a")

        self.assertEqual(detail["aff_quota_cents"], 250)
        self.assertTrue(result["ok"])
        self.assertEqual(result["transferred_cents"], 250)
        self.assertEqual(storage.accounts["acct_a"]["balance_cents"], 1250)
        self.assertEqual(refreshed["aff_quota_cents"], 0)

    def test_account_portal_filters_current_account_resources(self):
        storage = FakeAccountPortalStorage()
        admin_service = AdminConsoleService(storage=storage)
        service = AccountPortalService(admin_service)

        keys = service.list_api_keys("acct_a")
        orders = service.list_orders("acct_a")
        usage = service.list_usage("acct_a")

        self.assertEqual([item["id"] for item in keys["items"]], ["key_a"])
        self.assertEqual([item["id"] for item in orders["items"]], ["order_a"])
        self.assertEqual([item["request_id"] for item in usage["items"]], ["req_a"])
        self.assertEqual([item["id"] for item in keys["items"]], ["key_a"])
        self.assertEqual(keys["items"][0]["account_name"], "Account A")

    def test_account_portal_filters_channels_by_visible_groups(self):
        storage = FakeAccountPortalStorage()
        admin_service = AdminConsoleService(storage=storage)
        service = AccountPortalService(admin_service)

        channels = service.list_channels("acct_a")

        self.assertEqual([item["id"] for item in channels["items"]], ["channel_a", "channel_public"])

    def test_account_without_allowed_groups_can_still_list_all_groups(self):
        storage = FakeAccountPortalStorage()
        storage.accounts["acct_a"]["allowed_group_ids"] = []
        admin_service = AdminConsoleService(storage=storage)
        service = AccountPortalService(admin_service)

        groups = service.list_groups("acct_a")

        self.assertEqual([item["id"] for item in groups["items"]], ["group_a", "group_b"])

    def test_account_without_allowed_groups_can_create_key_for_existing_group(self):
        storage = FakeAccountPortalStorage()
        storage.accounts["acct_a"]["allowed_group_ids"] = []
        admin_service = AdminConsoleService(storage=storage)
        service = AccountPortalService(admin_service)

        created = service.create_api_key("acct_a", {"name": "Key C", "group_id": "group_b", "enabled": True})

        self.assertTrue(created["ok"])
        self.assertEqual(created["item"]["account_id"], "acct_a")
        self.assertEqual(created["item"]["group_id"], "group_b")
        self.assertEqual(created["item"]["group_name"], "Group B")

    def test_account_groups_are_loaded_from_storage_without_admin_analytics_shape(self):
        storage = FakeAccountPortalStorage()
        admin_service = AdminConsoleService(storage=storage)
        service = AccountPortalService(admin_service)

        groups = service.list_groups("acct_a")

        self.assertEqual(groups["total"], 1)
        self.assertEqual(groups["items"][0]["id"], "group_a")
        self.assertEqual(groups["items"][0]["name"], "Group A")


if __name__ == "__main__":
    unittest.main()
