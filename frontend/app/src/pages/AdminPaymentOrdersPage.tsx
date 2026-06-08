import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { BadgeCheck, CircleX, CreditCard, Eye, Plus, RefreshCw, ReceiptText, ShieldCheck, Wallet } from 'lucide-react';
import { createAdminPaymentOrder, fetchAdminUsers, fetchAdminPaymentChannels, fetchAdminPaymentOrders, fetchAdminSubscriptionPlans, updateAdminPaymentOrderStatus } from '../api';
import { Badge, Button, Field, Modal, ModalActions, Select, TextInput } from '../components';
import { ActionButton, FilterToolbar, ListEmptyRow, Pager, RowAction, RowActions, SearchField, TablePageLayout, ToolbarButtonRow, ToolsMenu } from '../components/admin';
import { queryClient } from '../state/queryClient';
import type { AdminPaymentOrder } from '../types';
import { buildBusinessUserPayload, formatCost, formatNumber, getBusinessUserId, getBusinessUserName, maskEmpty, readStorageJSON, writeStorageJSON } from '../utils';

const STORAGE_KEY = 'admin-payment-orders-view-state';

export function AdminPaymentOrdersPage() {
  const ordersQuery = useQuery({ queryKey: ['admin-payment-orders'], queryFn: fetchAdminPaymentOrders, refetchInterval: 10000 });
  const usersQuery = useQuery({ queryKey: ['admin-users'], queryFn: fetchAdminUsers, refetchInterval: 10000 });
  const plansQuery = useQuery({ queryKey: ['admin-subscription-plans'], queryFn: fetchAdminSubscriptionPlans, refetchInterval: 10000 });
  const channelsQuery = useQuery({ queryKey: ['admin-payment-channels'], queryFn: fetchAdminPaymentChannels, refetchInterval: 10000 });
  const [draft, setDraft] = useState<any | null>(null);
  const [createdOrder, setCreatedOrder] = useState<AdminPaymentOrder | null>(null);
  const [inspectOrder, setInspectOrder] = useState<AdminPaymentOrder | null>(null);
  const [statusTarget, setStatusTarget] = useState<{ id: string; status: string; title: string; subtitle: string } | null>(null);
  const savedState = readStorageJSON(STORAGE_KEY, {
    search: '',
    statusFilter: '',
    channelFilter: '',
    pageSize: 20,
  });
  const [search, setSearch] = useState(savedState.search);
  const [statusFilter, setStatusFilter] = useState(savedState.statusFilter);
  const [channelFilter, setChannelFilter] = useState(savedState.channelFilter || '');
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
    mutationFn: ({ orderId, status }: { orderId: string; status: string }) =>
      updateAdminPaymentOrderStatus(orderId, {
        status,
        provider_order_id: `manual_${Date.now()}`,
      }),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['admin-payment-orders'] }),
        queryClient.invalidateQueries({ queryKey: ['admin-user-subscriptions'] }),
      ]);
    },
  });

  const items = ordersQuery.data?.items || [];
  const users = usersQuery.data?.items || [];
  const plans = plansQuery.data?.items || [];
  const channels = channelsQuery.data?.items || [];
  const selectedPlan = draft?.plan_id ? plans.find((plan) => plan.id === draft.plan_id) : undefined;
  const selectedUser = draft?.user_id ? users.find((user) => user.id === draft.user_id) : undefined;
  const selectedChannel = draft?.channel_id ? channels.find((channel) => channel.id === draft.channel_id) : undefined;

  const filteredItems = useMemo(() => {
    const keyword = search.trim().toLowerCase();
    return items.filter((item) => {
      if (keyword) {
        const haystack = [item.id, getBusinessUserName(item), getBusinessUserId(item), item.plan_name, item.plan_id, item.channel_name, item.provider_order_id].map((value) => String(value || '').toLowerCase()).join(' ');
        if (!haystack.includes(keyword)) return false;
      }
      if (statusFilter && item.status !== statusFilter) return false;
      if (channelFilter && (item.channel_id || item.channel_name || item.provider || '') !== channelFilter) return false;
      return true;
    });
  }, [channelFilter, items, search, statusFilter]);

  const totalPages = Math.max(1, Math.ceil(filteredItems.length / pageSize));
  const pagedItems = useMemo(() => {
    const start = (page - 1) * pageSize;
    return filteredItems.slice(start, start + pageSize);
  }, [filteredItems, page, pageSize]);
  const paidCount = items.filter((item) => item.status === 'paid').length;
  const pendingCount = items.filter((item) => item.status === 'pending').length;
  const failedCount = items.filter((item) => item.status === 'failed').length;
  const manualCount = items.filter((item) => !item.provider || item.provider === 'manual').length;
  const totalAmount = items.reduce((sum, item) => sum + Number(item.amount_cents || 0), 0);
  const fulfilledCount = items.filter((item) => Array.isArray(item.fulfillment_logs) && item.fulfillment_logs.length > 0).length;
  const channelOptions = useMemo(
    () =>
      Array.from(
        new Map(
          channels
            .map((channel) => {
              const value = channel.id || channel.name || '';
              const label = channel.name || channel.id || '';
              return value ? ([value, label] as const) : null;
            })
            .filter((entry): entry is readonly [string, string] => Boolean(entry)),
        ).entries(),
      ),
    [channels],
  );

  useEffect(() => {
    writeStorageJSON(STORAGE_KEY, {
      search,
      statusFilter,
      channelFilter,
      pageSize,
    });
  }, [channelFilter, pageSize, search, statusFilter]);

  return (
    <section className="grid-page">
      <div className="sub2-page-head">
        <div className="sub2-page-title">
          <strong>订单管理</strong>
        </div>
        <div className="sub2-inline-summary">
          <div className="sub2-inline-summary-item"><span>订单总数</span><strong>{items.length}</strong><small>支付流水总量</small></div>
          <div className="sub2-inline-summary-item"><span>已支付</span><strong>{paidCount}</strong><small>待支付 {pendingCount}</small></div>
          <div className="sub2-inline-summary-item"><span>失败订单</span><strong>{failedCount}</strong><small>需要人工跟进</small></div>
          <div className="sub2-inline-summary-item"><span>履约日志</span><strong>{fulfilledCount}</strong><small>已关联订阅或履约记录</small></div>
          <div className="sub2-inline-summary-item"><span>人工订单</span><strong>{manualCount}</strong><small>后台创建</small></div>
          <div className="sub2-inline-summary-item"><span>累计订单金额</span><strong>${formatCost(totalAmount / 100, 2)}</strong><small>订单金额合计</small></div>
        </div>
      </div>
      <TablePageLayout
        filters={
          <FilterToolbar
            right={
              <ToolbarButtonRow>
                <ActionButton onClick={() => ordersQuery.refetch()}><RefreshCw size={15} />刷新</ActionButton>
                <ToolsMenu>
                  <button type="button" onClick={() => { setSearch(''); setStatusFilter(''); setChannelFilter(''); setPage(1); }}>
                    <span>清空筛选</span>
                  </button>
                  <button type="button" onClick={() => { setStatusFilter('pending'); setPage(1); }}>
                    <span>仅看待支付</span>
                  </button>
                  <button type="button" onClick={() => { setPageSize(50); setPage(1); }}>
                    <span>切换 50 / 页</span>
                  </button>
                </ToolsMenu>
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
            <Select value={channelFilter} onChange={(event) => { setChannelFilter(event.target.value); setPage(1); }}>
              <option value="">全部通道</option>
              {channelOptions.map(([value, label]) => <option key={String(value)} value={String(value)}>{String(label)}</option>)}
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
                  <th>分组 / 定价</th>
                  <th>通道</th>
                  <th>金额</th>
                  <th>状态</th>
                  <th>履约</th>
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
                    <td><div className="sub2-cell-stack sub2-cell-stack-tight"><strong>{getBusinessUserName(item)}</strong><small>{getBusinessUserId(item)}</small></div></td>
                    <td><div className="sub2-cell-stack sub2-cell-stack-tight"><strong>{item.plan_name || item.plan_id}</strong><small>{item.plan_id}</small></div></td>
                    <td>
                      <div className="sub2-cell-stack sub2-cell-stack-tight">
                        <strong>{item.group_name || item.group_id || '-'}</strong>
                        <small>{Number(item.base_price_cents ?? item.plan_price_cents ?? 0)} × {Number(item.rate_multiplier || 1)}</small>
                      </div>
                    </td>
                    <td><div className="sub2-cell-stack sub2-cell-stack-tight"><strong>{item.channel_name || item.channel_id || item.provider || '-'}</strong><small>{item.provider || 'manual'}</small></div></td>
                    <td>
                      <div className="sub2-order-amount">
                        <strong>${formatCost(Number(item.final_price_cents ?? item.amount_cents ?? 0) / 100, 2)}</strong>
                        <small>{item.currency || 'USD'}</small>
                      </div>
                    </td>
                    <td>
                      <div className="sub2-order-status">
                        <Badge tone={item.status === 'paid' ? 'ok' : item.status === 'pending' ? 'warn' : 'bad'}>{item.status || '-'}</Badge>
                        <small>{item.provider ? `provider: ${item.provider}` : 'manual'}</small>
                      </div>
                    </td>
                    <td><div className="sub2-cell-stack sub2-cell-stack-tight"><strong>{item.subscription_id || '-'}</strong><small>{Array.isArray(item.fulfillment_logs) ? `${item.fulfillment_logs.length} 条日志` : '0 条日志'}</small></div></td>
                    <td>
                      <RowActions>
                        <RowAction icon={Eye} label="详情" onClick={() => setInspectOrder(item)} />
                      </RowActions>
                    </td>
                    <td>
                      {item.status === 'paid' ? (
                        <div className="sub2-order-done">
                          <Badge tone="ok">已完成</Badge>
                        </div>
                      ) : (
                        <ToolsMenu label="订单操作" icon={false}>
                          <button
                            type="button"
                            onClick={() => setStatusTarget({ id: item.id, status: 'paid', title: '确认完成订单', subtitle: `${getBusinessUserName(item) || item.id} · ${item.plan_name || item.plan_id || '-'}` })}
                          >
                            <span>标记已支付</span>
                            <BadgeCheck size={14} />
                          </button>
                          <button
                            type="button"
                            onClick={() => setStatusTarget({ id: item.id, status: 'failed', title: '确认标记失败', subtitle: `${getBusinessUserName(item) || item.id} · ${item.plan_name || item.plan_id || '-'}` })}
                          >
                            <span>标记失败</span>
                            <CircleX size={14} />
                          </button>
                          <button type="button" onClick={() => setInspectOrder(item)}>
                            <span>查看拉起参数</span>
                            <ShieldCheck size={14} />
                          </button>
                        </ToolsMenu>
                      )}
                    </td>
                  </tr>
                )) : (
                  <ListEmptyRow
                    colSpan={10}
                    title="暂无订单"
                    description="当前没有可展示的订单记录。"
                    action={<Button tone="primary" onClick={() => setDraft({ user_id: '', plan_id: '', channel_id: '', amount_cents: 0, currency: 'CNY' })}>创建订单</Button>}
                  />
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
          title="创建订单"
          size="md"
          onClose={() => setDraft(null)}
          footer={<ModalActions><Button onClick={() => setDraft(null)}>取消</Button><Button tone="primary" disabled={createMutation.isPending || !draft.user_id || !draft.plan_id} onClick={() => createMutation.mutate(buildBusinessUserPayload(draft.user_id, { plan_id: draft.plan_id, channel_id: draft.channel_id, amount_cents: draft.amount_cents, currency: draft.currency }))}>创建</Button></ModalActions>}
        >
          <div className="admin-dialog">
            <div className="admin-dialog-intro">
              <strong>人工创建订单</strong>
            </div>
            <div className="admin-dialog-summary">
              <div className="admin-dialog-summary-card">
                <span>待处理订单</span>
                <strong>{pendingCount}</strong>
                <small>当前可继续拉起</small>
              </div>
              <div className="admin-dialog-summary-card">
                <span>失败订单</span>
                <strong>{failedCount}</strong>
                <small>待处理</small>
              </div>
              <div className="admin-dialog-summary-card">
                <span>当前金额</span>
                <strong>{formatCost(Number(draft.amount_cents || 0) / 100, 2)}</strong>
                <small>{draft.currency || 'CNY'}</small>
              </div>
            </div>
            <div className="admin-dialog-summary">
              <div className="admin-dialog-summary-card">
                <span>目标用户</span>
                <strong>{selectedUser?.name || '待选择用户'}</strong>
                <small>{selectedUser?.group_name || selectedUser?.group_id || '未分组'}</small>
              </div>
              <div className="admin-dialog-summary-card">
                <span>选中计划</span>
                <strong>{selectedPlan?.name || '待选择计划'}</strong>
                <small>{selectedPlan ? `${formatCost(Number(selectedPlan.final_price_cents || selectedPlan.price_cents || 0) / 100, 2)} · ${formatNumber(selectedPlan.validity_days || 0)} 天` : '未生成价格'}</small>
              </div>
              <div className="admin-dialog-summary-card">
                <span>支付通道</span>
                <strong>{selectedChannel?.name || '不指定'}</strong>
                <small>{selectedChannel?.provider || 'manual'}</small>
              </div>
            </div>
            <div className="admin-dialog-section">
              <div className="admin-dialog-section-head">
                <strong>订单信息</strong>
                <span>用户、计划、通道和金额会直接进入订单主记录</span>
              </div>
              <div className="admin-dialog-grid modal-grid">
                <Field label="用户"><Select value={draft.user_id} onChange={(e) => setDraft({ ...draft, user_id: e.target.value })}><option value="">请选择用户</option>{users.map((user) => <option key={user.id} value={user.id}>{user.name}</option>)}</Select></Field>
                <Field label="计划"><Select value={draft.plan_id} onChange={(e) => setDraft({ ...draft, plan_id: e.target.value })}><option value="">请选择计划</option>{plans.map((plan) => <option key={plan.id} value={plan.id}>{plan.name}</option>)}</Select></Field>
                <Field label="通道"><Select value={draft.channel_id} onChange={(e) => setDraft({ ...draft, channel_id: e.target.value })}><option value="">不指定</option>{channels.map((channel) => <option key={channel.id} value={channel.id}>{channel.name}</option>)}</Select></Field>
                <Field label="金额(分)"><TextInput type="number" value={String(draft.amount_cents)} onChange={(e) => setDraft({ ...draft, amount_cents: Number(e.target.value || 0) })} /></Field>
              </div>
            </div>
          </div>
        </Modal>
      ) : null}

      {createdOrder ? (
        <Modal title="订单已创建" size="md" onClose={() => setCreatedOrder(null)} footer={<ModalActions><Button onClick={() => setCreatedOrder(null)}>关闭</Button></ModalActions>}>
          <OrderInspect item={createdOrder} includePayload />
        </Modal>
      ) : null}

      {inspectOrder ? (
        <Modal title="订单详情" size="lg" onClose={() => setInspectOrder(null)} footer={<ModalActions><Button onClick={() => setInspectOrder(null)}>关闭</Button></ModalActions>}>
          <OrderInspect item={inspectOrder} includePayload includeOrderPayload />
        </Modal>
      ) : null}

      {statusTarget ? (
        <Modal
          title={statusTarget.title}
          size="md"
          onClose={() => setStatusTarget(null)}
          footer={
            <ModalActions>
              <Button onClick={() => setStatusTarget(null)}>取消</Button>
              <Button
                tone={statusTarget.status === 'failed' ? 'danger' : 'primary'}
                disabled={fulfillMutation.isPending}
                onClick={() => fulfillMutation.mutate({ orderId: statusTarget.id, status: statusTarget.status })}
              >
                确认
              </Button>
            </ModalActions>
          }
        >
          <div className="admin-dialog">
            <div className="admin-dialog-intro">
              <strong>{statusTarget.id}</strong>
              <span>{statusTarget.subtitle}</span>
            </div>
            <div className="admin-dialog-summary">
              <div className="admin-dialog-summary-card">
                <span>目标状态</span>
                <strong>{statusTarget.status}</strong>
                <small>{statusTarget.status === 'paid' ? '进入履约链' : '终止当前订单'}</small>
              </div>
              <div className="admin-dialog-summary-card">
                <span>执行方式</span>
                <strong>人工确认</strong>
                <small>后台直接更新订单状态</small>
              </div>
              <div className="admin-dialog-summary-card">
                <span>影响范围</span>
                <strong>单个订单</strong>
                <small>{statusTarget.status === 'paid' ? '可能生成订阅履约' : '不会再继续支付流程'}</small>
              </div>
            </div>
          </div>
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
      <div className="admin-dialog-summary">
        <div className="admin-dialog-summary-card">
          <span>订单金额</span>
          <strong>{formatCost(Number(item.final_price_cents ?? item.amount_cents ?? 0) / 100, 2)}</strong>
          <small>{item.currency || 'USD'}</small>
        </div>
        <div className="admin-dialog-summary-card">
          <span>订阅关联</span>
          <strong>{item.subscription_id || '-'}</strong>
          <small>{item.plan_name || item.plan_id || '未绑定计划'}</small>
        </div>
        <div className="admin-dialog-summary-card">
          <span>履约日志</span>
          <strong>{Array.isArray(item.fulfillment_logs) ? item.fulfillment_logs.length : 0} 条</strong>
          <small>{getBusinessUserName(item) || '未识别用户'}</small>
        </div>
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
      {Array.isArray(item.fulfillment_logs) && item.fulfillment_logs.length ? (
        <div className="payment-payload-block">
          <div className="payment-payload-head"><span>履约日志</span></div>
          <pre><code>{JSON.stringify(item.fulfillment_logs, null, 2)}</code></pre>
        </div>
      ) : null}
    </div>
  );
}
