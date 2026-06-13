"""Simple session-based authentication for the admin dashboard.

Credentials are set via environment variables:
  ADMIN_USERNAME  — default: admin
  ADMIN_PASSWORD  — plain-text password, salted & hashed at startup
"""

from __future__ import annotations

import hashlib
import os
import secrets
import time
from collections.abc import Callable
from functools import wraps

from flask import abort, redirect, request, session, url_for


def _env_str(key: str, default: str = "") -> str:
    return (os.getenv(key) or default).strip()


ADMIN_USERNAME = _env_str("ADMIN_USERNAME", "admin")
_ADMIN_PASSWORD_HASH = ""
_ADMIN_PASSWORD_SALT = ""
_PASSWORD_SET = False

# --- rate limiter ---
_MAX_ATTEMPTS = 5
_WINDOW_SECONDS = 300  # 5 minutes
_login_attempts: dict[str, list[float]] = {}  # key -> [timestamps]
_ACCOUNT_AUTHENTICATOR: Callable[[str, str], dict | None] | None = None
_ACCOUNT_LOOKUP: Callable[[str], dict | None] | None = None


def set_account_auth_handlers(
    *,
    authenticator: Callable[[str, str], dict | None] | None = None,
    lookup: Callable[[str], dict | None] | None = None,
) -> None:
    global _ACCOUNT_AUTHENTICATOR, _ACCOUNT_LOOKUP
    _ACCOUNT_AUTHENTICATOR = authenticator
    _ACCOUNT_LOOKUP = lookup


def _prune_attempts(key: str, now: float) -> list[float]:
    window_start = now - _WINDOW_SECONDS
    attempts = [t for t in _login_attempts.get(key, []) if t > window_start]
    _login_attempts[key] = attempts
    return attempts


def _rate_limited(key: str) -> bool:
    now = time.time()
    attempts = _prune_attempts(key, now)
    return len(attempts) >= _MAX_ATTEMPTS


def _record_attempt(key: str) -> None:
    now = time.time()
    _prune_attempts(key, now)
    _login_attempts.setdefault(key, []).append(now)


def _rate_limit_key() -> str:
    # Prefer X-Forwarded-For when behind a reverse proxy
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()
    else:
        client_ip = request.remote_addr or "127.0.0.1"
    return hashlib.sha256(client_ip.encode()).hexdigest()


# --- password hashing ---


def _hash_password(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), 200_000
    ).hex()


def init_auth(app) -> None:
    global _ADMIN_PASSWORD_HASH, _ADMIN_PASSWORD_SALT, _PASSWORD_SET

    app.secret_key = os.getenv(
        "FLASK_SECRET_KEY",
        hashlib.sha256(os.urandom(64)).hexdigest(),
    )

    # Session security defaults
    app.config.setdefault("SESSION_COOKIE_HTTPONLY", True)
    app.config.setdefault("SESSION_COOKIE_SAMESITE", "Lax")

    raw = _env_str("ADMIN_PASSWORD", "")
    if raw:
        _ADMIN_PASSWORD_SALT = os.getenv(
            "ADMIN_PASSWORD_SALT", secrets.token_hex(32)
        )
        _ADMIN_PASSWORD_HASH = _hash_password(raw, _ADMIN_PASSWORD_SALT)
        _PASSWORD_SET = True


def _check_password(password: str) -> bool:
    if not _PASSWORD_SET:
        return False
    return _ADMIN_PASSWORD_HASH == _hash_password(password, _ADMIN_PASSWORD_SALT)


def is_authenticated() -> bool:
    return session.get("_proxy_authed", False)


def get_authenticated_role() -> str:
    role = str(session.get("_proxy_role") or "admin").strip().lower()
    return role or "admin"


def get_authenticated_account_id() -> str:
    return str(session.get("_proxy_account_id") or "").strip()


def _set_authenticated_account(account: dict | None) -> None:
    if not isinstance(account, dict):
        return
    account_id = str(account.get("id") or account.get("account_id") or "").strip()
    if account_id:
        session["_proxy_account_id"] = account_id


def login_account_session(account: dict | None, *, role: str = "user") -> None:
    session.clear()
    session["_proxy_authed"] = True
    session["_proxy_role"] = str(role or "user").strip().lower() or "user"
    _set_authenticated_account(account)
    session.permanent = False
    _generate_csrf_token()


def _generate_csrf_token() -> str:
    token = session.get("_csrf_token", "")
    if not token:
        token = secrets.token_hex(32)
        session["_csrf_token"] = token
    return token


def _check_csrf() -> bool:
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return True
    token = request.form.get("_csrf_token", "")
    expected = session.get("_csrf_token", "")
    if not token or not expected:
        return False
    return secrets.compare_digest(token, expected)


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if request.method == "OPTIONS":
            return view(*args, **kwargs)
        if not is_authenticated():
            return redirect(url_for("login_page", next=request.full_path))
        return view(*args, **kwargs)

    return wrapper


def admin_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if request.method == "OPTIONS":
            return view(*args, **kwargs)
        if not is_authenticated():
            return redirect(url_for("login_page", next=request.full_path))
        if get_authenticated_role() != "admin":
            return abort(403)
        return view(*args, **kwargs)

    return wrapper


