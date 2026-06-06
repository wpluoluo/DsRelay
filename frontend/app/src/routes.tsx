import { createHashHistory, createRootRoute, createRoute, createRouter } from '@tanstack/react-router';
import { ConfigView } from './features/config/ConfigView';
import { RequestsView } from './features/requests/RequestsView';
import { DashboardLayout } from './layout/DashboardLayout';
import { LogsView } from './pages/LogsView';
import { Overview } from './pages/Overview';
import { ProxyKeysPage } from './pages/ProxyKeysPage';
import { useDashboard } from './state/dashboardContext';

function OverviewRoute() {
  const { state, keyQuery } = useDashboard();
  return <Overview state={state} keys={keyQuery.data} />;
}

function RequestsRoute() {
  const { state } = useDashboard();
  return <RequestsView state={state} />;
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
  return <ProxyKeysPage />;
}

const rootRoute = createRootRoute({ component: DashboardLayout });
const indexRoute = createRoute({ getParentRoute: () => rootRoute, path: '/', component: OverviewRoute });
const requestsRoute = createRoute({ getParentRoute: () => rootRoute, path: '/requests', component: RequestsRoute });
const logsRoute = createRoute({ getParentRoute: () => rootRoute, path: '/logs', component: LogsRoute });
const keysRoute = createRoute({ getParentRoute: () => rootRoute, path: '/keys', component: KeysRoute });
const configRoute = createRoute({ getParentRoute: () => rootRoute, path: '/config', component: ConfigRoute });

const routeTree = rootRoute.addChildren([indexRoute, requestsRoute, logsRoute, keysRoute, configRoute]);

export const router = createRouter({ routeTree, history: createHashHistory() });

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router;
  }
}
