import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Ban, Coins, Download, Pencil, Plus, RefreshCw, ShieldCheck } from 'lucide-react';
import { fetchAdminAccounts, fetchAdminGroups, saveAdminAccount, setAdminAccountBalance, setAdminAccountConcurrency } from '../api';
import { Button, Field, Modal, ModalActions, Select, TextArea, TextInput } from '../components';
import { ActionButton, ColumnMenu, FilterToolbar, ListEmptyRow, Pager, RowAction, RowActions, SearchField, TablePageLayout, ToolbarButtonRow, ToolsMenu } from '../components/admin';
import { queryClient } from '../state/queryClient';
import type { AdminAccount } from '../types';
import { cn, formatByteCount, formatCost, formatNumber, formatTokenCount, maskEmpty, readStorageJSON, writeStorageJSON } from '../utils';

type AccountDraft = {
  id?: string;
  name: string;
  external_key: string;
  source_type: string;
  role: string;
  status: string;
  balance_cents: number;
  concurrency_limit: number;
  allowed_group_ids: string[];
  enabled: boolean;
  note: string;
  group_ids: string[];
};

type AccountColumnKey =
  | 'name'
  | 'external_key'
  | 'role'
  | 'subscription'
  | 'quota'
  | 'group'
  | 'requests'
  | 'tokens'
  | 'input'
  | 'output'
  | 'last_seen'
  | 'status';

type AccountSourceFilter = '' | 'managed' | 'env' | 'anonymous';
type AccountSortKey = 'name_asc' | 'requests_desc' | 'tokens_desc' | 'last_seen_desc';

const EMPTY_DRAFT: AccountDraft = {
  name: '',
  external_key: '',
  source_type: 'managed',
  role: 'user',
  status: 'active',
  balance_cents: 0,
  concurrency_limit: 0,
  allowed_group_ids: [],
  enabled: true,
  note: '',
  group_ids: [],
};

const PAGE_SIZE = 20;
const DEFAULT_VISIBLE_COLUMNS: AccountColumnKey[] = ['external_key', 'subscription', 'group', 'requests', 'tokens', 'last_seen', 'status'];
const STORAGE_KEY = 'admin-accounts-view-state';
const ACCOUNT_SORT_OPTIONS: Array<{ value: AccountSortKey; label: string }> = [
  { value: 'name_asc', label: '名称排序' },
  { value: 'requests_desc', label: '请求数从高到低' },
  { value: 'tokens_desc', label: 'Token 从高到低' },
  { value: 'last_seen_desc', label: '最近请求优先' },
];
const ACCOUNT_SORT_SET = new Set<AccountSortKey>(ACCOUNT_SORT_OPTIONS.map((item) => item.value));

