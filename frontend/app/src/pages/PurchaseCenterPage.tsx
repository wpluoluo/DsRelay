import { useEffect, useMemo, useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { CreditCard, Eye, KeyRound, ShoppingCart, Ticket, UserRound } from 'lucide-react';
import { createAccountOrder } from '../api';
import { Badge, Button, Empty, Field, Metric, Modal, ModalActions, Panel, PanelHead, Select, TextArea, TextInput } from '../components';
import { queryClient } from '../state/queryClient';
import { useAccountCenter } from '../state/accountCenterContext';
import type { AdminPaymentOrder, AdminUserSubscription } from '../types';
import { formatNumber, formatUsdCost, getBusinessUserName } from '../utils';

type PurchaseDraft = {
  plan_id: string;
  channel_id: string;
  amount_cents: number;
  currency: string;
};

const DEFAULT_DRAFT: PurchaseDraft = {
  plan_id: '',
  channel_id: '',
  amount_cents: 0,
  currency: 'CNY',
};

export function PurchaseCenterPage() {
  const {
    plans,
    channels,
    orders,
    subscriptions,
    account,
    visiblePlans,
    visibleChannels,
  } = useAccountCenter();
  const [draft, setDraft] = useState<PurchaseDraft>(DEFAULT_DRAFT);
  const [createdOrder, setCreatedOrder] = useState<AdminPaymentOrder | null>(null);
  const [inspectOrder, setInspectOrder] = useState<AdminPaymentOrder | null>(null);
  const [confirmCreate, setConfirmCreate] = useState(false);
  const selectedPlan = visiblePlans.find((item) => item.id === draft.plan_id);
  const selectedOrders = useMemo(() => orders, [orders]);
  const selectedSubscriptions = useMemo(() => subscriptions, [subscriptions]);
  const paidOrders = selectedOrders.filter((item) => item.status === 'paid').length;
  const todayActualCost = selectedOrders.reduce((sum, item) => sum + Number(item.final_price_cents ?? item.amount_cents ?? 0), 0) / 100;

  const createMutation = useMutation({
    mutationFn: createAccountOrder,
    onSuccess: async (result) => {
      setCreatedOrder(result?.item || null);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['account-payment-orders'] }),
        queryClient.invalidateQueries({ queryKey: ['account-subscriptions'] }),
      ]);
    },
  });

  function updateDraft(patch: Partial<PurchaseDraft>) {
    setDraft((current) => ({ ...current, ...patch }));
  }

  useEffect(() => {
    if (!selectedPlan) return;
    setDraft((current) => {
      const priceCents = Number(selectedPlan.final_price_cents || selectedPlan.price_cents || 0);
      if (current.amount_cents === priceCents) return current;
      return { ...current, amount_cents: priceCents };
    });
  }, [selectedPlan?.id, selectedPlan?.price_cents, selectedPlan?.final_price_cents]);

  return (
    <section className="grid-page">
      <div className="sub2-page-head">
        <div className="sub2-page-title">
          <strong>充值/订阅</strong>
        </div>
        <div className="sub2-inline-summary">
          <div className="sub2-inline-summary-item"><span>账户</span><strong>{account?.name || '-'}</strong><small>{account?.source_type || account?.group_name || '-'}</small></div>
          <div className="sub2-inline-summary-item"><span>可用计划</span><strong>{formatNumber(visiblePlans.length)}</strong><small>启用计划</small></div>
          <div className="sub2-inline-summary-item"><span>支付通道</span><strong>{formatNumber(visibleChannels.length)}</strong><small>当前可用</small></div>
          <div className="sub2-inline-summary-item"><span>已支付订单</span><strong>{formatNumber(paidOrders)}</strong><small>待处理 {formatNumber(selectedOrders.filter((item) => item.status === 'pending').length)}</small></div>
          <div className="sub2-inline-summary-item"><span>当前消费</span><strong>{formatUsdCost(todayActualCost, 2)}</strong><small>按订单金额聚合</small></div>
        </div>
      </div>

      <div className="dashboard-main-grid purchase-grid">
        <Panel className="dashboard-card">
          <PanelHead title={<><ShoppingCart size={18} />购买中心</>} />
          <div className="section-stack">
            <div className="form-grid">
              <Field label="订阅计划">
                <Select value={draft.plan_id} onChange={(event) => updateDraft({ plan_id: event.target.value })}>
                  <option value="">请选择计划</option>
                  {visiblePlans.map((plan) => <option key={plan.id} value={plan.id}>{plan.name}</option>)}
                </Select>
              </Field>
              <Field label="支付通道">
                <Select value={draft.channel_id} onChange={(event) => updateDraft({ channel_id: event.target.value })}>
                  <option value="">不指定</option>
                  {visibleChannels.map((channel) => <option key={channel.id} value={channel.id}>{channel.name}</option>)}
                </Select>
              </Field>
              <Field label="金额(分)">
                <TextInput type="number" value={String(draft.amount_cents)} readOnly />
              </Field>
            </div>

            <div className="purchase-summary">
              <div className="quick-action">
                <span className="quick-action-icon blue"><UserRound size={20} /></span>
                <span className="quick-action-copy">
                  <strong>{account?.name || '-'}</strong>
                  <small>{account?.group_name || account?.source_type || '-'}</small>
                </span>
              </div>
              <div className="quick-action">
                <span className="quick-action-icon amber"><Ticket size={20} /></span>
                <span className="quick-action-copy">
                  <strong>{selectedPlan?.name || '未选择计划'}</strong>
                  <small>{selectedPlan ? `有效期 ${selectedPlan.validity_days || 0} 天 · 价格 ${formatUsdCost(Number(selectedPlan.final_price_cents || selectedPlan.price_cents || 0) / 100, 2)}` : '未选择计划'}</small>
                </span>
              </div>
              <div className="quick-action">
                <span className="quick-action-icon green"><CreditCard size={20} /></span>
                <span className="quick-action-copy">
                  <strong>{formatUsdCost(Number(draft.amount_cents || 0) / 100, 2)}</strong>
                  <small>{draft.channel_id ? channels.find((item) => item.id === draft.channel_id)?.name || draft.channel_id : '不指定通道'}</small>
                </span>
              </div>
              <div className="quick-action">
                <span className="quick-action-icon violet"><KeyRound size={20} /></span>
                <span className="quick-action-copy">
                  <strong>{formatNumber(selectedSubscriptions.filter((item) => item.status === 'active').length)} 个有效订阅</strong>
                  <small>已选用户当前订阅状态</small>
                </span>
              </div>
            </div>

            <div className="button-row">
              <Button
                tone="primary"
                disabled={createMutation.isPending || !draft.plan_id}
                onClick={() => setConfirmCreate(true)}
              >
                创建订单
              </Button>
              <Button onClick={() => setDraft(DEFAULT_DRAFT)}>重置选择</Button>
            </div>
          </div>
        </Panel>

        <Panel className="dashboard-card">
          <PanelHead title={<><Ticket size={18} />当前订阅</>} action={<span className="subtle">{selectedSubscriptions.length} 条</span>} />
          <div className="purchase-side-list">
            {selectedSubscriptions.length ? selectedSubscriptions.slice(0, 6).map((item) => <SubscriptionCard key={item.id} item={item} />) : <Empty>暂无订阅</Empty>}
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
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {selectedOrders.length ? selectedOrders.map((item) => (
                <tr key={item.id}>
                  <td><strong>{item.id}</strong><small>{item.provider_order_id || item.resume_token || '-'}</small></td>
                  <td>{getBusinessUserName(item)}</td>
                  <td>{item.plan_name || item.plan_id}</td>
                  <td>{item.channel_name || item.channel_id || item.provider || '-'}</td>
                  <td>{formatUsdCost(Number(item.final_price_cents ?? item.amount_cents ?? 0) / 100, 2)}</td>
                  <td><Badge tone={item.status === 'paid' ? 'ok' : item.status === 'pending' ? 'warn' : 'neutral'}>{item.status || '-'}</Badge></td>
                  <td><code>{compactPayload(item.provider_payload)}</code></td>
                  <td>
                    <Button onClick={() => setInspectOrder(item)}><Eye size={14} />详情</Button>
                  </td>
                </tr>
              )) : (
                <tr><td colSpan={8}><Empty>暂无订单记录。</Empty></td></tr>
              )}
            </tbody>
          </table>
        </div>
      </Panel>

      {createdOrder ? (
        <Modal
          title="最新创建订单"
          size="lg"
          onClose={() => setCreatedOrder(null)}
          footer={<ModalActions><Button onClick={() => setCreatedOrder(null)}>关闭</Button></ModalActions>}
        >
          <div className="admin-dialog">
            <div className="admin-dialog-intro">
              <strong>{createdOrder.id}</strong>
            </div>
            <div className="admin-dialog-summary">
              <div className="admin-dialog-summary-card">
                <span>状态</span>
                <strong>{createdOrder.status || '-'}</strong>
                <small>{getBusinessUserName(createdOrder)}</small>
              </div>
              <div className="admin-dialog-summary-card">
                <span>计划</span>
                <strong>{createdOrder.plan_name || createdOrder.plan_id || '-'}</strong>
                <small>{createdOrder.group_name || createdOrder.group_id || '-'}</small>
              </div>
              <div className="admin-dialog-summary-card">
                <span>金额</span>
                <strong>{formatUsdCost(Number(createdOrder.final_price_cents ?? createdOrder.amount_cents ?? 0) / 100, 2)}</strong>
                <small>{createdOrder.channel_name || createdOrder.channel_id || createdOrder.provider || '-'}</small>
              </div>
            </div>
            <Field label="拉起参数" full>
              <TextArea readOnly rows={10} value={JSON.stringify(createdOrder.provider_payload || {}, null, 2)} />
            </Field>
          </div>
        </Modal>
      ) : null}

      {confirmCreate ? (
        <Modal
          title="确认创建订单"
          size="md"
          onClose={() => setConfirmCreate(false)}
          footer={
            <ModalActions>
              <Button onClick={() => setConfirmCreate(false)}>取消</Button>
              <Button
                tone="primary"
                disabled={createMutation.isPending || !draft.plan_id}
                onClick={() => {
                  setConfirmCreate(false);
                  createMutation.mutate({ plan_id: draft.plan_id, channel_id: draft.channel_id, amount_cents: draft.amount_cents, currency: draft.currency });
                }}
              >
                确认创建
              </Button>
            </ModalActions>
          }
        >
          <div className="admin-dialog">
            <div className="admin-dialog-intro">
                <strong>{account?.name || '-'}</strong>
            </div>
            <div className="admin-dialog-summary">
              <div className="admin-dialog-summary-card">
                <span>订阅计划</span>
                <strong>{selectedPlan?.name || '未选择计划'}</strong>
                <small>{selectedPlan ? `${selectedPlan.validity_days || 0} 天` : '-'}</small>
              </div>
              <div className="admin-dialog-summary-card">
                <span>支付通道</span>
                <strong>{channels.find((item) => item.id === draft.channel_id)?.name || '不指定'}</strong>
                <small>{channels.find((item) => item.id === draft.channel_id)?.provider || 'manual'}</small>
              </div>
              <div className="admin-dialog-summary-card">
                <span>订单金额</span>
                <strong>{formatUsdCost(Number(draft.amount_cents || 0) / 100, 2)}</strong>
                <small>{draft.currency || 'CNY'}</small>
              </div>
            </div>
          </div>
        </Modal>
      ) : null}

      {inspectOrder ? (
        <Modal
          title="订单详情"
          size="lg"
          onClose={() => setInspectOrder(null)}
          footer={<ModalActions><Button onClick={() => setInspectOrder(null)}>关闭</Button></ModalActions>}
        >
          <div className="admin-dialog">
            <div className="admin-dialog-intro">
              <strong>{inspectOrder.id}</strong>
            </div>
            <div className="admin-dialog-summary">
              <div className="admin-dialog-summary-card">
                <span>状态</span>
                <strong>{inspectOrder.status || '-'}</strong>
                <small>{inspectOrder.provider || 'manual'}</small>
              </div>
              <div className="admin-dialog-summary-card">
                <span>订阅计划</span>
                <strong>{inspectOrder.plan_name || inspectOrder.plan_id || '-'}</strong>
                <small>{inspectOrder.group_name || inspectOrder.group_id || '-'}</small>
              </div>
              <div className="admin-dialog-summary-card">
                <span>金额</span>
                <strong>{formatUsdCost(Number(inspectOrder.final_price_cents ?? inspectOrder.amount_cents ?? 0) / 100, 2)}</strong>
                <small>{inspectOrder.channel_name || inspectOrder.channel_id || inspectOrder.provider || '-'}</small>
              </div>
            </div>
            <div className="admin-dialog-grid">
              <Field label="用户"><TextInput readOnly value={getBusinessUserName(inspectOrder)} /></Field>
              <Field label="计划"><TextInput readOnly value={inspectOrder.plan_name || inspectOrder.plan_id || '-'} /></Field>
              <Field label="通道"><TextInput readOnly value={inspectOrder.channel_name || inspectOrder.channel_id || inspectOrder.provider || '-'} /></Field>
              <Field label="金额"><TextInput readOnly value={formatUsdCost(Number(inspectOrder.final_price_cents ?? inspectOrder.amount_cents ?? 0) / 100, 2)} /></Field>
            </div>
            <Field label="支付参数" full>
              <TextArea readOnly rows={10} value={JSON.stringify(inspectOrder.provider_payload || {}, null, 2)} />
            </Field>
          </div>
        </Modal>
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
        <MetricLine label="用户" value={getBusinessUserName(item)} />
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
