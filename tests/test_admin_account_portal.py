import unittest

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
            }
        }
        self.app_config = {
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
                        "content": '{"user_id":"acct_a","aff_code":"AFFUSERA","amount_cents":250}',
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
            }
        ]

    def list_admin_account_groups(self):
        return [{"account_id": "acct_a", "group_id": "group_a"}]

    def list_admin_subscription_plans(self):
        return []

    def list_admin_account_subscriptions(self):
        return []

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


if __name__ == "__main__":
    unittest.main()
