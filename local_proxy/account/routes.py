from __future__ import annotations

from flask import jsonify, redirect, render_template_string, request


REGISTER_PAGE_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>注册 - 代理控制台</title>
<style>
  * { box-sizing:border-box; margin:0; padding:0 }
  body { font-family:"Segoe UI","Microsoft YaHei",sans-serif; background:#f1f5f9; display:flex; align-items:center; justify-content:center; min-height:100vh }
  .card { background:#fff; border:1px solid #e2e8f0; border-radius:12px; padding:32px 28px; width:100%; max-width:420px; box-shadow:0 4px 16px rgba(0,0,0,.06) }
  h1 { font-size:20px; margin-bottom:8px; color:#0f172a }
  .sub { font-size:13px; color:#64748b; margin-bottom:24px }
  label { display:block; font-size:13px; font-weight:600; margin-bottom:4px; color:#334155 }
  input { width:100%; padding:10px 12px; border:1px solid #cbd5e1; border-radius:8px; font-size:14px; margin-bottom:16px; outline:none }
  input:focus { border-color:#3b82f6; box-shadow:0 0 0 3px rgba(59,130,246,.15) }
  button { width:100%; padding:10px; background:#0f172a; color:#fff; border:none; border-radius:8px; font-size:14px; font-weight:600; cursor:pointer }
  .error { background:#fef2f2; color:#b91c1c; padding:10px 12px; border-radius:8px; font-size:13px; margin-bottom:16px; border:1px solid #fecaca }
  .hint { color:#64748b; font-size:12px; margin-top:-10px; margin-bottom:16px }
</style>
</head>
<body>
<div class="card">
  <h1>注册账户</h1>
  <p class="sub">创建业务账户后将自动登录到我的账户。</p>
  {% if error %}<div class="error">{{ error }}</div>{% endif %}
  <form method="post">
    <label for="name">账户名称</label>
    <input id="name" name="name" type="text" value="{{ name }}" autocomplete="name">
    <label for="email">邮箱</label>
    <input id="email" name="email" type="email" value="{{ email }}" autocomplete="email">
    <label for="username">用户名</label>
    <input id="username" name="username" type="text" value="{{ username }}" autocomplete="username">
    <label for="password">密码</label>
    <input id="password" name="password" type="password" autocomplete="new-password">
    <label for="confirm_password">确认密码</label>
    <input id="confirm_password" name="confirm_password" type="password" autocomplete="new-password">
    <label for="aff_code">邀请码</label>
    <input id="aff_code" name="aff_code" type="text" value="{{ aff_code }}">
    <div class="hint">可直接填写邀请码或访问邀请链接自动带入。</div>
    <button type="submit">注册并登录</button>
  </form>
</div>
</body>
</html>"""


def register_account_routes(app, *, account_required, account_service, get_account_id, login_account_session) -> None:
    @app.route("/register", methods=["GET", "POST"])
    def account_register_page():
        if request.method == "GET":
            return render_template_string(
                REGISTER_PAGE_HTML,
                error="",
                name="",
                email="",
                username="",
                aff_code=str(request.args.get("aff") or "").strip(),
            )
        name = str(request.form.get("name") or "").strip()
        email = str(request.form.get("email") or "").strip()
        username = str(request.form.get("username") or "").strip()
        password = str(request.form.get("password") or "").strip()
        confirm_password = str(request.form.get("confirm_password") or "").strip()
        aff_code = str(request.form.get("aff_code") or request.args.get("aff") or "").strip()
        error = ""
        if not (name or email or username):
            error = "请至少填写账户名称、邮箱或用户名中的一项"
        elif not password:
            error = "请输入密码"
        elif password != confirm_password:
            error = "两次输入的密码不一致"
        if error:
            return render_template_string(
                REGISTER_PAGE_HTML,
                error=error,
                name=name,
                email=email,
                username=username,
                aff_code=aff_code,
            ), 400
        try:
            result = account_service.register_account(
                {
                    "name": name,
                    "email": email,
                    "username": username,
                    "password": password,
                    "aff_code": aff_code,
                }
            )
        except Exception as exc:
            return render_template_string(
                REGISTER_PAGE_HTML,
                error=str(exc),
                name=name,
                email=email,
                username=username,
                aff_code=aff_code,
            ), 400
        item = result.get("item") if isinstance(result, dict) else None
        login_account_session(item, role="user")
        return redirect("/v1#/keys", code=302)

    @app.post("/account/register")
    def account_register_api():
        payload = request.get_json(silent=True) or {}
        try:
            result = account_service.register_account(payload)
        except Exception as exc:
            return jsonify({"ok": False, "message": str(exc)}), 400
        item = result.get("item") if isinstance(result, dict) else None
        login_account_session(item, role="user")
        return jsonify(result)

    def current_account_id() -> str:
        return str(get_account_id() or "").strip()

    @app.get("/account/me")
    @account_required
    def account_me():
        return jsonify(account_service.account_me(current_account_id()))

    @app.post("/account/me")
    @account_required
    def account_me_update():
        payload = request.get_json(silent=True) or {}
        return jsonify(account_service.update_profile(current_account_id(), payload))

    @app.get("/account/groups")
    @account_required
    def account_groups():
        return jsonify(account_service.list_groups(current_account_id()))

    @app.get("/account/channels")
    @account_required
    def account_channels():
        return jsonify(account_service.list_channels(current_account_id()))

    @app.get("/account/keys")
    @account_required
    def account_api_keys():
        return jsonify(account_service.list_api_keys(current_account_id()))

    @app.post("/account/keys")
    @account_required
    def account_api_keys_create():
        payload = request.get_json(silent=True) or {}
        return jsonify(account_service.create_api_key(current_account_id(), payload))

    @app.post("/account/keys/<key_id>")
    @account_required
    def account_api_keys_update(key_id: str):
        payload = request.get_json(silent=True) or {}
        return jsonify(account_service.update_api_key(current_account_id(), key_id, payload))

    @app.post("/account/keys/<key_id>/enabled")
    @account_required
    def account_api_keys_enabled(key_id: str):
        payload = request.get_json(silent=True) or {}
        return jsonify(account_service.set_api_key_enabled(current_account_id(), key_id, payload.get("enabled") is True))

    @app.delete("/account/keys/<key_id>")
    @account_required
    def account_api_keys_delete(key_id: str):
        return jsonify(account_service.delete_api_key(current_account_id(), key_id))

    @app.get("/account/usage")
    @account_required
    def account_usage():
        return jsonify(
            account_service.list_usage(
                current_account_id(),
                started_after=request.args.get("started_after"),
                started_before=request.args.get("started_before"),
                limit=request.args.get("limit", 5000),
            )
        )

    @app.get("/account/usage/stats")
    @account_required
    def account_usage_stats():
        return jsonify(
            account_service.usage_stats(
                current_account_id(),
                started_after=request.args.get("started_after"),
                started_before=request.args.get("started_before"),
            )
        )

    @app.get("/account/plans")
    @account_required
    def account_plans():
        return jsonify(account_service.list_subscription_plans(current_account_id()))

    @app.get("/account/subscription-plans")
    @account_required
    def account_subscription_plans():
        return jsonify(account_service.list_subscription_plans(current_account_id()))

    @app.get("/account/payment-channels")
    @account_required
    def account_payment_channels():
        return jsonify(account_service.list_payment_channels(current_account_id()))

    @app.get("/account/subscriptions")
    @account_required
    def account_subscriptions():
        return jsonify(account_service.list_subscriptions(current_account_id()))

    @app.get("/account/orders")
    @account_required
    def account_orders():
        return jsonify(account_service.list_orders(current_account_id()))

    @app.post("/account/orders")
    @account_required
    def account_orders_create():
        payload = request.get_json(silent=True) or {}
        return jsonify(account_service.create_order(current_account_id(), payload))

    @app.post("/account/orders/<order_id>/cancel")
    @account_required
    def account_orders_cancel(order_id: str):
        return jsonify(account_service.cancel_order(current_account_id(), order_id))

    @app.get("/account/redeem")
    @account_required
    def current_account_redeem_profile():
        return jsonify(account_service.redeem_profile(current_account_id()))

    @app.post("/account/redeem")
    @account_required
    def current_account_redeem_code():
        payload = request.get_json(silent=True) or {}
        return jsonify(account_service.redeem_code(current_account_id(), payload))

    @app.get("/account/affiliate")
    @account_required
    def current_account_affiliate_detail():
        return jsonify(account_service.affiliate_detail(current_account_id()))

    @app.post("/account/affiliate/transfer")
    @account_required
    def current_account_affiliate_transfer():
        return jsonify(account_service.transfer_affiliate_quota(current_account_id()))
