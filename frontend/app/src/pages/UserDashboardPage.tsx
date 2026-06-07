import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link } from '@tanstack/react-router';
import { Activity, CreditCard, KeyRound, Ticket, Zap } from 'lucide-react';
import { fetchAdminUsage } from '../api';
import { Empty, Panel, PanelHead } from '../components';
import { useUserCenter } from '../state/userCenterContext';
import { formatMs, formatNumber, formatTokenCount, formatUsdCost } from '../utils';

export function UserDashboardPage() {
  const { selectedUser, selectedUserId, orders, subscriptions, visiblePlans, visibleChannels } = useUserCenter();
  const usageQuery = useQuery({ queryKey: ['admin-usage'], queryFn: () => fetchAdminUsage(), refetchInterval: 10000 });
  const currentOrders = orders.filter((item) => !selectedUserId || item.user_id === selectedUserId);
  const currentSubscriptions = subscriptions.filter((item) => !selectedUserId || item.user_id === selectedUserId);
  const currentUsage = (usageQuery.data?.items || []).filter((item) => !selectedUserId || item.consumer_id === selectedUserId);
  const paidOrders = currentOrders.filter((item) => item.status === 'paid');
  const activeSubscriptions = currentSubscriptions.filter((item) => item.status === 'active');
  const totalPaid = paidOrders.reduce((sum, item) => sum + Number(item.final_price_cents ?? item.amount_cents ?? 0), 0) / 100;
  const totalTokens = currentUsage.reduce((sum, item) => sum + Number(item.total_tokens || 0), 0);
  const totalActualCost = currentUsage.reduce((sum, item) => sum + Number(item.actual_cost || item.total_cost || 0), 0);
  const avgDuration = currentUsage.length ? Math.round(currentUsage.reduce((sum, item) => sum + Number(item.duration_ms || 0), 0) / currentUsage.length) : 0;
  const trend = buildUsageTrend(currentUsage);
  const models = summarizeModels(currentUsage);

  return (
    <section className="grid-page">
      <div className="sub2-page-head">
        <div className="sub2-page-title">
          <strong>用户控制台</strong>
          <span>参考 SUB2 的用户首页结构，集中展示当前账户、订阅、订单和下一步操作。</span>
        </div>
        <div className="sub2-inline-summary">
          <div className="sub2-inline-summary-item"><span>当前账户</span><strong>{selectedUser?.name || '未选择用户'}</strong><small>{selectedUser?.group_name || selectedUser?.source_type || '请先选择用户'}</small></div>
          <div className="sub2-inline-summary-item"><span>有效订阅</span><strong>{formatNumber(activeSubscriptions.length)}</strong><small>总订阅 {formatNumber(currentSubscriptions.length)}</small></div>
          <div className="sub2-inline-summary-item"><span>已支付订单</span><strong>{formatNumber(paidOrders.length)}</strong><small>累计消费 {formatUsdCost(totalPaid, 2)}</small></div>
          <div className="sub2-inline-summary-item"><span>可购计划</span><strong>{formatNumber(visiblePlans.length)}</strong><small>通道 {formatNumber(visibleChannels.length)}</small></div>
        </div>
      </div>

      <div className="dashboard-stats-grid">
        <DashboardStat label="业务 Key" value={formatNumber(selectedUser?.request_count || 0)} sub="当前账户累计请求" tone="blue" />
        <DashboardStat label="总 Token" value={formatTokenCount(totalTokens)} sub="当前用户累计" tone="amber" />
        <DashboardStat label="累计消费" value={formatUsdCost(totalActualCost, 4)} sub="按实际计费累计" tone="violet" />
        <DashboardStat label="平均耗时" value={formatMs(avgDuration)} sub="最近用量平均值" tone="green" />
      </div>

      <div className="dashboard-charts-grid">
        <Panel className="dashboard-card">
          <PanelHead title="最近用量趋势" action={<Link to="/usage" className="panel-link">查看全部</Link>} />
          <TrendChart rows={trend} />
        </Panel>
        <Panel className="dashboard-card">
          <PanelHead title="模型分布" action={<span className="subtle">最近窗口</span>} />
          <ModelDistribution rows={models} />
        </Panel>
      </div>

      <div className="dashboard-main-grid">
        <Panel className="dashboard-card">
          <PanelHead title="最近用量" action={<Link to="/usage" className="panel-link">查看全部</Link>} />
          <div className="recent-usage-list">
            {currentUsage.slice(0, 5).map((item, index) => (
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
            {!currentUsage.length ? <Empty>暂无用量记录。</Empty> : null}
          </div>
        </Panel>

        <Panel className="dashboard-card">
          <PanelHead title="快捷操作" action={<span className="subtle">用户侧二级入口</span>} />
          <div className="quick-actions">
            <QuickAction to="/purchase" icon={<CreditCard size={20} />} title="购买订阅" desc="创建订单并选择计划、通道" tone="blue" />
            <QuickAction to="/user-subscriptions" icon={<Ticket size={20} />} title="查看订阅" desc="查看有效期、状态和最近分配结果" tone="green" />
            <QuickAction to="/user-orders" icon={<Zap size={20} />} title="查看订单" desc="跟踪支付状态和拉起结果" tone="amber" />
            <QuickAction to="/keys" icon={<KeyRound size={20} />} title="我的 API Key" desc="查看当前用户业务 Key 可用性" tone="violet" />
          </div>
        </Panel>
      </div>

      <Panel className="dashboard-card">
        <PanelHead title="当前订阅" action={<Link to="/user-subscriptions" className="panel-link">查看全部</Link>} />
        <div className="user-dashboard-subscriptions">
          {currentSubscriptions.length ? currentSubscriptions.slice(0, 4).map((item) => (
            <div className="channel-card" key={item.id}>
              <div className="channel-card-head">
                <strong>{item.plan_name || item.plan_id}</strong>
                <span className={item.status === 'active' ? 'status-dot ok' : 'status-dot warn'}>{item.status || '-'}</span>
              </div>
              <div className="channel-card-body">
                <MetricLine label="用户" value={item.user_name || item.user_id} />
                <MetricLine label="分组" value={item.group_name || item.group_id || '-'} />
                <MetricLine label="到期" value={formatDateTime(item.expires_at)} />
              </div>
            </div>
          )) : <Empty>当前用户暂无订阅。</Empty>}
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

function ModelDistribution({ rows }: { rows: Array<{ model: string; requests: number; tokens: number; share: number }> }) {
  if (!rows.length) return <Empty>暂无模型分布。</Empty>;
  return (
    <div className="distribution-list">
      {rows.slice(0, 8).map((row) => (
        <div className="distribution-row" key={row.model}>
          <div className="distribution-main"><strong>{row.model}</strong><span>{formatNumber(row.requests)} 次 · {formatTokenCount(row.tokens)}</span></div>
          <div className="distribution-bar"><span style={{ width: `${row.share}%` }} /></div>
          <em>{Math.round(row.share)}%</em>
        </div>
      ))}
    </div>
  );
}

function TrendChart({ rows }: { rows: Array<{ label: string; tokens: number }> }) {
  const max = Math.max(1, ...rows.map((row) => row.tokens));
  return (
    <div className="trend-bars">
      {rows.map((row) => (
        <div className="trend-bar-item" key={row.label}>
          <div className="trend-bar"><span style={{ height: `${Math.max(4, (row.tokens / max) * 100)}%` }} /></div>
          <small>{row.label}</small>
        </div>
      ))}
    </div>
  );
}

function summarizeModels(rows: Array<Record<string, unknown>>) {
  const map = new Map<string, { model: string; requests: number; tokens: number }>();
  for (const row of rows) {
    const model = String(row.model || row.resolved_model || '未归类');
    const current = map.get(model) || { model, requests: 0, tokens: 0 };
    current.requests += 1;
    current.tokens += Number(row.total_tokens || 0);
    map.set(model, current);
  }
  const total = Math.max(1, Array.from(map.values()).reduce((acc, row) => acc + row.requests, 0));
  return Array.from(map.values()).sort((a, b) => b.requests - a.requests).map((row) => ({ ...row, share: (row.requests / total) * 100 }));
}

function buildUsageTrend(rows: Array<Record<string, unknown>>) {
  const days = Array.from({ length: 7 }, (_, index) => {
    const date = new Date();
    date.setDate(date.getDate() - (6 - index));
    const key = date.toISOString().slice(0, 10);
    return { key, label: `${date.getMonth() + 1}/${date.getDate()}`, tokens: 0 };
  });
  const dayMap = new Map(days.map((day) => [day.key, day]));
  for (const row of rows) {
    const date = new Date(String(row.started_at || '').replace(',', '.'));
    if (Number.isNaN(date.getTime())) continue;
    const key = date.toISOString().slice(0, 10);
    const target = dayMap.get(key);
    if (target) target.tokens += Number(row.total_tokens || 0);
  }
  return days;
}

function formatDateTime(value: unknown) {
  const time = Number(value || 0);
  if (!Number.isFinite(time) || time <= 0) return '-';
  return new Date(time * 1000).toLocaleString('zh-CN', { hour12: false });
}
