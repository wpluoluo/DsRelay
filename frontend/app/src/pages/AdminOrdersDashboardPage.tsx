import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link } from '@tanstack/react-router';
import { ArrowRight, RefreshCw } from 'lucide-react';
import { fetchAdminPaymentChannels, fetchAdminPaymentOrders, fetchAdminSubscriptionPlans } from '../api';
import { Badge, Panel, PanelHead } from '../components';
import { ActionButton, FilterToolbar, TablePageLayout, ToolbarButtonRow } from '../components/admin';
import { buildPageIntro } from '../navigation';
import { formatCost, formatNumber, getAccountName } from '../utils';

export function AdminOrdersDashboardPage() {
  const ordersQuery = useQuery({ queryKey: ['admin-payment-orders'], queryFn: fetchAdminPaymentOrders, refetchInterval: 10000 });
  const plansQuery = useQuery({ queryKey: ['admin-subscription-plans'], queryFn: fetchAdminSubscriptionPlans, refetchInterval: 30000 });
  const channelsQuery = useQuery({ queryKey: ['admin-payment-channels'], queryFn: fetchAdminPaymentChannels, refetchInterval: 30000 });
  const orders = ordersQuery.data?.items || [];
  const plans = plansQuery.data?.items || [];
  const channels = channelsQuery.data?.items || [];
  const paidCount = orders.filter((item) => item.status === 'paid').length;
  const pendingCount = orders.filter((item) => item.status === 'pending').length;
  const failedCount = orders.filter((item) => item.status === 'failed').length;
  const amountCents = orders.reduce((sum, item) => sum + Number(item.final_price_cents || item.amount_cents || 0), 0);
  const providerBreakdown = useMemo(() => {
    const bucket = new Map<string, number>();
    for (const order of orders) {
      const key = order.provider || order.channel_name || 'manual';
      bucket.set(key, (bucket.get(key) || 0) + 1);
    }
    return Array.from(bucket.entries()).sort((left, right) => right[1] - left[1]).slice(0, 5);
  }, [orders]);
  const recentOrders = orders.slice(0, 10);

  return (
    <section className="grid-page">
      {buildPageIntro('/admin/orders/dashboard')}
      <div className="sub2-inline-summary">
        <div className="sub2-inline-summary-item"><span>订单总数</span><strong>{formatNumber(orders.length)}</strong><small>待支付 {formatNumber(pendingCount)}</small></div>
        <div className="sub2-inline-summary-item"><span>已支付</span><strong>{formatNumber(paidCount)}</strong><small>失败 {formatNumber(failedCount)}</small></div>
        <div className="sub2-inline-summary-item"><span>套餐数</span><strong>{formatNumber(plans.length)}</strong><small>渠道 {formatNumber(channels.length)}</small></div>
        <div className="sub2-inline-summary-item"><span>订单金额</span><strong>{formatCost(amountCents / 100, 2)}</strong><small>累计口径</small></div>
      </div>
      <TablePageLayout
        filters={
          <FilterToolbar
            right={
              <ToolbarButtonRow>
                <ActionButton onClick={() => { ordersQuery.refetch(); plansQuery.refetch(); channelsQuery.refetch(); }}>
                  <RefreshCw size={15} />
                  刷新
                </ActionButton>
              </ToolbarButtonRow>
            }
          >
            <div className="overview-summary-grid-compact">
              {providerBreakdown.map(([provider, count]) => (
                <div key={provider} className="overview-summary-item">
                  <span>{provider}</span>
                  <strong>{formatNumber(count)}</strong>
                  <small>最近订单通道占比</small>
                </div>
              ))}
            </div>
          </FilterToolbar>
        }
        table={
          <div className="dashboard-charts-grid">
            <Panel className="dashboard-card">
              <PanelHead title="最近订单" action={<Link to="/admin/orders" className="panel-link">进入订单管理 <ArrowRight size={14} /></Link>} />
              <div className="table-wrap table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>订单</th>
                      <th>用户</th>
                      <th>计划</th>
                      <th>通道</th>
                      <th>状态</th>
                      <th>金额</th>
                    </tr>
                  </thead>
                  <tbody>
                    {recentOrders.length ? recentOrders.map((item) => (
                      <tr key={item.id}>
                        <td>{item.id}</td>
                        <td>{getAccountName(item)}</td>
                        <td>{item.plan_name || item.plan_id || '-'}</td>
                        <td>{item.channel_name || item.provider || '-'}</td>
                        <td><Badge tone={item.status === 'paid' ? 'ok' : item.status === 'pending' ? 'warn' : 'bad'}>{item.status || '-'}</Badge></td>
                        <td>{formatCost(Number(item.final_price_cents || item.amount_cents || 0) / 100, 2)}</td>
                      </tr>
                    )) : (
                      <tr><td colSpan={6}>暂无订单数据。</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            </Panel>
          </div>
        }
      />
    </section>
  );
}
