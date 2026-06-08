import json
import time
import uuid

import pymysql


def _build_conn(conn_config: dict):
    return pymysql.connect(
        host=conn_config["host"],
        port=conn_config["port"],
        user=conn_config["user"],
        password=conn_config["password"],
        database=conn_config["database"],
        charset="utf8mb4",
        connect_timeout=5,
        read_timeout=10,
        write_timeout=10,
    )


class ProxyStorage:
    def __init__(self, conn_config: dict):
        self._cfg = dict(conn_config)
        self.init_schema()

    def _connect(self):
        return _build_conn(self._cfg)

    def init_schema(self) -> None:
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS model_route_cache (
                        logical_key VARCHAR(128) NOT NULL,
                        route_url VARCHAR(500) NOT NULL,
                        model_key VARCHAR(128) NOT NULL,
                        entry_json MEDIUMTEXT NOT NULL,
                        expires_at DOUBLE NOT NULL,
                        updated_at DOUBLE NOT NULL,
                        PRIMARY KEY (logical_key, route_url, model_key)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS model_list_cache (
                        cache_key VARCHAR(512) PRIMARY KEY,
                        models_json MEDIUMTEXT NOT NULL,
                        fetched_at DOUBLE NOT NULL,
                        expires_at DOUBLE NOT NULL
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS model_capability_cache (
                        logical_key VARCHAR(128) NOT NULL,
                        route_url VARCHAR(500) NOT NULL,
                        model_key VARCHAR(128) NOT NULL,
                        entry_json MEDIUMTEXT NOT NULL,
                        expires_at DOUBLE NOT NULL,
                        updated_at DOUBLE NOT NULL,
                        PRIMARY KEY (logical_key, route_url, model_key)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS request_history (
                        request_id VARCHAR(64) PRIMARY KEY,
                        started_at VARCHAR(32),
                        created_at DOUBLE NOT NULL,
                        meta_json MEDIUMTEXT NOT NULL,
                        INDEX idx_request_history_created_at (created_at)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS pool_runtime_state (
                        state_key VARCHAR(128) PRIMARY KEY,
                        state_json MEDIUMTEXT NOT NULL,
                        updated_at DOUBLE NOT NULL
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS app_config (
                        config_key VARCHAR(128) PRIMARY KEY,
                        config_json MEDIUMTEXT NOT NULL,
                        updated_at DOUBLE NOT NULL
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS admin_accounts (
                        id VARCHAR(64) PRIMARY KEY,
                        name VARCHAR(128) NOT NULL,
                        external_key VARCHAR(128) NOT NULL,
                        source_type VARCHAR(32) NOT NULL,
                        role_name VARCHAR(32) NOT NULL DEFAULT 'user',
                        status VARCHAR(32) NOT NULL DEFAULT 'active',
                        balance_cents BIGINT NOT NULL DEFAULT 0,
                        concurrency_limit INT NOT NULL DEFAULT 0,
                        allowed_group_ids_json MEDIUMTEXT NULL,
                        extra_json MEDIUMTEXT NULL,
                        enabled TINYINT(1) NOT NULL DEFAULT 1,
                        note TEXT NULL,
                        created_at DOUBLE NOT NULL,
                        updated_at DOUBLE NOT NULL,
                        UNIQUE KEY uniq_admin_accounts_external_key (external_key)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS admin_groups (
                        id VARCHAR(64) PRIMARY KEY,
                        name VARCHAR(128) NOT NULL,
                        description_text TEXT NULL,
                        platform VARCHAR(32) NOT NULL DEFAULT '',
                        is_exclusive TINYINT(1) NOT NULL DEFAULT 0,
                        rate_multiplier DOUBLE NOT NULL DEFAULT 1,
                        extra_json MEDIUMTEXT NULL,
                        enabled TINYINT(1) NOT NULL DEFAULT 1,
                        sort_order INT NOT NULL DEFAULT 0,
                        created_at DOUBLE NOT NULL,
                        updated_at DOUBLE NOT NULL
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """
                )
                try:
                    cur.execute("ALTER TABLE admin_accounts ADD COLUMN role_name VARCHAR(32) NOT NULL DEFAULT 'user' AFTER source_type")
                except Exception:
                    pass
                try:
                    cur.execute("ALTER TABLE admin_accounts ADD COLUMN status VARCHAR(32) NOT NULL DEFAULT 'active' AFTER role_name")
                except Exception:
                    pass
                try:
                    cur.execute("ALTER TABLE admin_accounts ADD COLUMN balance_cents BIGINT NOT NULL DEFAULT 0 AFTER status")
                except Exception:
                    pass
                try:
                    cur.execute("ALTER TABLE admin_accounts ADD COLUMN concurrency_limit INT NOT NULL DEFAULT 0 AFTER balance_cents")
                except Exception:
                    pass
                try:
                    cur.execute("ALTER TABLE admin_accounts ADD COLUMN allowed_group_ids_json MEDIUMTEXT NULL AFTER concurrency_limit")
                except Exception:
                    pass
                try:
                    cur.execute("ALTER TABLE admin_accounts ADD COLUMN extra_json MEDIUMTEXT NULL AFTER allowed_group_ids_json")
                except Exception:
                    pass
                try:
                    cur.execute("ALTER TABLE admin_groups ADD COLUMN platform VARCHAR(32) NOT NULL DEFAULT '' AFTER description_text")
                except Exception:
                    pass
                try:
                    cur.execute("ALTER TABLE admin_groups ADD COLUMN is_exclusive TINYINT(1) NOT NULL DEFAULT 0 AFTER platform")
                except Exception:
                    pass
                try:
                    cur.execute("ALTER TABLE admin_groups ADD COLUMN rate_multiplier DOUBLE NOT NULL DEFAULT 1 AFTER is_exclusive")
                except Exception:
                    pass
                try:
                    cur.execute("ALTER TABLE admin_groups ADD COLUMN extra_json MEDIUMTEXT NULL AFTER rate_multiplier")
                except Exception:
                    pass
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS admin_account_groups (
                        account_id VARCHAR(64) NOT NULL,
                        group_id VARCHAR(64) NOT NULL,
                        created_at DOUBLE NOT NULL,
                        PRIMARY KEY (account_id, group_id),
                        INDEX idx_admin_account_groups_group_id (group_id)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS admin_api_keys (
                        id VARCHAR(64) PRIMARY KEY,
                        account_id VARCHAR(64) NOT NULL,
                        group_id VARCHAR(64) NULL,
                        name VARCHAR(128) NOT NULL,
                        key_hash VARCHAR(128) NOT NULL,
                        key_preview VARCHAR(64) NOT NULL,
                        enabled TINYINT(1) NOT NULL DEFAULT 1,
                        last_used_at DOUBLE NULL,
                        created_at DOUBLE NOT NULL,
                        updated_at DOUBLE NOT NULL,
                        INDEX idx_admin_api_keys_account_id (account_id),
                        INDEX idx_admin_api_keys_group_id (group_id),
                        UNIQUE KEY uniq_admin_api_keys_hash (key_hash)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """
                )
                try:
                    cur.execute("ALTER TABLE admin_api_keys ADD COLUMN group_id VARCHAR(64) NULL AFTER account_id")
                except Exception:
                    pass
                try:
                    cur.execute("ALTER TABLE admin_api_keys ADD INDEX idx_admin_api_keys_group_id (group_id)")
                except Exception:
                    pass
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS admin_subscription_plans (
                        id VARCHAR(64) PRIMARY KEY,
                        name VARCHAR(128) NOT NULL,
                        group_id VARCHAR(64) NULL,
                        price_cents INT NOT NULL DEFAULT 0,
                        validity_days INT NOT NULL DEFAULT 30,
                        daily_limit INT NOT NULL DEFAULT 0,
                        weekly_limit INT NOT NULL DEFAULT 0,
                        monthly_limit INT NOT NULL DEFAULT 0,
                        enabled TINYINT(1) NOT NULL DEFAULT 1,
                        note TEXT NULL,
                        created_at DOUBLE NOT NULL,
                        updated_at DOUBLE NOT NULL
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS admin_balance_events (
                        id VARCHAR(64) PRIMARY KEY,
                        account_id VARCHAR(64) NOT NULL,
                        event_type VARCHAR(32) NOT NULL,
                        amount_cents BIGINT NOT NULL,
                        before_balance_cents BIGINT NOT NULL,
                        after_balance_cents BIGINT NOT NULL,
                        note TEXT NULL,
                        actor_type VARCHAR(32) NOT NULL DEFAULT 'admin',
                        actor_id VARCHAR(128) NULL,
                        created_at DOUBLE NOT NULL,
                        INDEX idx_admin_balance_events_account_id (account_id),
                        INDEX idx_admin_balance_events_created_at (created_at)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """
                )
                try:
                    cur.execute("ALTER TABLE admin_subscription_plans ADD COLUMN price_cents INT NOT NULL DEFAULT 0 AFTER group_id")
                except Exception:
                    pass
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS admin_account_subscriptions (
                        id VARCHAR(64) PRIMARY KEY,
                        account_id VARCHAR(64) NOT NULL,
                        plan_id VARCHAR(64) NOT NULL,
                        group_id VARCHAR(64) NULL,
                        status VARCHAR(32) NOT NULL,
                        started_at DOUBLE NOT NULL,
                        expires_at DOUBLE NULL,
                        daily_used INT NOT NULL DEFAULT 0,
                        weekly_used INT NOT NULL DEFAULT 0,
                        monthly_used INT NOT NULL DEFAULT 0,
                        created_at DOUBLE NOT NULL,
                        updated_at DOUBLE NOT NULL,
                        INDEX idx_admin_account_subscriptions_account_id (account_id),
                        INDEX idx_admin_account_subscriptions_plan_id (plan_id)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS admin_payment_channels (
                        id VARCHAR(64) PRIMARY KEY,
                        name VARCHAR(128) NOT NULL,
                        provider VARCHAR(64) NOT NULL,
                        config_json MEDIUMTEXT NOT NULL,
                        enabled TINYINT(1) NOT NULL DEFAULT 1,
                        created_at DOUBLE NOT NULL,
                        updated_at DOUBLE NOT NULL
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS admin_payment_orders (
                        id VARCHAR(64) PRIMARY KEY,
                        account_id VARCHAR(64) NOT NULL,
                        plan_id VARCHAR(64) NOT NULL,
                        subscription_id VARCHAR(64) NULL,
                        channel_id VARCHAR(64) NULL,
                        amount_cents INT NOT NULL DEFAULT 0,
                        currency VARCHAR(16) NOT NULL DEFAULT 'CNY',
                        status VARCHAR(32) NOT NULL,
                        provider_order_id VARCHAR(128) NULL,
                        resume_token VARCHAR(128) NULL,
                        payload_json MEDIUMTEXT NOT NULL,
                        provider_payload_json MEDIUMTEXT NOT NULL,
                        paid_at DOUBLE NULL,
                        created_at DOUBLE NOT NULL,
                        updated_at DOUBLE NOT NULL,
                        INDEX idx_admin_payment_orders_account_id (account_id),
                        INDEX idx_admin_payment_orders_plan_id (plan_id),
                        INDEX idx_admin_payment_orders_status (status)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """
                )
                try:
                    cur.execute("ALTER TABLE admin_payment_orders ADD COLUMN provider_payload_json MEDIUMTEXT NOT NULL AFTER payload_json")
                except Exception:
                    pass
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS admin_payment_webhook_events (
                        event_id VARCHAR(128) PRIMARY KEY,
                        order_id VARCHAR(64) NOT NULL,
                        provider VARCHAR(64) NOT NULL,
                        signature VARCHAR(256) NULL,
                        payload_json MEDIUMTEXT NOT NULL,
                        processed TINYINT(1) NOT NULL DEFAULT 0,
                        created_at DOUBLE NOT NULL,
                        updated_at DOUBLE NOT NULL,
                        INDEX idx_admin_payment_webhook_events_order_id (order_id)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS admin_payment_fulfillment_logs (
                        id VARCHAR(64) PRIMARY KEY,
                        order_id VARCHAR(64) NOT NULL,
                        subscription_id VARCHAR(64) NULL,
                        action VARCHAR(64) NOT NULL,
                        actor_type VARCHAR(32) NOT NULL,
                        actor_id VARCHAR(128) NULL,
                        note_text TEXT NULL,
                        payload_json MEDIUMTEXT NOT NULL,
                        created_at DOUBLE NOT NULL,
                        INDEX idx_admin_payment_fulfillment_logs_order_id (order_id),
                        INDEX idx_admin_payment_fulfillment_logs_subscription_id (subscription_id)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS request_cache (
                        cache_key VARCHAR(512) PRIMARY KEY,
                        protocol VARCHAR(32) NOT NULL,
                        path VARCHAR(1024) NOT NULL,
                        request_fingerprint VARCHAR(512) NOT NULL,
                        response_json MEDIUMTEXT NOT NULL,
                        meta_json MEDIUMTEXT NOT NULL,
                        expires_at DOUBLE NOT NULL,
                        updated_at DOUBLE NOT NULL,
                        INDEX idx_request_cache_expires_at (expires_at)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS tool_result_cache (
                        cache_key VARCHAR(512) PRIMARY KEY,
                        protocol VARCHAR(64) NOT NULL,
                        tool_name VARCHAR(128) NOT NULL,
                        arguments_json MEDIUMTEXT NOT NULL,
                        result_json MEDIUMTEXT NOT NULL,
                        meta_json MEDIUMTEXT NOT NULL,
                        expires_at DOUBLE NOT NULL,
                        updated_at DOUBLE NOT NULL,
                        INDEX idx_tool_result_cache_expires_at (expires_at),
                        INDEX idx_tool_result_cache_tool_name (tool_name)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS interrupted_responses (
                        resume_key VARCHAR(256) PRIMARY KEY,
                        protocol VARCHAR(32) NOT NULL,
                        model VARCHAR(128) NOT NULL,
                        partial_text MEDIUMTEXT NOT NULL,
                        meta_json MEDIUMTEXT NOT NULL,
                        created_at DOUBLE NOT NULL,
                        expires_at DOUBLE NOT NULL,
                        INDEX idx_interrupted_responses_expires_at (expires_at)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """
                )
            conn.commit()
        finally:
            conn.close()

    def load_model_route_cache(self) -> dict:
        now = time.time()
        cache = {"routes": {}, "model_lists": {}, "capabilities": {}}
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT logical_key, route_url, model_key, entry_json FROM model_route_cache WHERE expires_at > %s",
                    (now,),
                )
                for row in cur.fetchall():
                    try:
                        entry = json.loads(row[3])
                    except json.JSONDecodeError:
                        continue
                    cache["routes"].setdefault(row[0], {}).setdefault(row[1], {})[row[2]] = entry

                cur.execute(
                    "SELECT cache_key, models_json, fetched_at, expires_at FROM model_list_cache WHERE expires_at > %s",
                    (now,),
                )
                for row in cur.fetchall():
                    try:
                        models = json.loads(row[1])
                    except json.JSONDecodeError:
                        continue
                    if isinstance(models, list):
                        cache["model_lists"][row[0]] = {
                            "models": models,
                            "fetched_at": float(row[2] or 0.0),
                            "expires_at": float(row[3] or 0.0),
                        }

                cur.execute(
                    "SELECT logical_key, route_url, model_key, entry_json FROM model_capability_cache WHERE expires_at > %s",
                    (now,),
                )
                for row in cur.fetchall():
                    try:
                        entry = json.loads(row[3])
                    except json.JSONDecodeError:
                        continue
                    cache["capabilities"].setdefault(row[0], {}).setdefault(row[1], {})[row[2]] = entry
        finally:
            conn.close()
        return cache

    def save_model_route_cache(self, cache: dict) -> None:
        now = time.time()
        routes = cache.get("routes") if isinstance(cache, dict) else {}
        model_lists = cache.get("model_lists") if isinstance(cache, dict) else {}
        capabilities = cache.get("capabilities") if isinstance(cache, dict) else {}
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM model_route_cache")
                if isinstance(routes, dict):
                    for logical_key, logical_routes in routes.items():
                        if not isinstance(logical_routes, dict):
                            continue
                        for route_url, route_entries in logical_routes.items():
                            if not isinstance(route_entries, dict):
                                continue
                            for model_key, entry in route_entries.items():
                                if not isinstance(entry, dict):
                                    continue
                                cur.execute(
                                    """
                                    REPLACE INTO model_route_cache
                                    (logical_key, route_url, model_key, entry_json, expires_at, updated_at)
                                    VALUES (%s, %s, %s, %s, %s, %s)
                                    """,
                                    (
                                        str(logical_key),
                                        str(route_url),
                                        str(model_key),
                                        json.dumps(entry, ensure_ascii=False, separators=(",", ":")),
                                        float(entry.get("expires_at", 0.0) or 0.0),
                                        now,
                                    ),
                                )

                cur.execute("DELETE FROM model_list_cache")
                if isinstance(model_lists, dict):
                    for cache_key, entry in model_lists.items():
                        if not isinstance(entry, dict):
                            continue
                        models = entry.get("models")
                        if not isinstance(models, list):
                            continue
                        cur.execute(
                            """
                            REPLACE INTO model_list_cache
                            (cache_key, models_json, fetched_at, expires_at)
                            VALUES (%s, %s, %s, %s)
                            """,
                            (
                                str(cache_key),
                                json.dumps(models, ensure_ascii=False, separators=(",", ":")),
                                float(entry.get("fetched_at", 0.0) or 0.0),
                                float(entry.get("expires_at", 0.0) or 0.0),
                            ),
                        )

                cur.execute("DELETE FROM model_capability_cache")
                if isinstance(capabilities, dict):
                    for logical_key, logical_routes in capabilities.items():
                        if not isinstance(logical_routes, dict):
                            continue
                        for route_url, route_entries in logical_routes.items():
                            if not isinstance(route_entries, dict):
                                continue
                            for model_key, entry in route_entries.items():
                                if not isinstance(entry, dict):
                                    continue
                                cur.execute(
                                    """
                                    REPLACE INTO model_capability_cache
                                    (logical_key, route_url, model_key, entry_json, expires_at, updated_at)
                                    VALUES (%s, %s, %s, %s, %s, %s)
                                    """,
                                    (
                                        str(logical_key),
                                        str(route_url),
                                        str(model_key),
                                        json.dumps(entry, ensure_ascii=False, separators=(",", ":")),
                                        float(entry.get("expires_at", 0.0) or 0.0),
                                        now,
                                    ),
                                )
            conn.commit()
        finally:
            conn.close()

    def record_request(self, request_meta: dict, max_rows: int) -> None:
        if not isinstance(request_meta, dict):
            return
        request_id = str(request_meta.get("request_id") or "")
        if not request_id:
            return
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    REPLACE INTO request_history
                    (request_id, started_at, created_at, meta_json)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (
                        request_id,
                        str(request_meta.get("started_at") or ""),
                        time.time(),
                        json.dumps(request_meta, ensure_ascii=False, separators=(",", ":")),
                    ),
                )
                cur.execute(
                    """
                    DELETE FROM request_history
                    WHERE request_id NOT IN (
                        SELECT t.request_id FROM (
                            SELECT request_id FROM request_history ORDER BY created_at DESC LIMIT %s
                        ) t
                    )
                    """,
                    (max_rows,),
                )
            conn.commit()
        finally:
            conn.close()

    def load_recent_requests(self, limit: int) -> list[dict]:
        rows = []
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT meta_json FROM request_history ORDER BY created_at DESC LIMIT %s",
                    (limit,),
                )
                for row in cur.fetchall():
                    try:
                        item = json.loads(row[0])
                    except json.JSONDecodeError:
                        continue
                    if isinstance(item, dict):
                        rows.append(item)
        finally:
            conn.close()
        return rows

    def clear_request_history(self) -> None:
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM request_history")
            conn.commit()
        finally:
            conn.close()

    def load_pool_runtime_state(self, state_key: str = "default") -> dict:
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT state_json FROM pool_runtime_state WHERE state_key = %s",
                    (str(state_key),),
                )
                row = cur.fetchone()
        finally:
            conn.close()
        if row is None:
            return {}
        try:
            payload = json.loads(row[0])
        except json.JSONDecodeError:
            return {}
        return payload if isinstance(payload, dict) else {}

    def save_pool_runtime_state(self, payload: dict, state_key: str = "default") -> None:
        if not isinstance(payload, dict):
            return
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    REPLACE INTO pool_runtime_state
                    (state_key, state_json, updated_at)
                    VALUES (%s, %s, %s)
                    """,
                    (
                        str(state_key),
                        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                        time.time(),
                    ),
                )
            conn.commit()
        finally:
            conn.close()

    def load_app_config(self, config_key: str = "runtime_config") -> dict:
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT config_json FROM app_config WHERE config_key = %s",
                    (str(config_key),),
                )
                row = cur.fetchone()
        finally:
            conn.close()
        if row is None:
            return {}
        try:
            payload = json.loads(row[0])
        except json.JSONDecodeError:
            return {}
        return payload if isinstance(payload, dict) else {}

    def list_admin_accounts(self) -> list[dict]:
        rows = []
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, name, external_key, source_type, role_name, status, balance_cents,
                           concurrency_limit, allowed_group_ids_json, extra_json,
                           enabled, note, created_at, updated_at
                    FROM admin_accounts
                    ORDER BY updated_at DESC, created_at DESC
                    """
                )
                for row in cur.fetchall():
                    try:
                        allowed_group_ids = json.loads(row[8]) if row[8] else []
                    except json.JSONDecodeError:
                        allowed_group_ids = []
                    try:
                        extra = json.loads(row[9]) if row[9] else {}
                    except json.JSONDecodeError:
                        extra = {}
                    rows.append(
                        {
                            "id": str(row[0] or ""),
                            "name": str(row[1] or ""),
                            "external_key": str(row[2] or ""),
                            "source_type": str(row[3] or ""),
                            "role": str(row[4] or "user"),
                            "status": str(row[5] or "active"),
                            "balance_cents": int(row[6] or 0),
                            "concurrency_limit": int(row[7] or 0),
                            "allowed_group_ids": allowed_group_ids if isinstance(allowed_group_ids, list) else [],
                            "extra": extra if isinstance(extra, dict) else {},
                            "enabled": bool(row[10]),
                            "note": str(row[11] or ""),
                            "created_at": float(row[12] or 0.0),
                            "updated_at": float(row[13] or 0.0),
                        }
                    )
        finally:
            conn.close()
        return rows

    def get_admin_account(self, account_id: str) -> dict:
        target = str(account_id or "").strip()
        if not target:
            return {}
        for item in self.list_admin_accounts():
            if str(item.get("id") or "") == target:
                return item
        return {}

    def get_admin_account_by_external_key(self, external_key: str) -> dict:
        target = str(external_key or "").strip()
        if not target:
            return {}
        for item in self.list_admin_accounts():
            if str(item.get("external_key") or "") == target:
                return item
        return {}

    def upsert_admin_account(self, payload: dict) -> dict:
        now = time.time()
        item = {
            "id": str(payload.get("id") or "").strip(),
            "name": str(payload.get("name") or "").strip(),
            "external_key": str(payload.get("external_key") or "").strip(),
            "source_type": str(payload.get("source_type") or "").strip() or "managed",
            "role": str(payload.get("role") or "user").strip() or "user",
            "status": str(payload.get("status") or "active").strip() or "active",
            "balance_cents": int(payload.get("balance_cents") or 0),
            "concurrency_limit": int(payload.get("concurrency_limit") or 0),
            "allowed_group_ids": payload.get("allowed_group_ids") if isinstance(payload.get("allowed_group_ids"), list) else [],
            "extra": payload.get("extra") if isinstance(payload.get("extra"), dict) else {},
            "enabled": payload.get("enabled") is not False,
            "note": str(payload.get("note") or ""),
        }
        if not item["id"] or not item["name"] or not item["external_key"]:
            raise ValueError("missing required admin account fields")
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT created_at FROM admin_accounts WHERE id = %s", (item["id"],))
                row = cur.fetchone()
                created_at = float(row[0] or now) if row else now
                cur.execute(
                    """
                    REPLACE INTO admin_accounts
                    (id, name, external_key, source_type, role_name, status, balance_cents, concurrency_limit, allowed_group_ids_json, extra_json, enabled, note, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        item["id"],
                        item["name"],
                        item["external_key"],
                        item["source_type"],
                        item["role"],
                        item["status"],
                        item["balance_cents"],
                        item["concurrency_limit"],
                        json.dumps(item["allowed_group_ids"], ensure_ascii=False, separators=(",", ":")),
                        json.dumps(item["extra"], ensure_ascii=False, separators=(",", ":")),
                        1 if item["enabled"] else 0,
                        item["note"],
                        created_at,
                        now,
                    ),
                )
            conn.commit()
        finally:
            conn.close()
        item["created_at"] = created_at
        item["updated_at"] = now
        return item

    def delete_admin_account(self, account_id: str) -> None:
        target = str(account_id or "").strip()
        if not target:
            raise ValueError("account_id is required")
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM admin_account_groups WHERE account_id = %s", (target,))
                cur.execute("DELETE FROM admin_api_keys WHERE account_id = %s", (target,))
                cur.execute("DELETE FROM admin_account_subscriptions WHERE account_id = %s", (target,))
                cur.execute("DELETE FROM admin_payment_orders WHERE account_id = %s", (target,))
                cur.execute("DELETE FROM admin_balance_events WHERE account_id = %s", (target,))
                cur.execute("DELETE FROM admin_accounts WHERE id = %s", (target,))
            conn.commit()
        finally:
            conn.close()

    def adjust_admin_account_balance(self, account_id: str, amount_cents: int, *, event_type: str, note: str = "", actor_type: str = "admin", actor_id: str = "") -> dict:
        target = str(account_id or "").strip()
        if not target:
            raise ValueError("account_id is required")
        delta = int(amount_cents or 0)
        normalized_type = str(event_type or "").strip() or ("deposit" if delta >= 0 else "withdraw")
        now = time.time()
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT balance_cents FROM admin_accounts WHERE id = %s FOR UPDATE", (target,))
                row = cur.fetchone()
                if row is None:
                    raise ValueError("user not found")
                before_balance = int(row[0] or 0)
                after_balance = before_balance + delta
                if after_balance < 0:
                    raise ValueError("insufficient balance")
                cur.execute(
                    "UPDATE admin_accounts SET balance_cents = %s, updated_at = %s WHERE id = %s",
                    (after_balance, now, target),
                )
                event_id = f"bal_{uuid.uuid4().hex[:16]}"
                cur.execute(
                    """
                    INSERT INTO admin_balance_events
                    (id, account_id, event_type, amount_cents, before_balance_cents, after_balance_cents, note, actor_type, actor_id, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        event_id,
                        target,
                        normalized_type,
                        delta,
                        before_balance,
                        after_balance,
                        str(note or ""),
                        str(actor_type or "admin"),
                        str(actor_id or ""),
                        now,
                    ),
                )
            conn.commit()
        finally:
            conn.close()
        return {
            "id": event_id,
            "account_id": target,
            "event_type": normalized_type,
            "amount_cents": delta,
            "before_balance_cents": before_balance,
            "after_balance_cents": after_balance,
            "note": str(note or ""),
            "actor_type": str(actor_type or "admin"),
            "actor_id": str(actor_id or ""),
            "created_at": now,
        }

    def list_admin_balance_events(self, account_id: str | None = None, limit: int = 200) -> list[dict]:
        target = str(account_id or "").strip()
        rows = []
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                if target:
                    cur.execute(
                        """
                        SELECT e.id, e.account_id, e.event_type, e.amount_cents, e.before_balance_cents,
                               e.after_balance_cents, e.note, e.actor_type, e.actor_id, e.created_at, u.name
                        FROM admin_balance_events e
                        LEFT JOIN admin_accounts u ON u.id = e.account_id
                        WHERE e.account_id = %s
                        ORDER BY e.created_at DESC
                        LIMIT %s
                        """,
                        (target, int(limit or 200)),
                    )
                else:
                    cur.execute(
                        """
                        SELECT e.id, e.account_id, e.event_type, e.amount_cents, e.before_balance_cents,
                               e.after_balance_cents, e.note, e.actor_type, e.actor_id, e.created_at, u.name
                        FROM admin_balance_events e
                        LEFT JOIN admin_accounts u ON u.id = e.account_id
                        ORDER BY e.created_at DESC
                        LIMIT %s
                        """,
                        (int(limit or 200),),
                    )
                for row in cur.fetchall():
                    rows.append(
                        {
                            "id": str(row[0] or ""),
                            "account_id": str(row[1] or ""),
                            "event_type": str(row[2] or ""),
                            "amount_cents": int(row[3] or 0),
                            "before_balance_cents": int(row[4] or 0),
                            "after_balance_cents": int(row[5] or 0),
                            "note": str(row[6] or ""),
                            "actor_type": str(row[7] or ""),
                            "actor_id": str(row[8] or ""),
                            "created_at": float(row[9] or 0.0),
                            "account_name": str(row[10] or ""),
                        }
                    )
        finally:
            conn.close()
        return rows

    def list_admin_groups(self) -> list[dict]:
        rows = []
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, name, description_text, platform, is_exclusive, rate_multiplier, extra_json, enabled, sort_order, created_at, updated_at
                    FROM admin_groups
                    ORDER BY sort_order ASC, updated_at DESC, created_at DESC
                    """
                )
                for row in cur.fetchall():
                    try:
                        extra = json.loads(row[6]) if row[6] else {}
                    except json.JSONDecodeError:
                        extra = {}
                    rows.append(
                        {
                            "id": str(row[0] or ""),
                            "name": str(row[1] or ""),
                            "description": str(row[2] or ""),
                            "platform": str(row[3] or ""),
                            "is_exclusive": bool(row[4]),
                            "rate_multiplier": float(row[5] or 1),
                            "extra": extra if isinstance(extra, dict) else {},
                            "enabled": bool(row[7]),
                            "sort_order": int(row[8] or 0),
                            "created_at": float(row[9] or 0.0),
                            "updated_at": float(row[10] or 0.0),
                        }
                    )
        finally:
            conn.close()
        return rows

    def get_admin_group(self, group_id: str) -> dict:
        target = str(group_id or "").strip()
        if not target:
            return {}
        for item in self.list_admin_groups():
            if str(item.get("id") or "") == target:
                return item
        return {}

    def upsert_admin_group(self, payload: dict) -> dict:
        now = time.time()
        item = {
            "id": str(payload.get("id") or "").strip(),
            "name": str(payload.get("name") or "").strip(),
            "description": str(payload.get("description") or ""),
            "platform": str(payload.get("platform") or "").strip(),
            "is_exclusive": payload.get("is_exclusive") is True,
            "rate_multiplier": float(payload.get("rate_multiplier") or 1),
            "extra": payload.get("extra") if isinstance(payload.get("extra"), dict) else {},
            "enabled": payload.get("enabled") is not False,
            "sort_order": int(payload.get("sort_order") or 0),
        }
        if not item["id"] or not item["name"]:
            raise ValueError("missing required admin group fields")
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT created_at FROM admin_groups WHERE id = %s", (item["id"],))
                row = cur.fetchone()
                created_at = float(row[0] or now) if row else now
                cur.execute(
                    """
                    REPLACE INTO admin_groups
                    (id, name, description_text, platform, is_exclusive, rate_multiplier, extra_json, enabled, sort_order, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        item["id"],
                        item["name"],
                        item["description"],
                        item["platform"],
                        1 if item["is_exclusive"] else 0,
                        item["rate_multiplier"],
                        json.dumps(item["extra"], ensure_ascii=False, separators=(",", ":")),
                        1 if item["enabled"] else 0,
                        item["sort_order"],
                        created_at,
                        now,
                    ),
                )
            conn.commit()
        finally:
            conn.close()
        item["created_at"] = created_at
        item["updated_at"] = now
        return item

    def delete_admin_group(self, group_id: str) -> None:
        target = str(group_id or "").strip()
        if not target:
            raise ValueError("group_id is required")
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM admin_account_groups WHERE group_id = %s", (target,))
                cur.execute("UPDATE admin_api_keys SET group_id = NULL WHERE group_id = %s", (target,))
                cur.execute("UPDATE admin_subscription_plans SET group_id = NULL WHERE group_id = %s", (target,))
                cur.execute("UPDATE admin_account_subscriptions SET group_id = NULL WHERE group_id = %s", (target,))
                cur.execute("DELETE FROM admin_groups WHERE id = %s", (target,))
            conn.commit()
        finally:
            conn.close()

    def replace_admin_account_groups(self, account_id: str, group_ids: list[str]) -> None:
        normalized_account_id = str(account_id or "").strip()
        if not normalized_account_id:
            raise ValueError("missing account_id")
        normalized_group_ids = sorted({str(group_id or "").strip() for group_id in (group_ids or []) if str(group_id or "").strip()})
        now = time.time()
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM admin_account_groups WHERE account_id = %s", (normalized_account_id,))
                if normalized_group_ids:
                    cur.executemany(
                        """
                        INSERT INTO admin_account_groups (account_id, group_id, created_at)
                        VALUES (%s, %s, %s)
                        """,
                        [(normalized_account_id, group_id, now) for group_id in normalized_group_ids],
                    )
            conn.commit()
        finally:
            conn.close()

    def list_admin_account_groups(self) -> list[dict]:
        rows = []
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT account_id, group_id, created_at
                    FROM admin_account_groups
                    ORDER BY created_at DESC
                    """
                )
                for row in cur.fetchall():
                    rows.append(
                        {
                            "account_id": str(row[0] or ""),
                            "group_id": str(row[1] or ""),
                            "created_at": float(row[2] or 0.0),
                        }
                    )
        finally:
            conn.close()
        return rows

    def list_admin_api_keys(self) -> list[dict]:
        rows = []
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT k.id, k.account_id, k.group_id, k.name, k.key_hash, k.key_preview,
                           k.enabled, k.last_used_at, k.created_at, k.updated_at, g.name
                    FROM admin_api_keys k
                    LEFT JOIN admin_groups g ON g.id = k.group_id
                    ORDER BY k.updated_at DESC, k.created_at DESC
                    """
                )
                for row in cur.fetchall():
                    rows.append(
                        {
                            "id": str(row[0] or ""),
                            "account_id": str(row[1] or ""),
                            "group_id": str(row[2] or ""),
                            "name": str(row[3] or ""),
                            "key_hash": str(row[4] or ""),
                            "key_preview": str(row[5] or ""),
                            "enabled": bool(row[6]),
                            "last_used_at": float(row[7] or 0.0) if row[7] is not None else None,
                            "created_at": float(row[8] or 0.0),
                            "updated_at": float(row[9] or 0.0),
                            "group_name": str(row[10] or ""),
                        }
                    )
        finally:
            conn.close()
        return rows

    def get_admin_api_key(self, key_id: str) -> dict:
        target = str(key_id or "").strip()
        if not target:
            return {}
        for item in self.list_admin_api_keys():
            if str(item.get("id") or "") == target:
                return item
        return {}

    def upsert_admin_api_key(self, payload: dict) -> dict:
        now = time.time()
        item = {
            "id": str(payload.get("id") or "").strip(),
            "account_id": str(payload.get("account_id") or "").strip(),
            "group_id": str(payload.get("group_id") or "").strip(),
            "name": str(payload.get("name") or "").strip(),
            "key_hash": str(payload.get("key_hash") or "").strip(),
            "key_preview": str(payload.get("key_preview") or "").strip(),
            "enabled": payload.get("enabled") is not False,
            "last_used_at": payload.get("last_used_at"),
        }
        if not item["id"] or not item["account_id"] or not item["name"] or not item["key_hash"] or not item["key_preview"]:
            raise ValueError("missing required admin api key fields")
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT created_at FROM admin_api_keys WHERE id = %s", (item["id"],))
                row = cur.fetchone()
                created_at = float(row[0] or now) if row else now
                cur.execute(
                    """
                    REPLACE INTO admin_api_keys
                    (id, account_id, group_id, name, key_hash, key_preview, enabled, last_used_at, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        item["id"],
                        item["account_id"],
                        item["group_id"] or None,
                        item["name"],
                        item["key_hash"],
                        item["key_preview"],
                        1 if item["enabled"] else 0,
                        item["last_used_at"],
                        created_at,
                        now,
                    ),
                )
            conn.commit()
        finally:
            conn.close()
        item["created_at"] = created_at
        item["updated_at"] = now
        if item["group_id"]:
            group = self.get_admin_group(item["group_id"])
            item["group_name"] = str(group.get("name") or "")
        else:
            item["group_name"] = ""
        return item

    def delete_admin_api_key(self, key_id: str) -> None:
        target = str(key_id or "").strip()
        if not target:
            raise ValueError("key_id is required")
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM admin_api_keys WHERE id = %s", (target,))
            conn.commit()
        finally:
            conn.close()

    def touch_admin_api_key(self, key_id: str) -> None:
        now = time.time()
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE admin_api_keys SET last_used_at = %s, updated_at = %s WHERE id = %s",
                    (now, now, str(key_id or "").strip()),
                )
            conn.commit()
        finally:
            conn.close()

    def set_admin_api_key_enabled(self, key_id: str, enabled: bool) -> None:
        now = time.time()
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE admin_api_keys SET enabled = %s, updated_at = %s WHERE id = %s",
                    (1 if enabled else 0, now, str(key_id or "").strip()),
                )
            conn.commit()
        finally:
            conn.close()

    def find_admin_api_key_by_hash(self, key_hash: str) -> dict:
        normalized = str(key_hash or "").strip()
        if not normalized:
            return {}
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT k.id, k.account_id, k.group_id, k.name, k.key_hash, k.key_preview, k.enabled,
                           u.name, u.source_type, u.enabled, u.note, u.status, u.allowed_group_ids_json,
                           g.name
                    FROM admin_api_keys k
                    LEFT JOIN admin_accounts u ON u.id = k.account_id
                    LEFT JOIN admin_groups g ON g.id = k.group_id
                    WHERE k.key_hash = %s
                    LIMIT 1
                    """,
                    (normalized,),
                )
                row = cur.fetchone()
        finally:
            conn.close()
        if row is None:
            return {}
        try:
            allowed_group_ids = json.loads(row[12]) if row[12] else []
        except json.JSONDecodeError:
            allowed_group_ids = []
        return {
            "id": str(row[0] or ""),
            "account_id": str(row[1] or ""),
            "group_id": str(row[2] or ""),
            "name": str(row[3] or ""),
            "key_hash": str(row[4] or ""),
            "key_preview": str(row[5] or ""),
            "enabled": bool(row[6]),
            "account_name": str(row[7] or ""),
            "account_source_type": str(row[8] or ""),
            "account_enabled": bool(row[9]) if row[9] is not None else True,
            "account_note": str(row[10] or ""),
            "account_status": str(row[11] or ""),
            "account_allowed_group_ids": allowed_group_ids if isinstance(allowed_group_ids, list) else [],
            "group_name": str(row[13] or ""),
        }

    def list_admin_subscription_plans(self) -> list[dict]:
        rows = []
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, name, group_id, price_cents, validity_days, daily_limit, weekly_limit, monthly_limit, enabled, note, created_at, updated_at
                    FROM admin_subscription_plans
                    ORDER BY updated_at DESC, created_at DESC
                    """
                )
                for row in cur.fetchall():
                    rows.append(
                        {
                            "id": str(row[0] or ""),
                            "name": str(row[1] or ""),
                            "group_id": str(row[2] or ""),
                            "price_cents": int(row[3] or 0),
                            "validity_days": int(row[4] or 0),
                            "daily_limit": int(row[5] or 0),
                            "weekly_limit": int(row[6] or 0),
                            "monthly_limit": int(row[7] or 0),
                            "enabled": bool(row[8]),
                            "note": str(row[9] or ""),
                            "created_at": float(row[10] or 0.0),
                            "updated_at": float(row[11] or 0.0),
                        }
                    )
        finally:
            conn.close()
        return rows

    def upsert_admin_subscription_plan(self, payload: dict) -> dict:
        now = time.time()
        item = {
            "id": str(payload.get("id") or "").strip(),
            "name": str(payload.get("name") or "").strip(),
            "group_id": str(payload.get("group_id") or "").strip(),
            "price_cents": int(payload.get("price_cents") or 0),
            "validity_days": int(payload.get("validity_days") or 30),
            "daily_limit": int(payload.get("daily_limit") or 0),
            "weekly_limit": int(payload.get("weekly_limit") or 0),
            "monthly_limit": int(payload.get("monthly_limit") or 0),
            "enabled": payload.get("enabled") is not False,
            "note": str(payload.get("note") or ""),
        }
        if not item["id"] or not item["name"]:
            raise ValueError("missing required admin subscription plan fields")
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT created_at FROM admin_subscription_plans WHERE id = %s", (item["id"],))
                row = cur.fetchone()
                created_at = float(row[0] or now) if row else now
                cur.execute(
                    """
                    REPLACE INTO admin_subscription_plans
                    (id, name, group_id, price_cents, validity_days, daily_limit, weekly_limit, monthly_limit, enabled, note, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        item["id"],
                        item["name"],
                        item["group_id"] or None,
                        item["price_cents"],
                        item["validity_days"],
                        item["daily_limit"],
                        item["weekly_limit"],
                        item["monthly_limit"],
                        1 if item["enabled"] else 0,
                        item["note"],
                        created_at,
                        now,
                    ),
                )
            conn.commit()
        finally:
            conn.close()
        item["created_at"] = created_at
        item["updated_at"] = now
        return item

    def list_admin_account_subscriptions(self) -> list[dict]:
        rows = []
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT s.id, s.account_id, s.plan_id, s.group_id, s.status, s.started_at, s.expires_at,
                           s.daily_used, s.weekly_used, s.monthly_used, s.created_at, s.updated_at,
                           u.name, p.name, g.name, p.price_cents
                    FROM admin_account_subscriptions s
                    LEFT JOIN admin_accounts u ON u.id = s.account_id
                    LEFT JOIN admin_subscription_plans p ON p.id = s.plan_id
                    LEFT JOIN admin_groups g ON g.id = s.group_id
                    ORDER BY s.updated_at DESC, s.created_at DESC
                    """
                )
                for row in cur.fetchall():
                    rows.append(
                        {
                            "id": str(row[0] or ""),
                            "account_id": str(row[1] or ""),
                            "plan_id": str(row[2] or ""),
                            "group_id": str(row[3] or ""),
                            "status": str(row[4] or ""),
                            "started_at": float(row[5] or 0.0),
                            "expires_at": float(row[6] or 0.0) if row[6] is not None else None,
                            "daily_used": int(row[7] or 0),
                            "weekly_used": int(row[8] or 0),
                            "monthly_used": int(row[9] or 0),
                            "created_at": float(row[10] or 0.0),
                            "updated_at": float(row[11] or 0.0),
                            "account_name": str(row[12] or ""),
                            "plan_name": str(row[13] or ""),
                            "group_name": str(row[14] or ""),
                            "price_cents": int(row[15] or 0),
                        }
                    )
        finally:
            conn.close()
        return rows

    def upsert_admin_account_subscription(self, payload: dict) -> dict:
        now = time.time()
        item = {
            "id": str(payload.get("id") or "").strip(),
            "account_id": str(payload.get("account_id") or "").strip(),
            "plan_id": str(payload.get("plan_id") or "").strip(),
            "group_id": str(payload.get("group_id") or "").strip(),
            "status": str(payload.get("status") or "active").strip() or "active",
            "started_at": float(payload.get("started_at") or now),
            "expires_at": payload.get("expires_at"),
            "daily_used": int(payload.get("daily_used") or 0),
            "weekly_used": int(payload.get("weekly_used") or 0),
            "monthly_used": int(payload.get("monthly_used") or 0),
        }
        if not item["id"] or not item["account_id"] or not item["plan_id"]:
            raise ValueError("missing required admin account subscription fields")
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT created_at FROM admin_account_subscriptions WHERE id = %s", (item["id"],))
                row = cur.fetchone()
                created_at = float(row[0] or now) if row else now
                cur.execute(
                    """
                    REPLACE INTO admin_account_subscriptions
                    (id, account_id, plan_id, group_id, status, started_at, expires_at, daily_used, weekly_used, monthly_used, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        item["id"],
                        item["account_id"],
                        item["plan_id"],
                        item["group_id"] or None,
                        item["status"],
                        item["started_at"],
                        item["expires_at"],
                        item["daily_used"],
                        item["weekly_used"],
                        item["monthly_used"],
                        created_at,
                        now,
                    ),
                )
            conn.commit()
        finally:
            conn.close()
        item["created_at"] = created_at
        item["updated_at"] = now
        return item

    def list_admin_payment_channels(self) -> list[dict]:
        rows = []
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, name, provider, config_json, enabled, created_at, updated_at
                    FROM admin_payment_channels
                    ORDER BY updated_at DESC, created_at DESC
                    """
                )
                for row in cur.fetchall():
                    try:
                        config_payload = json.loads(row[3]) if row[3] else {}
                    except json.JSONDecodeError:
                        config_payload = {}
                    rows.append(
                        {
                            "id": str(row[0] or ""),
                            "name": str(row[1] or ""),
                            "provider": str(row[2] or ""),
                            "config": config_payload if isinstance(config_payload, dict) else {},
                            "enabled": bool(row[4]),
                            "created_at": float(row[5] or 0.0),
                            "updated_at": float(row[6] or 0.0),
                        }
                    )
        finally:
            conn.close()
        return rows

    def upsert_admin_payment_channel(self, payload: dict) -> dict:
        now = time.time()
        item = {
            "id": str(payload.get("id") or "").strip(),
            "name": str(payload.get("name") or "").strip(),
            "provider": str(payload.get("provider") or "").strip(),
            "config": payload.get("config") if isinstance(payload.get("config"), dict) else {},
            "enabled": payload.get("enabled") is not False,
        }
        if not item["id"] or not item["name"] or not item["provider"]:
            raise ValueError("missing required payment channel fields")
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT created_at FROM admin_payment_channels WHERE id = %s", (item["id"],))
                row = cur.fetchone()
                created_at = float(row[0] or now) if row else now
                cur.execute(
                    """
                    REPLACE INTO admin_payment_channels
                    (id, name, provider, config_json, enabled, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        item["id"],
                        item["name"],
                        item["provider"],
                        json.dumps(item["config"], ensure_ascii=False, separators=(",", ":")),
                        1 if item["enabled"] else 0,
                        created_at,
                        now,
                    ),
                )
            conn.commit()
        finally:
            conn.close()
        item["created_at"] = created_at
        item["updated_at"] = now
        return item

    def list_admin_payment_orders(self) -> list[dict]:
        rows = []
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT o.id, o.account_id, o.plan_id, o.subscription_id, o.channel_id, o.amount_cents, o.currency, o.status,
                           o.provider_order_id, o.resume_token, o.payload_json, o.provider_payload_json, o.paid_at, o.created_at, o.updated_at,
                           p.group_id, g.name, p.price_cents
                    FROM admin_payment_orders o
                    LEFT JOIN admin_subscription_plans p ON p.id = o.plan_id
                    LEFT JOIN admin_groups g ON g.id = p.group_id
                    ORDER BY updated_at DESC, created_at DESC
                    """
                )
                for row in cur.fetchall():
                    try:
                        payload_json = json.loads(row[10]) if row[10] else {}
                    except json.JSONDecodeError:
                        payload_json = {}
                    try:
                        provider_payload_json = json.loads(row[11]) if row[11] else {}
                    except json.JSONDecodeError:
                        provider_payload_json = {}
                    rows.append(
                        {
                            "id": str(row[0] or ""),
                            "account_id": str(row[1] or ""),
                            "plan_id": str(row[2] or ""),
                            "subscription_id": str(row[3] or ""),
                            "channel_id": str(row[4] or ""),
                            "amount_cents": int(row[5] or 0),
                            "currency": str(row[6] or ""),
                            "status": str(row[7] or ""),
                            "provider_order_id": str(row[8] or ""),
                            "resume_token": str(row[9] or ""),
                            "payload": payload_json if isinstance(payload_json, dict) else {},
                            "provider_payload": provider_payload_json if isinstance(provider_payload_json, dict) else {},
                            "paid_at": float(row[12] or 0.0) if row[12] is not None else None,
                            "created_at": float(row[13] or 0.0),
                            "updated_at": float(row[14] or 0.0),
                            "group_id": str(row[15] or ""),
                            "group_name": str(row[16] or ""),
                            "plan_price_cents": int(row[17] or 0),
                        }
                    )
        finally:
            conn.close()
        return rows

    def record_payment_fulfillment_log(self, payload: dict) -> dict:
        now = time.time()
        item = {
            "id": str(payload.get("id") or "").strip(),
            "order_id": str(payload.get("order_id") or "").strip(),
            "subscription_id": str(payload.get("subscription_id") or "").strip(),
            "action": str(payload.get("action") or "").strip(),
            "actor_type": str(payload.get("actor_type") or "").strip() or "system",
            "actor_id": str(payload.get("actor_id") or "").strip(),
            "note_text": str(payload.get("note_text") or "").strip(),
            "payload": payload.get("payload") if isinstance(payload.get("payload"), dict) else {},
        }
        if not item["id"] or not item["order_id"] or not item["action"]:
            raise ValueError("missing required payment fulfillment log fields")
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    REPLACE INTO admin_payment_fulfillment_logs
                    (id, order_id, subscription_id, action, actor_type, actor_id, note_text, payload_json, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        item["id"],
                        item["order_id"],
                        item["subscription_id"] or None,
                        item["action"],
                        item["actor_type"],
                        item["actor_id"] or None,
                        item["note_text"] or None,
                        json.dumps(item["payload"], ensure_ascii=False, separators=(",", ":")),
                        now,
                    ),
                )
            conn.commit()
        finally:
            conn.close()
        item["created_at"] = now
        return item

    def list_payment_fulfillment_logs(self, order_id: str) -> list[dict]:
        target = str(order_id or "").strip()
        if not target:
            return []
        conn = self._connect()
        rows = []
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, order_id, subscription_id, action, actor_type, actor_id, note_text, payload_json, created_at
                    FROM admin_payment_fulfillment_logs
                    WHERE order_id = %s
                    ORDER BY created_at DESC
                    """,
                    (target,),
                )
                for row in cur.fetchall():
                    try:
                        payload_json = json.loads(row[7]) if row[7] else {}
                    except json.JSONDecodeError:
                        payload_json = {}
                    rows.append(
                        {
                            "id": str(row[0] or ""),
                            "order_id": str(row[1] or ""),
                            "subscription_id": str(row[2] or ""),
                            "action": str(row[3] or ""),
                            "actor_type": str(row[4] or ""),
                            "actor_id": str(row[5] or ""),
                            "note_text": str(row[6] or ""),
                            "payload": payload_json if isinstance(payload_json, dict) else {},
                            "created_at": float(row[8] or 0.0),
                        }
                    )
        finally:
            conn.close()
        return rows

    def get_admin_payment_order(self, order_id: str) -> dict:
        target = str(order_id or "").strip()
        if not target:
            return {}
        for item in self.list_admin_payment_orders():
            if str(item.get("id") or "") == target:
                return item
        return {}

    def upsert_admin_payment_order(self, payload: dict) -> dict:
        now = time.time()
        item = {
            "id": str(payload.get("id") or "").strip(),
            "account_id": str(payload.get("account_id") or "").strip(),
            "plan_id": str(payload.get("plan_id") or "").strip(),
            "subscription_id": str(payload.get("subscription_id") or "").strip(),
            "channel_id": str(payload.get("channel_id") or "").strip(),
            "amount_cents": int(payload.get("amount_cents") or 0),
            "currency": str(payload.get("currency") or "CNY").strip() or "CNY",
            "status": str(payload.get("status") or "").strip(),
            "provider_order_id": str(payload.get("provider_order_id") or "").strip(),
            "resume_token": str(payload.get("resume_token") or "").strip(),
            "payload": payload.get("payload") if isinstance(payload.get("payload"), dict) else {},
            "provider_payload": payload.get("provider_payload") if isinstance(payload.get("provider_payload"), dict) else {},
            "paid_at": payload.get("paid_at"),
        }
        if not item["id"] or not item["account_id"] or not item["plan_id"] or not item["status"]:
            raise ValueError("missing required payment order fields")
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT created_at FROM admin_payment_orders WHERE id = %s", (item["id"],))
                row = cur.fetchone()
                created_at = float(row[0] or now) if row else now
                cur.execute(
                    """
                    REPLACE INTO admin_payment_orders
                    (id, account_id, plan_id, subscription_id, channel_id, amount_cents, currency, status, provider_order_id, resume_token, payload_json, provider_payload_json, paid_at, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        item["id"],
                        item["account_id"],
                        item["plan_id"],
                        item["subscription_id"] or None,
                        item["channel_id"] or None,
                        item["amount_cents"],
                        item["currency"],
                        item["status"],
                        item["provider_order_id"] or None,
                        item["resume_token"] or None,
                        json.dumps(item["payload"], ensure_ascii=False, separators=(",", ":")),
                        json.dumps(item["provider_payload"], ensure_ascii=False, separators=(",", ":")),
                        item["paid_at"],
                        created_at,
                        now,
                    ),
                )
            conn.commit()
        finally:
            conn.close()
        item["created_at"] = created_at
        item["updated_at"] = now
        return item

    def record_payment_webhook_event(self, payload: dict) -> dict:
        now = time.time()
        item = {
            "event_id": str(payload.get("event_id") or "").strip(),
            "order_id": str(payload.get("order_id") or "").strip(),
            "provider": str(payload.get("provider") or "").strip(),
            "signature": str(payload.get("signature") or "").strip(),
            "payload": payload.get("payload") if isinstance(payload.get("payload"), dict) else {},
            "processed": payload.get("processed") is True,
        }
        if not item["event_id"] or not item["order_id"] or not item["provider"]:
            raise ValueError("missing required payment webhook event fields")
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT created_at FROM admin_payment_webhook_events WHERE event_id = %s", (item["event_id"],))
                row = cur.fetchone()
                created_at = float(row[0] or now) if row else now
                cur.execute(
                    """
                    REPLACE INTO admin_payment_webhook_events
                    (event_id, order_id, provider, signature, payload_json, processed, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        item["event_id"],
                        item["order_id"],
                        item["provider"],
                        item["signature"] or None,
                        json.dumps(item["payload"], ensure_ascii=False, separators=(",", ":")),
                        1 if item["processed"] else 0,
                        created_at,
                        now,
                    ),
                )
            conn.commit()
        finally:
            conn.close()
        item["created_at"] = created_at
        item["updated_at"] = now
        return item

    def get_payment_webhook_event(self, event_id: str) -> dict:
        target = str(event_id or "").strip()
        if not target:
            return {}
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT event_id, order_id, provider, signature, payload_json, processed, created_at, updated_at
                    FROM admin_payment_webhook_events
                    WHERE event_id = %s
                    LIMIT 1
                    """,
                    (target,),
                )
                row = cur.fetchone()
        finally:
            conn.close()
        if row is None:
            return {}
        try:
            payload_json = json.loads(row[4]) if row[4] else {}
        except json.JSONDecodeError:
            payload_json = {}
        return {
            "event_id": str(row[0] or ""),
            "order_id": str(row[1] or ""),
            "provider": str(row[2] or ""),
            "signature": str(row[3] or ""),
            "payload": payload_json if isinstance(payload_json, dict) else {},
            "processed": bool(row[5]),
            "created_at": float(row[6] or 0.0),
            "updated_at": float(row[7] or 0.0),
        }

    def get_admin_account_subscription(self, subscription_id: str) -> dict:
        target = str(subscription_id or "").strip()
        if not target:
            return {}
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, account_id, plan_id, group_id, status, started_at, expires_at,
                           daily_used, weekly_used, monthly_used, created_at, updated_at
                    FROM admin_account_subscriptions
                    WHERE id = %s
                    LIMIT 1
                    """,
                    (target,),
                )
                row = cur.fetchone()
        finally:
            conn.close()
        if row is None:
            return {}
        return {
            "id": str(row[0] or ""),
            "account_id": str(row[1] or ""),
            "plan_id": str(row[2] or ""),
            "group_id": str(row[3] or ""),
            "status": str(row[4] or ""),
            "started_at": float(row[5] or 0.0),
            "expires_at": float(row[6] or 0.0) if row[6] is not None else None,
            "daily_used": int(row[7] or 0),
            "weekly_used": int(row[8] or 0),
            "monthly_used": int(row[9] or 0),
            "created_at": float(row[10] or 0.0),
            "updated_at": float(row[11] or 0.0),
        }

    def get_active_subscription_context_for_account(self, account_id: str, group_id: str = "") -> dict:
        target = str(account_id or "").strip()
        if not target:
            return {}
        target_group_id = str(group_id or "").strip()
        now = time.time()
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                params = [target, now]
                group_filter = ""
                if target_group_id:
                    group_filter = "AND s.group_id = %s"
                    params.append(target_group_id)
                cur.execute(
                    f"""
                    SELECT s.id, s.account_id, s.plan_id, s.group_id, s.status, s.started_at, s.expires_at,
                           p.name, p.price_cents, g.name
                    FROM admin_account_subscriptions s
                    LEFT JOIN admin_subscription_plans p ON p.id = s.plan_id
                    LEFT JOIN admin_groups g ON g.id = s.group_id
                    WHERE s.account_id = %s
                      AND s.status = 'active'
                      AND (s.expires_at IS NULL OR s.expires_at > %s)
                      {group_filter}
                    ORDER BY s.updated_at DESC, s.created_at DESC
                    LIMIT 1
                    """,
                    tuple(params),
                )
                row = cur.fetchone()
        finally:
            conn.close()
        if row is None:
            return {}
        return {
            "subscription_id": str(row[0] or ""),
            "account_id": str(row[1] or ""),
            "plan_id": str(row[2] or ""),
            "group_id": str(row[3] or ""),
            "status": str(row[4] or ""),
            "started_at": float(row[5] or 0.0),
            "expires_at": float(row[6] or 0.0) if row[6] is not None else None,
            "plan_name": str(row[7] or ""),
            "plan_price_cents": int(row[8] or 0),
            "group_name": str(row[9] or ""),
        }

    def extend_admin_account_subscription(self, subscription_id: str, extra_days: int) -> dict:
        current = self.get_admin_account_subscription(subscription_id)
        if not current:
            raise ValueError("subscription not found")
        now = time.time()
        current_expires = current.get("expires_at")
        base = float(current_expires or now)
        next_expires = base + max(0, int(extra_days)) * 86400
        current["expires_at"] = next_expires
        current["updated_at"] = now
        return self.upsert_admin_account_subscription(current)

    def revoke_admin_account_subscription(self, subscription_id: str) -> dict:
        current = self.get_admin_account_subscription(subscription_id)
        if not current:
            raise ValueError("subscription not found")
        current["status"] = "revoked"
        current["updated_at"] = time.time()
        return self.upsert_admin_account_subscription(current)

    def reset_admin_account_subscription_quota(self, subscription_id: str, *, daily: bool, weekly: bool, monthly: bool) -> dict:
        current = self.get_admin_account_subscription(subscription_id)
        if not current:
            raise ValueError("subscription not found")
        if daily:
            current["daily_used"] = 0
        if weekly:
            current["weekly_used"] = 0
        if monthly:
            current["monthly_used"] = 0
        current["updated_at"] = time.time()
        return self.upsert_admin_account_subscription(current)


    def save_app_config(self, payload: dict, config_key: str = "runtime_config") -> None:
        if not isinstance(payload, dict):
            return
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    REPLACE INTO app_config
                    (config_key, config_json, updated_at)
                    VALUES (%s, %s, %s)
                    """,
                    (
                        str(config_key),
                        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                        time.time(),
                    ),
                )
            conn.commit()
        finally:
            conn.close()

    def load_request_cache(self, cache_key: str) -> dict:
        now = time.time()
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT response_json, meta_json
                    FROM request_cache
                    WHERE cache_key = %s AND expires_at > %s
                    """,
                    (str(cache_key), now),
                )
                row = cur.fetchone()
        finally:
            conn.close()
        if row is None:
            return {}
        try:
            response_payload = json.loads(row[0])
            meta_payload = json.loads(row[1])
        except json.JSONDecodeError:
            return {}
        if not isinstance(response_payload, dict) or not isinstance(meta_payload, dict):
            return {}
        payload = dict(meta_payload)
        payload["response_body"] = response_payload
        return payload

    def save_request_cache(self, payload: dict) -> None:
        if not isinstance(payload, dict):
            return
        cache_key = str(payload.get("cache_key") or "")
        if not cache_key:
            return
        response_body = payload.get("response_body")
        if not isinstance(response_body, dict):
            return
        meta_payload = dict(payload)
        meta_payload.pop("response_body", None)
        now = time.time()
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    REPLACE INTO request_cache
                    (cache_key, protocol, path, request_fingerprint, response_json, meta_json, expires_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        cache_key,
                        str(payload.get("protocol") or ""),
                        str(payload.get("path") or ""),
                        str(payload.get("request_fingerprint") or cache_key),
                        json.dumps(response_body, ensure_ascii=False, separators=(",", ":")),
                        json.dumps(meta_payload, ensure_ascii=False, separators=(",", ":")),
                        float(payload.get("expires_at", now) or now),
                        now,
                    ),
                )
            conn.commit()
        finally:
            conn.close()

    def delete_expired_request_cache(self) -> None:
        now = time.time()
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM request_cache WHERE expires_at <= %s", (now,))
            conn.commit()
        finally:
            conn.close()

    def clear_request_cache(self) -> None:
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM request_cache")
            conn.commit()
        finally:
            conn.close()

    def load_tool_result_cache_many(self, cache_keys: list[str]) -> dict:
        keys = [str(item or "") for item in (cache_keys or []) if str(item or "")]
        if not keys:
            return {}
        now = time.time()
        placeholders = ",".join(["%s"] * len(keys))
        conn = self._connect()
        rows = []
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM tool_result_cache WHERE expires_at <= %s", (now,))
                cur.execute(
                    f"""
                    SELECT cache_key, result_json, meta_json
                    FROM tool_result_cache
                    WHERE expires_at > %s AND cache_key IN ({placeholders})
                    """,
                    tuple([now] + keys),
                )
                rows = cur.fetchall()
            conn.commit()
        finally:
            conn.close()
        results = {}
        for row in rows:
            try:
                result_payload = json.loads(row[1])
                meta_payload = json.loads(row[2])
            except json.JSONDecodeError:
                continue
            if not isinstance(result_payload, dict) or not isinstance(meta_payload, dict):
                continue
            payload = dict(meta_payload)
            payload["result_message"] = result_payload
            results[str(row[0])] = payload
        return results

    def save_tool_result_cache(self, payloads: list[dict]) -> int:
        valid_payloads = []
        for payload in payloads or []:
            if not isinstance(payload, dict):
                continue
            cache_key = str(payload.get("cache_key") or "")
            result_message = payload.get("result_message")
            if not cache_key or not isinstance(result_message, dict):
                continue
            valid_payloads.append(payload)
        if not valid_payloads:
            return 0
        now = time.time()
        conn = self._connect()
        saved = 0
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM tool_result_cache WHERE expires_at <= %s", (now,))
                for payload in valid_payloads:
                    meta_payload = dict(payload)
                    result_message = meta_payload.pop("result_message", None)
                    cur.execute(
                        """
                        REPLACE INTO tool_result_cache
                        (cache_key, protocol, tool_name, arguments_json, result_json, meta_json, expires_at, updated_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            str(payload.get("cache_key") or ""),
                            str(payload.get("protocol") or ""),
                            str(payload.get("tool_name") or ""),
                            json.dumps(payload.get("arguments", {}), ensure_ascii=False, separators=(",", ":")),
                            json.dumps(result_message, ensure_ascii=False, separators=(",", ":")),
                            json.dumps(meta_payload, ensure_ascii=False, separators=(",", ":")),
                            float(payload.get("expires_at", now) or now),
                            now,
                        ),
                    )
                    saved += 1
            conn.commit()
        finally:
            conn.close()
        return saved

    def clear_tool_result_cache(self) -> None:
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM tool_result_cache")
            conn.commit()
        finally:
            conn.close()

    def load_interrupted_response(self, resume_key: str) -> dict:
        now = time.time()
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM interrupted_responses WHERE expires_at <= %s", (now,))
                cur.execute(
                    """
                    SELECT resume_key, protocol, model, partial_text, meta_json, created_at, expires_at
                    FROM interrupted_responses
                    WHERE resume_key = %s AND expires_at > %s
                    """,
                    (str(resume_key), now),
                )
                row = cur.fetchone()
            conn.commit()
        finally:
            conn.close()
        if row is None:
            return {}
        try:
            meta_payload = json.loads(row[4])
        except json.JSONDecodeError:
            meta_payload = {}
        return {
            "resume_key": row[0],
            "protocol": row[1],
            "model": row[2],
            "partial_text": row[3],
            "meta": meta_payload if isinstance(meta_payload, dict) else {},
            "created_at": float(row[5] or 0.0),
            "expires_at": float(row[6] or 0.0),
        }

    def save_interrupted_response(self, payload: dict) -> None:
        if not isinstance(payload, dict):
            return
        resume_key = str(payload.get("resume_key") or "")
        partial_text = str(payload.get("partial_text") or "")
        if not resume_key or not partial_text:
            return
        meta_payload = payload.get("meta")
        if not isinstance(meta_payload, dict):
            meta_payload = {}
        now = time.time()
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM interrupted_responses WHERE expires_at <= %s", (now,))
                cur.execute(
                    """
                    REPLACE INTO interrupted_responses
                    (resume_key, protocol, model, partial_text, meta_json, created_at, expires_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        resume_key,
                        str(payload.get("protocol") or ""),
                        str(payload.get("model") or ""),
                        partial_text,
                        json.dumps(meta_payload, ensure_ascii=False, separators=(",", ":")),
                        float(payload.get("created_at", now) or now),
                        float(payload.get("expires_at", now) or now),
                    ),
                )
            conn.commit()
        finally:
            conn.close()

    def delete_interrupted_response(self, resume_key: str) -> None:
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM interrupted_responses WHERE resume_key = %s", (str(resume_key),))
            conn.commit()
        finally:
            conn.close()

    def delete_interrupted_responses(self, resume_keys: list[str]) -> None:
        keys = [str(item or "") for item in (resume_keys or []) if str(item or "")]
        if not keys:
            return
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.executemany(
                    "DELETE FROM interrupted_responses WHERE resume_key = %s",
                    [(key,) for key in keys],
                )
            conn.commit()
        finally:
            conn.close()

    def delete_expired_interrupted_responses(self) -> None:
        now = time.time()
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM interrupted_responses WHERE expires_at <= %s", (now,))
            conn.commit()
        finally:
            conn.close()

    def count_interrupted_responses(self) -> int:
        now = time.time()
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM interrupted_responses WHERE expires_at <= %s", (now,))
                cur.execute(
                    "SELECT COUNT(*) FROM interrupted_responses WHERE expires_at > %s",
                    (now,),
                )
                row = cur.fetchone()
            conn.commit()
        finally:
            conn.close()
        return int(row[0] if row is not None else 0)
