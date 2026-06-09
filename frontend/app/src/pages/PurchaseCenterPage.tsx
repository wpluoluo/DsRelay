import { useEffect, useMemo, useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { CreditCard, Eye, RefreshCw } from 'lucide-react';
import { createAccountOrder } from '../api';
import { Badge, Button, Field, Modal, ModalActions, Select, TextArea, TextInput } from '../components';
import { ColumnMenu, FilterToolbar, ListEmptyRow, Pager, RowAction, RowActions, SearchField, TablePageLayout, ToolbarButtonRow, ToolsMenu } from '../components/admin';
import { queryClient } from '../state/queryClient';
import { useAccountCenter } from '../state/accountCenterContext';
import type { AdminPaymentOrder, AdminSubscriptionPlan } from '../types';
import { formatNumber, formatUsdCost, getAccountName, readStorageJSON, writeStorageJSON } from '../utils';

type PurchaseDraft = {
  plan_id: string;
  channel_id: string;
  amount_cents: number;
  currency: string;
};

type PlanFilterKey = 'group';
type PlanColumnKey = 'group' | 'price' | 'validity' | 'limits' | 'status';

const DEFAULT_DRAFT: PurchaseDraft = {
  plan_id: '',
  channel_id: '',
  amount_cents: 0,
  currency: 'CNY',
};

const DEFAULT_VISIBLE_PLAN_COLUMNS: PlanColumnKey[] = ['group', 'price', 'validity', 'limits', 'status'];
const DEFAULT_VISIBLE_PLAN_FILTERS: PlanFilterKey[] = ['group'];
const STORAGE_KEY = 'account-purchase-view-state';

export function PurchaseCenterPage() {
  const {
    account,
    orders,
    subscriptions,
    visiblePlans,
    visibleChannels,
    reload,
  } = useAccountCenter();
  const savedState = readStorageJSON(STORAGE_KEY, {
    planSearch: '',
    groupFilter: '',
    planPageSize: 20,
    orderSearch: '',
    orderStatus: '',
    orderPageSize: 10,
    visiblePlanColumns: DEFAULT_VISIBLE_PLAN_COLUMNS,
    visiblePlanFilters: DEFAULT_VISIBLE_PLAN_FILTERS,
  });

  const [planSearch, setPlanSearch] = useState(savedState.planSearch || '');
  const [groupFilter, setGroupFilter] = useState(savedState.groupFilter || '');
  const [planPage, setPlanPage] = useState(1);
  const [planPageSize, setPlanPageSize] = useState(savedState.planPageSize || 20);
  const [visiblePlanColumns, setVisiblePlanColumns] = useState<Set<PlanColumnKey>>(new Set(savedState.visiblePlanColumns || DEFAULT_VISIBLE_PLAN_COLUMNS));
  const [visiblePlanFilters, setVisiblePlanFilters] = useState<Set<PlanFilterKey>>(new Set(savedState.visiblePlanFilters || DEFAULT_VISIBLE_PLAN_FILTERS));
  const [orderSearch, setOrderSearch] = useState(savedState.orderSearch || '');
  const [orderStatus, setOrderStatus] = useState(savedState.orderStatus || '');
  const [orderPage, setOrderPage] = useState(1);
  const [orderPageSize, setOrderPageSize] = useState(savedState.orderPageSize || 10);
  const [draft, setDraft] = useState<PurchaseDraft>(DEFAULT_DRAFT);
  const [confirmCreate, setConfirmCreate] = useState(false);
  const [createdOrder, setCreatedOrder] = useState<AdminPaymentOrder | null>(null);
  const [inspectOrder, setInspectOrder] = useState<AdminPaymentOrder | null>(null);
  const [inspectPlan, setInspectPlan] = useState<AdminSubscriptionPlan | null>(null);

  const createMutation = useMutation({
    mutationFn: createAccountOrder,
    onSuccess: async (result) => {
      setCreatedOrder(result?.item || null);
      setConfirmCreate(false);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['account-payment-orders'] }),
        queryClient.invalidateQueries({ queryKey: ['account-subscriptions'] }),
        queryClient.invalidateQueries({ queryKey: ['account-me'] }),
      ]);
    },
  });

  const activeSubscriptions = useMemo(
    () => subscriptions.filter((item) => item.status === 'active'),
    [subscriptions],
  );
  const activePlanIds = useMemo(() => new Set(activeSubscriptions.map((item) => item.plan_id)), [activeSubscriptions]);
  const activeGroupIds = useMemo(() => new Set(activeSubscriptions.map((item) => String(item.group_id || ''))), [activeSubscriptions]);
  const groupOptions = useMemo(
    () =>
      Array.from(
        new Map(
          visiblePlans
            .filter((plan) => plan.group_id || plan.group_name)
            .map((plan) => [String(plan.group_id || plan.group_name), String(plan.group_name || plan.group_id)] as const),
        ).entries(),
      ),
    [visiblePlans],
  );

  const filteredPlans = useMemo(() => {
    const keyword = planSearch.trim().toLowerCase();
    return visiblePlans.filter((item) => {
      if (groupFilter && String(item.group_id || '') !== groupFilter) return false;
      if (!keyword) return true;
      const haystack = [
        item.name,
        item.id,
        item.group_name,
        item.group_id,
        item.note,
      ]
        .map((value) => String(value || '').toLowerCase())
        .join(' ');
      return haystack.includes(keyword);
    });
  }, [groupFilter, planSearch, visiblePlans]);

  const filteredOrders = useMemo(() => {
    const keyword = orderSearch.trim().toLowerCase();
    return orders.filter((item) => {
      if (orderStatus && item.status !== orderStatus) return false;
      if (!keyword) return true;
      const haystack = [
        item.id,
        item.plan_name,
        item.plan_id,
        item.channel_name,
        item.channel_id,
        item.provider,
        item.provider_order_id,
        item.resume_token,
      ]
        .map((value) => String(value || '').toLowerCase())
        .join(' ');
      return haystack.includes(keyword);
    });
  }, [orderSearch, orderStatus, orders]);

  const selectedPlan = visiblePlans.find((item) => item.id === draft.plan_id);
  const selectedChannel = visibleChannels.find((item) => item.id === draft.channel_id);
  const paidOrders = filteredOrders.filter((item) => item.status === 'paid').length;
  const pendingOrders = filteredOrders.filter((item) => item.status === 'pending').length;
  const failedOrders = filteredOrders.filter((item) => item.status === 'failed').length;
  const totalOrderAmount = filteredOrders.reduce((sum, item) => sum + Number(item.final_price_cents ?? item.amount_cents ?? 0), 0);

  const planTotalPages = Math.max(1, Math.ceil(filteredPlans.length / planPageSize));
  const pagedPlans = filteredPlans.slice((planPage - 1) * planPageSize, planPage * planPageSize);
  const orderTotalPages = Math.max(1, Math.ceil(filteredOrders.length / orderPageSize));
  const pagedOrders = filteredOrders.slice((orderPage - 1) * orderPageSize, orderPage * orderPageSize);

  useEffect(() => {
    if (!selectedPlan) return;
    const amountCents = Number(selectedPlan.final_price_cents || selectedPlan.price_cents || 0);
    setDraft((current) => (current.amount_cents === amountCents ? current : { ...current, amount_cents: amountCents }));
  }, [selectedPlan?.id, selectedPlan?.price_cents, selectedPlan?.final_price_cents]);

  useEffect(() => {
    writeStorageJSON(STORAGE_KEY, {
      planSearch,
      groupFilter,
      planPageSize,
      orderSearch,
      orderStatus,
      orderPageSize,
      visiblePlanColumns: Array.from(visiblePlanColumns),
      visiblePlanFilters: Array.from(visiblePlanFilters),
    });
  }, [groupFilter, orderPageSize, orderSearch, orderStatus, planPageSize, planSearch, visiblePlanColumns, visiblePlanFilters]);

  function togglePlanColumn(key: PlanColumnKey) {
    setVisiblePlanColumns((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  function togglePlanFilter(key: PlanFilterKey) {
    setVisiblePlanFilters((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  function selectPlan(plan: AdminSubscriptionPlan, openConfirm = false) {
    setDraft({
      plan_id: plan.id,
      channel_id: draft.channel_id,
      amount_cents: Number(plan.final_price_cents || plan.price_cents || 0),
      currency: draft.currency || 'CNY',
    });
    if (openConfirm) setConfirmCreate(true);
  }

  return (
    <section className="grid-page">
      <div className="sub2-page-head">
        <div className="sub2-page-title">
          <strong>充值/订阅</strong>
        </div>
        <div className="sub2-inline-summary">
          <div className="sub2-inline-summary-item"><span>账户</span><strong>{account?.name || '-'}</strong><small>{account?.group_name || account?.source_type || '-'}</small></div>
          <div className="sub2-inline-summary-item"><span>可用计划</span><strong>{formatNumber(visiblePlans.length)}</strong><small>当前筛选 {formatNumber(filteredPlans.length)}</small></div>
          <div className="sub2-inline-summary-item"><span>有效订阅</span><strong>{formatNumber(activeSubscriptions.length)}</strong><small>可续费分组 {formatNumber(activeGroupIds.size)}</small></div>
          <div className="sub2-inline-summary-item"><span>支付通道</span><strong>{formatNumber(visibleChannels.length)}</strong><small>待支付 {formatNumber(pendingOrders)}</small></div>
          <div className="sub2-inline-summary-item"><span>订单金额</span><strong>{formatUsdCost(totalOrderAmount / 100, 2)}</strong><small>已支付 {formatNumber(paidOrders)} / 失败 {formatNumber(failedOrders)}</small></div>
        </div>
      </div>

      <TablePageLayout
        actions={(
          <div className="sub2-inline-summary">
            <div className="sub2-inline-summary-item"><span>当前计划</span><strong>{selectedPlan?.name || '未选择计划'}</strong><small>{selectedPlan?.group_name || selectedPlan?.group_id || '-'}</small></div>
            <div className="sub2-inline-summary-item"><span>订单金额</span><strong>{formatUsdCost(Number(draft.amount_cents || 0) / 100, 2)}</strong><small>{selectedPlan ? `${selectedPlan.validity_days || 0} 天` : '请先选择计划'}</small></div>
            <div className="sub2-inline-summary-item"><span>支付通道</span><strong>{selectedChannel?.name || '不指定'}</strong><small>{selectedChannel?.provider || 'manual'}</small></div>
            <div className="sub2-inline-summary-item"><span>续费状态</span><strong>{selectedPlan && activeGroupIds.has(String(selectedPlan.group_id || '')) ? '可续费' : '可购买'}</strong><small>{selectedPlan && activePlanIds.has(selectedPlan.id) ? '已订阅当前计划' : '未订阅当前计划'}</small></div>
          </div>
        )}
        filters={(
          <FilterToolbar
            right={(
              <ToolbarButtonRow>
                <Button onClick={() => void reload()}><RefreshCw size={15} />刷新</Button>
                <ToolsMenu label="筛选设置" icon={false}>
                  <button type="button" onClick={() => togglePlanFilter('group')}>
                    <span>分组</span>
                    <strong>{visiblePlanFilters.has('group') ? '✓' : ''}</strong>
                  </button>
                </ToolsMenu>
                <ColumnMenu
                  label="列设置"
                  items={[
                    { key: 'group', label: '分组', checked: visiblePlanColumns.has('group'), onToggle: () => togglePlanColumn('group') },
                    { key: 'price', label: '价格', checked: visiblePlanColumns.has('price'), onToggle: () => togglePlanColumn('price') },
                    { key: 'validity', label: '有效期', checked: visiblePlanColumns.has('validity'), onToggle: () => togglePlanColumn('validity') },
                    { key: 'limits', label: '额度', checked: visiblePlanColumns.has('limits'), onToggle: () => togglePlanColumn('limits') },
                    { key: 'status', label: '状态', checked: visiblePlanColumns.has('status'), onToggle: () => togglePlanColumn('status') },
                  ]}
                />
                <ToolsMenu>
                  <button type="button" onClick={() => { setPlanSearch(''); setGroupFilter(''); setPlanPage(1); }}>
                    <span>清空筛选</span>
                  </button>
                  <button type="button" onClick={() => { setPlanPageSize(50); setPlanPage(1); }}>
                    <span>切换 50 / 页</span>
                  </button>
                </ToolsMenu>
                <Button tone="primary" disabled={!draft.plan_id} onClick={() => setConfirmCreate(true)}>
                  <CreditCard size={15} />
                  创建订单
                </Button>
              </ToolbarButtonRow>
            )}
          >
            <SearchField value={planSearch} placeholder="搜索计划 / 分组" onChange={(value) => { setPlanSearch(value); setPlanPage(1); }} />
            {visiblePlanFilters.has('group') ? (
              <Select value={groupFilter} onChange={(event) => { setGroupFilter(event.target.value); setPlanPage(1); }}>
                <option value="">全部分组</option>
                {groupOptions.map(([value, label]) => (
                  <option key={value} value={value}>{label}</option>
                ))}
              </Select>
            ) : null}
          </FilterToolbar>
        )}
        table={(
          <div className="table-wrap table-scroll">
            <table>
              <thead>
                <tr>
                  <th>计划</th>
                  {visiblePlanColumns.has('group') ? <th>分组</th> : null}
                  {visiblePlanColumns.has('price') ? <th>价格</th> : null}
                  {visiblePlanColumns.has('validity') ? <th>有效期</th> : null}
                  {visiblePlanColumns.has('limits') ? <th>额度</th> : null}
                  {visiblePlanColumns.has('status') ? <th>状态</th> : null}
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {pagedPlans.length ? pagedPlans.map((item) => {
                  const hasSamePlan = activePlanIds.has(item.id);
                  const hasSameGroup = activeGroupIds.has(String(item.group_id || ''));
                  return (
                    <tr key={item.id}>
                      <td>
                        <div className="sub2-cell-stack">
                          <strong>{item.name}</strong>
                          <small>{item.note || item.id}</small>
                        </div>
                      </td>
                      {visiblePlanColumns.has('group') ? (
                        <td>
                          <div className="sub2-cell-stack sub2-cell-stack-tight">
                            <strong>{item.group_name || item.group_id || '-'}</strong>
                            <small>倍率 ×{formatNumber(item.rate_multiplier || 1)}</small>
                          </div>
                        </td>
                      ) : null}
                      {visiblePlanColumns.has('price') ? (
                        <td>
                          <div className="sub2-order-amount">
                            <strong>{formatUsdCost(Number(item.final_price_cents || item.price_cents || 0) / 100, 2)}</strong>
                            <small>标准 {formatUsdCost(Number(item.price_cents || 0) / 100, 2)}</small>
                          </div>
                        </td>
                      ) : null}
                      {visiblePlanColumns.has('validity') ? (
                        <td>
                          <div className="sub2-cell-stack sub2-cell-stack-tight">
                            <strong>{formatNumber(item.validity_days || 0)} 天</strong>
                            <small>{hasSameGroup ? '适合续费' : '新购/续费'}</small>
                          </div>
                        </td>
                      ) : null}
                      {visiblePlanColumns.has('limits') ? (
                        <td>
                          <div className="sub2-cell-stack sub2-cell-stack-tight">
                            <strong>{formatPlanLimits(item)}</strong>
                            <small>日 / 周 / 月额度</small>
                          </div>
                        </td>
                      ) : null}
                      {visiblePlanColumns.has('status') ? (
                        <td>
                          <div className="sub2-cell-stack sub2-cell-stack-tight">
                            <Badge tone={hasSamePlan ? 'ok' : hasSameGroup ? 'warn' : 'neutral'}>
                              {hasSamePlan ? '已订阅' : hasSameGroup ? '可续费' : '可购买'}
                            </Badge>
                            <small>{item.enabled === false ? '未启用' : '可下单'}</small>
                          </div>
                        </td>
                      ) : null}
                      <td>
                        <RowActions>
                          <RowAction icon={Eye} label="详情" onClick={() => setInspectPlan(item)} />
                          <RowAction icon={CreditCard} label={hasSameGroup ? '续费' : '购买'} onClick={() => { selectPlan(item, true); }} />
                        </RowActions>
                      </td>
                    </tr>
                  );
                }) : (
                  <ListEmptyRow colSpan={visiblePlanColumns.size + 2} title="暂无可购买计划" />
                )}
              </tbody>
            </table>
          </div>
        )}
        pagination={filteredPlans.length ? (
          <Pager
            page={Math.min(planPage, planTotalPages)}
            pageSize={planPageSize}
            total={filteredPlans.length}
            onPageChange={(next) => setPlanPage(Math.min(Math.max(1, next), planTotalPages))}
            onPageSizeChange={(next) => { setPlanPageSize(next); setPlanPage(1); }}
          />
        ) : null}
      />

      <TablePageLayout
        filters={(
          <FilterToolbar
            right={(
              <ToolbarButtonRow>
                <ToolsMenu>
                  <button type="button" onClick={() => { setOrderSearch(''); setOrderStatus(''); setOrderPage(1); }}>
                    <span>清空筛选</span>
                  </button>
                  <button type="button" onClick={() => { setOrderStatus('pending'); setOrderPage(1); }}>
                    <span>仅看待支付</span>
                  </button>
                </ToolsMenu>
              </ToolbarButtonRow>
            )}
          >
            <SearchField value={orderSearch} placeholder="搜索订单 / 计划 / 通道 / 上游单号" onChange={(value) => { setOrderSearch(value); setOrderPage(1); }} />
            <Select value={orderStatus} onChange={(event) => { setOrderStatus(event.target.value); setOrderPage(1); }}>
              <option value="">全部状态</option>
              <option value="pending">待支付</option>
              <option value="paid">已支付</option>
              <option value="failed">失败</option>
              <option value="cancelled">已取消</option>
            </Select>
          </FilterToolbar>
        )}
        table={(
          <div className="table-wrap table-scroll">
            <table>
              <thead>
                <tr>
                  <th>订单</th>
                  <th>计划</th>
                  <th>通道</th>
                  <th>金额</th>
                  <th>状态</th>
                  <th>履约</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {pagedOrders.length ? pagedOrders.map((item) => (
                  <tr key={item.id}>
                    <td><div className="sub2-cell-stack"><strong>{item.id}</strong><small>{getAccountName(item)}</small></div></td>
                    <td><div className="sub2-cell-stack"><strong>{item.plan_name || item.plan_id}</strong><small>{item.group_name || item.group_id || '-'}</small></div></td>
                    <td><div className="sub2-cell-stack"><strong>{item.channel_name || item.channel_id || item.provider || '-'}</strong><small>{item.provider_order_id || item.resume_token || '-'}</small></div></td>
                    <td><strong className="sub2-number-cell">{formatUsdCost(Number(item.final_price_cents ?? item.amount_cents ?? 0) / 100, 2)}</strong></td>
                    <td><Badge tone={item.status === 'paid' ? 'ok' : item.status === 'pending' ? 'warn' : 'bad'}>{item.status || '-'}</Badge></td>
                    <td><div className="sub2-cell-stack sub2-cell-stack-tight"><strong>{item.subscription_id || '-'}</strong><small>{Array.isArray(item.fulfillment_logs) ? `${item.fulfillment_logs.length} 条日志` : '0 条日志'}</small></div></td>
                    <td>
                      <RowActions>
                        <RowAction icon={Eye} label="详情" onClick={() => setInspectOrder(item)} />
                      </RowActions>
                    </td>
                  </tr>
                )) : (
                  <ListEmptyRow colSpan={7} title="暂无订单记录" />
                )}
              </tbody>
            </table>
          </div>
        )}
        pagination={filteredOrders.length ? (
          <Pager
            page={Math.min(orderPage, orderTotalPages)}
            pageSize={orderPageSize}
            total={filteredOrders.length}
            onPageChange={(next) => setOrderPage(Math.min(Math.max(1, next), orderTotalPages))}
            onPageSizeChange={(next) => { setOrderPageSize(next); setOrderPage(1); }}
          />
        ) : null}
      />

      {inspectPlan ? (
        <Modal
          title="计划详情"
          size="lg"
          onClose={() => setInspectPlan(null)}
          footer={(
            <ModalActions>
              <Button onClick={() => setInspectPlan(null)}>关闭</Button>
              <Button tone="primary" onClick={() => { selectPlan(inspectPlan, true); setInspectPlan(null); }}>
                创建订单
              </Button>
            </ModalActions>
          )}
        >
          <div className="admin-dialog">
            <div className="admin-dialog-intro">
              <strong>{inspectPlan.name}</strong>
            </div>
            <div className="admin-dialog-summary">
              <div className="admin-dialog-summary-card">
                <span>分组</span>
                <strong>{inspectPlan.group_name || inspectPlan.group_id || '-'}</strong>
                <small>倍率 ×{formatNumber(inspectPlan.rate_multiplier || 1)}</small>
              </div>
              <div className="admin-dialog-summary-card">
                <span>价格</span>
                <strong>{formatUsdCost(Number(inspectPlan.final_price_cents || inspectPlan.price_cents || 0) / 100, 2)}</strong>
                <small>标准 {formatUsdCost(Number(inspectPlan.price_cents || 0) / 100, 2)}</small>
              </div>
              <div className="admin-dialog-summary-card">
                <span>有效期</span>
                <strong>{formatNumber(inspectPlan.validity_days || 0)} 天</strong>
                <small>{formatPlanLimits(inspectPlan)}</small>
              </div>
            </div>
            <Field label="额度" full>
              <TextInput readOnly value={formatPlanLimits(inspectPlan)} />
            </Field>
            <Field label="备注" full>
              <TextArea readOnly rows={4} value={inspectPlan.note || '-'} />
            </Field>
          </div>
        </Modal>
      ) : null}

      {confirmCreate ? (
        <Modal
          title="确认创建订单"
          size="md"
          onClose={() => setConfirmCreate(false)}
          footer={(
            <ModalActions>
              <Button onClick={() => setConfirmCreate(false)}>取消</Button>
              <Button tone="primary" disabled={createMutation.isPending || !draft.plan_id} onClick={() => createMutation.mutate({ plan_id: draft.plan_id, channel_id: draft.channel_id, amount_cents: draft.amount_cents, currency: draft.currency })}>
                确认创建
              </Button>
            </ModalActions>
          )}
        >
          <div className="admin-dialog">
            <div className="admin-dialog-intro">
              <strong>{account?.name || '-'}</strong>
            </div>
            <div className="admin-dialog-summary">
              <div className="admin-dialog-summary-card">
                <span>订阅计划</span>
                <strong>{selectedPlan?.name || '未选择计划'}</strong>
                <small>{selectedPlan?.group_name || selectedPlan?.group_id || '-'}</small>
              </div>
              <div className="admin-dialog-summary-card">
                <span>订单金额</span>
                <strong>{formatUsdCost(Number(draft.amount_cents || 0) / 100, 2)}</strong>
                <small>{selectedPlan ? `${selectedPlan.validity_days || 0} 天` : '-'}</small>
              </div>
              <div className="admin-dialog-summary-card">
                <span>支付通道</span>
                <strong>{selectedChannel?.name || '不指定'}</strong>
                <small>{selectedChannel?.provider || 'manual'}</small>
              </div>
            </div>
            <Field label="支付通道" full>
              <Select value={draft.channel_id} onChange={(event) => setDraft((current) => ({ ...current, channel_id: event.target.value }))}>
                <option value="">不指定</option>
                {visibleChannels.map((channel) => (
                  <option key={channel.id} value={channel.id}>{channel.name}</option>
                ))}
              </Select>
            </Field>
          </div>
        </Modal>
      ) : null}

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
                <small>{getAccountName(createdOrder)}</small>
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
              <Field label="用户"><TextInput readOnly value={getAccountName(inspectOrder)} /></Field>
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

function formatPlanLimits(plan: AdminSubscriptionPlan) {
  const items = [
    ['日', plan.daily_limit],
    ['周', plan.weekly_limit],
    ['月', plan.monthly_limit],
  ].filter(([, value]) => Number(value || 0) > 0);
  if (!items.length) return '不限额';
  return items.map(([label, value]) => `${label} ${formatNumber(value || 0)}`).join(' / ');
}
