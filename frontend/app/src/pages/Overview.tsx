import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link } from '@tanstack/react-router';
import { ArrowRight, Coins, FolderTree, KeyRound, ListChecks, Receipt, Users } from 'lucide-react';
import { fetchAdminBilling, fetchAdminOverview } from '../api';
import { Empty, Panel, PanelHead } from '../components';
import type { DashboardState, ProxyKeyPayload } from '../types';
import { formatNumber, formatTokenCount, formatUsdCost } from '../utils';

export function Overview({ state, keys }: { state: DashboardState; keys?: ProxyKeyPayload }) {
  const overviewQuery = useQuery({ queryKey: ['admin-overview'], queryFn: fetchAdminOverview, refetchInterval: 10000 });
  const billingQuery = useQuery({ queryKey: ['admin-billing-overview'], queryFn: () => fetchAdminBilling(), refetchInterval: 15000 });
  const overview = overviewQuery.data || {};
  const billing = billingQuery.data || {};
  const summary = billing.summary || {};
  const topUsers = overview.top_users || [];
  const topGroups = overview.top_groups || [];

  const operationCards = useMemo(() => ([
    {
      to: '/users',
      icon: <Users size={20} />,
      title: '用户管理',
      desc: '管理用户状态、角色、余额和订阅关系',
      tone: 'blue',
    },
    {
      to: '/subscriptions',
      icon: <ListChecks size={20} />,
      title: '订阅管理',
      desc: '处理分配、延期、重置和撤销',
      tone: 'amber',
    },
    {
      to: '/payment-orders',
      icon: <Receipt size={20} />,
      title: '支付订单',
      desc: '查看履约状态、拉起参数和失败订单',
      tone: 'violet',
    },
    {
      to: '/billing',
      icon: <Coins size={20} />,
      title: '计费分析',
      desc: '按用户、分组、计划和订单核账',
      tone: 'green',
    },
  ]), []);

  return (
    <section className="dashboard-page">
      <div className="sub2-page-head">
        <div className="sub2-page-title">
          <strong>仪表盘</strong>
          <span>对齐 SUB2 的管理员总览口径，聚焦用户、分组、请求和计费核心数据。</span>
        </div>
        <div className="overview-command-actions">
          <Link to="/users" className="btn">用户管理</Link>
          <Link to="/groups" className="btn">分组管理</Link>
          <Link to="/billing" className="btn btn-primary">计费管理</Link>
        </div>
      </div>

      <div className="dashboard-stats-grid">
        <DashboardStat icon={<KeyRound size={18} />} label="API Key" value={formatNumber(keys?.managed_key_count ?? 0)} sub={`${formatNumber(keys?.managed_enabled_count ?? 0)} 个启用`} tone="blue" />
        <DashboardStat icon={<Users size={18} />} label="用户" value={formatNumber(overview.user_count ?? 0)} sub={`Top ${formatNumber(topUsers.length)} 已加载`} tone="green" />
        <DashboardStat icon={<FolderTree size={18} />} label="分组" value={formatNumber(overview.group_count ?? 0)} sub={`Top ${formatNumber(topGroups.length)} 已加载`} tone="amber" />
        <DashboardStat icon={<ListChecks size={18} />} label="请求" value={formatNumber(summary.request_count ?? overview.request_count ?? 0)} sub={`错误 ${formatNumber(summary.error_count ?? overview.error_count ?? 0)}`} tone="violet" />
      </div>

      <div className="dashboard-stats-grid">
        <DashboardStat icon={<Coins size={18} />} label="总 Token" value={formatTokenCount(summary.total_tokens ?? overview.total_tokens ?? 0)} sub={`输入 ${formatNumber(summary.input_bytes ?? overview.input_bytes ?? 0)} · 输出 ${formatNumber(summary.output_bytes ?? overview.output_bytes ?? 0)}`} tone="indigo" />
        <DashboardStat icon={<Coins size={18} />} label="标准成本" value={formatUsdCost(summary.total_cost ?? 0)} sub="按标准口径累计" tone="slate" />
        <DashboardStat icon={<Coins size={18} />} label="实际成本" value={formatUsdCost(summary.actual_cost ?? 0)} sub="按实际结算累计" tone="green" />
        <DashboardStat icon={<Coins size={18} />} label="账户成本" value={formatUsdCost(summary.account_cost ?? 0)} sub={`覆盖请求 ${formatNumber(summary.covered_request_count ?? 0)}`} tone="rose" />
      </div>

      <div className="dashboard-main-grid">
        <Panel className="dashboard-card">
          <PanelHead title="运营摘要" action={<Link to="/billing" className="panel-link">查看详情 <ArrowRight size={14} /></Link>} />
          <div className="overview-summary-grid">
            <SummaryItem label="总请求" value={formatNumber(summary.request_count ?? 0)} sub={`错误 ${formatNumber(summary.error_count ?? 0)}`} />
            <SummaryItem label="订阅中" value={formatNumber(summary.active_subscription_count ?? 0)} sub={`覆盖 ${formatNumber(summary.covered_request_count ?? 0)} 条请求`} />
            <SummaryItem label="缓存读取" value={formatTokenCount(summary.cache_read_tokens ?? 0)} sub={`缓存写入 ${formatTokenCount(summary.cache_write_tokens ?? 0)}`} />
            <SummaryItem label="订单金额" value={formatUsdCost((Number(summary.amount_cents ?? 0) || 0) / 100, 2)} sub="按订单累计" />
          </div>
        </Panel>

        <Panel className="dashboard-card">
          <PanelHead title="快捷入口" />
          <div className="quick-actions">
            {operationCards.map((item) => (
              <QuickAction key={item.to} to={item.to} icon={item.icon} title={item.title} desc={item.desc} tone={item.tone} />
            ))}
          </div>
        </Panel>
      </div>

      <div className="dashboard-charts-grid">
        <Panel className="dashboard-card">
          <PanelHead title="重点用户" action={<Link to="/users" className="panel-link">查看全部 <ArrowRight size={14} /></Link>} />
          <div className="recent-usage-list">
            {topUsers.length ? topUsers.map((item) => (
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
          <PanelHead title="重点分组" action={<Link to="/groups" className="panel-link">查看全部 <ArrowRight size={14} /></Link>} />
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

function SummaryItem({ label, value, sub }: { label: string; value: string; sub: string }) {
  return (
    <div className="overview-summary-item">
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{sub}</small>
    </div>
  );
}

function QuickAction({ to, icon, title, desc, tone }: { to: string; icon: React.ReactNode; title: string; desc: string; tone: string }) {
  return (
    <Link to={to} className="quick-action">
      <span className={`quick-action-icon ${tone}`}>{icon}</span>
      <span className="quick-action-copy"><strong>{title}</strong><small>{desc}</small></span>
      <ArrowRight size={16} />
    </Link>
  );
}
