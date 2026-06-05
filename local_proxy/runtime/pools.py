from __future__ import annotations

import hashlib
import time
from threading import Lock
from urllib.parse import urlsplit, urlunsplit


KNOWN_UPSTREAM_SUFFIXES = (
    "/chat/completions",
    "/completions",
    "/responses",
    "/embeddings",
    "/images/generations",
    "/audio/speech",
    "/audio/transcriptions",
    "/audio/translations",
    "/models",
)


def normalize_pool_url(value: object) -> str:
    url = str(value or "").strip()
    if not url:
        return ""
    normalized = url.rstrip("/")
    lower = normalized.lower()
    for suffix in KNOWN_UPSTREAM_SUFFIXES:
        if lower.endswith(suffix):
            normalized = normalized[: -len(suffix)].rstrip("/")
            break
    return normalized


def normalize_pool_key(value: object) -> str:
    key = str(value or "").strip()
    if not key:
        return ""
    if any(ch.isspace() for ch in key) and not key.lower().startswith("bearer "):
        return ""
    return key


def normalize_pool_model_aliases_text(value: object) -> str:
    return str(value or "").strip()


def normalize_pool_supported_models_text(value: object) -> str:
    return str(value or "").strip()


def normalize_proxy_pools(raw_pools: object) -> list[dict]:
    if not isinstance(raw_pools, list):
        return []

    normalized = []
    for index, item in enumerate(raw_pools, start=1):
        if not isinstance(item, dict):
            continue

        name = str(item.get("name") or "").strip() or f"Pool {index}"
        enabled = bool(item.get("enabled", True))
        try:
            priority = int(item.get("priority", 100) or 100)
        except Exception:
            priority = 100

        urls = []
        seen_urls = set()
        for raw_url in item.get("urls", []):
            url = normalize_pool_url(raw_url)
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            urls.append(url)

        keys = []
        seen_keys = set()
        for key_item in item.get("keys", []):
            if isinstance(key_item, dict):
                key = normalize_pool_key(key_item.get("key"))
            else:
                key = normalize_pool_key(key_item)
            if not key or key in seen_keys:
                continue
            seen_keys.add(key)
            keys.append({"key": key})

        if not urls and not keys:
            continue

        normalized.append(
            {
                "name": name,
                "enabled": enabled,
                "priority": priority,
                "urls": urls,
                "keys": keys,
                "model_aliases_text": normalize_pool_model_aliases_text(item.get("model_aliases_text")),
                "supported_models_text": normalize_pool_supported_models_text(item.get("supported_models_text")),
                "route_policy": item.get("route_policy") if isinstance(item.get("route_policy"), dict) else {},
            }
        )

    return normalized


