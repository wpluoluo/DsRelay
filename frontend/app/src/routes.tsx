import { createHashHistory, createRootRoute, createRoute, createRouter, redirect } from '@tanstack/react-router';
import { DashboardLayout } from './layout/DashboardLayout';
import { AdminAccountsPage } from './pages/AdminAccountsPage';
import { AdminUsagePage } from './pages/AdminUsagePage';
import { AdminChannelsMonitorPage, AdminChannelsPricingPage } from './pages/AdminChannelsPage';
import {
  AdminAffiliateInvitesPage,
  AdminAffiliateRebatesPage,
  AdminAffiliateTransfersPage,
  AdminAnnouncementsPage,
  AdminPromoCodesPage,
  AdminRedeemCodesPage,
  AdminRiskControlPage,
} from './pages/AdminContentPages';
import { AdminGroupsPage } from './pages/AdminGroupsPage';
import { AdminOpsPage } from './pages/AdminOpsPage';
import { AdminOrdersDashboardPage } from './pages/AdminOrdersDashboardPage';
import { AdminProxyPage } from './pages/AdminProxyPage';
import { AdminUsersPage } from './pages/AdminUsersPage';
import { AdminPaymentOrdersPage } from './pages/AdminPaymentOrdersPage';
import { AdminSettingsPage } from './pages/AdminSettingsPage';
import { AdminSubscriptionPlansPage } from './pages/AdminSubscriptionPlansPage';
import { AdminSubscriptionsPage } from './pages/AdminSubscriptionsPage';
import { AccountApiKeysPage } from './pages/AccountApiKeysPage';
import { AccountAvailableChannelsPage, AccountMonitorPage, AccountProfilePage } from './pages/AccountChannelPages';
import { AccountAffiliatePage, AccountRedeemPage } from './pages/AccountValuePages';
import { AccountOrdersPage } from './pages/AccountOrdersPage';
import { AccountSubscriptionsPage } from './pages/AccountSubscriptionsPage';
import { AccountUsagePage } from './pages/AccountUsagePage';
import { Overview } from './pages/Overview';
import { PurchaseCenterPage } from './pages/PurchaseCenterPage';
import { useDashboard } from './state/dashboardContext';

function AdminDashboardRoute() {
  const { state } = useDashboard();
  return <Overview state={state} />;
}

function AdminUsageRoute() {
  return <AdminUsagePage />;
}

function AccountKeysRoute() {
  return <AccountApiKeysPage />;
}

function AccountUsageRoute() {
  return <AccountUsagePage />;
}

function AccountSubscriptionsRoute() {
  return <AccountSubscriptionsPage />;
}

function AccountOrdersRoute() {
  return <AccountOrdersPage />;
}

function AccountPurchaseRoute() {
  return <PurchaseCenterPage />;
}

const rootRoute = createRootRoute({ component: DashboardLayout });

const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/',
  beforeLoad: () => {
    throw redirect({ to: '/admin/dashboard' });
  },
});

const adminRedirectRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/admin',
  beforeLoad: () => {
    throw redirect({ to: '/admin/dashboard' });
  },
});

