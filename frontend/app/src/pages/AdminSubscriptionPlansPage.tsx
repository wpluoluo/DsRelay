import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Ban, CalendarRange, FolderKanban, Pencil, Plus, RefreshCw, ShieldCheck, Ticket, Wallet } from 'lucide-react';
import { fetchAdminGroups, fetchAdminSubscriptionPlans, saveAdminSubscriptionPlan } from '../api';
import { Button, Field, Modal, Select, TextArea, TextInput } from '../components';
import { ActionButton, ColumnMenu, EmptyState, FilterToolbar, Pager, SearchField, TablePageLayout, ToolbarButtonRow } from '../components/admin';
import { queryClient } from '../state/queryClient';
import { cn, formatNumber, maskEmpty, readStorageJSON, writeStorageJSON } from '../utils';

type PlanColumnKey = 'group' | 'price' | 'validity' | 'daily' | 'weekly' | 'monthly' | 'status';

const DEFAULT_VISIBLE_COLUMNS: PlanColumnKey[] = ['group', 'price', 'validity', 'daily', 'weekly', 'monthly', 'status'];
const STORAGE_KEY = 'admin-subscription-plans-view-state';

export function AdminSubscriptionPlansPage() {
  const plansQuery = useQuery({ queryKey: ['admin-subscription-plans'], queryFn: fetchAdminSubscriptionPlans, refetchInterval: 10000 });
  const groupsQuery = useQuery({ queryKey: ['admin-groups'], queryFn: fetchAdminGroups, refetchInterval: 10000 });
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
  const [visibleColumns, setVisibleColumns] = useState<Set<PlanColumnKey>>(new Set(savedState.visibleColumns || DEFAULT_VISIBLE_COLUMNS));
  const groups = groupsQuery.data?.items || [];

  const saveMutation = useMutation({
    mutationFn: saveAdminSubscriptionPlan,
    onSuccess: async () => {
      setDraft(null);
      await queryClient.invalidateQueries({ queryKey: ['admin-subscription-plans'] });
    },
  });

  const items = plansQuery.data?.items || [];
  const groupMap = useMemo(() => new Map(groups.map((group) => [group.id, group.name])), [groups]);

  const filteredItems = useMemo(() => {
    const keyword = search.trim().toLowerCase();
    return items.filter((item) => {
      if (keyword) {
        const haystack = [item.name, item.id, item.group_id, item.note, groupMap.get(item.group_id || '')].map((value) => String(value || '').toLowerCase()).join(' ');
        if (!haystack.includes(keyword)) return false;
      }
      if (statusFilter) {
        const enabledValue = statusFilter === 'enabled';
        if ((item.enabled !== false) !== enabledValue) return false;
      }
      return true;
    });
  }, [groupMap, items, search, statusFilter]);

  const totalPages = Math.max(1, Math.ceil(filteredItems.length / pageSize));
  const pagedItems = useMemo(() => {
    const start = (page - 1) * pageSize;
    return filteredItems.slice(start, start + pageSize);
  }, [filteredItems, page, pageSize]);
  const enabledCount = filteredItems.filter((item) => item.enabled !== false).length;
  const totalPrice = filteredItems.reduce((sum, item) => sum + Number(item.price_cents || 0), 0);
  const maxValidity = filteredItems.reduce((max, item) => Math.max(max, Number(item.validity_days || 0)), 0);
  const groupedCount = filteredItems.filter((item) => item.group_id).length;

  useEffect(() => {
    writeStorageJSON(STORAGE_KEY, {
      search,
      statusFilter,
      pageSize,
      visibleColumns: Array.from(visibleColumns),
    });
  }, [pageSize, search, statusFilter, visibleColumns]);

  function toggleColumn(key: PlanColumnKey) {
    setVisibleColumns((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  function toggleEnabled(item: any) {
    saveMutation.mutate({
      ...item,
      enabled: item.enabled === false,
    });
  }

  return (
    <section className="grid-page">
      <div className="key-stat-grid">
        <div className="key-stat"><div className="key-stat-icon blue"><Ticket size={18} /></div><div><span>计划数</span><strong>{formatNumber(filteredItems.length)}</strong><small>当前筛选范围</small></div></div>
        <div className="key-stat"><div className="key-stat-icon green"><ShieldCheck size={18} /></div><div><span>启用计划</span><strong>{formatNumber(enabledCount)}</strong><small>{filteredItems.length ? `${Math.round((enabledCount / filteredItems.length) * 100)}%` : '0%'}</small></div></div>
        <div className="key-stat"><div className="key-stat-icon amber"><Wallet size={18} /></div><div><span>总价格</span><strong>{formatNumber(totalPrice)} CNY</strong><small>筛选计划价格合计</small></div></div>
        <div className="key-stat"><div className="key-stat-icon slate"><CalendarRange size={18} /></div><div><span>最长有效期</span><strong>{formatNumber(maxValidity)} 天</strong><small>绑定分组 {formatNumber(groupedCount)}</small></div></div>
      </div>
      <TablePageLayout
        filters={
          <FilterToolbar
            right={
              <ToolbarButtonRow>
                <ActionButton onClick={() => plansQuery.refetch()}><RefreshCw size={15} />刷新</ActionButton>
                <ColumnMenu
                  label="列设置"
                  items={[
                    { key: 'group', label: '分组', checked: visibleColumns.has('group'), onToggle: () => toggleColumn('group') },
                    { key: 'price', label: '价格', checked: visibleColumns.has('price'), onToggle: () => toggleColumn('price') },
                    { key: 'validity', label: '有效期', checked: visibleColumns.has('validity'), onToggle: () => toggleColumn('validity') },
                    { key: 'daily', label: '日限额', checked: visibleColumns.has('daily'), onToggle: () => toggleColumn('daily') },
                    { key: 'weekly', label: '周限额', checked: visibleColumns.has('weekly'), onToggle: () => toggleColumn('weekly') },
                    { key: 'monthly', label: '月限额', checked: visibleColumns.has('monthly'), onToggle: () => toggleColumn('monthly') },
                    { key: 'status', label: '状态', checked: visibleColumns.has('status'), onToggle: () => toggleColumn('status') },
                  ]}
                />
                <Button tone="primary" onClick={() => setDraft({ name: '', group_id: '', price_cents: 0, validity_days: 30, daily_limit: 0, weekly_limit: 0, monthly_limit: 0, enabled: true, note: '' })}>
                  <Plus size={15} />新增计划
                </Button>
              </ToolbarButtonRow>
            }
          >
            <SearchField value={search} placeholder="搜索计划 / 分组 / 备注" onChange={(value) => { setSearch(value); setPage(1); }} />
            <Select value={statusFilter} onChange={(event) => { setStatusFilter(event.target.value); setPage(1); }}>
              <option value="">全部状态</option>
              <option value="enabled">启用</option>
              <option value="disabled">停用</option>
            </Select>
          </FilterToolbar>
        }
        table={
          <div className="table-wrap table-scroll">
            <table>
              <thead>
                <tr>
                  <th>计划</th>
                  {visibleColumns.has('group') ? <th>分组</th> : null}
                  {visibleColumns.has('price') ? <th>价格</th> : null}
                  {visibleColumns.has('validity') ? <th>有效期</th> : null}
                  {visibleColumns.has('daily') ? <th>日限额</th> : null}
                  {visibleColumns.has('weekly') ? <th>周限额</th> : null}
                  {visibleColumns.has('monthly') ? <th>月限额</th> : null}
                  {visibleColumns.has('status') ? <th>状态</th> : null}
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {pagedItems.length ? pagedItems.map((item) => (
                  <tr key={item.id}>
                    <td>
                      <div className="sub2-cell-stack">
                        <strong>{item.name}</strong>
                        <small>{item.note || item.id}</small>
                      </div>
                    </td>
                    {visibleColumns.has('group') ? (
                      <td>
                        <div className="sub2-cell-stack sub2-cell-stack-tight">
                          <strong>{maskEmpty(groupMap.get(item.group_id || '') || item.group_id)}</strong>
                          <small>{item.group_id || '未绑定分组'}</small>
                        </div>
                      </td>
                    ) : null}
                    {visibleColumns.has('price') ? <td><strong className="sub2-number-cell">{formatNumber(item.price_cents || 0)} CNY</strong></td> : null}
                    {visibleColumns.has('validity') ? <td><strong className="sub2-number-cell">{formatNumber(item.validity_days || 0)} 天</strong></td> : null}
                    {visibleColumns.has('daily') ? <td><strong className="sub2-number-cell">{formatNumber(item.daily_limit || 0)}</strong></td> : null}
                    {visibleColumns.has('weekly') ? <td><strong className="sub2-number-cell">{formatNumber(item.weekly_limit || 0)}</strong></td> : null}
                    {visibleColumns.has('monthly') ? <td><strong className="sub2-number-cell">{formatNumber(item.monthly_limit || 0)}</strong></td> : null}
                    {visibleColumns.has('status') ? <td><span className={cn('badge', item.enabled === false ? 'badge-warn' : 'badge-ok')}>{item.enabled === false ? '停用' : '启用'}</span></td> : null}
                    <td>
                      <div className="sub2-action-stack">
                        <button type="button" className="sub2-icon-action" onClick={() => setDraft({ ...item })}>
                          <Pencil size={14} />
                          <span>编辑</span>
                        </button>
                        <button type="button" className={cn('sub2-icon-action', item.enabled === false ? '' : 'warn')} onClick={() => toggleEnabled(item)}>
                          {item.enabled === false ? <ShieldCheck size={14} /> : <Ban size={14} />}
                          <span>{item.enabled === false ? '启用' : '停用'}</span>
                        </button>
                      </div>
                    </td>
                  </tr>
                )) : (
                  <tr>
                    <td colSpan={visibleColumns.size + 2}>
                      <EmptyState title="暂无订阅计划" description="当前没有可展示的订阅计划。" action={<Button tone="primary" onClick={() => setDraft({ name: '', group_id: '', price_cents: 0, validity_days: 30, daily_limit: 0, weekly_limit: 0, monthly_limit: 0, enabled: true, note: '' })}>新增计划</Button>} />
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
          title="订阅计划"
          onClose={() => setDraft(null)}
          footer={
            <>
              <Button onClick={() => setDraft(null)}>取消</Button>
              <Button tone="primary" disabled={saveMutation.isPending || !draft.name?.trim()} onClick={() => saveMutation.mutate(draft)}>保存</Button>
            </>
          }
        >
          <div className="form-grid modal-grid">
            <Field label="计划名称"><TextInput value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} /></Field>
            <Field label="关联分组">
              <Select value={draft.group_id} onChange={(e) => setDraft({ ...draft, group_id: e.target.value })}>
                <option value="">不指定</option>
                {groups.map((group) => <option key={group.id} value={group.id}>{group.name}</option>)}
              </Select>
            </Field>
            <Field label="价格(分)"><TextInput type="number" value={String(draft.price_cents)} onChange={(e) => setDraft({ ...draft, price_cents: Number(e.target.value || 0) })} /></Field>
            <Field label="有效期天数"><TextInput type="number" value={String(draft.validity_days)} onChange={(e) => setDraft({ ...draft, validity_days: Number(e.target.value || 0) })} /></Field>
            <Field label="日限额"><TextInput type="number" value={String(draft.daily_limit)} onChange={(e) => setDraft({ ...draft, daily_limit: Number(e.target.value || 0) })} /></Field>
            <Field label="周限额"><TextInput type="number" value={String(draft.weekly_limit)} onChange={(e) => setDraft({ ...draft, weekly_limit: Number(e.target.value || 0) })} /></Field>
            <Field label="月限额"><TextInput type="number" value={String(draft.monthly_limit)} onChange={(e) => setDraft({ ...draft, monthly_limit: Number(e.target.value || 0) })} /></Field>
            <Field label="启用状态">
              <Select value={draft.enabled === false ? '0' : '1'} onChange={(e) => setDraft({ ...draft, enabled: e.target.value === '1' })}>
                <option value="1">启用</option>
                <option value="0">停用</option>
              </Select>
            </Field>
            <Field label="备注" full><TextArea rows={4} value={draft.note || ''} onChange={(e) => setDraft({ ...draft, note: e.target.value })} /></Field>
          </div>
        </Modal>
      ) : null}
    </section>
  );
}
