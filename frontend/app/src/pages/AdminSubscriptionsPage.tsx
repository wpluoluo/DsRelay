import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Ban, Calendar, Eye, Plus, RefreshCw, RotateCcw } from 'lucide-react';
import { assignAdminAccountSubscription, extendAdminAccountSubscription, fetchAdminUsers, fetchAdminSubscriptionPlans, fetchAdminAccountSubscriptions, resetAdminAccountSubscriptionQuota, revokeAdminAccountSubscription } from '../api';
import { Button, Field, Modal, ModalActions, Select, TextInput } from '../components';
import { ActionButton, ColumnMenu, FilterToolbar, ListEmptyRow, Pager, RowAction, RowActions, SearchField, TablePageLayout, ToolbarButtonRow, ToolsMenu } from '../components/admin';
import { queryClient } from '../state/queryClient';
import { cn, formatNumber, readStorageJSON, writeStorageJSON } from '../utils';

type SubscriptionColumnKey = 'status' | 'daily' | 'weekly' | 'monthly' | 'expires';

const DEFAULT_VISIBLE_COLUMNS: SubscriptionColumnKey[] = ['status', 'daily', 'weekly', 'monthly', 'expires'];
const STORAGE_KEY = 'admin-subscriptions-view-state';

export function AdminSubscriptionsPage() {
  const subsQuery = useQuery({ queryKey: ['admin-subscriptions'], queryFn: fetchAdminAccountSubscriptions, refetchInterval: 10000 });
  const accountsQuery = useQuery({ queryKey: ['admin-users'], queryFn: fetchAdminUsers, refetchInterval: 10000 });
  const plansQuery = useQuery({ queryKey: ['admin-subscription-plans'], queryFn: fetchAdminSubscriptionPlans, refetchInterval: 10000 });
  const [draft, setDraft] = useState<any | null>(null);
  const [inspectSubscription, setInspectSubscription] = useState<any | null>(null);
  const [extendTarget, setExtendTarget] = useState<{ id: string; name: string; days: number } | null>(null);
  const [actionTarget, setActionTarget] = useState<{ id: string; name: string; action: 'reset' | 'revoke' } | null>(null);
  const savedState = readStorageJSON(STORAGE_KEY, {
    search: '',
    statusFilter: '',
    groupFilter: '',
    pageSize: 20,
    visibleColumns: DEFAULT_VISIBLE_COLUMNS,
  });
  const [search, setSearch] = useState(savedState.search);
  const [statusFilter, setStatusFilter] = useState(savedState.statusFilter);
  const [groupFilter, setGroupFilter] = useState(savedState.groupFilter || '');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(savedState.pageSize || 20);
  const [visibleColumns, setVisibleColumns] = useState<Set<SubscriptionColumnKey>>(new Set(savedState.visibleColumns || DEFAULT_VISIBLE_COLUMNS));

  const assignMutation = useMutation({
    mutationFn: assignAdminAccountSubscription,
    onSuccess: async () => {
      setDraft(null);
      await queryClient.invalidateQueries({ queryKey: ['admin-subscriptions'] });
    },
  });
  const extendMutation = useMutation({
    mutationFn: ({ id, days }: { id: string; days: number }) => extendAdminAccountSubscription(id, days),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['admin-subscriptions'] });
    },
  });
  const revokeMutation = useMutation({
    mutationFn: (id: string) => revokeAdminAccountSubscription(id),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['admin-subscriptions'] });
    },
  });
  const resetQuotaMutation = useMutation({
    mutationFn: (id: string) => resetAdminAccountSubscriptionQuota(id, { daily: true, weekly: true, monthly: true }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['admin-subscriptions'] });
    },
  });

  const items = subsQuery.data?.items || [];
  const accounts = accountsQuery.data?.items || [];
  const plans = plansQuery.data?.items || [];
  const planMap = useMemo(() => new Map(plans.map((plan) => [plan.id, plan])), [plans]);
  const selectedPlan = draft?.plan_id ? planMap.get(draft.plan_id) : undefined;
  const selectedAccount = draft?.account_id ? accounts.find((account) => account.id === draft.account_id) : undefined;
  const groupOptions = useMemo(
    () =>
      Array.from(new Map(plans.filter((plan) => plan.group_id).map((plan) => [plan.group_id, plan.group_name || plan.group_id])).entries()).sort((left, right) =>
        String(left[1]).localeCompare(String(right[1]), 'zh-CN'),
      ),
    [plans],
  );

  const filteredItems = useMemo(() => {
    const keyword = search.trim().toLowerCase();
    return items.filter((item) => {
      if (keyword) {
        const haystack = [item.account_name, item.account_id, item.plan_name, item.plan_id, item.id].map((value) => String(value || '').toLowerCase()).join(' ');
        if (!haystack.includes(keyword)) return false;
      }
      if (statusFilter && item.status !== statusFilter) return false;
      if (groupFilter && item.group_id !== groupFilter) return false;
      return true;
    });
  }, [groupFilter, items, search, statusFilter]);

  const totalPages = Math.max(1, Math.ceil(filteredItems.length / pageSize));
  const pagedItems = useMemo(() => {
    const start = (page - 1) * pageSize;
    return filteredItems.slice(start, start + pageSize);
  }, [filteredItems, page, pageSize]);
  const activeCount = filteredItems.filter((item) => item.status === 'active').length;
  const expiredCount = filteredItems.filter((item) => item.status === 'expired').length;
  const expiringSoonCount = filteredItems.filter((item) => {
    if (!item.expires_at) return false;
    const days = Math.ceil(item.expires_at * 1000 - Date.now()) / 86400000;
    return days >= 0 && days <= 7;
  }).length;
  const totalDailyUsed = filteredItems.reduce((sum, item) => sum + Number(item.daily_used || 0), 0);

  useEffect(() => {
    writeStorageJSON(STORAGE_KEY, {
      search,
      statusFilter,
      groupFilter,
      pageSize,
      visibleColumns: Array.from(visibleColumns),
    });
  }, [groupFilter, pageSize, search, statusFilter, visibleColumns]);

  function toggleColumn(key: SubscriptionColumnKey) {
    setVisibleColumns((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  return (
    <section className="grid-page">
      <div className="sub2-page-head">
        <div className="sub2-page-title">
          <strong>账户订阅</strong>
          <span>按订阅处理分配、延期、重置与撤销，保持和 SUB2 一致的列表工作流。</span>
        </div>
        <div className="sub2-inline-summary">
          <div className="sub2-inline-summary-item"><span>订阅数</span><strong>{formatNumber(filteredItems.length)}</strong><small>当前筛选范围</small></div>
          <div className="sub2-inline-summary-item"><span>有效订阅</span><strong>{formatNumber(activeCount)}</strong><small>已过期 {formatNumber(expiredCount)}</small></div>
          <div className="sub2-inline-summary-item"><span>即将到期</span><strong>{formatNumber(expiringSoonCount)}</strong><small>7 天内到期</small></div>
          <div className="sub2-inline-summary-item"><span>日累计用量</span><strong>{formatNumber(totalDailyUsed)}</strong><small>筛选订阅合计</small></div>
        </div>
      </div>
      <TablePageLayout
        filters={
          <FilterToolbar
            right={
              <ToolbarButtonRow>
                <ActionButton onClick={() => subsQuery.refetch()}><RefreshCw size={15} />刷新</ActionButton>
                <ColumnMenu
                  label="列设置"
                  items={[
                    { key: 'status', label: '状态', checked: visibleColumns.has('status'), onToggle: () => toggleColumn('status') },
                    { key: 'daily', label: '日用量', checked: visibleColumns.has('daily'), onToggle: () => toggleColumn('daily') },
                    { key: 'weekly', label: '周用量', checked: visibleColumns.has('weekly'), onToggle: () => toggleColumn('weekly') },
                    { key: 'monthly', label: '月用量', checked: visibleColumns.has('monthly'), onToggle: () => toggleColumn('monthly') },
                    { key: 'expires', label: '到期时间', checked: visibleColumns.has('expires'), onToggle: () => toggleColumn('expires') },
                  ]}
                />
                <ToolsMenu>
                  <button type="button" onClick={() => { setSearch(''); setStatusFilter(''); setGroupFilter(''); setPage(1); }}>
                    <span>清空筛选</span>
                  </button>
                  <button type="button" onClick={() => { setStatusFilter('active'); setPage(1); }}>
                    <span>仅看有效订阅</span>
                  </button>
                  <button type="button" onClick={() => { setPageSize(50); setPage(1); }}>
                    <span>切换 50 / 页</span>
                  </button>
                </ToolsMenu>
                <Button tone="primary" onClick={() => setDraft({ account_id: '', plan_id: '', status: 'active' })}><Plus size={15} />分配订阅</Button>
              </ToolbarButtonRow>
            }
          >
            <SearchField value={search} placeholder="搜索账户 / 计划 / 订阅 ID" onChange={(value) => { setSearch(value); setPage(1); }} />
            <Select value={statusFilter} onChange={(event) => { setStatusFilter(event.target.value); setPage(1); }}>
              <option value="">全部状态</option>
              <option value="active">active</option>
              <option value="expired">expired</option>
              <option value="revoked">revoked</option>
            </Select>
            <Select value={groupFilter} onChange={(event) => { setGroupFilter(event.target.value); setPage(1); }}>
              <option value="">全部分组</option>
              {groupOptions.map(([groupId, groupName]) => (
                <option key={groupId} value={groupId}>{groupName}</option>
              ))}
            </Select>
          </FilterToolbar>
        }
        table={
          <div className="table-wrap table-scroll">
            <table>
              <thead>
                <tr>
                  <th>账户</th>
                  <th>计划</th>
                  <th>分组 / 价格</th>
                  {visibleColumns.has('status') ? <th>状态</th> : null}
                  {visibleColumns.has('daily') ? <th>日用量</th> : null}
                  {visibleColumns.has('weekly') ? <th>周用量</th> : null}
                  {visibleColumns.has('monthly') ? <th>月用量</th> : null}
                  {visibleColumns.has('expires') ? <th>到期时间</th> : null}
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {pagedItems.length ? pagedItems.map((item) => (
                  <tr key={item.id}>
                    <td>
                      <div className="sub2-cell-stack">
                        <strong>{item.account_name || item.account_id}</strong>
                        <small>{item.id}</small>
                      </div>
                    </td>
                    <td>
                      <div className="sub2-cell-stack sub2-cell-stack-tight">
                        <strong>{item.plan_name || item.plan_id}</strong>
                        <small>{item.plan_id}</small>
                      </div>
                    </td>
                    <td>
                      <div className="sub2-cell-stack sub2-cell-stack-tight">
                        <strong>{item.group_name || item.group_id || '-'}</strong>
                        <small>{Number(item.price_cents || 0)} · ×{Number(item.rate_multiplier || 1)}</small>
                      </div>
                    </td>
                    {visibleColumns.has('status') ? <td><span className={cn('badge', item.status === 'active' ? 'badge-ok' : item.status === 'expired' ? 'badge-warn' : 'badge-bad')}>{item.status || '-'}</span></td> : null}
                    {visibleColumns.has('daily') ? <td><UsageProgress used={Number(item.daily_used || 0)} limit={Number(planMap.get(item.plan_id)?.daily_limit || 0)} label="日" /></td> : null}
                    {visibleColumns.has('weekly') ? <td><UsageProgress used={Number(item.weekly_used || 0)} limit={Number(planMap.get(item.plan_id)?.weekly_limit || 0)} label="周" /></td> : null}
                    {visibleColumns.has('monthly') ? <td><UsageProgress used={Number(item.monthly_used || 0)} limit={Number(planMap.get(item.plan_id)?.monthly_limit || 0)} label="月" /></td> : null}
                    {visibleColumns.has('expires') ? <td><ExpiryCell value={item.expires_at} /></td> : null}
                    <td>
                      <RowActions>
                        <RowAction icon={Eye} label="详情" onClick={() => setInspectSubscription(item)} />
                        <RowAction icon={Calendar} label="延期" onClick={() => setExtendTarget({ id: item.id, name: item.account_name || item.account_id || item.id, days: 30 })} />
                        <RowAction icon={RotateCcw} label="重置" onClick={() => setActionTarget({ id: item.id, name: item.account_name || item.account_id || item.id, action: 'reset' })} />
                        <RowAction icon={Ban} label="撤销" tone="danger" onClick={() => setActionTarget({ id: item.id, name: item.account_name || item.account_id || item.id, action: 'revoke' })} />
                      </RowActions>
                    </td>
                  </tr>
                )) : (
                  <ListEmptyRow
                    colSpan={visibleColumns.size + 4}
                    title="暂无账户订阅"
                    description="当前没有可展示的订阅记录。"
                    action={<Button tone="primary" onClick={() => setDraft({ account_id: '', plan_id: '', status: 'active' })}>分配订阅</Button>}
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
          title="分配订阅"
          size="md"
          onClose={() => setDraft(null)}
          footer={
            <ModalActions>
              <Button onClick={() => setDraft(null)}>取消</Button>
              <Button tone="primary" disabled={assignMutation.isPending || !draft.account_id || !draft.plan_id} onClick={() => assignMutation.mutate(draft)}>分配</Button>
            </ModalActions>
          }
        >
          <div className="admin-dialog">
            <div className="admin-dialog-intro">
              <strong>向账户分配新的订阅</strong>
              <span>订阅会直接参与请求鉴权、额度校验和消费归因。这里的操作需要和计划、分组、支付记录保持一致。</span>
            </div>
            <div className="admin-dialog-summary">
              <div className="admin-dialog-summary-card">
                <span>当前有效订阅</span>
                <strong>{formatNumber(activeCount)}</strong>
                <small>当前筛选范围</small>
              </div>
              <div className="admin-dialog-summary-card">
                <span>即将到期</span>
                <strong>{formatNumber(expiringSoonCount)}</strong>
                <small>7 天内到期</small>
              </div>
              <div className="admin-dialog-summary-card">
                <span>待分配状态</span>
                <strong>{draft.status || 'active'}</strong>
                <small>{draft.plan_id ? '已选择计划' : '待选择计划'}</small>
              </div>
            </div>
            <div className="admin-dialog-summary">
              <div className="admin-dialog-summary-card">
                <span>目标账户</span>
                <strong>{selectedAccount?.name || '待选择账户'}</strong>
                <small>{selectedAccount?.group_name || selectedAccount?.group_id || '未分组'}</small>
              </div>
              <div className="admin-dialog-summary-card">
                <span>计划价格</span>
                <strong>{selectedPlan ? formatNumber(selectedPlan.final_price_cents || selectedPlan.price_cents || 0) : '-'}</strong>
                <small>{selectedPlan ? `${formatNumber(selectedPlan.validity_days || 0)} 天` : '待选择计划'}</small>
              </div>
              <div className="admin-dialog-summary-card">
                <span>额度预览</span>
                <strong>{selectedPlan ? `${formatNumber(selectedPlan.daily_limit || 0)} / ${formatNumber(selectedPlan.weekly_limit || 0)} / ${formatNumber(selectedPlan.monthly_limit || 0)}` : '-'}</strong>
                <small>日 / 周 / 月</small>
              </div>
            </div>
            <div className="admin-dialog-section">
              <div className="admin-dialog-section-head">
                <strong>订阅信息</strong>
                <span>账户与计划确认后即可直接落订阅记录</span>
              </div>
              <div className="admin-dialog-grid modal-grid">
                <Field label="账户">
                  <Select value={draft.account_id} onChange={(e) => setDraft({ ...draft, account_id: e.target.value })}>
                    <option value="">请选择账户</option>
                    {accounts.map((account) => <option key={account.id} value={account.id}>{account.name}</option>)}
                  </Select>
                </Field>
                <Field label="计划">
                  <Select value={draft.plan_id} onChange={(e) => setDraft({ ...draft, plan_id: e.target.value })}>
                    <option value="">请选择计划</option>
                    {plans.map((plan) => <option key={plan.id} value={plan.id}>{plan.name}</option>)}
                  </Select>
                </Field>
                <Field label="状态">
                  <Select value={draft.status} onChange={(e) => setDraft({ ...draft, status: e.target.value })}>
                    <option value="active">active</option>
                    <option value="expired">expired</option>
                    <option value="revoked">revoked</option>
                  </Select>
                </Field>
              </div>
            </div>
            <div className="admin-dialog-note">
              分配完成后，账户在 API Key 校验和使用记录中会立即看到新的订阅归属。
            </div>
          </div>
        </Modal>
      ) : null}

      {inspectSubscription ? (
        <Modal
          title="订阅详情"
          size="md"
          onClose={() => setInspectSubscription(null)}
          footer={<ModalActions><Button onClick={() => setInspectSubscription(null)}>关闭</Button></ModalActions>}
        >
          <div className="admin-dialog">
            <div className="admin-dialog-intro">
              <strong>{inspectSubscription.account_name || inspectSubscription.account_id}</strong>
              <span>查看订阅归属、用量和到期信息，便于管理员快速核验。</span>
            </div>
            <div className="admin-dialog-summary">
              <div className="admin-dialog-summary-card">
                <span>计划</span>
                <strong>{inspectSubscription.plan_name || inspectSubscription.plan_id || '-'}</strong>
                <small>{inspectSubscription.group_name || inspectSubscription.group_id || '未分组'}</small>
              </div>
              <div className="admin-dialog-summary-card">
                <span>状态</span>
                <strong>{inspectSubscription.status || '-'}</strong>
                <small>{formatDateTime(inspectSubscription.expires_at)}</small>
              </div>
              <div className="admin-dialog-summary-card">
                <span>价格</span>
                <strong>{formatNumber(inspectSubscription.price_cents || 0)}</strong>
                <small>倍率 ×{formatNumber(inspectSubscription.rate_multiplier || 1)}</small>
              </div>
            </div>
            <div className="admin-dialog-section">
              <div className="admin-dialog-section-head">
                <strong>额度使用</strong>
                <span>当前订阅的日 / 周 / 月用量</span>
              </div>
              <div className="admin-dialog-grid">
                <Field label="日额度"><TextInput readOnly value={`${formatNumber(inspectSubscription.daily_used || 0)} / ${formatNumber(inspectSubscription.daily_limit || 0)}`} /></Field>
                <Field label="周额度"><TextInput readOnly value={`${formatNumber(inspectSubscription.weekly_used || 0)} / ${formatNumber(inspectSubscription.weekly_limit || 0)}`} /></Field>
                <Field label="月额度"><TextInput readOnly value={`${formatNumber(inspectSubscription.monthly_used || 0)} / ${formatNumber(inspectSubscription.monthly_limit || 0)}`} /></Field>
                <Field label="到期时间"><TextInput readOnly value={formatDateTime(inspectSubscription.expires_at)} /></Field>
              </div>
            </div>
          </div>
        </Modal>
      ) : null}

      {extendTarget ? (
        <Modal
          title="订阅延期"
          size="md"
          onClose={() => setExtendTarget(null)}
          footer={
            <ModalActions>
              <Button onClick={() => setExtendTarget(null)}>取消</Button>
              <Button
                tone="primary"
                disabled={extendMutation.isPending}
                onClick={() => extendMutation.mutate({ id: extendTarget.id, days: extendTarget.days })}
              >
                确认延期
              </Button>
            </ModalActions>
          }
        >
          <div className="admin-dialog">
            <div className="admin-dialog-intro">
              <strong>{extendTarget.name}</strong>
              <span>确认要为该订阅增加有效期。默认增加 30 天，可手动调整。</span>
            </div>
            <div className="admin-dialog-summary">
              <div className="admin-dialog-summary-card">
                <span>操作类型</span>
                <strong>延期</strong>
                <small>直接写入新的到期时间</small>
              </div>
              <div className="admin-dialog-summary-card">
                <span>当前选择</span>
                <strong>{extendTarget.days} 天</strong>
                <small>支持 7 / 30 / 90 / 365 天</small>
              </div>
              <div className="admin-dialog-summary-card">
                <span>影响范围</span>
                <strong>单个订阅</strong>
                <small>不会变更额度历史</small>
              </div>
            </div>
            <div className="admin-dialog-section">
              <div className="admin-dialog-section-head">
                <strong>延期参数</strong>
                <span>提交后立即写入订阅到期时间</span>
              </div>
              <div className="admin-dialog-grid">
                <Field label="延期天数">
                  <Select value={String(extendTarget.days)} onChange={(e) => setExtendTarget({ ...extendTarget, days: Number(e.target.value || 30) })}>
                    <option value="7">7 天</option>
                    <option value="30">30 天</option>
                    <option value="90">90 天</option>
                    <option value="365">365 天</option>
                  </Select>
                </Field>
              </div>
            </div>
          </div>
        </Modal>
      ) : null}

      {actionTarget ? (
        <Modal
          title={actionTarget.action === 'reset' ? '确认重置额度' : '确认撤销订阅'}
          size="md"
          onClose={() => setActionTarget(null)}
          footer={
            <ModalActions>
              <Button onClick={() => setActionTarget(null)}>取消</Button>
              <Button
                tone={actionTarget.action === 'revoke' ? 'danger' : 'primary'}
                disabled={resetQuotaMutation.isPending || revokeMutation.isPending}
                onClick={() => {
                  if (actionTarget.action === 'reset') resetQuotaMutation.mutate(actionTarget.id);
                  else revokeMutation.mutate(actionTarget.id);
                }}
              >
                {actionTarget.action === 'reset' ? '确认重置' : '确认撤销'}
              </Button>
            </ModalActions>
          }
        >
          <div className="admin-dialog">
            <div className="admin-dialog-intro">
              <strong>{actionTarget.name}</strong>
              <span>{actionTarget.action === 'reset' ? '将清空该订阅的日、周、月额度使用量。' : '撤销后该订阅会立刻失效，影响用户调用。'}</span>
            </div>
            <div className="admin-dialog-summary">
              <div className="admin-dialog-summary-card">
                <span>操作类型</span>
                <strong>{actionTarget.action === 'reset' ? '重置额度' : '撤销订阅'}</strong>
                <small>{actionTarget.action === 'reset' ? '清空日 / 周 / 月用量' : '状态会立即失效'}</small>
              </div>
              <div className="admin-dialog-summary-card">
                <span>执行对象</span>
                <strong>{actionTarget.name}</strong>
                <small>当前选中的单个订阅</small>
              </div>
              <div className="admin-dialog-summary-card">
                <span>风险级别</span>
                <strong>{actionTarget.action === 'reset' ? '中' : '高'}</strong>
                <small>{actionTarget.action === 'reset' ? '仅影响配额统计' : '会影响后续调用可用性'}</small>
              </div>
            </div>
          </div>
        </Modal>
      ) : null}
    </section>
  );
}

function formatDateTime(value: number | null | undefined) {
  if (!value) return '-';
  const date = new Date(value * 1000);
  if (Number.isNaN(date.getTime())) return '-';
  return date.toLocaleString('zh-CN', { hour12: false });
}

function ExpiryCell({ value }: { value: number | null | undefined }) {
  if (!value) return <span className="table-muted">-</span>;
  const date = new Date(value * 1000);
  if (Number.isNaN(date.getTime())) return <span className="table-muted">-</span>;
  const days = Math.ceil((date.getTime() - Date.now()) / 86400000);
  return (
    <div className="sub2-expiry-cell">
      <strong className={days <= 7 ? 'bad-text' : ''}>{date.toLocaleDateString('zh-CN')}</strong>
      <small>{days >= 0 ? `剩余 ${days} 天` : '已到期'}</small>
    </div>
  );
}

function UsageProgress({ used, limit, label }: { used: number; limit: number; label: string }) {
  if (!limit) {
    return (
      <div className="sub2-usage-cell">
        <div className="sub2-usage-head">
          <span>{label}</span>
          <strong>{formatNumber(used)}</strong>
        </div>
        <small>无限额</small>
      </div>
    );
  }
  const ratio = Math.max(0, Math.min(100, Math.round((used / limit) * 100)));
  const tone = ratio >= 90 ? 'danger' : ratio >= 70 ? 'warn' : 'ok';
  return (
    <div className="sub2-usage-cell">
      <div className="sub2-usage-head">
        <span>{label}</span>
        <strong>{formatNumber(used)} / {formatNumber(limit)}</strong>
      </div>
      <div className="sub2-usage-bar">
        <span className={tone} style={{ width: `${Math.max(6, ratio)}%` }} />
      </div>
      <small>{ratio}%</small>
    </div>
  );
}