const adminDashboardRoute = createRoute({ getParentRoute: () => rootRoute, path: '/admin/dashboard', component: AdminDashboardRoute });
const adminOpsRoute = createRoute({ getParentRoute: () => rootRoute, path: '/admin/ops', component: AdminOpsPage });
const adminUsersRoute = createRoute({ getParentRoute: () => rootRoute, path: '/admin/users', component: AdminUsersPage });
const adminGroupsRoute = createRoute({ getParentRoute: () => rootRoute, path: '/admin/groups', component: AdminGroupsPage });
const adminChannelsRedirectRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/admin/channels',
  beforeLoad: () => {
    throw redirect({ to: '/admin/channels/pricing' });
  },
});
const adminChannelsPricingRoute = createRoute({ getParentRoute: () => rootRoute, path: '/admin/channels/pricing', component: AdminChannelsPricingPage });
const adminChannelsMonitorRoute = createRoute({ getParentRoute: () => rootRoute, path: '/admin/channels/monitor', component: AdminChannelsMonitorPage });
const adminSubscriptionsRoute = createRoute({ getParentRoute: () => rootRoute, path: '/admin/subscriptions', component: AdminSubscriptionsPage });
const adminAccountsRoute = createRoute({ getParentRoute: () => rootRoute, path: '/admin/accounts', component: AdminAccountsPage });
const adminAnnouncementsRoute = createRoute({ getParentRoute: () => rootRoute, path: '/admin/announcements', component: AdminAnnouncementsPage });
const adminProxiesRoute = createRoute({ getParentRoute: () => rootRoute, path: '/admin/proxies', component: AdminProxyPage });
const adminRiskControlRoute = createRoute({ getParentRoute: () => rootRoute, path: '/admin/risk-control', component: AdminRiskControlPage });
const adminRedeemRoute = createRoute({ getParentRoute: () => rootRoute, path: '/admin/redeem', component: AdminRedeemCodesPage });
const adminPromoCodesRoute = createRoute({ getParentRoute: () => rootRoute, path: '/admin/promo-codes', component: AdminPromoCodesPage });
const adminAffiliatesRedirectRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/admin/affiliates',
  beforeLoad: () => {
    throw redirect({ to: '/admin/affiliates/invites' });
  },
});
const adminAffiliateInvitesRoute = createRoute({ getParentRoute: () => rootRoute, path: '/admin/affiliates/invites', component: AdminAffiliateInvitesPage });
const adminAffiliateRebatesRoute = createRoute({ getParentRoute: () => rootRoute, path: '/admin/affiliates/rebates', component: AdminAffiliateRebatesPage });
const adminAffiliateTransfersRoute = createRoute({ getParentRoute: () => rootRoute, path: '/admin/affiliates/transfers', component: AdminAffiliateTransfersPage });
const adminOrdersDashboardRoute = createRoute({ getParentRoute: () => rootRoute, path: '/admin/orders/dashboard', component: AdminOrdersDashboardPage });
const adminOrdersRoute = createRoute({ getParentRoute: () => rootRoute, path: '/admin/orders', component: AdminPaymentOrdersPage });
const adminOrdersPlansRoute = createRoute({ getParentRoute: () => rootRoute, path: '/admin/orders/plans', component: AdminSubscriptionPlansPage });
const adminUsageRoute = createRoute({ getParentRoute: () => rootRoute, path: '/admin/usage', component: AdminUsageRoute });
const adminSettingsRoute = createRoute({ getParentRoute: () => rootRoute, path: '/admin/settings', component: AdminSettingsPage });

const keysRoute = createRoute({ getParentRoute: () => rootRoute, path: '/keys', component: AccountKeysRoute });
const usageRoute = createRoute({ getParentRoute: () => rootRoute, path: '/usage', component: AccountUsageRoute });
const availableChannelsRoute = createRoute({ getParentRoute: () => rootRoute, path: '/available-channels', component: AccountAvailableChannelsPage });
const monitorRoute = createRoute({ getParentRoute: () => rootRoute, path: '/monitor', component: AccountMonitorPage });
const subscriptionsRoute = createRoute({ getParentRoute: () => rootRoute, path: '/subscriptions', component: AccountSubscriptionsRoute });
const purchaseRoute = createRoute({ getParentRoute: () => rootRoute, path: '/purchase', component: AccountPurchaseRoute });
const ordersRoute = createRoute({ getParentRoute: () => rootRoute, path: '/orders', component: AccountOrdersRoute });
const redeemRoute = createRoute({ getParentRoute: () => rootRoute, path: '/redeem', component: AccountRedeemPage });
const affiliateRoute = createRoute({ getParentRoute: () => rootRoute, path: '/affiliate', component: AccountAffiliatePage });
const profileRoute = createRoute({ getParentRoute: () => rootRoute, path: '/profile', component: AccountProfilePage });

const routeTree = rootRoute.addChildren([
  indexRoute,
  adminRedirectRoute,
  adminDashboardRoute,
  adminOpsRoute,
  adminUsersRoute,
  adminGroupsRoute,
  adminChannelsRedirectRoute,
  adminChannelsPricingRoute,
  adminChannelsMonitorRoute,
  adminSubscriptionsRoute,
  adminAccountsRoute,
  adminAnnouncementsRoute,
  adminProxiesRoute,
  adminRiskControlRoute,
  adminRedeemRoute,
  adminPromoCodesRoute,
  adminAffiliatesRedirectRoute,
  adminAffiliateInvitesRoute,
  adminAffiliateRebatesRoute,
  adminAffiliateTransfersRoute,
  adminOrdersDashboardRoute,
  adminOrdersRoute,
  adminOrdersPlansRoute,
  adminUsageRoute,
  adminSettingsRoute,
  keysRoute,
  usageRoute,
  availableChannelsRoute,
  monitorRoute,
  subscriptionsRoute,
  purchaseRoute,
  ordersRoute,
  redeemRoute,
  affiliateRoute,
  profileRoute,
]);

export const router = createRouter({ routeTree, history: createHashHistory() });

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router;
  }
}
