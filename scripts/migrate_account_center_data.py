from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from local_proxy.storage import ProxyStorage
from local_proxy.storage_local import LocalProxyStorage


def build_local_storage(path: str) -> LocalProxyStorage:
    return LocalProxyStorage(path)


def build_mysql_storage(host: str, port: int, user: str, password: str, database: str) -> ProxyStorage:
    return ProxyStorage(
        {
            "host": host,
            "port": port,
            "user": user,
            "password": password,
            "database": database,
        }
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate account-center truth from local storage into MySQL.")
    parser.add_argument("--source-local-storage-path", default=str(Path("var/data/local-storage.json")))
    parser.add_argument("--db-host", required=True)
    parser.add_argument("--db-port", type=int, default=3306)
    parser.add_argument("--db-user", required=True)
    parser.add_argument("--db-password", required=True)
    parser.add_argument("--db-name", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    source = build_local_storage(args.source_local_storage_path)
    target = build_mysql_storage(args.db_host, args.db_port, args.db_user, args.db_password, args.db_name)

    groups = source.list_admin_groups()
    accounts = source.list_admin_accounts()
    memberships = source.list_admin_account_groups()
    api_keys = source.list_admin_api_keys()
    plans = source.list_admin_subscription_plans()
    subscriptions = source.list_admin_account_subscriptions()
    payment_channels = source.list_admin_payment_channels()

    summary = {
        "groups": len(groups),
        "accounts": len(accounts),
        "memberships": len(memberships),
        "api_keys": len(api_keys),
        "plans": len(plans),
        "subscriptions": len(subscriptions),
        "payment_channels": len(payment_channels),
        "apply": args.apply,
    }

    if args.apply:
        for group in groups:
            target.upsert_admin_group(group)

        for account in accounts:
            target.upsert_admin_account(account)

        membership_map: dict[str, list[str]] = {}
        for row in memberships:
            account_id = str(row.get("account_id") or "").strip()
            group_id = str(row.get("group_id") or "").strip()
            if not account_id or not group_id:
                continue
            membership_map.setdefault(account_id, [])
            if group_id not in membership_map[account_id]:
                membership_map[account_id].append(group_id)
        for account_id, group_ids in membership_map.items():
            target.replace_admin_account_groups(account_id, group_ids)

        for key in api_keys:
            target.upsert_admin_api_key(key)

        for plan in plans:
            target.upsert_admin_subscription_plan(plan)

        for subscription in subscriptions:
            target.upsert_admin_account_subscription(subscription)

        for channel in payment_channels:
            target.upsert_admin_payment_channel(channel)

    print(json.dumps({"ok": True, "summary": summary}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