def account_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if request.method == "OPTIONS":
            return view(*args, **kwargs)
        if not is_authenticated():
            return redirect(url_for("login_page", next=request.full_path))
        if not get_authenticated_account_id():
            return abort(403)
        return view(*args, **kwargs)

    return wrapper


# --- login page ---

LOGIN_PAGE_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>登录 — 代理控制台</title>
<style>
  * { box-sizing:border-box; margin:0; padding:0 }
  body { font-family:"Segoe UI","Microsoft YaHei",sans-serif; background:#f1f5f9; display:flex; align-items:center; justify-content:center; min-height:100vh }
  .card { background:#fff; border:1px solid #e2e8f0; border-radius:12px; padding:32px 28px; width:100%; max-width:380px; box-shadow:0 4px 16px rgba(0,0,0,.06) }
  h1 { font-size:20px; margin-bottom:8px; color:#0f172a }
  .sub { font-size:13px; color:#64748b; margin-bottom:24px }
  label { display:block; font-size:13px; font-weight:600; margin-bottom:4px; color:#334155 }
  input { width:100%; padding:10px 12px; border:1px solid #cbd5e1; border-radius:8px; font-size:14px; margin-bottom:16px; outline:none }
  input:focus { border-color:#3b82f6; box-shadow:0 0 0 3px rgba(59,130,246,.15) }
  button { width:100%; padding:10px; background:#0f172a; color:#fff; border:none; border-radius:8px; font-size:14px; font-weight:600; cursor:pointer }
  button:hover { background:#1e293b }
  .error { background:#fef2f2; color:#b91c1c; padding:10px 12px; border-radius:8px; font-size:13px; margin-bottom:16px; border:1px solid #fecaca }
  .info { background:#eff6ff; color:#1d4ed8; padding:10px 12px; border-radius:8px; font-size:13px; margin-bottom:16px; border:1px solid #bfdbfe }
</style>
</head>
<body>
<div class="card">
  <h1>代理控制台</h1>
  <p class="sub">请输入管理员密码以继续</p>
  {% if error %}<div class="error">{{ error }}</div>{% endif %}
  {% if info %}<div class="info">{{ info }}</div>{% endif %}
  <form method="post">
    <input type="hidden" name="_csrf_token" value="{{ csrf_token }}">
    <label for="username">用户名</label>
    <input id="username" name="username" type="text" value="{{ username }}" autocomplete="username" autofocus>
    <label for="password">密码</label>
    <input id="password" name="password" type="password" autocomplete="current-password">
    <button type="submit">登 录</button>
  </form>
</div>
</body>
</html>"""


def login_page():
    if is_authenticated():
        if get_authenticated_role() == "user":
            return redirect("/v1#/keys")
        return redirect("/v1#/admin/dashboard")
    error = ""
    info = ""
    username = ""
    csrf_token = _generate_csrf_token()

    if request.method == "POST":
        if not _check_csrf():
            error = "请求已过期，请刷新页面后重试"
            from flask import render_template_string

            return (
                render_template_string(
                    LOGIN_PAGE_HTML,
                    error=error,
                    info=info,
                    username=username,
                    csrf_token=csrf_token,
                ),
                403,
            )

        rate_key = _rate_limit_key()
        if _rate_limited(rate_key):
            error = f"尝试次数过多，请 {_WINDOW_SECONDS // 60} 分钟后再试"
            from flask import render_template_string

            return (
                render_template_string(
                    LOGIN_PAGE_HTML,
                    error=error,
                    info=info,
                    username=username,
                    csrf_token=csrf_token,
                ),
                429,
            )

        username = (request.form.get("username") or "").strip()
        password_val = (request.form.get("password") or "").strip()

        if username == ADMIN_USERNAME and _check_password(password_val):
            _login_attempts.pop(rate_key, None)
            # Regenerate session on login to prevent fixation
            session.clear()
            session["_proxy_authed"] = True
            session["_proxy_role"] = "admin"
            if _ACCOUNT_LOOKUP is not None:
                _set_authenticated_account(_ACCOUNT_LOOKUP(username))
            session.permanent = False
            _generate_csrf_token()
            next_url = request.args.get("next", "")
            if next_url and (next_url.startswith("/") and "//" not in next_url):
                return redirect(next_url)
            return redirect("/v1#/admin/dashboard")

        if _ACCOUNT_AUTHENTICATOR is not None:
            account = _ACCOUNT_AUTHENTICATOR(username, password_val)
            if account:
                _login_attempts.pop(rate_key, None)
                session.clear()
                session["_proxy_authed"] = True
                session["_proxy_role"] = "user"
                _set_authenticated_account(account)
                session.permanent = False
                _generate_csrf_token()
                next_url = request.args.get("next", "")
                if next_url and (next_url.startswith("/") and "//" not in next_url):
                    return redirect(next_url)
                return redirect("/v1#/keys")

        _record_attempt(rate_key)
        remaining = _MAX_ATTEMPTS - len(
            _prune_attempts(rate_key, time.time())
        )
        error = f"用户名或密码错误，还可尝试 {remaining} 次"

    from flask import render_template_string

    return render_template_string(
        LOGIN_PAGE_HTML,
        error=error,
        info=info,
        username=username,
        csrf_token=csrf_token,
    )


def logout():
    session.clear()
    return redirect(url_for("login_page"))
