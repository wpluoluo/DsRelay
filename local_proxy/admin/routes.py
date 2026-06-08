from __future__ import annotations

from flask import jsonify, request

def register_admin_routes(app, *, admin_required, analytics_service) -> None:
    @app.get("/admin/overview")
    @admin_required
    def admin_overview():
        return jsonify(analytics_service.dashboard_summary())

    @app.get("/admin/accounts")
    @admin_required
    def admin_accounts():
        return jsonify(analytics_service.list_accounts())

    @app.post("/admin/accounts")
    @admin_required
    def admin_accounts_upsert():
        payload = request.get_json(silent=True) or {}
        return jsonify(analytics_service.upsert_account(payload))

    @app.get("/admin/accounts/<account_id>")
    @admin_required
    def admin_account_get(account_id: str):
        return jsonify(analytics_service.get_account(account_id))

    @app.post("/admin/accounts/<account_id>/balance")
    @admin_required
    def admin_account_balance(account_id: str):
        payload = request.get_json(silent=True) or {}
        return jsonify(analytics_service.set_account_balance(account_id, payload))

    @app.post("/admin/accounts/<account_id>/concurrency")
    @admin_required
    def admin_account_concurrency(account_id: str):
        payload = request.get_json(silent=True) or {}
        return jsonify(analytics_service.set_account_concurrency(account_id, payload))

    @app.post("/admin/accounts/<account_id>/allowed-groups")
    @admin_required
    def admin_account_allowed_groups(account_id: str):
        payload = request.get_json(silent=True) or {}
        return jsonify(analytics_service.set_account_allowed_groups(account_id, payload))

    @app.post("/admin/accounts/<account_id>/memberships")
    @admin_required
    def admin_account_memberships(account_id: str):
        payload = request.get_json(silent=True) or {}
        return jsonify(analytics_service.set_account_membership_groups(account_id, payload))

    @app.post("/admin/accounts/<account_id>/role-status")
    @admin_required
    def admin_account_role_status(account_id: str):
        payload = request.get_json(silent=True) or {}
        return jsonify(analytics_service.set_account_role_status(account_id, payload))

    @app.get("/admin/groups")
    @admin_required
    def admin_groups():
        return jsonify(analytics_service.list_groups())

    @app.post("/admin/groups")
    @admin_required
    def admin_groups_upsert():
        payload = request.get_json(silent=True) or {}
        return jsonify(analytics_service.upsert_group(payload))

    @app.get("/admin/usage")
    @admin_required
    def admin_usage():
        return jsonify(
            analytics_service.list_usage(
                started_after=request.args.get("started_after"),
                started_before=request.args.get("started_before"),
            )
        )

    @app.get("/admin/billing")
    @admin_required
    def admin_billing():
        return jsonify(
            analytics_service.billing_summary(
                started_after=request.args.get("started_after"),
                started_before=request.args.get("started_before"),
            )
        )

    @app.get("/admin/api-keys")
    @admin_required
    def admin_api_keys():
        return jsonify(analytics_service.list_api_keys())

    @app.post("/admin/api-keys")
    @admin_required
    def admin_api_keys_create():
        payload = request.get_json(silent=True) or {}
        return jsonify(analytics_service.create_api_key(payload))

    @app.post("/admin/api-keys/<key_id>/enabled")
    @admin_required
    def admin_api_keys_enabled(key_id: str):
        payload = request.get_json(silent=True) or {}
        return jsonify(analytics_service.set_api_key_enabled(key_id, payload.get("enabled") is True))

    @app.get("/admin/subscription-plans")
    @admin_required
    def admin_subscription_plans():
        return jsonify(analytics_service.list_subscription_plans())

    @app.post("/admin/subscription-plans")
    @admin_required
    def admin_subscription_plans_upsert():
        payload = request.get_json(silent=True) or {}
        return jsonify(analytics_service.upsert_subscription_plan(payload))

    @app.get("/admin/subscriptions")
    @admin_required
    def admin_subscriptions():
        return jsonify(analytics_service.list_account_subscriptions())

    @app.post("/admin/subscriptions/assign")
    @admin_required
    def admin_subscriptions_assign():
        payload = request.get_json(silent=True) or {}
        return jsonify(analytics_service.assign_subscription(payload))

    @app.post("/admin/subscriptions/<subscription_id>/extend")
    @admin_required
    def admin_subscriptions_extend(subscription_id: str):
        payload = request.get_json(silent=True) or {}
        return jsonify(analytics_service.extend_subscription(subscription_id, payload))

    @app.post("/admin/subscriptions/<subscription_id>/reset-quota")
    @admin_required
    def admin_subscriptions_reset_quota(subscription_id: str):
        payload = request.get_json(silent=True) or {}
        return jsonify(analytics_service.reset_subscription_quota(subscription_id, payload))

    @app.delete("/admin/subscriptions/<subscription_id>")
    @admin_required
    def admin_subscriptions_revoke(subscription_id: str):
        return jsonify(analytics_service.revoke_subscription(subscription_id))

    @app.get("/admin/payment-channels")
    @admin_required
    def admin_payment_channels():
        return jsonify(analytics_service.list_payment_channels())

    @app.post("/admin/payment-channels")
    @admin_required
    def admin_payment_channels_upsert():
        payload = request.get_json(silent=True) or {}
        return jsonify(analytics_service.upsert_payment_channel(payload))

    @app.get("/admin/payment-channels/template")
    @admin_required
    def admin_payment_channels_template():
        provider = str(request.args.get("provider") or "")
        return jsonify({"ok": True, "provider": provider or "manual", "config": analytics_service.payment_channel_config_template(provider)})

    @app.get("/admin/payment-orders")
    @admin_required
    def admin_payment_orders():
        return jsonify(analytics_service.list_payment_orders())

    @app.post("/admin/payment-orders")
    @admin_required
    def admin_payment_orders_create():
        payload = request.get_json(silent=True) or {}
        return jsonify(analytics_service.create_payment_order(payload))

    @app.post("/admin/payment-orders/<order_id>/status")
    @admin_required
    def admin_payment_orders_update_status(order_id: str):
        payload = request.get_json(silent=True) or {}
        return jsonify(analytics_service.update_payment_order_status(order_id, payload))

    @app.get("/admin/protocols")
    @admin_required
    def admin_protocols():
        return jsonify(analytics_service.list_protocol_profiles())

    @app.post("/payment/webhook/<order_id>")
    def payment_webhook(order_id: str):
        payload = request.get_json(silent=True) or {}
        signature = str(request.headers.get("X-Payment-Signature") or request.headers.get("X-Signature") or "")
        return jsonify(analytics_service.process_payment_webhook(order_id, payload, signature))
