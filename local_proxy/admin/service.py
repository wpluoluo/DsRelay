from __future__ import annotations

from .analytics import AdminAnalyticsMixin
from .api_keys import AdminApiKeysMixin
from .base import AdminServiceBase
from .content import AdminContentMixin
from .payments import AdminPaymentsMixin
from .protocols import AdminProtocolsMixin
from .subscriptions import AdminSubscriptionsMixin
from .users import AdminUsersMixin


class AdminConsoleService(
    AdminContentMixin,
    AdminProtocolsMixin,
    AdminPaymentsMixin,
    AdminSubscriptionsMixin,
    AdminApiKeysMixin,
    AdminUsersMixin,
    AdminAnalyticsMixin,
    AdminServiceBase,
):
    pass
