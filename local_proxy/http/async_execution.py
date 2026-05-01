from __future__ import annotations

import queue
from threading import Event, Thread


class BackgroundExecution:
    def __init__(self, target, *, on_cancel_result=None, thread_name: str = "background-execution"):
        self._target = target
        self._on_cancel_result = on_cancel_result
        self._cancel_event = Event()
        self._queue = queue.Queue(maxsize=1)
        self._completed = None
        self._thread = Thread(target=self._run, name=thread_name, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        try:
            result = self._target()
        except BaseException as exc:  # pragma: no cover
            self._completed = ("error", exc)
            self._queue.put(self._completed)
            return

        if self._cancel_event.is_set() and self._on_cancel_result is not None:
            try:
                self._on_cancel_result(result)
            except Exception:
                pass

        self._completed = ("result", result)
        self._queue.put(self._completed)

    def wait(self, timeout: float | None):
        if self._completed is not None:
            return self._completed
        try:
            self._completed = self._queue.get(timeout=timeout)
        except queue.Empty:
            return None
        return self._completed

    def cancel(self) -> None:
        self._cancel_event.set()
