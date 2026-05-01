import json
import sqlite3
import time
from pathlib import Path
from threading import Lock


class ProxyStorage:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.lock = Lock()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_schema()

    def connect(self):
        connection = sqlite3.connect(str(self.db_path), timeout=30)
        connection.row_factory = sqlite3.Row
        return connection

    def init_schema(self) -> None:
        with self.lock, self.connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS model_route_cache (
                    logical_key TEXT NOT NULL,
                    route_url TEXT NOT NULL,
                    model_key TEXT NOT NULL,
                    entry_json TEXT NOT NULL,
                    expires_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    PRIMARY KEY (logical_key, route_url, model_key)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS model_list_cache (
                    cache_key TEXT PRIMARY KEY,
                    models_json TEXT NOT NULL,
                    fetched_at REAL NOT NULL,
                    expires_at REAL NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS model_capability_cache (
                    logical_key TEXT NOT NULL,
                    route_url TEXT NOT NULL,
                    model_key TEXT NOT NULL,
                    entry_json TEXT NOT NULL,
                    expires_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    PRIMARY KEY (logical_key, route_url, model_key)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS request_history (
                    request_id TEXT PRIMARY KEY,
                    started_at TEXT,
                    created_at REAL NOT NULL,
                    meta_json TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_request_history_created_at ON request_history(created_at DESC)"
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS pool_runtime_state (
                    state_key TEXT PRIMARY KEY,
                    state_json TEXT NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS app_config (
                    config_key TEXT PRIMARY KEY,
                    config_json TEXT NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS request_cache (
                    cache_key TEXT PRIMARY KEY,
                    protocol TEXT NOT NULL,
                    path TEXT NOT NULL,
                    request_fingerprint TEXT NOT NULL,
                    response_json TEXT NOT NULL,
                    meta_json TEXT NOT NULL,
                    expires_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_request_cache_expires_at ON request_cache(expires_at)"
            )

    def load_model_route_cache(self) -> dict:
        now = time.time()
        cache = {"routes": {}, "model_lists": {}, "capabilities": {}}
        with self.lock, self.connect() as connection:
            for row in connection.execute(
                "SELECT logical_key, route_url, model_key, entry_json FROM model_route_cache WHERE expires_at > ?",
                (now,),
            ):
                try:
                    entry = json.loads(row["entry_json"])
                except json.JSONDecodeError:
                    continue
                cache["routes"].setdefault(row["logical_key"], {}).setdefault(row["route_url"], {})[
                    row["model_key"]
                ] = entry

            for row in connection.execute(
                "SELECT cache_key, models_json, fetched_at, expires_at FROM model_list_cache WHERE expires_at > ?",
                (now,),
            ):
                try:
                    models = json.loads(row["models_json"])
                except json.JSONDecodeError:
                    continue
                if isinstance(models, list):
                    cache["model_lists"][row["cache_key"]] = {
                        "models": models,
                        "fetched_at": float(row["fetched_at"] or 0.0),
                        "expires_at": float(row["expires_at"] or 0.0),
                    }
            for row in connection.execute(
                "SELECT logical_key, route_url, model_key, entry_json FROM model_capability_cache WHERE expires_at > ?",
                (now,),
            ):
                try:
                    entry = json.loads(row["entry_json"])
                except json.JSONDecodeError:
                    continue
                cache["capabilities"].setdefault(row["logical_key"], {}).setdefault(row["route_url"], {})[
                    row["model_key"]
                ] = entry
        return cache

    def save_model_route_cache(self, cache: dict) -> None:
        now = time.time()
        routes = cache.get("routes") if isinstance(cache, dict) else {}
        model_lists = cache.get("model_lists") if isinstance(cache, dict) else {}
        capabilities = cache.get("capabilities") if isinstance(cache, dict) else {}
        with self.lock, self.connect() as connection:
            connection.execute("DELETE FROM model_route_cache")
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
                            connection.execute(
                                """
                                INSERT OR REPLACE INTO model_route_cache
                                (logical_key, route_url, model_key, entry_json, expires_at, updated_at)
                                VALUES (?, ?, ?, ?, ?, ?)
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

            connection.execute("DELETE FROM model_list_cache")
            if isinstance(model_lists, dict):
                for cache_key, entry in model_lists.items():
                    if not isinstance(entry, dict):
                        continue
                    models = entry.get("models")
                    if not isinstance(models, list):
                        continue
                    connection.execute(
                        """
                        INSERT OR REPLACE INTO model_list_cache
                        (cache_key, models_json, fetched_at, expires_at)
                        VALUES (?, ?, ?, ?)
                        """,
                        (
                            str(cache_key),
                            json.dumps(models, ensure_ascii=False, separators=(",", ":")),
                            float(entry.get("fetched_at", 0.0) or 0.0),
                            float(entry.get("expires_at", 0.0) or 0.0),
                        ),
                    )

            connection.execute("DELETE FROM model_capability_cache")
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
                            connection.execute(
                                """
                                INSERT OR REPLACE INTO model_capability_cache
                                (logical_key, route_url, model_key, entry_json, expires_at, updated_at)
                                VALUES (?, ?, ?, ?, ?, ?)
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

    def record_request(self, request_meta: dict, max_rows: int) -> None:
        if not isinstance(request_meta, dict):
            return
        request_id = str(request_meta.get("request_id") or "")
        if not request_id:
            return
        with self.lock, self.connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO request_history
                (request_id, started_at, created_at, meta_json)
                VALUES (?, ?, ?, ?)
                """,
                (
                    request_id,
                    str(request_meta.get("started_at") or ""),
                    time.time(),
                    json.dumps(request_meta, ensure_ascii=False, separators=(",", ":")),
                ),
            )
            connection.execute(
                """
                DELETE FROM request_history
                WHERE request_id NOT IN (
                    SELECT request_id FROM request_history ORDER BY created_at DESC LIMIT ?
                )
                """,
                (max_rows,),
            )

    def load_recent_requests(self, limit: int) -> list[dict]:
        rows = []
        with self.lock, self.connect() as connection:
            for row in connection.execute(
                "SELECT meta_json FROM request_history ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ):
                try:
                    item = json.loads(row["meta_json"])
                except json.JSONDecodeError:
                    continue
                if isinstance(item, dict):
                    rows.append(item)
        return rows

    def clear_request_history(self) -> None:
        with self.lock, self.connect() as connection:
            connection.execute("DELETE FROM request_history")

    def load_pool_runtime_state(self, state_key: str = "default") -> dict:
        with self.lock, self.connect() as connection:
            row = connection.execute(
                "SELECT state_json FROM pool_runtime_state WHERE state_key = ?",
                (str(state_key),),
            ).fetchone()
        if row is None:
            return {}
        try:
            payload = json.loads(row["state_json"])
        except json.JSONDecodeError:
            return {}
        return payload if isinstance(payload, dict) else {}

    def save_pool_runtime_state(self, payload: dict, state_key: str = "default") -> None:
        if not isinstance(payload, dict):
            return
        with self.lock, self.connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO pool_runtime_state
                (state_key, state_json, updated_at)
                VALUES (?, ?, ?)
                """,
                (
                    str(state_key),
                    json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                    time.time(),
                ),
            )

    def load_app_config(self, config_key: str = "runtime_config") -> dict:
        with self.lock, self.connect() as connection:
            row = connection.execute(
                "SELECT config_json FROM app_config WHERE config_key = ?",
                (str(config_key),),
            ).fetchone()
        if row is None:
            return {}
        try:
            payload = json.loads(row["config_json"])
        except json.JSONDecodeError:
            return {}
        return payload if isinstance(payload, dict) else {}

    def save_app_config(self, payload: dict, config_key: str = "runtime_config") -> None:
        if not isinstance(payload, dict):
            return
        with self.lock, self.connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO app_config
                (config_key, config_json, updated_at)
                VALUES (?, ?, ?)
                """,
                (
                    str(config_key),
                    json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                    time.time(),
                ),
            )

    def load_request_cache(self, cache_key: str) -> dict:
        now = time.time()
        with self.lock, self.connect() as connection:
            row = connection.execute(
                """
                SELECT response_json, meta_json
                FROM request_cache
                WHERE cache_key = ? AND expires_at > ?
                """,
                (str(cache_key), now),
            ).fetchone()
        if row is None:
            return {}
        try:
            response_payload = json.loads(row["response_json"])
            meta_payload = json.loads(row["meta_json"])
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
        with self.lock, self.connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO request_cache
                (cache_key, protocol, path, request_fingerprint, response_json, meta_json, expires_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
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

    def delete_expired_request_cache(self) -> None:
        now = time.time()
        with self.lock, self.connect() as connection:
            connection.execute("DELETE FROM request_cache WHERE expires_at <= ?", (now,))
