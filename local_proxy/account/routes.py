from __future__ import annotations

from flask import jsonify, request


def register_account_routes(app, *, account_required, account_service, get_account_id) -> None:
    def current_account_id() -> str:
        return str(get_account_id() or "").strip()

    @app.get("/account/me")
    @account_required
    def account_me():
        return jsonify(account_service.account_me(current_account_id()))

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
