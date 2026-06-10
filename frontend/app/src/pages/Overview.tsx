import { useQuery } from '@tanstack/react-query';
import { Link } from '@tanstack/react-router';
import { ArrowRight, Coins, FolderTree, ListChecks, Receipt, Server, Users } from 'lucide-react';
import { fetchAdminBilling, fetchAdminOverview } from '../api';
import { Empty, Panel, PanelHead } from '../components';
import { buildPageIntro } from '../navigation';
import type { DashboardState } from '../types';
import { formatNumber, formatTokenCount, formatUsdCost } from '../utils';

export function Overview({ state }: { state: DashboardState }) {
  const overviewQuery = useQuery({ queryKey: ['admin-overview'], queryFn: fetchAdminOverview, refetchInterval: 10000 });
  const billingQuery = useQuery({ queryKey: ['admin-billing-overview'], queryFn: () => fetchAdminBilling(), refetchInterval: 15000 });
  const overview = overviewQuery.data || {};
  const billing = billingQuery.data || {};
  const summary = billing.summary || {};
  const topAccounts = overview.top_accounts || [];
  const topGroups = overview.top_groups || [];

  return (
    <section className="dashboard-page">
      {buildPageIntro('/admin/dashboard')}

      <div className="dashboard-stats-grid">
        <DashboardStat icon={<Users size={18} />} label="用户" value={formatNumber(overview.account_count ?? 0)} sub={`重点 ${formatNumber(topAccounts.length)}`} tone="green" />
        <DashboardStat icon={<Server size={18} />} label="账号" value={formatNumber(state.pools_count ?? 0)} sub={`启用 ${formatNumber(state.pools_enabled_count ?? 0)}`} tone="violet" />
        <DashboardStat icon={<ListChecks size={18} />} label="请求" value={formatNumber(summary.request_count ?? overview.request_count ?? 0)} sub={`错误 ${formatNumber(summary.error_count ?? overview.error_count ?? 0)}`} tone="amber" />
        <DashboardStat icon={<FolderTree size={18} />} label="分组" value={formatNumber(overview.group_count ?? 0)} sub={`重点 ${formatNumber(topGroups.length)}`} tone="indigo" />
      </div>

      <div className="dashboard-stats-grid">
        <DashboardStat icon={<Coins size={18} />} label="总 Token" value={formatTokenCount(summary.total_tokens ?? overview.total_tokens ?? 0)} sub={`请求 ${formatNumber(summary.request_count ?? overview.request_count ?? 0)}`} tone="slate" />
        <DashboardStat icon={<Coins size={18} />} label="标准成本" value={formatUsdCost(summary.total_cost ?? 0)} sub="累计口径" tone="green" />
        <DashboardStat icon={<Coins size={18} />} label="实际成本" value={formatUsdCost(summary.actual_cost ?? 0)} sub={`覆盖请求 ${formatNumber(summary.covered_request_count ?? 0)}`} tone="rose" />
        <DashboardStat
          icon={<Receipt size={18} />}
          label="订单金额"
          value={formatUsdCost((Number(summary.amount_cents ?? 0) || 0) / 100, 2)}
          sub={`订阅中 ${formatNumber(summary.active_subscription_count ?? 0)}`}
          tone="amber"
        />
      </div>

      <div className="dashboard-charts-grid">
        <Panel className="dashboard-card">
          <PanelHead title="重点用户" action={<Link to="/admin/users" className="panel-link">查看全部 <ArrowRight size={14} /></Link>} />
          <div className="recent-usage-list">
            {topAccounts.length ? topAccounts.map((item) => (
              <div className="recent-usage-item" key={item.id}>
                <div className="recent-usage-icon"><Users size={17} /></div>
                <div className="recent-usage-main">
                  <strong>{item.name || item.id}</strong>
                  <span>{item.group_name || item.source_type || '-'}</span>
                </div>
                <div className="recent-usage-meta">
                  <strong>{formatTokenCount(item.total_tokens || 0)}</strong>
                  <span className={(item.error_count || 0) > 0 ? 'bad' : 'ok'}>
                    {(item.error_count || 0) > 0 ? `错误 ${formatNumber(item.error_count || 0)}` : `请求 ${formatNumber(item.request_count || 0)}`}
                  </span>
                </div>
              </div>
            )) : <Empty>暂无用户数据。</Empty>}
          </div>
        </Panel>

        <Panel className="dashboard-card">
          <PanelHead title="重点分组" action={<Link to="/admin/groups" className="panel-link">查看全部 <ArrowRight size={14} /></Link>} />
          <div className="recent-usage-list">
            {topGroups.length ? topGroups.map((item) => (
              <div className="recent-usage-item" key={item.id}>
                <div className="recent-usage-icon"><FolderTree size={17} /></div>
                <div className="recent-usage-main">
                  <strong>{item.name || item.id}</strong>
                  <span>{item.description || item.platform || '-'}</span>
                </div>
                <div className="recent-usage-meta">
                  <strong>{formatTokenCount(item.total_tokens || 0)}</strong>
                  <span className={(item.error_count || 0) > 0 ? 'bad' : 'ok'}>
                    {(item.error_count || 0) > 0 ? `错误 ${formatNumber(item.error_count || 0)}` : `请求 ${formatNumber(item.request_count || 0)}`}
                  </span>
                </div>
              </div>
            )) : <Empty>暂无分组数据。</Empty>}
          </div>
        </Panel>
      </div>
    </section>
  );
}

function DashboardStat({
  icon,
  label,
  value,
  sub,
  tone,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  sub: string;
  tone: string;
}) {
  return (
    <div className="dashboard-stat">
      <div className={`dashboard-stat-icon ${tone}`}>{icon}</div>
      <div className="dashboard-stat-body">
        <span>{label}</span>
        <strong>{value}</strong>
        <small>{sub}</small>
      </div>
    </div>
  );
}
