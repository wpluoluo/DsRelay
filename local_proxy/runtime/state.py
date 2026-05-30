from __future__ import annotations

import time
from collections import deque
from threading import Lock
from typing import Any


class RequestRecorder:
    """Tracks request lifecycle state and persists sanitized request metadata."""

    def __init__(
        self,
        max_recent: int,
        storage: Any = None,
        logger: Any = None,
        *,
        load_persisted_recent: bool = True,
    ):
        self.max_recent = max_recent
        self.storage = storage
        self.logger = logger
        self.lock = Lock()
        self.request_stats = {
            "total_requests": 0,
            "completed_requests": 0,
            "error_requests": 0,
            "client_gone_requests": 0,
        }
        self.active_requests = {}
        self.recent_requests = deque(maxlen=max_recent)
        if load_persisted_recent:
            self._load_recent_from_storage()

    @staticmethod
    def _looks_like_reserved_example(value: object) -> bool:
        text = str(value or "").strip().lower()
        if not text:
            return False
        return (
            "example domain" in text
            or "example.com" in text
            or ".example" in text
        )

    @staticmethod
    def _should_hide_request(item: dict) -> bool:
        if not isinstance(item, dict):
            return False
        method = str(item.get("method") or "").strip().upper()
        protocol = str(item.get("protocol") or "").strip().lower()
        remote = str(item.get("remote") or "").strip()
        if method == "REQ" and protocol == "auto" and remote in {"", "-"}:
            return True
        haystacks = [
            item.get("upstream_url"),
            item.get("route_url"),
            item.get("url"),
            item.get("response_preview"),
            item.get("error"),
        ]
        for value in haystacks:
            if RequestRecorder._looks_like_reserved_example(value):
                return True
        return False

    def _load_recent_from_storage(self) -> None:
        if self.storage is None:
            return
        try:
            for item in reversed(self.storage.load_recent_requests(self.max_recent)):
                if isinstance(item, dict) and not self._should_hide_request(item):
                    self.recent_requests.appendleft(item)
        except Exception as exc:  # pragma: no cover
            if self.logger:
                self.logger.warning("load_recent_requests_failed error=%s", str(exc))

    def start(self, request_id: str, request_meta: dict) -> None:
        with self.lock:
            self.request_stats["total_requests"] += 1
            self.active_requests[request_id] = request_meta

    def finish(
        self,
        request_id: str,
        *,
        status_code: int | None,
        bytes_sent: int,
        duration_ms: int,
        stream: bool,
        error: str | None = None,
        sanitized_markers: int = 0,
        response_preview: str | None = None,
        repaired_tool_args: int = 0,
        client_gone: bool = False,
        extra_meta: dict | None = None,
    ) -> dict:
        with self.lock:
            request_meta = self.active_requests.pop(request_id, {"request_id": request_id})
            request_meta["status_code"] = status_code
            request_meta["bytes_sent"] = bytes_sent
            request_meta["duration_ms"] = duration_ms
            request_meta["stream"] = stream
            request_meta["error"] = error
            request_meta["client_gone"] = bool(client_gone)
            request_meta["sanitized_markers"] = sanitized_markers
            request_meta["response_preview"] = response_preview
            request_meta["repaired_tool_args"] = repaired_tool_args
            if isinstance(extra_meta, dict):
                request_meta.update(
                    {
                        key: value
                        for key, value in extra_meta.items()
                        if not str(key).startswith("_")
                    }
                )

            self.request_stats["completed_requests"] += 1
            if client_gone:
                self.request_stats["client_gone_requests"] += 1
            elif error or (status_code is not None and status_code >= 400):
                self.request_stats["error_requests"] += 1

            if not self._should_hide_request(request_meta):
                self.recent_requests.appendleft(request_meta)
            persisted_meta = dict(request_meta)

        if self.storage is not None:
            try:
                self.storage.record_request(persisted_meta, self.max_recent)
            except Exception as exc:  # pragma: no cover
                if self.logger:
                    self.logger.warning("record_request_history_failed request_id=%s error=%s", request_id, str(exc))

        return persisted_meta

    def snapshot(self) -> dict:
        with self.lock:
            active_requests = []
            for item in self.active_requests.values():
                active_item = dict(item)
                active_item["active"] = True
                active_item.setdefault("status_text", "处理中")
                active_requests.append(active_item)
            return {
                "stats": dict(self.request_stats),
                "active_requests": active_requests,
                "recent_requests": list(self.recent_requests),
            }

    def clear_history(self) -> None:
        with self.lock:
            self.active_requests.clear()
            self.recent_requests.clear()
        if self.storage is not None:
            try:
                self.storage.clear_request_history()
            except Exception as exc:  # pragma: no cover
                if self.logger:
                    self.logger.warning("clear_request_history_failed error=%s", str(exc))


class CounterStore:
    def __init__(self, initial: dict[str, int] | None = None):
        self.lock = Lock()
        self.values = dict(initial or {})

    def bump(self, key: str, amount: int = 1) -> None:
        with self.lock:
            self.values[key] = int(self.values.get(key, 0) or 0) + amount

    def snapshot(self) -> dict:
        with self.lock:
            return dict(self.values)
