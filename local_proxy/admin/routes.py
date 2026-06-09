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
        return jsonify(analytics_service.list_provider_accounts())

    @app.get("/admin/users")
    @admin_required
    def admin_users():
        return jsonify(analytics_service.list_users())

    @app.post("/admin/users")
    @admin_required
    def admin_users_create():
        payload = request.get_json(silent=True) or {}
        return jsonify(analytics_service.create_user(payload))

    @app.post("/admin/users/<account_id>")
    @admin_required
    def admin_users_update(account_id: str):
        payload = request.get_json(silent=True) or {}
        return jsonify(analytics_service.update_user(account_id, payload))

    @app.post("/admin/users/<account_id>/enabled")
    @admin_required
    def admin_users_enabled(account_id: str):
        payload = request.get_json(silent=True) or {}
        return jsonify(analytics_service.set_user_enabled(account_id, payload.get("enabled") is True))

    @app.post("/admin/users/<account_id>/reset-key")
    @admin_required
    def admin_users_reset_key(account_id: str):
        return jsonify(analytics_service.reset_user_external_key(account_id))

    @app.get("/admin/users/<account_id>/balance-events")
    @admin_required
    def admin_users_balance_events(account_id: str):
        limit = request.args.get("limit", "200")
        try:
            normalized_limit = int(limit)
        except Exception:
            normalized_limit = 200
        return jsonify(analytics_service.list_user_balance_events(account_id, limit=normalized_limit))

    @app.post("/admin/users/<account_id>/balance")
    @admin_required
    def admin_users_balance(account_id: str):
        payload = request.get_json(silent=True) or {}
        return jsonify(analytics_service.adjust_user_balance(account_id, payload))

    @app.delete("/admin/users/<account_id>")
    @admin_required
    def admin_users_delete(account_id: str):
        return jsonify(analytics_service.delete_user(account_id))

    @app.get("/admin/groups")
    @admin_required
    def admin_groups():
        return jsonify(analytics_service.list_groups())

    @app.post("/admin/groups")
    @admin_required
    def admin_groups_upsert():
        payload = request.get_json(silent=True) or {}
        return jsonify(analytics_service.upsert_group(payload))

    @app.delete("/admin/groups/<group_id>")
    @admin_required
    def admin_groups_delete(group_id: str):
        return jsonify(analytics_service.delete_group(group_id))

    @app.get("/admin/channels")
    @admin_required
    def admin_channels():
        return jsonify(analytics_service.list_channels())

    @app.post("/admin/channels")
    @admin_required
    def admin_channels_upsert():
        payload = request.get_json(silent=True) or {}
        return jsonify(analytics_service.upsert_channel(payload))

    @app.delete("/admin/channels/<channel_id>")
    @admin_required
    def admin_channels_delete(channel_id: str):
        return jsonify(analytics_service.delete_channel(channel_id))

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

    @app.post("/admin/api-keys/<key_id>")
    @admin_required
    def admin_api_keys_update(key_id: str):
        payload = request.get_json(silent=True) or {}
        return jsonify(analytics_service.update_api_key(key_id, payload))

    @app.post("/admin/api-keys/<key_id>/enabled")
    @admin_required
    def admin_api_keys_enabled(key_id: str):
        payload = request.get_json(silent=True) or {}
        return jsonify(analytics_service.set_api_key_enabled(key_id, payload.get("enabled") is True))

    @app.delete("/admin/api-keys/<key_id>")
    @admin_required
    def admin_api_keys_delete(key_id: str):
        return jsonify(analytics_service.delete_api_key(key_id))

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

    @app.get("/admin/announcements")
    @admin_required
    def admin_announcements():
        return jsonify(analytics_service.list_content_bucket("announcements"))

    @app.post("/admin/announcements")
    @admin_required
    def admin_announcements_upsert():
        payload = request.get_json(silent=True) or {}
        return jsonify(analytics_service.upsert_content_bucket_item("announcements", payload))

    @app.delete("/admin/announcements/<item_id>")
    @admin_required
    def admin_announcements_delete(item_id: str):
        return jsonify(analytics_service.delete_content_bucket_item("announcements", item_id))

    @app.get("/admin/risk-control")
    @admin_required
    def admin_risk_control():
        return jsonify(analytics_service.list_content_bucket("risk-rules"))

    @app.post("/admin/risk-control")
    @admin_required
    def admin_risk_control_upsert():
        payload = request.get_json(silent=True) or {}
        return jsonify(analytics_service.upsert_content_bucket_item("risk-rules", payload))

    @app.delete("/admin/risk-control/<item_id>")
    @admin_required
    def admin_risk_control_delete(item_id: str):
        return jsonify(analytics_service.delete_content_bucket_item("risk-rules", item_id))

    @app.get("/admin/redeem")
    @admin_required
    def admin_redeem():
        return jsonify(analytics_service.list_content_bucket("redeem-codes"))

    @app.post("/admin/redeem")
    @admin_required
    def admin_redeem_upsert():
        payload = request.get_json(silent=True) or {}
        return jsonify(analytics_service.upsert_content_bucket_item("redeem-codes", payload))

    @app.delete("/admin/redeem/<item_id>")
    @admin_required
    def admin_redeem_delete(item_id: str):
        return jsonify(analytics_service.delete_content_bucket_item("redeem-codes", item_id))

    @app.get("/admin/promo-codes")
    @admin_required
    def admin_promo_codes():
        return jsonify(analytics_service.list_content_bucket("promo-codes"))

    @app.post("/admin/promo-codes")
    @admin_required
    def admin_promo_codes_upsert():
        payload = request.get_json(silent=True) or {}
        return jsonify(analytics_service.upsert_content_bucket_item("promo-codes", payload))

    @app.delete("/admin/promo-codes/<item_id>")
    @admin_required
    def admin_promo_codes_delete(item_id: str):
        return jsonify(analytics_service.delete_content_bucket_item("promo-codes", item_id))

    @app.get("/admin/affiliates/invites")
    @admin_required
    def admin_affiliate_invites():
        return jsonify(analytics_service.list_content_bucket("affiliate-invites"))

    @app.post("/admin/affiliates/invites")
    @admin_required
    def admin_affiliate_invites_upsert():
        payload = request.get_json(silent=True) or {}
        return jsonify(analytics_service.upsert_content_bucket_item("affiliate-invites", payload))

    @app.delete("/admin/affiliates/invites/<item_id>")
    @admin_required
    def admin_affiliate_invites_delete(item_id: str):
        return jsonify(analytics_service.delete_content_bucket_item("affiliate-invites", item_id))

    @app.get("/admin/affiliates/rebates")
    @admin_required
    def admin_affiliate_rebates():
        return jsonify(analytics_service.list_content_bucket("affiliate-rebates"))

    @app.post("/admin/affiliates/rebates")
    @admin_required
    def admin_affiliate_rebates_upsert():
        payload = request.get_json(silent=True) or {}
        return jsonify(analytics_service.upsert_content_bucket_item("affiliate-rebates", payload))

    @app.delete("/admin/affiliates/rebates/<item_id>")
    @admin_required
    def admin_affiliate_rebates_delete(item_id: str):
        return jsonify(analytics_service.delete_content_bucket_item("affiliate-rebates", item_id))

    @app.get("/admin/affiliates/transfers")
    @admin_required
    def admin_affiliate_transfers():
        return jsonify(analytics_service.list_content_bucket("affiliate-transfers"))

    @app.post("/admin/affiliates/transfers")
    @admin_required
    def admin_affiliate_transfers_upsert():
        payload = request.get_json(silent=True) or {}
        return jsonify(analytics_service.upsert_content_bucket_item("affiliate-transfers", payload))

    @app.delete("/admin/affiliates/transfers/<item_id>")
    @admin_required
    def admin_affiliate_transfers_delete(item_id: str):
        return jsonify(analytics_service.delete_content_bucket_item("affiliate-transfers", item_id))

    @app.get("/admin/protocols")
    @admin_required
    def admin_protocols():
        return jsonify(analytics_service.list_protocol_profiles())

    @app.post("/payment/webhook/<order_id>")
    def payment_webhook(order_id: str):
        payload = request.get_json(silent=True) or {}
        signature = str(request.headers.get("X-Payment-Signature") or request.headers.get("X-Signature") or "")
        return jsonify(analytics_service.process_payment_webhook(order_id, payload, signature))
