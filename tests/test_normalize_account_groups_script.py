import json
import subprocess
import tempfile
import unittest
from pathlib import Path


class NormalizeAccountGroupsScriptTests(unittest.TestCase):
    def test_script_normalizes_membership_and_allowed_groups(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(__file__).resolve().parents[1]
            storage_path = Path(tmpdir) / "local-storage.json"
            payload = {
                "model_route_cache": {"routes": {}, "model_lists": {}, "capabilities": {}},
                "request_history": {},
                "pool_runtime_state": {},
                "app_config": {},
                "admin_accounts": {
                    "acct_1": {
                        "id": "acct_1",
                        "name": "Account 1",
                        "external_key": "user-1",
                        "source_type": "managed",
                        "role": "user",
                        "status": "active",
                        "balance_cents": 0,
                        "concurrency_limit": 1,
                        "allowed_group_ids": ["group_a"],
                        "extra": {},
                        "enabled": True,
                        "note": "",
                    }
                },
                "admin_groups": {
                    "group_a": {
                        "id": "group_a",
                        "name": "Group A",
                        "description": "",
                        "platform": "openai",
                        "is_exclusive": False,
                        "rate_multiplier": 1.0,
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
                        "rate_multiplier": 1.0,
                        "extra": {},
                        "enabled": True,
                        "sort_order": 0,
                    },
                },
                "admin_account_groups": [
                    {"account_id": "acct_1", "group_id": "group_a", "created_at": 1.0},
                    {"account_id": "acct_1", "group_id": "missing_group", "created_at": 1.0},
                ],
                "admin_api_keys": {},
                "admin_subscription_plans": {},
                "admin_account_subscriptions": {
                    "sub_1": {
                        "id": "sub_1",
                        "account_id": "acct_1",
                        "plan_id": "plan_1",
                        "group_id": "group_b",
                        "status": "active",
                        "started_at": 1.0,
                        "expires_at": None,
                        "daily_used": 0,
                        "weekly_used": 0,
                        "monthly_used": 0,
                        "created_at": 1.0,
                        "updated_at": 1.0,
                    }
                },
                "admin_balance_events": {},
                "admin_payment_channels": {},
                "admin_payment_orders": {},
                "admin_payment_webhook_events": {},
                "admin_payment_fulfillment_logs": {},
                "request_cache": {},
                "tool_result_cache": {},
                "interrupted_responses": {},
            }
            storage_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

            subprocess.run(
                [
                    "python",
                    "scripts/normalize_account_groups.py",
                    "--backend",
                    "local",
                    "--local-storage-path",
                    str(storage_path),
                    "--apply",
                ],
                cwd=repo_root,
                check=True,
            )

            updated = json.loads(storage_path.read_text(encoding="utf-8"))
            account = updated["admin_accounts"]["acct_1"]
            membership_rows = updated["admin_account_groups"]
            group_ids = sorted(row["group_id"] for row in membership_rows if row["account_id"] == "acct_1")

            self.assertEqual(account["allowed_group_ids"], ["group_a", "group_b"])
            self.assertEqual(group_ids, ["group_a", "group_b"])


if __name__ == "__main__":
    unittest.main()