export function AdminAccountsPage() {
  const accountsQuery = useQuery({ queryKey: ['admin-accounts'], queryFn: fetchAdminAccounts, refetchInterval: 10000 });
  const groupsQuery = useQuery({ queryKey: ['admin-groups'], queryFn: fetchAdminGroups, refetchInterval: 10000 });
  const [draft, setDraft] = useState<AccountDraft | null>(null);
  const [quotaDraft, setQuotaDraft] = useState<{ id: string; name: string; balance_cents: number; concurrency_limit: number } | null>(null);
  const savedState = readStorageJSON(STORAGE_KEY, {
    search: '',
    statusFilter: '',
    groupFilter: '',
    sourceFilter: '',
    sortBy: 'name_asc',
    pageSize: PAGE_SIZE,
    visibleColumns: DEFAULT_VISIBLE_COLUMNS,
  });
  const [search, setSearch] = useState(savedState.search);
  const [statusFilter, setStatusFilter] = useState(savedState.statusFilter);
  const [groupFilter, setGroupFilter] = useState(savedState.groupFilter);
  const [sourceFilter, setSourceFilter] = useState<AccountSourceFilter>(isAccountSourceFilter(savedState.sourceFilter) ? savedState.sourceFilter : '');
  const [sortBy, setSortBy] = useState<AccountSortKey>(isAccountSortKey(savedState.sortBy) ? savedState.sortBy : 'name_asc');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(savedState.pageSize || PAGE_SIZE);
  const [visibleColumns, setVisibleColumns] = useState<Set<AccountColumnKey>>(new Set(savedState.visibleColumns || DEFAULT_VISIBLE_COLUMNS));

  const saveMutation = useMutation({
    mutationFn: saveAdminAccount,
    onSuccess: async () => {
      setDraft(null);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['admin-accounts'] }),
        queryClient.invalidateQueries({ queryKey: ['admin-groups'] }),
        queryClient.invalidateQueries({ queryKey: ['admin-overview'] }),
      ]);
    },
  });
  const quotaMutation = useMutation({
    mutationFn: async (payload: { id: string; balance_cents: number; concurrency_limit: number }) => {
      await Promise.all([
        setAdminAccountBalance(payload.id, payload.balance_cents),
        setAdminAccountConcurrency(payload.id, payload.concurrency_limit),
      ]);
    },
    onSuccess: async () => {
      setQuotaDraft(null);
      await queryClient.invalidateQueries({ queryKey: ['admin-accounts'] });
    },
  });

  const items = accountsQuery.data?.items || [];
  const groups = groupsQuery.data?.items || [];

  const filteredItems = useMemo(() => {
    const keyword = search.trim().toLowerCase();
    const scopedItems = items.filter((item) => {
      if (keyword) {
        const haystack = [item.name, item.preview, item.id, item.external_key, item.group_name].map((value) => String(value || '').toLowerCase()).join(' ');
        if (!haystack.includes(keyword)) return false;
      }
      if (statusFilter) {
        const enabledValue = statusFilter === 'enabled';
        if ((item.enabled !== false) !== enabledValue) return false;
      }
      if (groupFilter && item.group_id !== groupFilter) return false;
      if (sourceFilter && (item.source_type || 'managed') !== sourceFilter) return false;
      return true;
    });
    return [...scopedItems].sort((left, right) => compareAccounts(left, right, sortBy));
  }, [groupFilter, items, search, sortBy, sourceFilter, statusFilter]);

  const pagedItems = useMemo(() => {
    const start = (page - 1) * pageSize;
    return filteredItems.slice(start, start + pageSize);
  }, [filteredItems, page, pageSize]);

  const groupOptions = useMemo(() => groups.map((item) => ({ value: item.id, label: item.name })), [groups]);
  const totalPages = Math.max(1, Math.ceil(filteredItems.length / pageSize));
  const enabledCount = items.filter((item) => item.enabled !== false).length;
  const requestTotal = items.reduce((sum, item) => sum + Number(item.request_count || 0), 0);
  const tokenTotal = items.reduce((sum, item) => sum + Number(item.total_tokens || 0), 0);
  const activeSubscriptionCount = items.filter((item) => item.subscription_active).length;
  const latestSeenAt = filteredItems.reduce<number | null>((latest, item) => {
    const current = parseMaybeDate(item.last_seen_at);
    if (current === null) return latest;
    if (latest === null || current > latest) return current;
    return latest;
  }, null);
  const disabledCount = items.length - enabledCount;
  const uncoveredCount = Math.max(0, items.length - activeSubscriptionCount);

  useEffect(() => {
    writeStorageJSON(STORAGE_KEY, {
      search,
      statusFilter,
      groupFilter,
      sourceFilter,
      sortBy,
      pageSize,
      visibleColumns: Array.from(visibleColumns),
    });
  }, [groupFilter, pageSize, search, sortBy, sourceFilter, statusFilter, visibleColumns]);

  function openCreate() {
    setDraft({ ...EMPTY_DRAFT });
  }

  function openEdit(item: AdminAccount) {
    setDraft({
      id: item.id,
      name: item.name || '',
      external_key: item.external_key || item.id || '',
      source_type: item.source_type || 'managed',
      role: item.role || 'user',
      status: item.status || 'active',
      balance_cents: Number(item.balance_cents || 0),
      concurrency_limit: Number(item.concurrency_limit || 0),
      allowed_group_ids: Array.isArray(item.allowed_group_ids) ? item.allowed_group_ids : [],
      enabled: item.enabled !== false,
      note: item.note || '',
      group_ids: item.group_id ? [item.group_id] : [],
    });
  }

  function openQuota(item: AdminAccount) {
    setQuotaDraft({
      id: item.id,
      name: item.name || item.id,
      balance_cents: Number(item.balance_cents || 0),
      concurrency_limit: Number(item.concurrency_limit || 0),
    });
  }

  function toggleEnabled(item: AdminAccount) {
    saveMutation.mutate({
      id: item.id,
      name: item.name || '',
      external_key: item.external_key || item.id || '',
      source_type: item.source_type || 'managed',
      role: item.role || 'user',
      status: item.status || 'active',
      balance_cents: Number(item.balance_cents || 0),
      concurrency_limit: Number(item.concurrency_limit || 0),
      allowed_group_ids: Array.isArray(item.allowed_group_ids) ? item.allowed_group_ids : [],
      enabled: item.enabled === false,
      note: item.note || '',
      group_ids: item.group_id ? [item.group_id] : [],
    });
  }

  function toggleColumn(key: AccountColumnKey) {
    setVisibleColumns((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  function resetPage(nextPageSize?: number) {
    setPage(1);
    if (typeof nextPageSize === 'number') setPageSize(nextPageSize);
  }

  function exportCurrentView() {
    const lines = [
      ['账户', '来源键', '来源类型', '额度', '分组', '请求数', '总Token', '请求字节', '响应字节', '最后请求', '状态'].join('\t'),
      ...filteredItems.map((item) => [
        item.name || '-',
        item.external_key || item.id || '-',
        item.source_type || 'managed',
        item.role || 'user',
        `${Number(item.balance_cents || 0)} / ${Number(item.concurrency_limit || 0)}`,
        item.group_name || item.group_id || '未分组',
        String(item.request_count || 0),
        String(item.total_tokens || 0),
        String(item.input_bytes || 0),
        String(item.output_bytes || 0),
        String(item.last_seen_at || '-'),
        item.enabled === false ? '停用' : '启用',
      ].join('\t')),
    ].join('\n');
    const blob = new Blob([lines], { type: 'text/tab-separated-values;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'admin-accounts.tsv';
    link.click();
    URL.revokeObjectURL(url);
  }

  return (
    <section className="grid-page">
      <div className="sub2-page-head">
        <div className="sub2-page-title">
          <strong>账户管理</strong>
          <span>按业务账户管理订阅、分组和用量，保持和 SUB2 一致的运营表格视图。</span>
        </div>
        <div className="sub2-inline-summary">
          <div className="sub2-inline-summary-item"><span>账户总数</span><strong>{formatNumber(items.length)}</strong><small>当前业务账户</small></div>
          <div className="sub2-inline-summary-item"><span>启用状态</span><strong>{formatNumber(enabledCount)}</strong><small>停用 {formatNumber(disabledCount)}</small></div>
          <div className="sub2-inline-summary-item"><span>有效订阅</span><strong>{formatNumber(activeSubscriptionCount)}</strong><small>未覆盖 {formatNumber(uncoveredCount)}</small></div>
          <div className="sub2-inline-summary-item"><span>累计请求</span><strong>{formatNumber(requestTotal)}</strong><small>{formatTokenCount(tokenTotal)}</small></div>
          <div className="sub2-inline-summary-item"><span>最近请求</span><strong>{latestSeenAt ? formatDateTime(latestSeenAt) : '-'}</strong><small>{sourceFilter ? `来源：${formatAccountSource(sourceFilter)}` : (ACCOUNT_SORT_OPTIONS.find((item) => item.value === sortBy)?.label || '名称排序')}</small></div>
        </div>
      </div>
      <TablePageLayout
        filters={
          <FilterToolbar
            right={
              <ToolbarButtonRow>
                <ActionButton onClick={() => accountsQuery.refetch()}><RefreshCw size={15} />刷新</ActionButton>
                <ColumnMenu
                  label="列设置"
                  items={[
                    { key: 'external_key', label: '来源键', checked: visibleColumns.has('external_key'), onToggle: () => toggleColumn('external_key') },
                    { key: 'role', label: '角色 / 状态', checked: visibleColumns.has('role'), onToggle: () => toggleColumn('role') },
                    { key: 'subscription', label: '订阅', checked: visibleColumns.has('subscription'), onToggle: () => toggleColumn('subscription') },
                    { key: 'quota', label: '余额 / 并发', checked: visibleColumns.has('quota'), onToggle: () => toggleColumn('quota') },
                    { key: 'group', label: '分组', checked: visibleColumns.has('group'), onToggle: () => toggleColumn('group') },
                    { key: 'requests', label: '请求数', checked: visibleColumns.has('requests'), onToggle: () => toggleColumn('requests') },
                    { key: 'tokens', label: '总 Token', checked: visibleColumns.has('tokens'), onToggle: () => toggleColumn('tokens') },
                    { key: 'input', label: '请求字节', checked: visibleColumns.has('input'), onToggle: () => toggleColumn('input') },
                    { key: 'output', label: '响应字节', checked: visibleColumns.has('output'), onToggle: () => toggleColumn('output') },
                    { key: 'last_seen', label: '最后请求', checked: visibleColumns.has('last_seen'), onToggle: () => toggleColumn('last_seen') },
                    { key: 'status', label: '状态', checked: visibleColumns.has('status'), onToggle: () => toggleColumn('status') },
                  ]}
                />
                <ToolsMenu>
                    <button type="button" onClick={() => { setSearch(''); setStatusFilter(''); setGroupFilter(''); setSourceFilter(''); setSortBy('name_asc'); resetPage(); }}>
                      <span>清空筛选</span>
                    </button>
                    <button type="button" onClick={() => { setSourceFilter('managed'); resetPage(); }}>
                      <span>仅看托管 Key</span>
                    </button>
                    <button type="button" onClick={() => { setSourceFilter('env'); resetPage(); }}>
                      <span>仅看环境 Key</span>
                    </button>
                    <button type="button" onClick={() => { setSourceFilter('anonymous'); resetPage(); }}>
                      <span>仅看匿名来源</span>
                    </button>
                    <button type="button" onClick={() => { setSortBy('name_asc'); resetPage(); }}>
                      <span>按名称排序</span>
                    </button>
                    <button type="button" onClick={() => { setSortBy('requests_desc'); resetPage(); }}>
                      <span>按请求数排序</span>
                    </button>
                    <button type="button" onClick={() => { setSortBy('tokens_desc'); resetPage(); }}>
                      <span>按 Token 排序</span>
                    </button>
                    <button type="button" onClick={() => { setSortBy('last_seen_desc'); resetPage(); }}>
                      <span>按最近请求排序</span>
                    </button>
                    <button type="button" onClick={() => { resetPage(50); }}>
                      <span>切换 50 / 页</span>
                    </button>
                    <button type="button" onClick={() => { exportCurrentView(); }}>
                      <span>导出当前视图</span>
                      <Download size={14} />
                    </button>
                </ToolsMenu>
                <Button tone="primary" onClick={openCreate}><Plus size={15} />新增账户</Button>
              </ToolbarButtonRow>
            }
          >
            <SearchField value={search} placeholder="搜索账户 / 来源键 / 分组" onChange={(value) => { setSearch(value); resetPage(); }} />
            <Select value={statusFilter} onChange={(event) => { setStatusFilter(event.target.value); resetPage(); }}>
              <option value="">全部状态</option>
              <option value="enabled">启用</option>
              <option value="disabled">停用</option>
            </Select>
            <Select value={groupFilter} onChange={(event) => { setGroupFilter(event.target.value); resetPage(); }}>
              <option value="">全部分组</option>
              {groupOptions.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
            </Select>
          </FilterToolbar>
        }
        table={
          <div className="table-wrap table-scroll">
            <table>
              <thead>
                <tr>
                  <th>账户</th>
                  {visibleColumns.has('external_key') ? <th>来源键</th> : null}
                  {visibleColumns.has('role') ? <th>角色 / 状态</th> : null}
                  {visibleColumns.has('subscription') ? <th>订阅</th> : null}
                  {visibleColumns.has('quota') ? <th>余额 / 并发</th> : null}
                  {visibleColumns.has('group') ? <th>分组</th> : null}
                  {visibleColumns.has('requests') ? <th>请求数</th> : null}
                  {visibleColumns.has('tokens') ? <th>总 Token</th> : null}
                  {visibleColumns.has('input') ? <th>请求字节</th> : null}
                  {visibleColumns.has('output') ? <th>响应字节</th> : null}
                  {visibleColumns.has('last_seen') ? <th>最后请求</th> : null}
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
                        <small>{item.preview || item.id}</small>
                      </div>
                    </td>
                    {visibleColumns.has('external_key') ? (
                      <td>
                        <div className="sub2-cell-stack sub2-cell-stack-tight">
                          <strong>{maskEmpty(item.external_key)}</strong>
                          <small>{item.source_type || 'managed'}</small>
                        </div>
                      </td>
                    ) : null}
                    {visibleColumns.has('role') ? (
                      <td>
                        <div className="sub2-cell-stack sub2-cell-stack-tight">
                          <strong>{item.role || 'user'}</strong>
                          <small>{item.status || 'active'}</small>
                        </div>
                      </td>
                    ) : null}
                    {visibleColumns.has('subscription') ? (
                      <td>
                        <div className="sub2-cell-stack sub2-cell-stack-tight">
                          <strong>{item.subscription_active ? (item.active_plan_name || '订阅有效') : '无可用订阅'}</strong>
                          <small>
                            {item.subscription_active
                              ? `${item.active_group_name || item.active_group_id || '未分组'} · ${item.active_subscription_status || 'active'}`
                              : (item.active_subscription_status || 'inactive')}
                          </small>
                        </div>
                      </td>
                    ) : null}
                    {visibleColumns.has('quota') ? (
                      <td>
                        <div className="sub2-cell-stack sub2-cell-stack-tight">
                          <strong>${formatCost(Number(item.balance_cents || 0) / 100, 2)}</strong>
                          <small>并发 {formatNumber(item.concurrency_limit || 0)}</small>
                        </div>
                      </td>
                    ) : null}
                    {visibleColumns.has('group') ? (
                      <td>
                        <div className="sub2-cell-stack sub2-cell-stack-tight">
                          <strong>{maskEmpty(item.group_name)}</strong>
                          <small>{item.group_id || '未分组'}</small>
                        </div>
                      </td>
                    ) : null}
                    {visibleColumns.has('requests') ? <td><strong className="sub2-number-cell">{formatNumber(item.request_count || 0)}</strong></td> : null}
                    {visibleColumns.has('tokens') ? <td><strong className="sub2-number-cell">{formatTokenCount(item.total_tokens || 0)}</strong></td> : null}
                    {visibleColumns.has('input') ? <td><strong className="sub2-number-cell">{formatByteCount(item.input_bytes || 0)}</strong></td> : null}
                    {visibleColumns.has('output') ? <td><strong className="sub2-number-cell">{formatByteCount(item.output_bytes || 0)}</strong></td> : null}
                    {visibleColumns.has('last_seen') ? (
                      <td>
                        <div className="sub2-cell-stack sub2-cell-stack-tight">
                          <strong>{maskEmpty(item.last_seen_at)}</strong>
                          <small>最近请求时间</small>
                        </div>
                      </td>
                    ) : null}
                    {visibleColumns.has('status') ? <td><span className={cn('badge', item.enabled === false ? 'badge-warn' : 'badge-ok')}>{item.enabled === false ? '停用' : '启用'}</span></td> : null}
                    <td>
                      <RowActions>
                        <RowAction icon={Pencil} label="编辑" onClick={() => openEdit(item)} />
                        <RowAction icon={Coins} label="调额" onClick={() => openQuota(item)} />
                        <RowAction icon={item.enabled === false ? ShieldCheck : Ban} label={item.enabled === false ? '启用' : '停用'} tone={item.enabled === false ? 'default' : 'warn'} onClick={() => toggleEnabled(item)} />
                      </RowActions>
                    </td>
                  </tr>
                )) : (
                  <ListEmptyRow
                    colSpan={visibleColumns.size + 2}
                    title="暂无账户归因数据"
                    description="当前没有可展示的业务账户记录。"
                    action={<Button tone="primary" onClick={openCreate}>新增账户</Button>}
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
              onPageSizeChange={(next) => resetPage(next)}
            />
          ) : null
        }
      />

      {draft ? (
        <Modal
          title={draft.id ? '编辑账户' : '新增账户'}
          onClose={() => setDraft(null)}
          footer={
            <ModalActions>
              <Button onClick={() => setDraft(null)}>取消</Button>
              <Button
                tone="primary"
                onClick={() => saveMutation.mutate(draft)}
                disabled={saveMutation.isPending || !draft.name.trim() || !draft.external_key.trim()}
              >
                保存
              </Button>
            </ModalActions>
          }
        >
          <div className="admin-dialog">
            <div className="admin-dialog-intro">
              <strong>{draft.id ? '编辑账户' : '新增账户'}</strong>
              <span>这里维护业务账户归属、来源键、订阅覆盖和额度边界，属于管理员日常操作主流程。</span>
            </div>
            <div className="admin-dialog-summary">
              <div className="admin-dialog-summary-card">
                <span>账户总数</span>
                <strong>{formatNumber(items.length)}</strong>
                <small>当前业务账户</small>
              </div>
              <div className="admin-dialog-summary-card">
                <span>有效订阅</span>
                <strong>{formatNumber(activeSubscriptionCount)}</strong>
                <small>未覆盖 {formatNumber(uncoveredCount)}</small>
              </div>
              <div className="admin-dialog-summary-card">
                <span>当前草稿</span>
                <strong>{draft.name?.trim() || '待填写账户名'}</strong>
                <small>{draft.external_key?.trim() || '待填写来源键'}</small>
              </div>
            </div>
            <div className="admin-dialog-section">
              <div className="admin-dialog-section-head">
                <strong>账户信息</strong>
                <span>用户名、来源、角色和状态</span>
              </div>
              <div className="admin-dialog-grid modal-grid">
                <Field label="账户名称"><TextInput value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} /></Field>
                <Field label="来源键"><TextInput value={draft.external_key} onChange={(e) => setDraft({ ...draft, external_key: e.target.value })} /></Field>
                <Field label="来源类型">
                  <Select value={draft.source_type} onChange={(e) => setDraft({ ...draft, source_type: e.target.value })}>
                    <option value="managed">托管 Key</option>
                    <option value="env">环境 Key</option>
                    <option value="anonymous">匿名</option>
                  </Select>
                </Field>
                <Field label="角色">
                  <Select value={draft.role} onChange={(e) => setDraft({ ...draft, role: e.target.value })}>
                    <option value="user">user</option>
                    <option value="admin">admin</option>
                  </Select>
                </Field>
                <Field label="状态">
                  <Select value={draft.status} onChange={(e) => setDraft({ ...draft, status: e.target.value })}>
                    <option value="active">active</option>
                    <option value="disabled">disabled</option>
                  </Select>
                </Field>
                <Field label="启用状态">
                  <Select value={draft.enabled ? '1' : '0'} onChange={(e) => setDraft({ ...draft, enabled: e.target.value === '1' })}>
                    <option value="1">启用</option>
                    <option value="0">停用</option>
                  </Select>
                </Field>
              </div>
            </div>
            <div className="admin-dialog-section">
              <div className="admin-dialog-section-head">
                <strong>归属与额度</strong>
                <span>分组、允许范围、余额和并发</span>
              </div>
              <div className="admin-dialog-grid modal-grid">
                <Field label="分组">
                  <Select value={draft.group_ids[0] || ''} onChange={(e) => setDraft({ ...draft, group_ids: e.target.value ? [e.target.value] : [] })}>
                    <option value="">未分配</option>
                    {groupOptions.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
                  </Select>
                </Field>
                <Field label="允许分组">
                  <Select value={draft.allowed_group_ids[0] || ''} onChange={(e) => setDraft({ ...draft, allowed_group_ids: e.target.value ? [e.target.value] : [] })}>
                    <option value="">未限制</option>
                    {groupOptions.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
                  </Select>
                </Field>
                <Field label="余额"><TextInput type="number" value={String(draft.balance_cents)} onChange={(e) => setDraft({ ...draft, balance_cents: Number(e.target.value || 0) })} /></Field>
                <Field label="并发"><TextInput type="number" value={String(draft.concurrency_limit)} onChange={(e) => setDraft({ ...draft, concurrency_limit: Number(e.target.value || 0) })} /></Field>
              </div>
            </div>
            <Field label="备注" full><TextArea rows={4} value={draft.note} onChange={(e) => setDraft({ ...draft, note: e.target.value })} /></Field>
          </div>
        </Modal>
      ) : null}

      {quotaDraft ? (
        <Modal
          title="调整额度"
          size="md"
          onClose={() => setQuotaDraft(null)}
          footer={
            <ModalActions>
              <Button onClick={() => setQuotaDraft(null)}>取消</Button>
              <Button
                tone="primary"
                disabled={quotaMutation.isPending}
                onClick={() => quotaMutation.mutate(quotaDraft)}
              >
                保存
              </Button>
            </ModalActions>
          }
        >
          <div className="admin-dialog">
            <div className="admin-dialog-intro">
              <strong>{quotaDraft.name}</strong>
              <span>快速调整余额和并发，不进入完整账户编辑流程。</span>
            </div>
            <div className="admin-dialog-summary">
              <div className="admin-dialog-summary-card">
                <span>当前余额</span>
                <strong>{formatCost(quotaDraft.balance_cents / 100, 2)}</strong>
                <small>以分存储</small>
              </div>
              <div className="admin-dialog-summary-card">
                <span>当前并发</span>
                <strong>{formatNumber(quotaDraft.concurrency_limit)}</strong>
                <small>即时生效</small>
              </div>
              <div className="admin-dialog-summary-card">
                <span>作用范围</span>
                <strong>账户级</strong>
                <small>只改当前账户</small>
              </div>
            </div>
            <div className="admin-dialog-section">
              <div className="admin-dialog-section-head">
                <strong>额度参数</strong>
                <span>调整后会立即更新到用户视图和鉴权链</span>
              </div>
              <div className="admin-dialog-grid">
                <Field label="余额(分)">
                  <TextInput
                    type="number"
                    value={String(quotaDraft.balance_cents)}
                    onChange={(e) => setQuotaDraft({ ...quotaDraft, balance_cents: Number(e.target.value || 0) })}
                  />
                </Field>
                <Field label="并发">
                  <TextInput
                    type="number"
                    value={String(quotaDraft.concurrency_limit)}
                    onChange={(e) => setQuotaDraft({ ...quotaDraft, concurrency_limit: Number(e.target.value || 0) })}
                  />
                </Field>
              </div>
            </div>
          </div>
        </Modal>
      ) : null}
    </section>
  );
}

function compareAccounts(left: AdminAccount, right: AdminAccount, sortBy: AccountSortKey) {
  if (sortBy === 'requests_desc') {
    return compareNumbers(Number(right.request_count || 0), Number(left.request_count || 0));
  }
  if (sortBy === 'tokens_desc') {
    return compareNumbers(Number(right.total_tokens || 0), Number(left.total_tokens || 0));
  }
  if (sortBy === 'last_seen_desc') {
    return compareNumbers(parseMaybeDate(right.last_seen_at), parseMaybeDate(left.last_seen_at));
  }
  return String(left.name || '').localeCompare(String(right.name || ''), 'zh-CN');
}

function compareNumbers(left: number | null, right: number | null) {
  const normalizedLeft = left ?? -1;
  const normalizedRight = right ?? -1;
  return normalizedLeft - normalizedRight;
}

function parseMaybeDate(value?: string) {
  if (!value) return null;
  const timestamp = Date.parse(value);
  return Number.isNaN(timestamp) ? null : timestamp;
}

function formatDateTime(timestamp: number) {
  return new Date(timestamp).toLocaleString('zh-CN', { hour12: false });
}

function isAccountSourceFilter(value: unknown): value is AccountSourceFilter {
  return value === '' || value === 'managed' || value === 'env' || value === 'anonymous';
}

function isAccountSortKey(value: unknown): value is AccountSortKey {
  return typeof value === 'string' && ACCOUNT_SORT_SET.has(value as AccountSortKey);
}

function formatAccountSource(value: AccountSourceFilter) {
  if (value === 'managed') return '托管 Key';
  if (value === 'env') return '环境 Key';
  if (value === 'anonymous') return '匿名';
  return '全部来源';
}
