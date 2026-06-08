from __future__ import annotations

from .analytics import AdminAnalyticsMixin
from .api_keys import AdminApiKeysMixin
from .base import AdminServiceBase
from .content import AdminContentMixin
from .payments import AdminPaymentsMixin
from .protocols import AdminProtocolsMixin
from .subscriptions import AdminSubscriptionsMixin
from .accounts import AdminAccountsMixin


class AdminConsoleService(
    AdminContentMixin,
    AdminProtocolsMixin,
    AdminPaymentsMixin,
    AdminSubscriptionsMixin,
    AdminApiKeysMixin,
    AdminAccountsMixin,
    AdminAnalyticsMixin,
    AdminServiceBase,
):
    pass
