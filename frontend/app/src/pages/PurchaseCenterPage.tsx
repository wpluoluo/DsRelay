import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { CreditCard, ShoppingCart, Ticket, UserRound } from 'lucide-react';
import { createAdminPaymentOrder, fetchAdminPaymentChannels, fetchAdminPaymentOrders, fetchAdminSubscriptionPlans, fetchAdminSubscriptions, fetchAdminUsers } from '../api';
import { Badge, Button, Empty, Field, Metric, Panel, PanelHead, Select, TextInput } from '../components';
import { queryClient } from '../state/queryClient';
import type { AdminPaymentOrder, AdminUserSubscription } from '../types';
import { formatNumber } from '../utils';

type PurchaseDraft = {
  user_id: string;
  plan_id: string;
  channel_id: string;
  amount_cents: number;
  currency: string;
};

const DEFAULT_DRAFT: PurchaseDraft = {
  user_id: '',
  plan_id: '',
  channel_id: '',
  amount_cents: 0,
  currency: 'CNY',
};

export function PurchaseCenterPage() {
  const usersQuery = useQuery({ queryKey: ['admin-users'], queryFn: fetchAdminUsers, refetchInterval: 10000 });
  const plansQuery = useQuery({ queryKey: ['admin-subscription-plans'], queryFn: fetchAdminSubscriptionPlans, refetchInterval: 10000 });
  const channelsQuery = useQuery({ queryKey: ['admin-payment-channels'], queryFn: fetchAdminPaymentChannels, refetchInterval: 10000 });
  const ordersQuery = useQuery({ queryKey: ['admin-payment-orders'], queryFn: fetchAdminPaymentOrders, refetchInterval: 10000 });
  const subscriptionsQuery = useQuery({ queryKey: ['admin-subscriptions'], queryFn: fetchAdminSubscriptions, refetchInterval: 10000 });
  const [draft, setDraft] = useState<PurchaseDraft>(DEFAULT_DRAFT);
  const [createdOrder, setCreatedOrder] = useState<AdminPaymentOrder | null>(null);

  const users = usersQuery.data?.items || [];
  const plans = plansQuery.data?.items || [];
  const channels = channelsQuery.data?.items?.filter((item) => item.enabled !== false) || [];
  const orders = ordersQuery.data?.items || [];
  const subscriptions = subscriptionsQuery.data?.items || [];

  const selectedPlan = plans.find((item) => item.id === draft.plan_id);
  const selectedUser = users.find((item) => item.id === draft.user_id);
  const selectedOrders = useMemo(() => orders.filter((item) => !draft.user_id || item.user_id === draft.user_id), [orders, draft.user_id]);
  const selectedSubscriptions = useMemo(
    () => subscriptions.filter((item) => !draft.user_id || item.user_id === draft.user_id),
    [subscriptions, draft.user_id],
  );

  const createMutation = useMutation({
    mutationFn: createAdminPaymentOrder,
    onSuccess: async (result) => {
      setCreatedOrder(result?.item || null);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['admin-payment-orders'] }),
        queryClient.invalidateQueries({ queryKey: ['admin-subscriptions'] }),
      ]);
    },
  });

  function updateDraft(patch: Partial<PurchaseDraft>) {
    setDraft((current) => ({ ...current, ...patch }));
  }

  useEffect(() => {
    if (!selectedPlan) return;
    setDraft((current) => {
      const priceCents = Number(selectedPlan.price_cents || 0);
      if (current.amount_cents === priceCents) return current;
      return { ...current, amount_cents: priceCents };
    });
  }, [selectedPlan?.id, selectedPlan?.price_cents]);

  return (
    <section className="grid-page">
      <div className="metrics-row">
        <Metric label="可选用户" value={formatNumber(users.length)} sub="当前可绑定购买账户" />
        <Metric label="订阅计划" value={formatNumber(plans.length)} sub="启用计划供购买选择" />
        <Metric label="支付通道" value={formatNumber(channels.length)} sub="当前可拉起支付配置" />
        <Metric label="待支付订单" value={formatNumber(selectedOrders.filter((item) => item.status === 'pending').length)} sub="当前筛选用户范围" />
      </div>

      <div className="dashboard-main-grid purchase-grid">
        <Panel className="dashboard-card">
          <PanelHead title={<><ShoppingCart size={18} />购买中心</>} action={<span className="subtle">创建订单并核对拉起参数</span>} />
          <div className="section-stack">
            <div className="form-grid">
              <Field label="用户">
                <Select value={draft.user_id} onChange={(event) => updateDraft({ user_id: event.target.value })}>
                  <option value="">请选择用户</option>
                  {users.map((user) => <option key={user.id} value={user.id}>{user.name}</option>)}
                </Select>
              </Field>
              <Field label="订阅计划">
                <Select value={draft.plan_id} onChange={(event) => updateDraft({ plan_id: event.target.value })}>
                  <option value="">请选择计划</option>
                  {plans.map((plan) => <option key={plan.id} value={plan.id}>{plan.name}</option>)}
                </Select>
              </Field>
              <Field label="支付通道">
                <Select value={draft.channel_id} onChange={(event) => updateDraft({ channel_id: event.target.value })}>
                  <option value="">不指定</option>
                  {channels.map((channel) => <option key={channel.id} value={channel.id}>{channel.name}</option>)}
                </Select>
              </Field>
              <Field label="金额(分)" note="跟随订阅计划价格自动带出。">
                <TextInput type="number" value={String(draft.amount_cents)} readOnly />
              </Field>
            </div>

            <div className="purchase-summary">
              <div className="quick-action">
                <span className="quick-action-icon blue"><UserRound size={20} /></span>
                <span className="quick-action-copy">
                  <strong>{selectedUser?.name || '未选择用户'}</strong>
                  <small>{selectedUser?.group_name || selectedUser?.type || '用户归属将在这里显示'}</small>
                </span>
              </div>
              <div className="quick-action">
                <span className="quick-action-icon amber"><Ticket size={20} /></span>
                <span className="quick-action-copy">
                  <strong>{selectedPlan?.name || '未选择计划'}</strong>
                  <small>{selectedPlan ? `有效期 ${selectedPlan.validity_days || 0} 天 · 价格 ${selectedPlan.price_cents || 0} CNY` : '计划有效期、价格与限额将在这里显示'}</small>
                </span>
              </div>
              <div className="quick-action">
                <span className="quick-action-icon green"><CreditCard size={20} /></span>
                <span className="quick-action-copy">
                  <strong>{draft.amount_cents || 0} {draft.currency}</strong>
                  <small>{draft.channel_id ? channels.find((item) => item.id === draft.channel_id)?.name || draft.channel_id : '手工通道或后续自动分配'}</small>
                </span>
              </div>
            </div>

            <div className="button-row">
              <Button
                tone="primary"
                disabled={createMutation.isPending || !draft.user_id || !draft.plan_id}
                onClick={() => createMutation.mutate(draft)}
              >
                创建支付订单
              </Button>
              <Button onClick={() => setDraft(DEFAULT_DRAFT)}>重置选择</Button>
            </div>
          </div>
        </Panel>

        <Panel className="dashboard-card">
          <PanelHead title={<><Ticket size={18} />当前订阅</>} action={<span className="subtle">{selectedSubscriptions.length} 条</span>} />
          <div className="purchase-side-list">
            {selectedSubscriptions.length ? selectedSubscriptions.slice(0, 6).map((item) => <SubscriptionCard key={item.id} item={item} />) : <Empty>当前用户暂无订阅。</Empty>}
          </div>
        </Panel>
      </div>

      <Panel>
        <PanelHead title="订单记录" action={<span className="subtle">{selectedOrders.length} 条</span>} />
        <div className="table-wrap table-scroll">
          <table>
            <thead>
              <tr>
                <th>订单</th>
                <th>用户</th>
                <th>计划</th>
                <th>通道</th>
                <th>金额</th>
                <th>状态</th>
                <th>拉起参数</th>
              </tr>
            </thead>
            <tbody>
              {selectedOrders.length ? selectedOrders.map((item) => (
                <tr key={item.id}>
                  <td><strong>{item.id}</strong><small>{item.provider_order_id || item.resume_token || '-'}</small></td>
                  <td>{item.user_name || item.user_id}</td>
                  <td>{item.plan_name || item.plan_id}</td>
                  <td>{item.channel_name || item.channel_id || item.provider || '-'}</td>
                  <td>{item.amount_cents || 0} {item.currency || 'CNY'}</td>
                  <td><Badge tone={item.status === 'paid' ? 'ok' : item.status === 'pending' ? 'warn' : 'neutral'}>{item.status || '-'}</Badge></td>
                  <td><code>{compactPayload(item.provider_payload)}</code></td>
                </tr>
              )) : (
                <tr><td colSpan={7}><Empty>暂无订单记录。</Empty></td></tr>
              )}
            </tbody>
          </table>
        </div>
      </Panel>

      {createdOrder ? (
        <Panel>
          <PanelHead title="最新创建订单" action={<Button onClick={() => setCreatedOrder(null)}>关闭</Button>} />
          <div className="section-stack payment-order-inspect">
            <div className="payment-order-summary">
              <div><span>订单号</span><code>{createdOrder.id}</code></div>
              <div><span>状态</span><strong>{createdOrder.status || '-'}</strong></div>
              <div><span>计划</span><strong>{createdOrder.plan_name || createdOrder.plan_id || '-'}</strong></div>
              <div><span>用户</span><strong>{createdOrder.user_name || createdOrder.user_id || '-'}</strong></div>
            </div>
            <div className="payment-payload-block">
              <div className="payment-payload-head"><span>拉起参数</span></div>
              <pre><code>{JSON.stringify(createdOrder.provider_payload || {}, null, 2)}</code></pre>
            </div>
          </div>
        </Panel>
      ) : null}
    </section>
  );
}

function SubscriptionCard({ item }: { item: AdminUserSubscription }) {
  const tone = item.status === 'active' ? 'ok' : item.status === 'expired' ? 'warn' : 'bad';
  return (
    <div className="channel-card">
      <div className="channel-card-head">
        <strong>{item.plan_name || item.plan_id}</strong>
        <Badge tone={tone}>{item.status || '-'}</Badge>
      </div>
      <div className="channel-card-body">
        <MetricLine label="订阅 ID" value={item.id} />
        <MetricLine label="用户" value={item.user_name || item.user_id} />
        <MetricLine label="到期" value={formatDateTime(item.expires_at)} />
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

function compactPayload(payload: Record<string, unknown> | undefined) {
  const text = JSON.stringify(payload || {});
  if (text.length <= 96) return text;
  return `${text.slice(0, 92)}...`;
}
