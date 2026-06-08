from __future__ import annotations

from .analytics import AdminAnalyticsMixin
from .api_keys import AdminApiKeysMixin
from .base import AdminServiceBase
from .channels import AdminChannelsMixin
from .content import AdminContentMixin
from .payments import AdminPaymentsMixin
from .protocols import AdminProtocolsMixin
from .subscriptions import AdminSubscriptionsMixin
from .users import AdminUsersMixin


class AdminConsoleService(
    AdminContentMixin,
    AdminChannelsMixin,
    AdminProtocolsMixin,
    AdminPaymentsMixin,
    AdminSubscriptionsMixin,
    AdminApiKeysMixin,
    AdminUsersMixin,
    AdminAnalyticsMixin,
    AdminServiceBase,
):
    pass
