import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link } from '@tanstack/react-router';
import { Activity, ArrowRight, CreditCard, Gift, KeyRound, ListChecks } from 'lucide-react';
import { fetchAdminApiKeys, fetchAdminUsage } from '../api';
import { Empty, Panel, PanelHead } from '../components';
import { useAccountCenter } from '../state/accountCenterContext';
import { formatNumber, formatTokenCount, formatUsdCost } from '../utils';

export function AccountDashboardPage() {
  const { selectedAccount, selectedAccountId, orders, subscriptions, visiblePlans, visibleChannels } = useAccountCenter();
  const usageQuery = useQuery({ queryKey: ['admin-usage'], queryFn: () => fetchAdminUsage(), refetchInterval: 10000 });
  const keysQuery = useQuery({ queryKey: ['admin-api-keys'], queryFn: fetchAdminApiKeys, refetchInterval: 10000 });
  const currentOrders = orders.filter((item) => !selectedAccountId || item.account_id === selectedAccountId);
  const currentSubscriptions = subscriptions.filter((item) => !selectedAccountId || item.account_id === selectedAccountId);
  const currentUsage = (usageQuery.data?.items || []).filter((item) => !selectedAccountId || item.consumer_id === selectedAccountId);
  const currentKeys = (keysQuery.data?.items || []).filter((item) => !selectedAccountId || item.account_id === selectedAccountId);
  const paidOrders = currentOrders.filter((item) => item.status === 'paid');
  const activeSubscriptions = currentSubscriptions.filter((item) => item.status === 'active');
  const recentUsage = currentUsage.slice(0, 5);
  const todayKey = new Date().toISOString().slice(0, 10);
  const todayUsage = currentUsage.filter((item) => String(item.started_at || '').slice(0, 10) === todayKey);
  const totalTokens = currentUsage.reduce((sum, item) => sum + Number(item.total_tokens || 0), 0);
  const totalActualCost = currentUsage.reduce((sum, item) => sum + Number(item.actual_cost || item.total_cost || 0), 0);
  const todayTokens = todayUsage.reduce((sum, item) => sum + Number(item.total_tokens || 0), 0);
  const todayActualCost = todayUsage.reduce((sum, item) => sum + Number(item.actual_cost || item.total_cost || 0), 0);
  const activeKeys = currentKeys.filter((item) => item.enabled !== false);
  const balance = Number(selectedAccount?.balance_cents || 0) / 100;

  return (
    <section className="grid-page">
      <div className="sub2-page-head">
        <div className="sub2-page-title">
          <strong>账户控制台</strong>
          <span>按业务账户首页主结构展示状态、最近记录和快捷操作。</span>
        </div>
        <div className="sub2-inline-summary">
          <div className="sub2-inline-summary-item"><span>当前账户</span><strong>{selectedAccount?.name || '未选择账户'}</strong><small>{selectedAccount?.group_name || selectedAccount?.source_type || '请先选择账户'}</small></div>
          <div className="sub2-inline-summary-item"><span>有效订阅</span><strong>{formatNumber(activeSubscriptions.length)}</strong><small>总订阅 {formatNumber(currentSubscriptions.length)}</small></div>
          <div className="sub2-inline-summary-item"><span>API Key</span><strong>{formatNumber(currentKeys.length)}</strong><small>启用 {formatNumber(activeKeys.length)}</small></div>
          <div className="sub2-inline-summary-item"><span>可购计划</span><strong>{formatNumber(visiblePlans.length)}</strong><small>可用通道 {formatNumber(visibleChannels.length)}</small></div>
        </div>
      </div>

      <div className="dashboard-stats-grid">
        <DashboardStat label="账户余额" value={formatUsdCost(balance, 2)} sub="当前可用余额" tone="green" />
        <DashboardStat label="今日请求" value={formatNumber(todayUsage.length)} sub={`总请求 ${formatNumber(currentUsage.length)}`} tone="amber" />
        <DashboardStat label="今日 Token" value={formatTokenCount(todayTokens)} sub={`累计 ${formatTokenCount(totalTokens)}`} tone="violet" />
        <DashboardStat label="今日消费" value={formatUsdCost(todayActualCost, 4)} sub={`累计 ${formatUsdCost(totalActualCost, 4)}`} tone="violet" />
      </div>

      <div className="dashboard-main-grid">
        <Panel className="dashboard-card">
          <PanelHead title="最近使用记录" action={<span className="subtle">最近 7 天</span>} />
          <div className="recent-usage-list">
            {recentUsage.map((item, index) => (
              <div className="recent-usage-item" key={`${item.request_id || index}-${index}`}>
                <div className="recent-usage-icon"><Activity size={17} /></div>
                <div className="recent-usage-main">
                  <strong>{item.model || '-'}</strong>
                  <span>{item.started_at || '-'} · {item.route_url || '-'}</span>
                </div>
                <div className="recent-usage-meta">
                  <strong>{formatUsdCost(Number(item.actual_cost || item.total_cost || 0), 4)}</strong>
                  <span className={!item.error && Number(item.status_code || 0) < 400 ? 'ok' : 'bad'}>
                    {!item.error && Number(item.status_code || 0) < 400 ? '成功' : '异常'}
                  </span>
                </div>
              </div>
            ))}
            {currentUsage.length ? (
              <Link to="/usage" className="quick-action" style={{ marginTop: 8 }}>
                <span className="quick-action-icon blue"><ListChecks size={20} /></span>
                <span className="quick-action-copy"><strong>查看全部使用记录</strong><small>按请求明细查看 Token、缓存和消费</small></span>
                <ArrowRight size={16} />
              </Link>
            ) : <Empty>暂无使用记录。</Empty>}
          </div>
        </Panel>

        <Panel className="dashboard-card">
          <PanelHead title="快捷操作" />
          <div className="quick-actions">
            <QuickAction to="/keys" icon={<KeyRound size={20} />} title="创建 API Key" desc="查看和管理当前账户 Key" tone="blue" />
            <QuickAction to="/usage" icon={<ListChecks size={20} />} title="查看使用记录" desc="检查详细请求记录和缓存情况" tone="green" />
            <QuickAction to="/purchase" icon={<CreditCard size={20} />} title="购买订阅" desc="创建订单并选择计划、通道" tone="amber" />
            <QuickAction to="/account-orders" icon={<Gift size={20} />} title="查看订单" desc="跟踪支付状态和履约结果" tone="violet" />
          </div>
        </Panel>
      </div>

      <Panel className="dashboard-card">
        <PanelHead title="当前订阅" action={<Link to="/account-subscriptions" className="panel-link">查看全部</Link>} />
        <div className="user-dashboard-subscriptions">
          {currentSubscriptions.length ? currentSubscriptions.slice(0, 4).map((item) => (
            <div className="channel-card" key={item.id}>
              <div className="channel-card-head">
                <strong>{item.plan_name || item.plan_id}</strong>
                <span className={item.status === 'active' ? 'status-dot ok' : 'status-dot warn'}>{item.status || '-'}</span>
              </div>
              <div className="channel-card-body">
                <MetricLine label="账户" value={item.account_name || item.account_id} />
                <MetricLine label="分组" value={item.group_name || item.group_id || '-'} />
                <MetricLine label="到期" value={formatDateTime(item.expires_at)} />
              </div>
            </div>
          )) : <Empty>当前账户暂无订阅。</Empty>}
        </div>
      </Panel>
    </section>
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

function DashboardStat({ label, value, sub, tone }: { label: string; value: string; sub: string; tone: string }) {
  return (
    <div className="dashboard-stat">
      <div className={`dashboard-stat-icon ${tone}`} />
      <div className="dashboard-stat-body">
        <span>{label}</span>
        <strong>{value}</strong>
        <small>{sub}</small>
      </div>
    </div>
  );
}

function MetricLine({ label, value }: { label: string; value: string }) {
  return <div className="metric-line"><span>{label}</span><strong>{value}</strong></div>;
}

function formatDateTime(value: unknown) {
  const time = Number(value || 0);
  if (!Number.isFinite(time) || time <= 0) return '-';
  return new Date(time * 1000).toLocaleString('zh-CN', { hour12: false });
}
