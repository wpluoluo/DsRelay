import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Ban, Calendar, CalendarClock, Plus, RefreshCw, RotateCcw, ShieldCheck, Ticket, Users } from 'lucide-react';
import { assignAdminSubscription, extendAdminSubscription, fetchAdminSubscriptionPlans, fetchAdminSubscriptions, fetchAdminUsers, resetAdminSubscriptionQuota, revokeAdminSubscription } from '../api';
import { Button, Field, Modal, Select } from '../components';
import { ActionButton, ColumnMenu, EmptyState, FilterToolbar, Pager, SearchField, TablePageLayout, ToolbarButtonRow } from '../components/admin';
import { queryClient } from '../state/queryClient';
import { cn, formatNumber, readStorageJSON, writeStorageJSON } from '../utils';

type SubscriptionColumnKey = 'status' | 'daily' | 'weekly' | 'monthly' | 'expires';

const DEFAULT_VISIBLE_COLUMNS: SubscriptionColumnKey[] = ['status', 'daily', 'weekly', 'monthly', 'expires'];
const STORAGE_KEY = 'admin-subscriptions-view-state';

export function AdminSubscriptionsPage() {
  const subsQuery = useQuery({ queryKey: ['admin-subscriptions'], queryFn: fetchAdminSubscriptions, refetchInterval: 10000 });
  const usersQuery = useQuery({ queryKey: ['admin-users'], queryFn: fetchAdminUsers, refetchInterval: 10000 });
  const plansQuery = useQuery({ queryKey: ['admin-subscription-plans'], queryFn: fetchAdminSubscriptionPlans, refetchInterval: 10000 });
  const [draft, setDraft] = useState<any | null>(null);
  const savedState = readStorageJSON(STORAGE_KEY, {
    search: '',
    statusFilter: '',
    pageSize: 20,
    visibleColumns: DEFAULT_VISIBLE_COLUMNS,
  });
  const [search, setSearch] = useState(savedState.search);
  const [statusFilter, setStatusFilter] = useState(savedState.statusFilter);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(savedState.pageSize || 20);
  const [visibleColumns, setVisibleColumns] = useState<Set<SubscriptionColumnKey>>(new Set(savedState.visibleColumns || DEFAULT_VISIBLE_COLUMNS));

  const assignMutation = useMutation({
    mutationFn: assignAdminSubscription,
    onSuccess: async () => {
      setDraft(null);
      await queryClient.invalidateQueries({ queryKey: ['admin-subscriptions'] });
    },
  });
  const extendMutation = useMutation({
    mutationFn: ({ id, days }: { id: string; days: number }) => extendAdminSubscription(id, days),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['admin-subscriptions'] });
    },
  });
  const revokeMutation = useMutation({
    mutationFn: (id: string) => revokeAdminSubscription(id),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['admin-subscriptions'] });
    },
  });
  const resetQuotaMutation = useMutation({
    mutationFn: (id: string) => resetAdminSubscriptionQuota(id, { daily: true, weekly: true, monthly: true }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['admin-subscriptions'] });
    },
  });

  const items = subsQuery.data?.items || [];
  const users = usersQuery.data?.items || [];
  const plans = plansQuery.data?.items || [];
  const planMap = useMemo(() => new Map(plans.map((plan) => [plan.id, plan])), [plans]);

  const filteredItems = useMemo(() => {
    const keyword = search.trim().toLowerCase();
    return items.filter((item) => {
      if (keyword) {
        const haystack = [item.user_name, item.user_id, item.plan_name, item.plan_id, item.id].map((value) => String(value || '').toLowerCase()).join(' ');
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
  const activeCount = filteredItems.filter((item) => item.status === 'active').length;
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
      pageSize,
      visibleColumns: Array.from(visibleColumns),
    });
  }, [pageSize, search, statusFilter, visibleColumns]);

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
      <div className="key-stat-grid">
        <div className="key-stat"><div className="key-stat-icon blue"><Ticket size={18} /></div><div><span>订阅数</span><strong>{formatNumber(filteredItems.length)}</strong><small>当前筛选范围</small></div></div>
        <div className="key-stat"><div className="key-stat-icon green"><ShieldCheck size={18} /></div><div><span>有效订阅</span><strong>{formatNumber(activeCount)}</strong><small>当前 active</small></div></div>
        <div className="key-stat"><div className="key-stat-icon amber"><CalendarClock size={18} /></div><div><span>即将到期</span><strong>{formatNumber(expiringSoonCount)}</strong><small>7 天内到期</small></div></div>
        <div className="key-stat"><div className="key-stat-icon slate"><Users size={18} /></div><div><span>日累计用量</span><strong>{formatNumber(totalDailyUsed)}</strong><small>筛选订阅合计</small></div></div>
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
                <Button tone="primary" onClick={() => setDraft({ user_id: '', plan_id: '', status: 'active' })}><Plus size={15} />分配订阅</Button>
              </ToolbarButtonRow>
            }
          >
            <SearchField value={search} placeholder="搜索用户 / 计划 / 订阅 ID" onChange={(value) => { setSearch(value); setPage(1); }} />
            <Select value={statusFilter} onChange={(event) => { setStatusFilter(event.target.value); setPage(1); }}>
              <option value="">全部状态</option>
              <option value="active">active</option>
              <option value="expired">expired</option>
              <option value="revoked">revoked</option>
            </Select>
          </FilterToolbar>
        }
        table={
          <div className="table-wrap table-scroll">
            <table>
              <thead>
                <tr>
                  <th>用户</th>
                  <th>计划</th>
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
                        <strong>{item.user_name || item.user_id}</strong>
                        <small>{item.id}</small>
                      </div>
                    </td>
                    <td>
                      <div className="sub2-cell-stack sub2-cell-stack-tight">
                        <strong>{item.plan_name || item.plan_id}</strong>
                        <small>{item.plan_id}</small>
                      </div>
                    </td>
                    {visibleColumns.has('status') ? <td><span className={cn('badge', item.status === 'active' ? 'badge-ok' : item.status === 'expired' ? 'badge-warn' : 'badge-bad')}>{item.status || '-'}</span></td> : null}
                    {visibleColumns.has('daily') ? <td><UsageProgress used={Number(item.daily_used || 0)} limit={Number(planMap.get(item.plan_id)?.daily_limit || 0)} label="日" /></td> : null}
                    {visibleColumns.has('weekly') ? <td><UsageProgress used={Number(item.weekly_used || 0)} limit={Number(planMap.get(item.plan_id)?.weekly_limit || 0)} label="周" /></td> : null}
                    {visibleColumns.has('monthly') ? <td><UsageProgress used={Number(item.monthly_used || 0)} limit={Number(planMap.get(item.plan_id)?.monthly_limit || 0)} label="月" /></td> : null}
                    {visibleColumns.has('expires') ? <td><ExpiryCell value={item.expires_at} /></td> : null}
                    <td>
                      <div className="sub2-action-stack">
                        <button type="button" className="sub2-icon-action" onClick={() => extendMutation.mutate({ id: item.id, days: 30 })}>
                          <Calendar size={14} />
                          <span>延期</span>
                        </button>
                        <button type="button" className="sub2-icon-action" onClick={() => resetQuotaMutation.mutate(item.id)}>
                          <RotateCcw size={14} />
                          <span>重置</span>
                        </button>
                        <button type="button" className="sub2-icon-action danger" onClick={() => revokeMutation.mutate(item.id)}>
                          <Ban size={14} />
                          <span>撤销</span>
                        </button>
                      </div>
                    </td>
                  </tr>
                )) : (
                  <tr>
                    <td colSpan={visibleColumns.size + 3}>
                      <EmptyState title="暂无用户订阅" description="当前没有可展示的订阅记录。" action={<Button tone="primary" onClick={() => setDraft({ user_id: '', plan_id: '', status: 'active' })}>分配订阅</Button>} />
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
          title="分配订阅"
          onClose={() => setDraft(null)}
          footer={
            <>
              <Button onClick={() => setDraft(null)}>取消</Button>
              <Button tone="primary" disabled={assignMutation.isPending || !draft.user_id || !draft.plan_id} onClick={() => assignMutation.mutate(draft)}>分配</Button>
            </>
          }
        >
          <div className="form-grid modal-grid">
            <Field label="用户">
              <Select value={draft.user_id} onChange={(e) => setDraft({ ...draft, user_id: e.target.value })}>
                <option value="">请选择用户</option>
                {users.map((user) => <option key={user.id} value={user.id}>{user.name}</option>)}
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