class ConnectionPoolState:
    def __init__(
        self,
        *,
        key_failure_threshold: int = 2,
        key_cooldown_seconds: int = 180,
    ):
        self.lock = Lock()
        self.key_failure_threshold = max(1, int(key_failure_threshold or 1))
        self.key_cooldown_seconds = max(5, int(key_cooldown_seconds or 5))
        self.pools: list[dict] = []
        self.url_key_map: dict[str, list[str]] = {}
        self.url_key_meta: dict[str, dict[str, dict]] = {}
        self.url_pool_name_map: dict[str, str] = {}
        self.key_states: dict[str, dict[str, dict]] = {}
        self.round_robin: dict[str, int] = {}

    @staticmethod
    def route_id_for(pool_name: str, raw_url: str, ordinal: int) -> str:
        normalized_url = normalize_pool_url(raw_url)
        base = f"{str(pool_name or '').strip()}|{normalized_url}|{int(ordinal)}"
        digest = hashlib.sha1(base.encode("utf-8")).hexdigest()[:12]
        return f"{normalized_url}#__route={digest}"

    @staticmethod
    def strip_route_identity(url: str) -> str:
        text = str(url or "").strip()
        if not text:
            return ""
        parts = urlsplit(text)
        return urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, ""))

    @classmethod
    def base_url_from_route_url(cls, url: str) -> str:
        return normalize_pool_url(cls.strip_route_identity(url))

    @classmethod
    def is_route_url(cls, url: str) -> bool:
        parts = urlsplit(str(url or "").strip())
        return bool(parts.fragment and parts.fragment.startswith("__route="))

    @staticmethod
    def route_fragment(url: str) -> str:
        parts = urlsplit(str(url or "").strip())
        fragment = str(parts.fragment or "").strip()
        return fragment if fragment.startswith("__route=") else ""

    def _resolve_stored_route_url(self, url: str) -> str:
        normalized_url = str(url or "").strip()
        if not normalized_url:
            return ""
        if normalized_url in self.url_key_map:
            return normalized_url

        fragment = self.route_fragment(normalized_url)
        if fragment:
            for route_url in self.url_key_map:
                if self.route_fragment(route_url) == fragment:
                    return route_url

        if not self.is_route_url(normalized_url):
            base_url = normalize_pool_url(normalized_url)
            for route_url in self.url_key_map:
                if self.base_url_from_route_url(route_url) == base_url:
                    return route_url
        return normalized_url

    def rebuild(self, pools: list[dict]) -> list[str]:
        normalized = normalize_proxy_pools(pools)
        urls: list[str] = []
        url_key_map: dict[str, list[str]] = {}
        url_key_meta: dict[str, dict[str, dict]] = {}
        url_pool_name_map: dict[str, str] = {}

        ordered_pools = sorted(
            enumerate(normalized),
            key=lambda item: (int(item[1].get("priority", 100) or 100), item[0]),
        )

        for _, pool in ordered_pools:
            if not pool.get("enabled", True):
                continue
            pool_name = str(pool.get("name") or "").strip()
            keys = [str(item.get("key") or "").strip() for item in pool.get("keys", []) if str(item.get("key") or "").strip()]
            key_meta = {
                key: {
                    "pool_name": pool_name,
                    "key_index": idx,
                    "key_id": self._key_id(key),
                }
                for idx, key in enumerate(keys)
            }
            for route_ordinal, raw_url in enumerate(pool.get("urls", []), start=1):
                normalized_base_url = normalize_pool_url(raw_url)
                url = self.route_id_for(pool_name, normalized_base_url, route_ordinal)
                if not url:
                    continue
                urls.append(url)
                url_key_map[url] = list(keys)
                url_pool_name_map[url] = pool_name
                if keys:
                    url_key_meta[url] = dict(key_meta)

        deduped_urls = list(dict.fromkeys(urls))
        with self.lock:
            self.pools = normalized
            self.url_key_map = url_key_map
            self.url_key_meta = url_key_meta
            self.url_pool_name_map = url_pool_name_map
            self.key_states = {
                url: {
                    key: dict(existing)
                    for key, existing in self.key_states.get(url, {}).items()
                    if key in keys
                }
                for url, keys in url_key_map.items()
            }
            self.round_robin = {
                url: min(self.round_robin.get(url, 0), max(0, len(keys) - 1))
                for url, keys in url_key_map.items()
            }
        return deduped_urls

    def has_url(self, url: str) -> bool:
        """Check if a URL (or its resolved form) is registered in any pool."""
        with self.lock:
            normalized_url = self._resolve_stored_route_url(str(url or "").strip())
            return normalized_url in self.url_key_map

    def get_api_keys_for_url(self, url: str) -> list[str]:
        with self.lock:
            normalized_url = self._resolve_stored_route_url(str(url or "").strip())
            return list(self.url_key_map.get(normalized_url, []))

    def route_identity(self, url: str) -> dict:
        with self.lock:
            normalized_url = self._resolve_stored_route_url(str(url or "").strip())
            keys = list(self.url_key_map.get(normalized_url, []))
            pool_name = self.url_pool_name_map.get(normalized_url, "")
            return {
                "url": normalized_url if normalized_url in self.url_key_map else str(url or "").strip(),
                "pool_name": pool_name,
                "key_count": len(keys),
                "has_keys": bool(keys),
            }

    def choose_key(self, url: str, *, exclude: set[str] | None = None) -> dict | None:
        exclude = set(exclude or ())
        now = time.time()
        with self.lock:
            normalized_url = self._resolve_stored_route_url(str(url or "").strip())
            keys = list(self.url_key_map.get(normalized_url, []))
            if not keys:
                return None

            start = int(self.round_robin.get(normalized_url, 0) or 0) % max(1, len(keys))
            available = []
            for offset in range(len(keys)):
                idx = (start + offset) % len(keys)
                key = keys[idx]
                if key in exclude:
                    continue
                state = self.key_states.setdefault(normalized_url, {}).setdefault(
                    key,
                    {
                        "consecutive_failures": 0,
                        "cooldown_until": 0.0,
                        "last_reason": "",
                        "last_failure_at": 0.0,
                        "last_success_at": 0.0,
                        "successes": 0,
                        "failures": 0,
                    },
                )
                if float(state.get("cooldown_until", 0.0) or 0.0) <= now:
                    available.append((idx, key, state))

            if not available:
                return None

            idx, key, state = available[0]
            self.round_robin[normalized_url] = (idx + 1) % len(keys)
            meta = self.url_key_meta.get(normalized_url, {}).get(key, {})
            return {
                "url": normalized_url,
                "key": key,
                "key_index": idx,
                "key_count": len(keys),
                "pool_name": meta.get("pool_name") or self.url_pool_name_map.get(normalized_url) or "",
                "key_id": meta.get("key_id") or self._key_id(key),
                "cooldown_until": float(state.get("cooldown_until", 0.0) or 0.0),
                "from_pool": True,
            }

    def mark_key_success(self, url: str, key: str) -> None:
        normalized_url = str(url or "").strip()
        if not normalized_url or not key:
            return
        now = time.time()
        with self.lock:
            normalized_url = self._resolve_stored_route_url(normalized_url)
            state = self.key_states.setdefault(normalized_url, {}).setdefault(
                key,
                {
                    "consecutive_failures": 0,
                    "cooldown_until": 0.0,
                    "last_reason": "",
                    "last_failure_at": 0.0,
                    "last_success_at": 0.0,
                    "successes": 0,
                    "failures": 0,
                },
            )
            state["consecutive_failures"] = 0
            state["cooldown_until"] = 0.0
            state["last_reason"] = ""
            state["last_success_at"] = now
            state["successes"] = int(state.get("successes", 0) or 0) + 1

    def mark_key_failure(self, url: str, key: str, reason: str, *, force_cooldown: bool = False) -> None:
        normalized_url = str(url or "").strip()
        if not normalized_url or not key:
            return
        now = time.time()
        with self.lock:
            normalized_url = self._resolve_stored_route_url(normalized_url)
            state = self.key_states.setdefault(normalized_url, {}).setdefault(
                key,
                {
                    "consecutive_failures": 0,
                    "cooldown_until": 0.0,
                    "last_reason": "",
                    "last_failure_at": 0.0,
                    "last_success_at": 0.0,
                    "successes": 0,
                    "failures": 0,
                },
            )
            state["consecutive_failures"] = int(state.get("consecutive_failures", 0) or 0) + 1
            state["last_reason"] = str(reason or "")
            state["last_failure_at"] = now
            state["failures"] = int(state.get("failures", 0) or 0) + 1
            if force_cooldown or state["consecutive_failures"] >= self.key_failure_threshold:
                state["cooldown_until"] = max(
                    float(state.get("cooldown_until", 0.0) or 0.0),
                    now + self.key_cooldown_seconds,
                )

    def export_state(self) -> dict:
        with self.lock:
            return {
                "key_states": self.key_states,
                "round_robin": self.round_robin,
                "updated_at": time.time(),
            }

    def load_state(self, payload: object) -> None:
        if not isinstance(payload, dict):
            return
        key_states = payload.get("key_states")
        round_robin = payload.get("round_robin")
        with self.lock:
            if isinstance(key_states, dict):
                self.key_states = {
                    str(url).strip(): {
                        str(key): dict(state)
                        for key, state in states.items()
                        if str(url).strip() and isinstance(state, dict)
                    }
                    for url, states in key_states.items()
                    if isinstance(states, dict)
                }
            if isinstance(round_robin, dict):
                self.round_robin = {
                    str(url).strip(): max(0, int(value or 0))
                    for url, value in round_robin.items()
                    if str(url).strip()
                }

    def snapshot(self) -> dict:
        now = time.time()
        with self.lock:
            cooled_keys = 0
            total_keys = 0
            urls = {}
            for url, keys in self.url_key_map.items():
                url_states = self.key_states.get(url, {})
                total_keys += len(keys)
                cooled_for_url = 0
                for key in keys:
                    state = url_states.get(key, {})
                    if float(state.get("cooldown_until", 0.0) or 0.0) > now:
                        cooled_keys += 1
                        cooled_for_url += 1
                urls[url] = {
                    "pool_name": self.url_pool_name_map.get(url, ""),
                    "key_count": len(keys),
                    "cooling_keys": cooled_for_url,
                    "round_robin_index": int(self.round_robin.get(url, 0) or 0),
                }
            return {
                "pool_count": len(self.pools),
                "enabled_pool_count": sum(1 for pool in self.pools if pool.get("enabled", True)),
                "url_count": len(self.url_key_map),
                "key_count": total_keys,
                "cooling_key_count": cooled_keys,
                "urls": urls,
            }

    @staticmethod
    def _key_id(key: str) -> str:
        digest = hashlib.sha1(str(key or "").encode("utf-8")).hexdigest()
        return digest[:10]
