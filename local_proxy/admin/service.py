from __future__ import annotations

from .analytics import AdminAnalyticsMixin
from .api_keys import AdminApiKeysMixin
from .base import AdminServiceBase
from .payments import AdminPaymentsMixin
from .protocols import AdminProtocolsMixin
from .subscriptions import AdminSubscriptionsMixin
from .users import AdminUsersMixin


class AdminAnalyticsService(
    AdminProtocolsMixin,
    AdminPaymentsMixin,
    AdminSubscriptionsMixin,
    AdminApiKeysMixin,
    AdminUsersMixin,
    AdminAnalyticsMixin,
    AdminServiceBase,
):
    pass
