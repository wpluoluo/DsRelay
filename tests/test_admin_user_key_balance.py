import unittest

from local_proxy.admin.service import AdminConsoleService


class FakeUserKeyBalanceStorage:
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
                "concurrency_limit": 1,
                "allowed_group_ids": ["group_a"],
                "extra": {},
                "enabled": True,
                "note": "",
            }
        }
        self.groups = {
            "group_a": {
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
            "group_b": {
                "id": "group_b",
                "name": "Group B",
                "description": "",
                "platform": "openai",
                "is_exclusive": False,
                "rate_multiplier": 1,
                "extra": {},
                "enabled": True,
                "sort_order": 0,
            },
        }
        self.memberships = {"acct_a": {"group_a"}}
        self.keys = {}
        self.balance_events = []

    def list_admin_accounts(self):
        return list(self.accounts.values())

    def get_admin_account(self, account_id):
        return dict(self.accounts.get(account_id, {}))

    def upsert_admin_account(self, payload):
        self.accounts[payload["id"]] = dict(payload)
        return dict(payload)

    def list_admin_groups(self):
        return list(self.groups.values())

    def get_admin_group(self, group_id):
        return dict(self.groups.get(group_id, {}))

    def list_admin_account_groups(self):
        rows = []
        for account_id, group_ids in self.memberships.items():
            for group_id in group_ids:
                rows.append({"account_id": account_id, "group_id": group_id, "created_at": 1.0})
        return rows

    def replace_admin_account_groups(self, account_id, group_ids):
        self.memberships[account_id] = set(group_ids)

    def list_admin_api_keys(self):
        return list(self.keys.values())

    def get_admin_api_key(self, key_id):
        return dict(self.keys.get(key_id, {}))

    def upsert_admin_api_key(self, payload):
        item = dict(payload)
        group_id = item.get("group_id") or ""
        item["group_name"] = self.groups.get(group_id, {}).get("name", "")
        self.keys[item["id"]] = item
        return dict(item)

    def list_admin_account_subscriptions(self):
        return []

    def get_active_subscription_context_for_account(self, account_id, group_id=""):
        if account_id != "acct_a" or group_id not in {"", "group_a"}:
            return {}
        return {
            "subscription_id": "sub_a",
            "account_id": "acct_a",
            "plan_id": "plan_a",
            "group_id": "group_a",
            "status": "active",
            "plan_name": "Plan A",
            "group_name": "Group A",
            "expires_at": None,
            "plan_price_cents": 1000,
        }

    def adjust_admin_account_balance(self, account_id, amount_cents, **kwargs):
        account = self.accounts[account_id]
        before = int(account.get("balance_cents") or 0)
        after = before + int(amount_cents)
        if after < 0:
            raise ValueError("insufficient balance")
        account["balance_cents"] = after
        event = {
            "id": f"event_{len(self.balance_events) + 1}",
            "account_id": account_id,
            "event_type": kwargs.get("event_type"),
            "amount_cents": amount_cents,
            "before_balance_cents": before,
            "after_balance_cents": after,
            "note": kwargs.get("note", ""),
            "created_at": 1.0 + len(self.balance_events),
        }
        self.balance_events.append(event)
        return dict(event)

    def list_admin_balance_events(self, account_id=None, limit=200):
        rows = [item for item in self.balance_events if not account_id or item["account_id"] == account_id]
        return rows[:limit]


class AdminUserKeyBalanceTests(unittest.TestCase):
    def test_api_key_group_is_validated_and_returned(self):
        storage = FakeUserKeyBalanceStorage()
        service = AdminConsoleService(storage=storage)

        result = service.create_api_key({"account_id": "acct_a", "name": "Key A", "group_id": "group_a"})

        self.assertTrue(result["ok"])
        self.assertEqual(result["item"]["group_id"], "group_a")
        self.assertEqual(result["item"]["group_name"], "Group A")

    def test_api_key_group_must_be_allowed_for_user(self):
        storage = FakeUserKeyBalanceStorage()
        service = AdminConsoleService(storage=storage)

        with self.assertRaises(ValueError):
            service.create_api_key({"account_id": "acct_a", "name": "Key B", "group_id": "group_b"})

    def test_balance_adjustment_records_events(self):
        storage = FakeUserKeyBalanceStorage()
        service = AdminConsoleService(storage=storage)

        result = service.adjust_user_balance("acct_a", {"operation": "withdraw", "amount_cents": 300, "note": "manual"})
        history = service.list_user_balance_events("acct_a")

        self.assertTrue(result["ok"])
        self.assertEqual(result["item"]["balance_cents"], 700)
        self.assertEqual(result["event"]["amount_cents"], -300)
        self.assertEqual(history["total"], 1)
        self.assertEqual(history["items"][0]["after_balance_cents"], 700)

    def test_subscription_status_reads_subscription_id(self):
        storage = FakeUserKeyBalanceStorage()
        service = AdminConsoleService(storage=storage)

        status = service._get_account_subscription_status("acct_a")

        self.assertTrue(status["subscription_active"])
        self.assertEqual(status["active_subscription_id"], "sub_a")


if __name__ == "__main__":
    unittest.main()
