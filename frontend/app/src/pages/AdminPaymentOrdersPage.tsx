import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { BadgeCheck, CreditCard, Eye, Plus, RefreshCw, ReceiptText, ShieldCheck, Wallet } from 'lucide-react';
import { createAdminPaymentOrder, fetchAdminPaymentChannels, fetchAdminPaymentOrders, fetchAdminSubscriptionPlans, fetchAdminUsers, fulfillAdminPaymentOrder } from '../api';
import { Badge, Button, Field, Modal, Select, TextInput } from '../components';
import { ActionButton, EmptyState, FilterToolbar, Pager, SearchField, TablePageLayout, ToolbarButtonRow } from '../components/admin';
import { queryClient } from '../state/queryClient';
import type { AdminPaymentOrder } from '../types';
import { maskEmpty, readStorageJSON, writeStorageJSON } from '../utils';

const STORAGE_KEY = 'admin-payment-orders-view-state';

export function AdminPaymentOrdersPage() {
  const ordersQuery = useQuery({ queryKey: ['admin-payment-orders'], queryFn: fetchAdminPaymentOrders, refetchInterval: 10000 });
  const usersQuery = useQuery({ queryKey: ['admin-users'], queryFn: fetchAdminUsers, refetchInterval: 10000 });
  const plansQuery = useQuery({ queryKey: ['admin-subscription-plans'], queryFn: fetchAdminSubscriptionPlans, refetchInterval: 10000 });
  const channelsQuery = useQuery({ queryKey: ['admin-payment-channels'], queryFn: fetchAdminPaymentChannels, refetchInterval: 10000 });
  const [draft, setDraft] = useState<any | null>(null);
  const [createdOrder, setCreatedOrder] = useState<AdminPaymentOrder | null>(null);
  const [inspectOrder, setInspectOrder] = useState<AdminPaymentOrder | null>(null);
  const savedState = readStorageJSON(STORAGE_KEY, {
    search: '',
    statusFilter: '',
    pageSize: 20,
  });
  const [search, setSearch] = useState(savedState.search);
  const [statusFilter, setStatusFilter] = useState(savedState.statusFilter);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(savedState.pageSize || 20);

  const createMutation = useMutation({
    mutationFn: createAdminPaymentOrder,
    onSuccess: async (result) => {
      setCreatedOrder(result?.item || null);
      setDraft(null);
      await queryClient.invalidateQueries({ queryKey: ['admin-payment-orders'] });
    },
  });
  const fulfillMutation = useMutation({
    mutationFn: (orderId: string) => fulfillAdminPaymentOrder(orderId, { provider_order_id: `manual_${Date.now()}` }),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['admin-payment-orders'] }),
        queryClient.invalidateQueries({ queryKey: ['admin-subscriptions'] }),
      ]);
    },
  });

  const items = ordersQuery.data?.items || [];
  const users = usersQuery.data?.items || [];
  const plans = plansQuery.data?.items || [];
  const channels = channelsQuery.data?.items || [];

  const filteredItems = useMemo(() => {
    const keyword = search.trim().toLowerCase();
    return items.filter((item) => {
      if (keyword) {
        const haystack = [item.id, item.user_name, item.user_id, item.plan_name, item.plan_id, item.channel_name, item.provider_order_id].map((value) => String(value || '').toLowerCase()).join(' ');
        if (!haystack.includes(keyword)) return false;
      }
      if (statusFilter && item.status !== statusFilter) return false;
      return true;
    });
  }, [items, search, statusFilter]);

  const totalPages = Math.max(1, Math.ceil(filteredItems.length / pageSize));
  const pagedItems = useMemo(() => {
    const start = (page - 1) * pageSize;
    return filteredItems.slice(start, start + pageSize);
  }, [filteredItems, page, pageSize]);
  const paidCount = items.filter((item) => item.status === 'paid').length;
  const pendingCount = items.filter((item) => item.status === 'pending').length;
  const totalAmount = items.reduce((sum, item) => sum + Number(item.amount_cents || 0), 0);

  useEffect(() => {
    writeStorageJSON(STORAGE_KEY, {
      search,
      statusFilter,
      pageSize,
    });
  }, [pageSize, search, statusFilter]);

  return (
    <section className="grid-page">
      <div className="key-stat-grid">
        <div className="key-stat"><div className="key-stat-icon blue"><ReceiptText size={18} /></div><div><span>订单总数</span><strong>{items.length}</strong><small>支付流水总量</small></div></div>
        <div className="key-stat"><div className="key-stat-icon green"><ShieldCheck size={18} /></div><div><span>已支付</span><strong>{paidCount}</strong><small>已完成订单</small></div></div>
        <div className="key-stat"><div className="key-stat-icon amber"><CreditCard size={18} /></div><div><span>待支付</span><strong>{pendingCount}</strong><small>仍在等待回调</small></div></div>
        <div className="key-stat"><div className="key-stat-icon slate"><Wallet size={18} /></div><div><span>累计金额</span><strong>{totalAmount}</strong><small>单位分</small></div></div>
      </div>
      <TablePageLayout
        filters={
          <FilterToolbar
            right={
              <ToolbarButtonRow>
                <ActionButton onClick={() => ordersQuery.refetch()}><RefreshCw size={15} />刷新</ActionButton>
                <Button tone="primary" onClick={() => setDraft({ user_id: '', plan_id: '', channel_id: '', amount_cents: 0, currency: 'CNY' })}>
                  <Plus size={15} />创建订单
                </Button>
              </ToolbarButtonRow>
            }
          >
            <SearchField value={search} placeholder="搜索订单 / 用户 / 计划 / 通道" onChange={(value) => { setSearch(value); setPage(1); }} />
            <Select value={statusFilter} onChange={(event) => { setStatusFilter(event.target.value); setPage(1); }}>
              <option value="">全部状态</option>
              <option value="pending">pending</option>
              <option value="paid">paid</option>
              <option value="failed">failed</option>
            </Select>
          </FilterToolbar>
        }
        table={
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
                  <th>详情</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {pagedItems.length ? pagedItems.map((item) => (
                  <tr key={item.id}>
                    <td>
                      <div className="sub2-cell-stack">
                        <strong>{item.id}</strong>
                        <small>{item.provider_order_id || item.resume_token || '-'}</small>
                      </div>
                    </td>
                    <td><div className="sub2-cell-stack sub2-cell-stack-tight"><strong>{item.user_name || item.user_id}</strong><small>{item.user_id}</small></div></td>
                    <td><div className="sub2-cell-stack sub2-cell-stack-tight"><strong>{item.plan_name || item.plan_id}</strong><small>{item.plan_id}</small></div></td>
                    <td><div className="sub2-cell-stack sub2-cell-stack-tight"><strong>{item.channel_name || item.channel_id || item.provider || '-'}</strong><small>{item.provider || 'manual'}</small></div></td>
                    <td>
                      <div className="sub2-order-amount">
                        <strong>{item.amount_cents || 0}</strong>
                        <small>{item.currency || 'CNY'}</small>
                      </div>
                    </td>
                    <td>
                      <div className="sub2-order-status">
                        <Badge tone={item.status === 'paid' ? 'ok' : item.status === 'pending' ? 'warn' : 'bad'}>{item.status || '-'}</Badge>
                        <small>{item.provider ? `provider: ${item.provider}` : 'manual'}</small>
                      </div>
                    </td>
                    <td>
                      <div className="sub2-action-stack">
                        <button type="button" className="sub2-icon-action" onClick={() => setInspectOrder(item)}>
                          <Eye size={14} />
                          <span>{item.provider_payload ? '参数' : '详情'}</span>
                        </button>
                      </div>
                    </td>
                    <td>
                      {item.status === 'paid' ? (
                        <div className="sub2-order-done">
                          <Badge tone="ok">已完成</Badge>
                        </div>
                      ) : (
                        <div className="sub2-action-stack">
                          <button type="button" className="sub2-icon-action" onClick={() => fulfillMutation.mutate(item.id)}>
                            <BadgeCheck size={14} />
                            <span>完成</span>
                          </button>
                        </div>
                      )}
                    </td>
                  </tr>
                )) : (
                  <tr>
                    <td colSpan={8}>
                      <EmptyState title="暂无支付订单" description="当前没有可展示的支付订单记录。" action={<Button tone="primary" onClick={() => setDraft({ user_id: '', plan_id: '', channel_id: '', amount_cents: 0, currency: 'CNY' })}>创建订单</Button>} />
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        }
        pagination={
          filteredItems.length ? (
            <Pager
              page={Math.min(page, totalPages)}
              pageSize={pageSize}
              total={filteredItems.length}
              onPageChange={(next) => setPage(Math.min(Math.max(1, next), totalPages))}
              onPageSizeChange={(next) => { setPageSize(next); setPage(1); }}
            />
          ) : null
        }
      />

      {draft ? (
        <Modal
          title="创建支付订单"
          onClose={() => setDraft(null)}
          footer={<><Button onClick={() => setDraft(null)}>取消</Button><Button tone="primary" disabled={createMutation.isPending || !draft.user_id || !draft.plan_id} onClick={() => createMutation.mutate(draft)}>创建</Button></>}
        >
          <div className="form-grid modal-grid">
            <Field label="用户"><Select value={draft.user_id} onChange={(e) => setDraft({ ...draft, user_id: e.target.value })}><option value="">请选择用户</option>{users.map((user) => <option key={user.id} value={user.id}>{user.name}</option>)}</Select></Field>
            <Field label="计划"><Select value={draft.plan_id} onChange={(e) => setDraft({ ...draft, plan_id: e.target.value })}><option value="">请选择计划</option>{plans.map((plan) => <option key={plan.id} value={plan.id}>{plan.name}</option>)}</Select></Field>
            <Field label="通道"><Select value={draft.channel_id} onChange={(e) => setDraft({ ...draft, channel_id: e.target.value })}><option value="">不指定</option>{channels.map((channel) => <option key={channel.id} value={channel.id}>{channel.name}</option>)}</Select></Field>
            <Field label="金额(分)"><TextInput type="number" value={String(draft.amount_cents)} onChange={(e) => setDraft({ ...draft, amount_cents: Number(e.target.value || 0) })} /></Field>
          </div>
        </Modal>
      ) : null}

      {createdOrder ? (
        <Modal title="订单已创建" onClose={() => setCreatedOrder(null)} footer={<Button onClick={() => setCreatedOrder(null)}>关闭</Button>}>
          <OrderInspect item={createdOrder} includePayload />
        </Modal>
      ) : null}

      {inspectOrder ? (
        <Modal title="支付订单详情" onClose={() => setInspectOrder(null)} footer={<Button onClick={() => setInspectOrder(null)}>关闭</Button>}>
          <OrderInspect item={inspectOrder} includePayload includeOrderPayload />
        </Modal>
      ) : null}
    </section>
  );
}

function OrderInspect({ item, includePayload, includeOrderPayload }: { item: AdminPaymentOrder; includePayload?: boolean; includeOrderPayload?: boolean }) {
  return (
    <div className="section-stack payment-order-inspect">
      <div className="payment-order-summary">
        <div><span>订单号</span><code>{item.id}</code></div>
        <div><span>状态</span><strong>{item.status || '-'}</strong></div>
        <div><span>通道</span><strong>{item.channel_name || item.channel_id || 'manual'}</strong></div>
        <div><span>上游单号</span><strong>{maskEmpty(item.provider_order_id)}</strong></div>
      </div>
      {includePayload ? (
        <div className="payment-payload-block">
          <div className="payment-payload-head"><span>拉起参数</span></div>
          <pre><code>{JSON.stringify(item.provider_payload || {}, null, 2)}</code></pre>
        </div>
      ) : null}
      {includeOrderPayload ? (
        <div className="payment-payload-block">
          <div className="payment-payload-head"><span>订单载荷</span></div>
          <pre><code>{JSON.stringify(item.payload || {}, null, 2)}</code></pre>
        </div>
      ) : null}
    </div>
  );
}
