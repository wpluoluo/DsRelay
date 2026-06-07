from __future__ import annotations

from flask import jsonify, request


def register_admin_routes(app, *, login_required, analytics_service) -> None:
    @app.get("/admin/overview")
    @login_required
    def admin_overview():
        return jsonify(analytics_service.dashboard_summary())

    @app.get("/admin/users")
    @login_required
    def admin_users():
        return jsonify(analytics_service.list_users())

    @app.post("/admin/users")
    @login_required
    def admin_users_upsert():
        payload = request.get_json(silent=True) or {}
        return jsonify(analytics_service.upsert_user(payload))

    @app.get("/admin/groups")
    @login_required
    def admin_groups():
        return jsonify(analytics_service.list_groups())

    @app.post("/admin/groups")
    @login_required
    def admin_groups_upsert():
        payload = request.get_json(silent=True) or {}
        return jsonify(analytics_service.upsert_group(payload))

    @app.get("/admin/usage")
    @login_required
    def admin_usage():
        return jsonify(analytics_service.list_usage())

    @app.get("/admin/api-keys")
    @login_required
    def admin_api_keys():
        return jsonify(analytics_service.list_api_keys())

    @app.post("/admin/api-keys")
    @login_required
    def admin_api_keys_create():
        payload = request.get_json(silent=True) or {}
        return jsonify(analytics_service.create_api_key(payload))

    @app.post("/admin/api-keys/<key_id>/enabled")
    @login_required
    def admin_api_keys_enabled(key_id: str):
        payload = request.get_json(silent=True) or {}
        return jsonify(analytics_service.set_api_key_enabled(key_id, payload.get("enabled") is True))

    @app.get("/admin/subscription-plans")
    @login_required
    def admin_subscription_plans():
        return jsonify(analytics_service.list_subscription_plans())

    @app.post("/admin/subscription-plans")
    @login_required
    def admin_subscription_plans_upsert():
        payload = request.get_json(silent=True) or {}
        return jsonify(analytics_service.upsert_subscription_plan(payload))

    @app.get("/admin/subscriptions")
    @login_required
    def admin_subscriptions():
        return jsonify(analytics_service.list_user_subscriptions())

    @app.post("/admin/subscriptions/assign")
    @login_required
    def admin_subscriptions_assign():
        payload = request.get_json(silent=True) or {}
        return jsonify(analytics_service.assign_subscription(payload))

    @app.post("/admin/subscriptions/<subscription_id>/extend")
    @login_required
    def admin_subscriptions_extend(subscription_id: str):
        payload = request.get_json(silent=True) or {}
        return jsonify(analytics_service.extend_subscription(subscription_id, payload))

    @app.post("/admin/subscriptions/<subscription_id>/reset-quota")
    @login_required
    def admin_subscriptions_reset_quota(subscription_id: str):
        payload = request.get_json(silent=True) or {}
        return jsonify(analytics_service.reset_subscription_quota(subscription_id, payload))

    @app.delete("/admin/subscriptions/<subscription_id>")
    @login_required
    def admin_subscriptions_revoke(subscription_id: str):
        return jsonify(analytics_service.revoke_subscription(subscription_id))

    @app.get("/admin/payment-channels")
    @login_required
    def admin_payment_channels():
        return jsonify(analytics_service.list_payment_channels())

    @app.post("/admin/payment-channels")
    @login_required
    def admin_payment_channels_upsert():
        payload = request.get_json(silent=True) or {}
        return jsonify(analytics_service.upsert_payment_channel(payload))

    @app.get("/admin/payment-channels/template")
    @login_required
    def admin_payment_channels_template():
        provider = str(request.args.get("provider") or "")
        return jsonify({"ok": True, "provider": provider or "manual", "config": analytics_service.payment_channel_config_template(provider)})

    @app.get("/admin/payment-orders")
    @login_required
    def admin_payment_orders():
        return jsonify(analytics_service.list_payment_orders())

    @app.post("/admin/payment-orders")
    @login_required
    def admin_payment_orders_create():
        payload = request.get_json(silent=True) or {}
        return jsonify(analytics_service.create_payment_order(payload))

    @app.post("/payment/webhook/<order_id>")
    def payment_webhook(order_id: str):
        payload = request.get_json(silent=True) or {}
        signature = str(request.headers.get("X-Payment-Signature") or request.headers.get("X-Signature") or "")
        return jsonify(analytics_service.process_payment_webhook(order_id, payload, signature))
