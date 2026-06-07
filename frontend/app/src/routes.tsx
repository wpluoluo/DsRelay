import { createHashHistory, createRootRoute, createRoute, createRouter } from '@tanstack/react-router';
import { ConfigView } from './features/config/ConfigView';
import { RequestsView } from './features/requests/RequestsView';
import { DashboardLayout } from './layout/DashboardLayout';
import { AdminApiKeysPage } from './pages/AdminApiKeysPage';
import { AdminBillingPage } from './pages/AdminBillingPage';
import { AdminGroupsPage } from './pages/AdminGroupsPage';
import { AdminPaymentChannelsPage } from './pages/AdminPaymentChannelsPage';
import { AdminPaymentOrdersPage } from './pages/AdminPaymentOrdersPage';
import { AdminSubscriptionPlansPage } from './pages/AdminSubscriptionPlansPage';
import { AdminSubscriptionsPage } from './pages/AdminSubscriptionsPage';
import { AdminAccountsPage } from './pages/AdminAccountsPage';
import { LogsView } from './pages/LogsView';
import { Overview } from './pages/Overview';
import { PurchaseCenterPage } from './pages/PurchaseCenterPage';
import { ProxyKeysPage } from './pages/ProxyKeysPage';
import { UserApiKeysPage } from './pages/UserApiKeysPage';
import { UserDashboardPage } from './pages/UserDashboardPage';
import { UserOrdersPage } from './pages/UserOrdersPage';
import { UserSubscriptionsPage } from './pages/UserSubscriptionsPage';
import { UserUsagePage } from './pages/UserUsagePage';
import { useDashboard } from './state/dashboardContext';

function OverviewRoute() {
  const { state, keyQuery } = useDashboard();
  return <Overview state={state} keys={keyQuery.data} />;
}

function RequestsRoute() {
  const { state } = useDashboard();
  return <RequestsView state={state} />;
}

function UserUsageRoute() {
  return <UserUsagePage />;
}

function UserDashboardRoute() {
  return <UserDashboardPage />;
}

function UserOrdersRoute() {
  return <UserOrdersPage />;
}

function UserSubscriptionsRoute() {
  return <UserSubscriptionsPage />;
}

function LogsRoute() {
  const { state } = useDashboard();
  return <LogsView state={state} />;
}

function ConfigRoute() {
  const dashboard = useDashboard();
  return (
    <ConfigView
      draft={dashboard.draft}
      pools={dashboard.pools}
      configTab={dashboard.configTab}
      setConfigTab={dashboard.setConfigTab}
      status={dashboard.status}
      saving={dashboard.saving}
      onPatch={dashboard.patchDraft}
      onSave={dashboard.saveConfig}
      onOpenPool={dashboard.openPool}
      onDeletePool={dashboard.deletePool}
      onMovePool={dashboard.movePool}
    />
  );
}

function KeysRoute() {
  return <UserApiKeysPage />;
}

function ProxyKeysRoute() {
  return <ProxyKeysPage />;
}

function UsersRoute() {
  return <AdminAccountsPage />;
}

function GroupsRoute() {
  return <AdminGroupsPage />;
}

function BillingRoute() {
  return <AdminBillingPage />;
}

function AdminApiKeysRoute() {
  return <AdminApiKeysPage />;
}

function SubscriptionPlansRoute() {
  return <AdminSubscriptionPlansPage />;
}

function SubscriptionsRoute() {
  return <AdminSubscriptionsPage />;
}

function PaymentChannelsRoute() {
  return <AdminPaymentChannelsPage />;
}

function PaymentOrdersRoute() {
  return <AdminPaymentOrdersPage />;
}

function PurchaseCenterRoute() {
  return <PurchaseCenterPage />;
}

const rootRoute = createRootRoute({ component: DashboardLayout });
const indexRoute = createRoute({ getParentRoute: () => rootRoute, path: '/', component: OverviewRoute });
const requestsRoute = createRoute({ getParentRoute: () => rootRoute, path: '/requests', component: RequestsRoute });
const userUsageRoute = createRoute({ getParentRoute: () => rootRoute, path: '/usage', component: UserUsageRoute });
const userDashboardRoute = createRoute({ getParentRoute: () => rootRoute, path: '/user-dashboard', component: UserDashboardRoute });
const userOrdersRoute = createRoute({ getParentRoute: () => rootRoute, path: '/user-orders', component: UserOrdersRoute });
const userSubscriptionsRoute = createRoute({ getParentRoute: () => rootRoute, path: '/user-subscriptions', component: UserSubscriptionsRoute });
const logsRoute = createRoute({ getParentRoute: () => rootRoute, path: '/logs', component: LogsRoute });
const keysRoute = createRoute({ getParentRoute: () => rootRoute, path: '/keys', component: KeysRoute });
const proxyKeysRoute = createRoute({ getParentRoute: () => rootRoute, path: '/proxy-keys', component: ProxyKeysRoute });
const usersRoute = createRoute({ getParentRoute: () => rootRoute, path: '/users', component: UsersRoute });
const groupsRoute = createRoute({ getParentRoute: () => rootRoute, path: '/groups', component: GroupsRoute });
const billingRoute = createRoute({ getParentRoute: () => rootRoute, path: '/billing', component: BillingRoute });
const adminApiKeysRoute = createRoute({ getParentRoute: () => rootRoute, path: '/user-api-keys', component: AdminApiKeysRoute });
const subscriptionPlansRoute = createRoute({ getParentRoute: () => rootRoute, path: '/subscription-plans', component: SubscriptionPlansRoute });
const subscriptionsRoute = createRoute({ getParentRoute: () => rootRoute, path: '/subscriptions', component: SubscriptionsRoute });
const paymentChannelsRoute = createRoute({ getParentRoute: () => rootRoute, path: '/payment-channels', component: PaymentChannelsRoute });
const paymentOrdersRoute = createRoute({ getParentRoute: () => rootRoute, path: '/payment-orders', component: PaymentOrdersRoute });
const purchaseCenterRoute = createRoute({ getParentRoute: () => rootRoute, path: '/purchase', component: PurchaseCenterRoute });
const configRoute = createRoute({ getParentRoute: () => rootRoute, path: '/config', component: ConfigRoute });

const routeTree = rootRoute.addChildren([
  indexRoute,
  requestsRoute,
  userDashboardRoute,
  userOrdersRoute,
  userSubscriptionsRoute,
  userUsageRoute,
  logsRoute,
  keysRoute,
  proxyKeysRoute,
  usersRoute,
  groupsRoute,
  billingRoute,
  adminApiKeysRoute,
  subscriptionPlansRoute,
  subscriptionsRoute,
  paymentChannelsRoute,
  paymentOrdersRoute,
  purchaseCenterRoute,
  configRoute,
]);

export const router = createRouter({ routeTree, history: createHashHistory() });

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router;
  }
}
