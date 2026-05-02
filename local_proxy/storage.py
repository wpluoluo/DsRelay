import json
import time

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
