import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Ban, Eye, Pencil, Plus, RefreshCw, ShieldCheck } from 'lucide-react';
import { fetchAdminGroups, fetchAdminSubscriptionPlans, saveAdminSubscriptionPlan } from '../api';
import { Button, Field, Modal, ModalActions, Select, TextArea, TextInput } from '../components';
import { ActionButton, ColumnMenu, FilterToolbar, ListEmptyRow, Pager, RowAction, RowActions, SearchField, TablePageLayout, ToolbarButtonRow, ToolsMenu } from '../components/admin';
import { buildPageIntro } from '../navigation';
import { queryClient } from '../state/queryClient';
import { cn, formatNumber, maskEmpty, readStorageJSON, writeStorageJSON } from '../utils';

type PlanColumnKey = 'group' | 'price' | 'validity' | 'daily' | 'weekly' | 'monthly' | 'status';

const DEFAULT_VISIBLE_COLUMNS: PlanColumnKey[] = ['group', 'price', 'validity', 'daily', 'weekly', 'monthly', 'status'];
const STORAGE_KEY = 'admin-subscription-plans-view-state';

export function AdminSubscriptionPlansPage() {
  const plansQuery = useQuery({ queryKey: ['admin-subscription-plans'], queryFn: fetchAdminSubscriptionPlans, refetchInterval: 10000 });
  const groupsQuery = useQuery({ queryKey: ['admin-groups'], queryFn: fetchAdminGroups, refetchInterval: 10000 });
  const [draft, setDraft] = useState<any | null>(null);
  const [inspectPlan, setInspectPlan] = useState<any | null>(null);
  const [toggleTarget, setToggleTarget] = useState<any | null>(null);
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
  const groupOptions = useMemo(() => groups.map((group) => ({ value: group.id, label: group.name })), [groups]);

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
      if (groupFilter && item.group_id !== groupFilter) return false;
      return true;
    });
  }, [groupFilter, groupMap, items, search, statusFilter]);

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
      groupFilter,
      pageSize,
      visibleColumns: Array.from(visibleColumns),
    });
  }, [groupFilter, pageSize, search, statusFilter, visibleColumns]);

  function toggleColumn(key: PlanColumnKey) {
    setVisibleColumns((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  function toggleEnabled(item: any) {
    setToggleTarget(item);
  }

  return (
    <section className="grid-page">
      {buildPageIntro('/admin/orders/plans')}
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
                <ToolsMenu>
                  <button type="button" onClick={() => { setSearch(''); setStatusFilter(''); setGroupFilter(''); setPage(1); }}>
                    <span>清空筛选</span>
                  </button>
                  <button type="button" onClick={() => { setStatusFilter('enabled'); setPage(1); }}>
                    <span>仅看启用计划</span>
                  </button>
                  <button type="button" onClick={() => { setPageSize(50); setPage(1); }}>
                    <span>切换 50 / 页</span>
                  </button>
                </ToolsMenu>
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
            <Select value={groupFilter} onChange={(event) => { setGroupFilter(event.target.value); setPage(1); }}>
              <option value="">全部分组</option>
              {groupOptions.map((group) => <option key={group.value} value={group.value}>{group.label}</option>)}
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
                          <strong>{maskEmpty(item.group_name || groupMap.get(item.group_id || '') || item.group_id)}</strong>
                          <small>{item.group_id || '未绑定分组'} · ×{Number(item.rate_multiplier || 1)}</small>
                        </div>
                      </td>
                    ) : null}
                    {visibleColumns.has('price') ? (
                      <td>
                        <div className="sub2-cell-stack sub2-cell-stack-tight">
                          <strong className="sub2-number-cell">{formatNumber(item.final_price_cents || 0)}</strong>
                          <small>基础 {formatNumber(item.price_cents || 0)}</small>
                        </div>
                      </td>
                    ) : null}
                    {visibleColumns.has('validity') ? <td><strong className="sub2-number-cell">{formatNumber(item.validity_days || 0)} 天</strong></td> : null}
                    {visibleColumns.has('daily') ? <td><strong className="sub2-number-cell">{formatNumber(item.daily_limit || 0)}</strong></td> : null}
                    {visibleColumns.has('weekly') ? <td><strong className="sub2-number-cell">{formatNumber(item.weekly_limit || 0)}</strong></td> : null}
                    {visibleColumns.has('monthly') ? <td><strong className="sub2-number-cell">{formatNumber(item.monthly_limit || 0)}</strong></td> : null}
                    {visibleColumns.has('status') ? <td><span className={cn('badge', item.enabled === false ? 'badge-warn' : 'badge-ok')}>{item.enabled === false ? '停用' : '启用'}</span></td> : null}
                    <td>
                      <RowActions>
                        <RowAction icon={Eye} label="详情" onClick={() => setInspectPlan(item)} />
                        <RowAction icon={Pencil} label="编辑" onClick={() => setDraft({ ...item })} />
                        <RowAction icon={item.enabled === false ? ShieldCheck : Ban} label={item.enabled === false ? '启用' : '停用'} tone={item.enabled === false ? 'default' : 'warn'} onClick={() => toggleEnabled(item)} />
                      </RowActions>
                    </td>
                  </tr>
                )) : (
                  <ListEmptyRow
                    colSpan={visibleColumns.size + 2}
                    title="暂无订阅计划"
                    action={<Button tone="primary" onClick={() => setDraft({ name: '', group_id: '', price_cents: 0, validity_days: 30, daily_limit: 0, weekly_limit: 0, monthly_limit: 0, enabled: true, note: '' })}>新增计划</Button>}
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
          title="订阅计划"
          onClose={() => setDraft(null)}
          footer={
            <ModalActions>
              <Button onClick={() => setDraft(null)}>取消</Button>
              <Button tone="primary" disabled={saveMutation.isPending || !draft.name?.trim()} onClick={() => saveMutation.mutate(draft)}>保存</Button>
            </ModalActions>
          }
        >
          <div className="admin-dialog">
            <div className="admin-dialog-intro">
              <strong>{draft.id ? '编辑订阅计划' : '新增订阅计划'}</strong>
            </div>
            <div className="admin-dialog-summary">
              <div className="admin-dialog-summary-card">
                <span>计划数</span>
                <strong>{formatNumber(filteredItems.length)}</strong>
                <small>计划</small>
              </div>
              <div className="admin-dialog-summary-card">
                <span>最长有效期</span>
                <strong>{formatNumber(maxValidity)} 天</strong>
                <small>绑定分组 {formatNumber(groupedCount)}</small>
              </div>
              <div className="admin-dialog-summary-card">
                <span>当前价格</span>
                <strong>{formatNumber(draft.price_cents || 0)}</strong>
                <small>{draft.name?.trim() || '待填写计划名'}</small>
              </div>
            </div>
            <div className="admin-dialog-section">
              <div className="admin-dialog-section-head">
                <strong>基础信息</strong>
                <span>计划名、分组和状态先定下来</span>
              </div>
              <div className="admin-dialog-grid modal-grid">
                <Field label="计划名称"><TextInput value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} /></Field>
                <Field label="关联分组">
                  <Select value={draft.group_id} onChange={(e) => setDraft({ ...draft, group_id: e.target.value })}>
                    <option value="">不指定</option>
                    {groups.map((group) => <option key={group.id} value={group.id}>{group.name}</option>)}
                  </Select>
                </Field>
                <Field label="启用状态">
                  <Select value={draft.enabled === false ? '0' : '1'} onChange={(e) => setDraft({ ...draft, enabled: e.target.value === '1' })}>
                    <option value="1">启用</option>
                    <option value="0">停用</option>
                  </Select>
                </Field>
              </div>
            </div>
            <div className="admin-dialog-section">
              <div className="admin-dialog-section-head">
                <strong>价格与额度</strong>
                <span>这些值直接参与下游订阅校验</span>
              </div>
              <div className="admin-dialog-grid modal-grid">
                <Field label="价格(分)"><TextInput type="number" value={String(draft.price_cents)} onChange={(e) => setDraft({ ...draft, price_cents: Number(e.target.value || 0) })} /></Field>
                <Field label="有效期天数"><TextInput type="number" value={String(draft.validity_days)} onChange={(e) => setDraft({ ...draft, validity_days: Number(e.target.value || 0) })} /></Field>
                <Field label="日限额"><TextInput type="number" value={String(draft.daily_limit)} onChange={(e) => setDraft({ ...draft, daily_limit: Number(e.target.value || 0) })} /></Field>
                <Field label="周限额"><TextInput type="number" value={String(draft.weekly_limit)} onChange={(e) => setDraft({ ...draft, weekly_limit: Number(e.target.value || 0) })} /></Field>
                <Field label="月限额"><TextInput type="number" value={String(draft.monthly_limit)} onChange={(e) => setDraft({ ...draft, monthly_limit: Number(e.target.value || 0) })} /></Field>
              </div>
            </div>
            <Field label="备注" full><TextArea rows={4} value={draft.note || ''} onChange={(e) => setDraft({ ...draft, note: e.target.value })} /></Field>
          </div>
        </Modal>
      ) : null}

      {inspectPlan ? (
        <Modal
          title="计划详情"
          size="md"
          onClose={() => setInspectPlan(null)}
          footer={<ModalActions><Button onClick={() => setInspectPlan(null)}>关闭</Button></ModalActions>}
        >
          <div className="admin-dialog">
            <div className="admin-dialog-intro">
              <strong>{inspectPlan.name}</strong>
              <span>查看计划价格、有效期、额度和分组归属，便于核对订阅分配前置条件。</span>
            </div>
            <div className="admin-dialog-summary">
              <div className="admin-dialog-summary-card">
                <span>分组</span>
                <strong>{maskEmpty(inspectPlan.group_name || groupMap.get(inspectPlan.group_id || '') || inspectPlan.group_id)}</strong>
                <small>{inspectPlan.group_id || '未绑定分组'}</small>
              </div>
              <div className="admin-dialog-summary-card">
                <span>价格</span>
                <strong>{formatNumber(inspectPlan.final_price_cents || inspectPlan.price_cents || 0)}</strong>
                <small>基础 {formatNumber(inspectPlan.price_cents || 0)}</small>
              </div>
              <div className="admin-dialog-summary-card">
                <span>状态</span>
                <strong>{inspectPlan.enabled === false ? '停用' : '启用'}</strong>
                <small>{formatNumber(inspectPlan.validity_days || 0)} 天</small>
              </div>
            </div>
            <div className="admin-dialog-section">
              <div className="admin-dialog-section-head">
                <strong>额度信息</strong>
                <span>订阅分配时会直接使用这些额度上限</span>
              </div>
              <div className="admin-dialog-grid">
                <Field label="日限额"><TextInput readOnly value={String(inspectPlan.daily_limit || 0)} /></Field>
                <Field label="周限额"><TextInput readOnly value={String(inspectPlan.weekly_limit || 0)} /></Field>
                <Field label="月限额"><TextInput readOnly value={String(inspectPlan.monthly_limit || 0)} /></Field>
                <Field label="备注"><TextInput readOnly value={inspectPlan.note || '-'} /></Field>
              </div>
            </div>
          </div>
        </Modal>
      ) : null}

      {toggleTarget ? (
        <Modal
          title={toggleTarget.enabled === false ? '确认启用计划' : '确认停用计划'}
          size="md"
          onClose={() => setToggleTarget(null)}
          footer={
            <ModalActions>
              <Button onClick={() => setToggleTarget(null)}>取消</Button>
              <Button
                tone={toggleTarget.enabled === false ? 'primary' : 'danger'}
                disabled={saveMutation.isPending}
                onClick={() => saveMutation.mutate({ ...toggleTarget, enabled: toggleTarget.enabled === false })}
              >
                确认
              </Button>
            </ModalActions>
          }
        >
          <div className="admin-dialog">
            <div className="admin-dialog-intro">
              <strong>{toggleTarget.name}</strong>
            </div>
          </div>
        </Modal>
      ) : null}
    </section>
  );
}
