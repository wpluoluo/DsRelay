from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from local_proxy.platform.validation import normalize_admin_account_payload
from local_proxy.storage import ProxyStorage
from local_proxy.storage_local import LocalProxyStorage


def _load_env_file(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    if not path.exists():
        return result
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in raw_line:
            continue
        key, value = raw_line.split("=", 1)
        result[key.strip()] = value
    return result


def _build_storage(args: argparse.Namespace):
    if args.backend == "local":
        return LocalProxyStorage(args.local_storage_path)
    if args.backend == "mysql":
        return ProxyStorage(
            {
                "host": args.db_host,
                "port": args.db_port,
                "user": args.db_user,
                "password": args.db_password,
                "database": args.db_name,
            }
        )

    env = _load_env_file(Path(args.env_file))
    db_host = (env.get("STORAGE_DB_HOST") or os.getenv("STORAGE_DB_HOST") or "").strip()
    if db_host:
        return ProxyStorage(
            {
                "host": db_host,
                "port": int(env.get("STORAGE_DB_PORT") or os.getenv("STORAGE_DB_PORT") or "3306"),
                "user": env.get("STORAGE_DB_USER") or os.getenv("STORAGE_DB_USER") or "",
                "password": env.get("STORAGE_DB_PASSWORD") or os.getenv("STORAGE_DB_PASSWORD") or "",
                "database": env.get("STORAGE_DB_NAME") or os.getenv("STORAGE_DB_NAME") or "",
            }
        )
    return LocalProxyStorage(args.local_storage_path)


def _normalize_group_ids(values, valid_group_ids: set[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in values or []:
        value = str(raw or "").strip()
        if not value or value in seen or value not in valid_group_ids:
            continue
        normalized.append(value)
        seen.add(value)
    return normalized


def main() -> int:
    parser = argparse.ArgumentParser(description="Normalize account/group relations in storage truth.")
    parser.add_argument("--backend", choices=("auto", "mysql", "local"), default="auto")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--local-storage-path", default=str(Path("var/data/local-storage.json")))
    parser.add_argument("--db-host", default="")
    parser.add_argument("--db-port", type=int, default=3306)
    parser.add_argument("--db-user", default="")
    parser.add_argument("--db-password", default="")
    parser.add_argument("--db-name", default="")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    storage = _build_storage(args)
    groups = {
        str(item.get("id") or "").strip(): item
        for item in storage.list_admin_groups()
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    }
    valid_group_ids = set(groups.keys())
    membership_rows = storage.list_admin_account_groups()
    raw_memberships: dict[str, set[str]] = {}
    memberships: dict[str, set[str]] = {}
    for row in membership_rows:
        account_id = str(row.get("account_id") or "").strip()
        group_id = str(row.get("group_id") or "").strip()
        if not account_id:
            continue
        raw_memberships.setdefault(account_id, set()).add(group_id)
        if group_id not in valid_group_ids:
            continue
        memberships.setdefault(account_id, set()).add(group_id)

    active_subscription_groups: dict[str, set[str]] = {}
    for row in storage.list_admin_account_subscriptions():
        if not isinstance(row, dict):
            continue
        if str(row.get("status") or "").strip() != "active":
            continue
        group_id = str(row.get("group_id") or "").strip()
        if group_id not in valid_group_ids:
            continue
        account_id = str(row.get("account_id") or "").strip()
        if not account_id:
            continue
        active_subscription_groups.setdefault(account_id, set()).add(group_id)

    report: list[dict] = []
    for account in storage.list_admin_accounts():
        if not isinstance(account, dict):
            continue
        account_id = str(account.get("id") or "").strip()
        if not account_id:
            continue
        original_allowed = account.get("allowed_group_ids") if isinstance(account.get("allowed_group_ids"), list) else []
        normalized_allowed = _normalize_group_ids(original_allowed, valid_group_ids)
        raw_membership_group_ids = raw_memberships.get(account_id, set())
        membership_group_ids = memberships.get(account_id, set())
        active_group_ids = active_subscription_groups.get(account_id, set())
        next_membership_group_ids = sorted(set(membership_group_ids) | set(active_group_ids))
        next_allowed_group_ids = normalized_allowed
        if normalized_allowed:
            next_allowed_group_ids = sorted(set(normalized_allowed) | set(next_membership_group_ids))

        changed_memberships = sorted(group_id for group_id in raw_membership_group_ids if group_id) != next_membership_group_ids
        changed_allowed = normalized_allowed != next_allowed_group_ids or original_allowed != normalized_allowed
        if not changed_memberships and not changed_allowed:
            continue

        report.append(
            {
                "account_id": account_id,
                "memberships_before": sorted(membership_group_ids),
                "memberships_after": next_membership_group_ids,
                "allowed_before": normalized_allowed,
                "allowed_after": next_allowed_group_ids,
            }
        )

        if not args.apply:
            continue

        if changed_memberships:
            storage.replace_admin_account_groups(account_id, next_membership_group_ids)
        if changed_allowed:
            updated_account = normalize_admin_account_payload(
                {
                    **account,
                    "allowed_group_ids": next_allowed_group_ids,
                }
            )
            storage.upsert_admin_account(updated_account)

    print(
        json.dumps(
            {
                "ok": True,
                "apply": args.apply,
                "backend": args.backend,
                "changed_accounts": len(report),
                "items": report,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
