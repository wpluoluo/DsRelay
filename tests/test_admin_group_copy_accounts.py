import unittest

from local_proxy.admin.service import AdminConsoleService


class FakeGroupStorage:
    def __init__(self):
        self.groups = {
            "source": {
                "id": "source",
                "name": "Source",
                "description": "",
                "platform": "openai",
                "is_exclusive": False,
                "rate_multiplier": 1,
                "extra": {},
                "enabled": True,
                "sort_order": 0,
            },
        }
        self.memberships = {
            "acct_a": {"source"},
            "acct_b": {"source", "other"},
            "acct_c": {"other"},
        }

    def list_admin_groups(self):
        return list(self.groups.values())

    def upsert_admin_group(self, payload):
        self.groups[payload["id"]] = dict(payload)
        return dict(payload)

    def list_admin_account_groups(self):
        rows = []
        for account_id, group_ids in self.memberships.items():
            for group_id in group_ids:
                rows.append({"account_id": account_id, "group_id": group_id, "created_at": 1.0})
        return rows

    def replace_admin_account_groups(self, account_id, group_ids):
        self.memberships[account_id] = set(group_ids)


class AdminGroupCopyAccountsTests(unittest.TestCase):
    def test_upsert_group_copies_memberships_from_selected_source_groups(self):
        storage = FakeGroupStorage()
        service = AdminConsoleService(storage=storage)

        result = service.upsert_group(
            {
                "id": "target",
                "name": "Target",
                "platform": "openai",
                "copy_accounts_from_group_ids": ["source"],
            }
        )

        self.assertTrue(result["ok"])
        self.assertIn("target", storage.memberships["acct_a"])
        self.assertIn("target", storage.memberships["acct_b"])
        self.assertNotIn("target", storage.memberships["acct_c"])
        self.assertNotIn("copy_accounts_from_group_ids", storage.groups["target"].get("extra", {}))


if __name__ == "__main__":
    unittest.main()
