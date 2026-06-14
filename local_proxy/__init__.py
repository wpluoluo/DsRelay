from __future__ import annotations

__all__ = ["app"]


def __getattr__(name: str):
    if name != "app":
        raise AttributeError(name)
    from .server import app as flask_app

    return flask_app
