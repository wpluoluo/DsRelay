import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Ban, Download, Edit, Eye, Plus, RefreshCw, Server, ShieldCheck, Trash2 } from 'lucide-react';
import { fetchAdminProviderAccounts, saveConfig, testPool } from '../api';
import { Badge, Button, Field, Modal, ModalActions, NumberInput, Select, TextArea, TextInput, Toggle } from '../components';
import {
  ActionButton,
  ColumnMenu,
  FilterToolbar,
  ListEmptyRow,
  Pager,
  RowAction,
  RowActions,
  SearchField,
  TablePageLayout,
  ToolbarButtonRow,
  ToolsMenu,
} from '../components/admin';
import type { AdminProviderAccount } from '../types';
import type { Pool, PoolTestResult, RuntimeConfig } from '../types';
import { splitLines, textFromLines, formatByteCount, formatNumber, formatTokenCount, readStorageJSON, writeStorageJSON } from '../utils';
import { useDashboard } from '../state/dashboardContext';
import { queryClient } from '../state/queryClient';
import { defaultPolicy, normalizePool } from '../features/config/model';
import { PoolTestView } from '../features/routes/RouteTable';

type StatusFilter = '' | 'enabled' | 'disabled';
type HealthFilter = '' | 'error' | 'used' | 'unused';
type AccountColumnKey = 'route' | 'protocol' | 'models' | 'requests' | 'traffic' | 'status';
type BulkEditTarget = 'selected' | 'filtered';

type BulkEditDraft = {
  enabled: '' | 'enabled' | 'disabled';
  priority: string;
  protocol: string;
  prompt_cache_mode: string;
  prompt_cache_hints_mode: string;
  prompt_cache_provider: string;
  route_cooldown_seconds: string;
  route_cooldown_multiplier: string;
  route_cooldown_max_seconds: string;
  rate_limit_retry_attempts: string;
  rate_limit_backoff_initial_ms: string;
  rate_limit_backoff_multiplier: string;
  rate_limit_backoff_max_ms: string;
};

const DEFAULT_VISIBLE_COLUMNS: AccountColumnKey[] = ['route', 'protocol', 'models', 'requests', 'traffic', 'status'];
const STORAGE_KEY = 'admin-provider-accounts-view-state';
const EMPTY_BULK_EDIT: BulkEditDraft = {
  enabled: '',
  priority: '',
  protocol: '',
  prompt_cache_mode: '',
  prompt_cache_hints_mode: '',
  prompt_cache_provider: '',
  route_cooldown_seconds: '',
  route_cooldown_multiplier: '',
  route_cooldown_max_seconds: '',
  rate_limit_retry_attempts: '',
  rate_limit_backoff_initial_ms: '',
  rate_limit_backoff_multiplier: '',
  rate_limit_backoff_max_ms: '',
};

export function AdminAccountsPage() {
  const dashboard = useDashboard();
  const savedState = readStorageJSON(STORAGE_KEY, {
    search: '',
    statusFilter: '' as StatusFilter,
    healthFilter: '' as HealthFilter,
    poolFilter: '',
    protocolFilter: '',
    autoRefreshEnabled: true,
    autoRefreshInterval: 10,
    pageSize: 20,
    visibleColumns: DEFAULT_VISIBLE_COLUMNS,
  });

  const [search, setSearch] = useState(savedState.search);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>(savedState.statusFilter || '');
  const [healthFilter, setHealthFilter] = useState<HealthFilter>(savedState.healthFilter || '');
  const [poolFilter, setPoolFilter] = useState(savedState.poolFilter || '');
  const [protocolFilter, setProtocolFilter] = useState(savedState.protocolFilter || '');
  const [autoRefreshEnabled, setAutoRefreshEnabled] = useState(savedState.autoRefreshEnabled !== false);
  const [autoRefreshInterval, setAutoRefreshInterval] = useState(Number(savedState.autoRefreshInterval || 10));
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(savedState.pageSize || 20);
  const initialVisibleColumns = ((savedState.visibleColumns || DEFAULT_VISIBLE_COLUMNS) as string[]).map((item) => (item === 'pool' ? 'route' : item)) as AccountColumnKey[];
  const [visibleColumns, setVisibleColumns] = useState<Set<AccountColumnKey>>(new Set(initialVisibleColumns.length ? initialVisibleColumns : DEFAULT_VISIBLE_COLUMNS));
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [inspectAccount, setInspectAccount] = useState<AdminProviderAccount | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<AdminProviderAccount | null>(null);
  const [bulkDeleteOpen, setBulkDeleteOpen] = useState(false);
  const [bulkEditTarget, setBulkEditTarget] = useState<BulkEditTarget | null>(null);
  const [bulkEditDraft, setBulkEditDraft] = useState<BulkEditDraft>({ ...EMPTY_BULK_EDIT });
  const [accountIndex, setAccountIndex] = useState<number | null>(null);
  const [accountDraft, setAccountDraft] = useState<Pool | null>(null);
  const [accountTest, setAccountTest] = useState<PoolTestResult | null>(null);
  const [accountStatus, setAccountStatus] = useState('');
  const accountsQuery = useQuery({
    queryKey: ['admin-provider-accounts'],
    queryFn: fetchAdminProviderAccounts,
    refetchInterval: autoRefreshEnabled ? Math.max(5, autoRefreshInterval) * 1000 : false,
  });

  const savePoolsMutation = useMutation({
    mutationFn: (config: RuntimeConfig) => saveConfig(config),
    onSuccess: async (state) => {
      queryClient.setQueryData(['dashboard-state'], state);
      setAccountDraft(null);
      setAccountIndex(null);
      setAccountTest(null);
      setAccountStatus('账号已保存。');
      await queryClient.invalidateQueries({ queryKey: ['admin-provider-accounts'] });
    },
    onError: (error) => {
      setAccountStatus(error instanceof Error ? error.message : '账号保存失败');
    },
  });
  const testMutation = useMutation({
    mutationFn: async ({ index, pool }: { index: number; pool: Pool }) => testPool(index, pool.name),
    onSuccess: setAccountTest,
    onError: (error) => {
      setAccountTest({ ok: false, message: error instanceof Error ? error.message : '测试失败' });
    },
  });

  const items = accountsQuery.data?.items || [];
  const poolOptions = useMemo(() => Array.from(new Set(items.map((item) => item.pool_name).filter(Boolean))).sort(), [items]);
  const protocolOptions = useMemo(() => Array.from(new Set(items.map((item) => item.protocol).filter(Boolean))).sort(), [items]);

  const filteredItems = useMemo(() => {
    const keyword = search.trim().toLowerCase();
    return items.filter((item) => {
      if (statusFilter) {
        const enabledValue = statusFilter === 'enabled';
        if ((item.enabled !== false) !== enabledValue) return false;
      }
      if (healthFilter === 'error' && Number(item.error_count || 0) <= 0) return false;
      if (healthFilter === 'used' && Number(item.request_count || 0) <= 0) return false;
      if (healthFilter === 'unused' && Number(item.request_count || 0) > 0) return false;
      if (poolFilter && item.pool_name !== poolFilter) return false;
      if (protocolFilter && item.protocol !== protocolFilter) return false;
      if (!keyword) return true;
      const haystack = [
        item.provider_name,
        item.pool_name,
        item.route_url,
        ...(item.route_urls || []),
        item.protocol,
        ...(item.models || []),
      ]
        .map((value) => String(value || '').toLowerCase())
        .join(' ');
      return haystack.includes(keyword);
    });
  }, [healthFilter, items, poolFilter, protocolFilter, search, statusFilter]);

  const totalPages = Math.max(1, Math.ceil(filteredItems.length / pageSize));
  const pagedItems = filteredItems.slice((page - 1) * pageSize, page * pageSize);
  const allPageSelected = pagedItems.length > 0 && pagedItems.every((item) => selectedIds.has(item.id));
  const selectedItems = useMemo(() => items.filter((item) => selectedIds.has(item.id)), [items, selectedIds]);

  useEffect(() => {
    writeStorageJSON(STORAGE_KEY, {
      search,
      statusFilter,
      healthFilter,
      poolFilter,
      protocolFilter,
      autoRefreshEnabled,
      autoRefreshInterval,
      pageSize,
      visibleColumns: Array.from(visibleColumns),
    });
  }, [autoRefreshEnabled, autoRefreshInterval, healthFilter, pageSize, poolFilter, protocolFilter, search, statusFilter, visibleColumns]);

  useEffect(() => {
    const validIds = new Set(items.map((item) => item.id));
    setSelectedIds((current) => {
      const next = new Set(Array.from(current).filter((id) => validIds.has(id)));
      return next.size === current.size ? current : next;
    });
  }, [items]);

  function toggleColumn(key: AccountColumnKey) {
    setVisibleColumns((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  function resetFilters() {
    setSearch('');
    setStatusFilter('');
    setHealthFilter('');
    setPoolFilter('');
    setProtocolFilter('');
    setPage(1);
  }

  function toggleSelected(itemId: string) {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (next.has(itemId)) next.delete(itemId);
      else next.add(itemId);
      return next;
    });
  }

  function togglePageSelected() {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (allPageSelected) {
        for (const item of pagedItems) next.delete(item.id);
      } else {
        for (const item of pagedItems) next.add(item.id);
      }
      return next;
    });
  }

  function updateSelectedAccountsEnabled(enabled: boolean) {
    const selectedIndexes = selectedPoolIndexes(selectedItems);
    if (!selectedIndexes.size) return;
    const next = dashboard.pools.map((pool, index) => (selectedIndexes.has(index) ? normalizePool({ ...pool, enabled }) : pool));
    saveAccountPools(next);
    setSelectedIds(new Set());
  }

  function openBulkEdit(target: BulkEditTarget) {
    const targetItems = getBulkTargetItems(target);
    if (!targetItems.length) return;
    setBulkEditDraft({ ...EMPTY_BULK_EDIT });
    setBulkEditTarget(target);
  }

  function selectedPoolIndexes(sourceItems: AdminProviderAccount[]) {
    return new Set(sourceItems.map(resolvePoolIndex).filter((index) => index >= 0 && index < dashboard.pools.length));
  }

  function getBulkTargetItems(target: BulkEditTarget) {
    return target === 'selected' ? selectedItems : filteredItems;
  }

  function applyBulkEdit() {
    if (!bulkEditTarget) return;
    const indexes = selectedPoolIndexes(getBulkTargetItems(bulkEditTarget));
    if (!indexes.size) return;
    const next = dashboard.pools.map((pool, index) => {
      if (!indexes.has(index)) return pool;
      const current = normalizePool(pool);
      const policy = { ...defaultPolicy, ...(current.route_policy || {}) };
      const policyPatch: Partial<NonNullable<Pool['route_policy']>> = {};
      const updated: Pool = { ...current };
      if (bulkEditDraft.enabled) updated.enabled = bulkEditDraft.enabled === 'enabled';
      const priority = parseOptionalNumber(bulkEditDraft.priority);
      if (priority !== undefined) updated.priority = priority;
      if (bulkEditDraft.protocol) policyPatch.text_upstream_protocol = bulkEditDraft.protocol;
      if (bulkEditDraft.prompt_cache_mode) policyPatch.prompt_cache_mode = bulkEditDraft.prompt_cache_mode;
      if (bulkEditDraft.prompt_cache_hints_mode) policyPatch.prompt_cache_hints_mode = bulkEditDraft.prompt_cache_hints_mode;
      if (bulkEditDraft.prompt_cache_provider) policyPatch.prompt_cache_provider = bulkEditDraft.prompt_cache_provider;
      patchNumber(policyPatch, 'route_cooldown_seconds', bulkEditDraft.route_cooldown_seconds);
      patchNumber(policyPatch, 'route_cooldown_multiplier', bulkEditDraft.route_cooldown_multiplier);
      patchNumber(policyPatch, 'route_cooldown_max_seconds', bulkEditDraft.route_cooldown_max_seconds);
      patchNumber(policyPatch, 'rate_limit_retry_attempts', bulkEditDraft.rate_limit_retry_attempts);
      patchNumber(policyPatch, 'rate_limit_backoff_initial_ms', bulkEditDraft.rate_limit_backoff_initial_ms);
      patchNumber(policyPatch, 'rate_limit_backoff_multiplier', bulkEditDraft.rate_limit_backoff_multiplier);
      patchNumber(policyPatch, 'rate_limit_backoff_max_ms', bulkEditDraft.rate_limit_backoff_max_ms);
      if (Object.keys(policyPatch).length) updated.route_policy = { ...policy, ...policyPatch };
      return normalizePool(updated);
    });
    saveAccountPools(next);
    setSelectedIds(new Set());
    setBulkEditTarget(null);
  }

  function confirmBulkDeleteAccounts() {
    const selectedIndexes = selectedPoolIndexes(selectedItems);
    if (!selectedIndexes.size) return;
    saveAccountPools(dashboard.pools.filter((_, index) => !selectedIndexes.has(index)));
    setSelectedIds(new Set());
    setBulkDeleteOpen(false);
  }

  function exportFilteredAccounts() {
    const payload = JSON.stringify(filteredItems, null, 2);
    const blob = new Blob([payload], { type: 'application/json;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `provider-accounts-${new Date().toISOString().slice(0, 10)}.json`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }

  function openAccountForm(index: number | null) {
    setAccountStatus('');
    setAccountTest(null);
    setAccountIndex(index);
    setAccountDraft(normalizePool(index == null ? undefined : dashboard.pools[index]));
  }

  function saveAccountPools(nextPools: Pool[]) {
    const nextConfig = { ...dashboard.draft, pools: nextPools.map(normalizePool) };
    savePoolsMutation.mutate(nextConfig);
  }

  function saveAccountDraft() {
    if (!accountDraft) return;
    const next = dashboard.pools.slice();
    if (accountIndex == null) next.push(normalizePool(accountDraft));
    else next[accountIndex] = normalizePool(accountDraft);
    saveAccountPools(next);
  }

  function confirmDeleteAccount() {
    if (!deleteTarget) return;
    const index = resolvePoolIndex(deleteTarget);
    if (index < 0 || index >= dashboard.pools.length) {
      setAccountStatus('账号不存在或已被删除。');
      setDeleteTarget(null);
      return;
    }
    saveAccountPools(dashboard.pools.filter((_, itemIndex) => itemIndex !== index));
    setDeleteTarget(null);
  }

  return (
    <section className="grid-page">
      <div className="sub2-page-head">
        <div className="sub2-page-title">
          <strong>账号管理</strong>
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
                    { key: 'route', label: '线路', checked: visibleColumns.has('route'), onToggle: () => toggleColumn('route') },
                    { key: 'protocol', label: '协议', checked: visibleColumns.has('protocol'), onToggle: () => toggleColumn('protocol') },
                    { key: 'models', label: '模型', checked: visibleColumns.has('models'), onToggle: () => toggleColumn('models') },
                    { key: 'requests', label: '请求', checked: visibleColumns.has('requests'), onToggle: () => toggleColumn('requests') },
                    { key: 'traffic', label: '流量', checked: visibleColumns.has('traffic'), onToggle: () => toggleColumn('traffic') },
                    { key: 'status', label: '状态', checked: visibleColumns.has('status'), onToggle: () => toggleColumn('status') },
                  ]}
                />
                <ToolsMenu label="自动刷新">
                  <button type="button" onClick={() => accountsQuery.refetch()}>
                    <span>立即刷新</span>
                    <RefreshCw size={14} />
                  </button>
                  <button type="button" onClick={() => setAutoRefreshEnabled(!autoRefreshEnabled)}>
                    <span>{autoRefreshEnabled ? '关闭自动刷新' : '开启自动刷新'}</span>
                    <strong>{autoRefreshEnabled ? '✓' : ''}</strong>
                  </button>
                  {[10, 30, 60, 120].map((seconds) => (
                    <button key={seconds} type="button" onClick={() => { setAutoRefreshInterval(seconds); setAutoRefreshEnabled(true); }}>
                      <span>{seconds} 秒</span>
                      <strong>{autoRefreshEnabled && autoRefreshInterval === seconds ? '✓' : ''}</strong>
                    </button>
                  ))}
                </ToolsMenu>
                <ToolsMenu>
                  <button type="button" onClick={resetFilters}>
                    <span>清空筛选</span>
                  </button>
                  <button type="button" onClick={() => { setHealthFilter('used'); setPage(1); }}>
                    <span>仅看有请求</span>
                  </button>
                  <button type="button" onClick={() => { setHealthFilter('error'); setPage(1); }}>
                    <span>仅看异常</span>
                  </button>
                  <button type="button" onClick={() => { setHealthFilter('unused'); setPage(1); }}>
                    <span>仅看未使用</span>
                  </button>
                  <button type="button" onClick={() => { setPageSize(50); setPage(1); }}>
                    <span>切换 50 / 页</span>
                  </button>
                  <button type="button" onClick={() => openBulkEdit('filtered')} disabled={!filteredItems.length}>
                    <span>批量编辑筛选结果</span>
                    <Edit size={14} />
                  </button>
                  <button type="button" onClick={exportFilteredAccounts}>
                    <span>数据导出</span>
                    <Download size={14} />
                  </button>
                </ToolsMenu>
                <Button tone="primary" data-tour="accounts-create-btn" onClick={() => openAccountForm(null)}><Plus size={15} />添加账号</Button>
              </ToolbarButtonRow>
            }
          >
            <SearchField value={search} placeholder="搜索上游账号 / 线路 / 模型" onChange={(value) => { setSearch(value); setPage(1); }} />
            <Select value={statusFilter} onChange={(event) => { setStatusFilter(event.target.value as StatusFilter); setPage(1); }}>
              <option value="">全部状态</option>
              <option value="enabled">启用</option>
              <option value="disabled">停用</option>
            </Select>
            <Select value={poolFilter} onChange={(event) => { setPoolFilter(event.target.value); setPage(1); }}>
              <option value="">全部上游账号</option>
              {poolOptions.map((pool) => <option key={pool} value={pool}>{pool}</option>)}
            </Select>
            <Select value={protocolFilter} onChange={(event) => { setProtocolFilter(event.target.value); setPage(1); }}>
              <option value="">全部协议</option>
              {protocolOptions.map((protocol) => <option key={protocol} value={protocol}>{protocol}</option>)}
            </Select>
            <Select value={healthFilter} onChange={(event) => { setHealthFilter(event.target.value as HealthFilter); setPage(1); }}>
              <option value="">全部观测</option>
              <option value="used">有请求</option>
              <option value="unused">未使用</option>
              <option value="error">有异常</option>
            </Select>
          </FilterToolbar>
        }
        table={
          <div className="table-wrap table-scroll table-wide">
            {selectedIds.size ? (
              <div className="sub2-bulk-bar">
                <strong>已选择 {formatNumber(selectedIds.size)} 个账号</strong>
                <div className="button-row">
                  <Button tone="danger" onClick={() => setBulkDeleteOpen(true)}><Trash2 size={14} />删除</Button>
                  <Button onClick={() => updateSelectedAccountsEnabled(true)}><ShieldCheck size={14} />启用</Button>
                  <Button tone="danger" onClick={() => updateSelectedAccountsEnabled(false)}><Ban size={14} />停用</Button>
                  <Button onClick={() => openBulkEdit('selected')}><Edit size={14} />批量编辑</Button>
                  <Button onClick={() => setSelectedIds(new Set())}>取消选择</Button>
                </div>
              </div>
            ) : null}
            <table>
              <thead>
                <tr>
                  <th><input type="checkbox" checked={allPageSelected} onChange={togglePageSelected} aria-label="选择当前页账号" /></th>
                  <th>上游账号</th>
                  {visibleColumns.has('route') ? <th>线路</th> : null}
                  {visibleColumns.has('protocol') ? <th>协议</th> : null}
                  {visibleColumns.has('models') ? <th>模型</th> : null}
                  {visibleColumns.has('requests') ? <th>请求</th> : null}
                  {visibleColumns.has('traffic') ? <th>流量</th> : null}
                  {visibleColumns.has('status') ? <th>状态</th> : null}
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {pagedItems.length ? pagedItems.map((item) => (
                  <tr key={item.id}>
                    <td><input type="checkbox" checked={selectedIds.has(item.id)} onChange={() => toggleSelected(item.id)} aria-label={`选择 ${item.pool_name || item.id}`} /></td>
                    <td>
                      <div className="sub2-cell-stack sub2-cell-stack-tight">
                        <strong>{item.pool_name || item.provider_name || item.id}</strong>
                        <small>{item.provider_name || routeHost(item.route_url) || '-'}</small>
                      </div>
                    </td>
                    {visibleColumns.has('route') ? (
                      <td>
                        <div className="sub2-cell-stack sub2-cell-stack-tight">
                          <strong>{item.pool_name || '-'}</strong>
                          <small>优先级 {formatNumber(item.priority || 0)} · 线路 {formatNumber(item.route_count || item.route_urls?.length || 0)}</small>
                        </div>
                      </td>
                    ) : null}
                    {visibleColumns.has('protocol') ? (
                      <td>
                        <div className="sub2-cell-stack sub2-cell-stack-tight">
                          <strong>{item.protocol || '-'}</strong>
                          <small>Key {formatNumber(item.key_count || 0)}</small>
                        </div>
                      </td>
                    ) : null}
                    {visibleColumns.has('models') ? (
                      <td>
                        <div className="sub2-cell-stack sub2-cell-stack-tight">
                          <strong>{item.models?.[0] || '-'}</strong>
                          <small>{item.models?.slice(1, 3).join(' / ') || '未观测到模型'}</small>
                        </div>
                      </td>
                    ) : null}
                    {visibleColumns.has('requests') ? (
                      <td>
                        <div className="sub2-cell-stack sub2-cell-stack-tight">
                          <strong>{formatNumber(item.request_count || 0)}</strong>
                          <small>异常 {formatNumber(item.error_count || 0)}</small>
                        </div>
                      </td>
                    ) : null}
                    {visibleColumns.has('traffic') ? (
                      <td>
                        <div className="sub2-cell-stack sub2-cell-stack-tight">
                          <strong>{formatByteCount(item.input_bytes || 0)}</strong>
                          <small>{formatByteCount(item.output_bytes || 0)} / {formatTokenCount(item.total_tokens || 0)}</small>
                        </div>
                      </td>
                    ) : null}
                    {visibleColumns.has('status') ? (
                      <td>
                        <div className="sub2-cell-stack sub2-cell-stack-tight">
                          <Badge tone={item.enabled === false ? 'warn' : Number(item.error_count || 0) > 0 ? 'bad' : 'ok'}>{item.enabled === false ? '停用' : Number(item.error_count || 0) > 0 ? '异常' : '启用'}</Badge>
                          <small>{item.last_seen_at || '暂无请求'}</small>
                        </div>
                      </td>
                    ) : null}
                    <td>
                      <RowActions>
                        <RowAction icon={Eye} label="详情" onClick={() => setInspectAccount(item)} />
                        <RowAction icon={Edit} label="编辑" onClick={() => openAccountForm(resolvePoolIndex(item))} />
                        <ToolsMenu label="更多">
                          <button type="button" onClick={() => setDeleteTarget(item)} className="danger">
                            <span>删除</span>
                            <Trash2 size={14} />
                          </button>
                        </ToolsMenu>
                      </RowActions>
                    </td>
                  </tr>
                )) : (
                  <ListEmptyRow
                    colSpan={visibleColumns.size + 3}
                    title="暂无账号数据"
                    action={<Button tone="primary" data-tour="accounts-create-btn" onClick={() => openAccountForm(null)}><Plus size={14} />添加账号</Button>}
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

      {inspectAccount ? (
        <Modal
          title="账号详情"
          size="lg"
          onClose={() => setInspectAccount(null)}
          footer={<ModalActions><Button onClick={() => setInspectAccount(null)}>关闭</Button></ModalActions>}
        >
          <div className="admin-dialog">
            <div className="admin-dialog-intro">
              <strong>{inspectAccount.provider_name || routeHost(inspectAccount.route_url) || inspectAccount.id}</strong>
            </div>
            <div className="admin-dialog-summary">
              <div className="admin-dialog-summary-card">
                <span>上游账号</span>
                <strong>{inspectAccount.pool_name || '-'}</strong>
                <small>优先级 {formatNumber(inspectAccount.priority || 0)} · 线路 {formatNumber(inspectAccount.route_count || inspectAccount.route_urls?.length || 0)}</small>
              </div>
              <div className="admin-dialog-summary-card">
                <span>状态</span>
                <strong>{inspectAccount.enabled === false ? '停用' : Number(inspectAccount.error_count || 0) > 0 ? '异常' : '启用'}</strong>
                <small>{inspectAccount.last_seen_at || '暂无请求'}</small>
              </div>
              <div className="admin-dialog-summary-card">
                <span>请求</span>
                <strong>{formatNumber(inspectAccount.request_count || 0)}</strong>
                <small>异常 {formatNumber(inspectAccount.error_count || 0)}</small>
              </div>
            </div>
            <div className="admin-dialog-section">
              <div className="admin-dialog-section-head">
                <strong>连接信息</strong>
              </div>
              <div className="admin-dialog-grid">
                <Field label="线路数量"><TextInput readOnly value={formatNumber(inspectAccount.route_count || inspectAccount.route_urls?.length || 0)} /></Field>
                <Field label="协议"><TextInput readOnly value={inspectAccount.protocol || '-'} /></Field>
                <Field label="Key 数量"><TextInput readOnly value={String(inspectAccount.key_count || 0)} /></Field>
                <Field label="冷却秒数"><TextInput readOnly value={String(inspectAccount.cooldown_seconds || 0)} /></Field>
                <Field label="退避次数"><TextInput readOnly value={String(inspectAccount.backoff_attempts || 0)} /></Field>
                <Field label="最近请求"><TextInput readOnly value={inspectAccount.last_seen_at || '-'} /></Field>
              </div>
            </div>
            <Field label="线路 URL" full>
              <TextArea readOnly rows={Math.min(6, Math.max(2, inspectAccount.route_urls?.length || 1))} value={(inspectAccount.route_urls || [inspectAccount.route_url || '-']).join('\n')} />
            </Field>
            <div className="admin-dialog-section">
              <div className="admin-dialog-section-head">
                <strong>用量观测</strong>
              </div>
              <div className="admin-dialog-grid">
                <Field label="请求字节"><TextInput readOnly value={formatByteCount(inspectAccount.input_bytes || 0)} /></Field>
                <Field label="响应字节"><TextInput readOnly value={formatByteCount(inspectAccount.output_bytes || 0)} /></Field>
                <Field label="请求 Token"><TextInput readOnly value={formatTokenCount(inspectAccount.prompt_tokens || 0)} /></Field>
                <Field label="回复 Token"><TextInput readOnly value={formatTokenCount(inspectAccount.completion_tokens || 0)} /></Field>
                <Field label="总 Token"><TextInput readOnly value={formatTokenCount(inspectAccount.total_tokens || 0)} /></Field>
                <Field label="模型数量"><TextInput readOnly value={formatNumber(inspectAccount.models?.length || 0)} /></Field>
              </div>
            </div>
            <div className="admin-dialog-note">
              <Server size={14} /> 模型观测：{inspectAccount.models?.join(' / ') || '未观测到模型'}
            </div>
          </div>
        </Modal>
      ) : null}

      {deleteTarget ? (
        <Modal
          title="删除账号"
          size="md"
          onClose={() => setDeleteTarget(null)}
          footer={
            <ModalActions>
              <Button onClick={() => setDeleteTarget(null)}>取消</Button>
              <Button tone="danger" onClick={confirmDeleteAccount}>删除</Button>
            </ModalActions>
          }
        >
          <div className="admin-dialog">
            <div className="admin-dialog-intro">
              <strong>{deleteTarget.pool_name || deleteTarget.provider_name || deleteTarget.id}</strong>
            </div>
          </div>
        </Modal>
      ) : null}

      {bulkDeleteOpen ? (
        <Modal
          title="批量删除账号"
          size="md"
          onClose={() => setBulkDeleteOpen(false)}
          footer={
            <ModalActions>
              <Button onClick={() => setBulkDeleteOpen(false)}>取消</Button>
              <Button tone="danger" disabled={!selectedItems.length || savePoolsMutation.isPending} onClick={confirmBulkDeleteAccounts}>删除</Button>
            </ModalActions>
          }
        >
          <div className="admin-dialog">
            <div className="admin-dialog-intro">
              <strong>已选择 {formatNumber(selectedItems.length)} 个账号</strong>
            </div>
            <div className="table-wrap table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>账号</th>
                    <th>线路</th>
                    <th>状态</th>
                  </tr>
                </thead>
                <tbody>
                  {selectedItems.map((item) => (
                    <tr key={item.id}>
                      <td>{item.pool_name || item.provider_name || item.id}</td>
                      <td>{formatNumber(item.route_count || item.route_urls?.length || 0)}</td>
                      <td>{item.enabled === false ? '停用' : '启用'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </Modal>
      ) : null}

      {bulkEditTarget ? (
        <Modal
          title="批量编辑账号"
          size="lg"
          onClose={() => setBulkEditTarget(null)}
          footer={
            <ModalActions>
              <Button onClick={() => setBulkEditTarget(null)}>取消</Button>
              <Button tone="primary" disabled={!getBulkTargetItems(bulkEditTarget).length || savePoolsMutation.isPending} onClick={applyBulkEdit}>保存</Button>
            </ModalActions>
          }
        >
          <div className="admin-dialog">
            <div className="admin-dialog-intro">
              <strong>{bulkTargetLabel(bulkEditTarget)} {formatNumber(getBulkTargetItems(bulkEditTarget).length)} 个账号</strong>
            </div>
            <div className="admin-dialog-section">
              <div className="admin-dialog-section-head">
                <strong>基础信息</strong>
              </div>
              <div className="admin-dialog-grid modal-grid">
                <Field label="状态">
                  <Select value={bulkEditDraft.enabled} onChange={(event) => setBulkEditDraft({ ...bulkEditDraft, enabled: event.target.value as BulkEditDraft['enabled'] })}>
                    <option value="">保持不变</option>
                    <option value="enabled">启用</option>
                    <option value="disabled">停用</option>
                  </Select>
                </Field>
                <Field label="优先级">
                  <TextInput type="number" value={bulkEditDraft.priority} onChange={(event) => setBulkEditDraft({ ...bulkEditDraft, priority: event.target.value })} placeholder="保持不变" />
                </Field>
                <Field label="文本上游协议">
                  <Select value={bulkEditDraft.protocol} onChange={(event) => setBulkEditDraft({ ...bulkEditDraft, protocol: event.target.value })}>
                    <option value="">保持不变</option>
                    <option value="auto">自动</option>
                    <option value="openai">OpenAI 兼容</option>
                    <option value="responses">Responses</option>
                    <option value="anthropic">Anthropic</option>
                    <option value="gemini">Gemini</option>
                  </Select>
                </Field>
              </div>
            </div>
            <div className="admin-dialog-section">
              <div className="admin-dialog-section-head">
                <strong>缓存与退避</strong>
              </div>
              <div className="admin-dialog-grid modal-grid">
                <Field label="本地精确缓存">
                  <Select value={bulkEditDraft.prompt_cache_mode} onChange={(event) => setBulkEditDraft({ ...bulkEditDraft, prompt_cache_mode: event.target.value })}>
                    <option value="">保持不变</option>
                    <option value="off">关闭</option>
                    <option value="exact">开启</option>
                  </Select>
                </Field>
                <Field label="上游缓存 Hint">
                  <Select value={bulkEditDraft.prompt_cache_hints_mode} onChange={(event) => setBulkEditDraft({ ...bulkEditDraft, prompt_cache_hints_mode: event.target.value })}>
                    <option value="">保持不变</option>
                    <option value="off">关闭</option>
                    <option value="auto">自动判断</option>
                    <option value="passthrough">仅透传</option>
                  </Select>
                </Field>
                <Field label="缓存提供方">
                  <Select value={bulkEditDraft.prompt_cache_provider} onChange={(event) => setBulkEditDraft({ ...bulkEditDraft, prompt_cache_provider: event.target.value })}>
                    <option value="">保持不变</option>
                    <option value="auto">自动识别</option>
                    <option value="openai">OpenAI</option>
                    <option value="openrouter">OpenRouter</option>
                    <option value="deepseek">DeepSeek</option>
                    <option value="anthropic">Anthropic</option>
                    <option value="gemini">Gemini</option>
                    <option value="observe">仅观测</option>
                    <option value="none">不支持</option>
                  </Select>
                </Field>
                <BulkNumberField label="基础冷却秒数" value={bulkEditDraft.route_cooldown_seconds} onChange={(value) => setBulkEditDraft({ ...bulkEditDraft, route_cooldown_seconds: value })} />
                <BulkNumberField label="冷却指数" step="0.1" value={bulkEditDraft.route_cooldown_multiplier} onChange={(value) => setBulkEditDraft({ ...bulkEditDraft, route_cooldown_multiplier: value })} />
                <BulkNumberField label="最大冷却秒数" value={bulkEditDraft.route_cooldown_max_seconds} onChange={(value) => setBulkEditDraft({ ...bulkEditDraft, route_cooldown_max_seconds: value })} />
                <BulkNumberField label="429 重试次数" value={bulkEditDraft.rate_limit_retry_attempts} onChange={(value) => setBulkEditDraft({ ...bulkEditDraft, rate_limit_retry_attempts: value })} />
                <BulkNumberField label="429 初始退避毫秒" value={bulkEditDraft.rate_limit_backoff_initial_ms} onChange={(value) => setBulkEditDraft({ ...bulkEditDraft, rate_limit_backoff_initial_ms: value })} />
                <BulkNumberField label="429 退避倍率" step="0.1" value={bulkEditDraft.rate_limit_backoff_multiplier} onChange={(value) => setBulkEditDraft({ ...bulkEditDraft, rate_limit_backoff_multiplier: value })} />
                <BulkNumberField label="429 最大退避毫秒" value={bulkEditDraft.rate_limit_backoff_max_ms} onChange={(value) => setBulkEditDraft({ ...bulkEditDraft, rate_limit_backoff_max_ms: value })} />
              </div>
            </div>
          </div>
        </Modal>
      ) : null}

      {accountDraft ? (
        <ProviderAccountModal
          pool={accountDraft}
          title={accountIndex == null ? '添加账号' : '编辑账号'}
          saving={savePoolsMutation.isPending}
          testing={testMutation.isPending}
          status={accountStatus}
          testResult={accountTest}
          canTest={accountIndex != null}
          onChange={setAccountDraft}
          onClose={() => { setAccountDraft(null); setAccountIndex(null); setAccountTest(null); setAccountStatus(''); }}
          onSave={saveAccountDraft}
          onTest={() => {
            if (accountIndex == null) {
              setAccountTest(null);
              return;
            }
            testMutation.mutate({ index: accountIndex, pool: accountDraft });
          }}
        />
      ) : null}
    </section>
  );
}

export function ProviderAccountModal({
  pool,
  title,
  saving,
  testing,
  status,
  testResult,
  canTest,
  onChange,
  onClose,
  onSave,
  onTest,
}: {
  pool: Pool;
  title: string;
  saving: boolean;
  testing: boolean;
  status: string;
  testResult: PoolTestResult | null;
  canTest: boolean;
  onChange: (pool: Pool) => void;
  onClose: () => void;
  onSave: () => void;
  onTest: () => void;
}) {
  const p = normalizePool(pool);
  const policy = { ...defaultPolicy, ...(p.route_policy || {}) };
  const patch = (next: Partial<Pool>) => onChange(normalizePool({ ...p, ...next }));
  const patchPolicy = (next: Record<string, unknown>) => patch({ route_policy: { ...policy, ...next } });

  return (
    <Modal
      title={title}
      size="lg"
      onClose={onClose}
      footer={
        <ModalActions>
          <Button onClick={onTest} disabled={!canTest || testing}>{testing ? '测试中' : '测试线路'}</Button>
          <Button onClick={onClose}>取消</Button>
          <Button tone="primary" disabled={saving || !String(p.name || '').trim()} onClick={onSave}>{saving ? '保存中' : '保存账号'}</Button>
        </ModalActions>
      }
    >
      <div className="admin-dialog provider-account-dialog">
        <div className="admin-dialog-section">
          <div className="admin-dialog-section-head">
            <strong>基础信息</strong>
          </div>
          <div className="admin-dialog-grid modal-grid">
            <Field label="账号名称"><TextInput value={p.name || ''} onChange={(event) => patch({ name: event.target.value })} /></Field>
            <Field label="优先级"><NumberInput value={p.priority ?? 100} onChange={(event) => patch({ priority: Number(event.target.value || 100) })} /></Field>
            <Toggle label="启用账号" checked={p.enabled !== false} onChange={(enabled) => patch({ enabled })} />
          </div>
          <Field label="上游地址" full>
            <TextArea rows={3} value={textFromLines(p.urls)} onChange={(event) => patch({ urls: splitLines(event.target.value) })} />
          </Field>
          <Field label="API Key" full>
            <TextArea rows={3} value={(p.keys || []).map((item) => item.key).join('\n')} onChange={(event) => patch({ keys: splitLines(event.target.value).map((key) => ({ key })) })} />
          </Field>
        </div>
        <div className="admin-dialog-section">
          <div className="admin-dialog-section-head">
            <strong>模型与协议</strong>
          </div>
          <Field label="该账号支持模型" full>
            <TextArea rows={4} value={p.supported_models_text || ''} onChange={(event) => patch({ supported_models_text: event.target.value })} />
          </Field>
          <Field label="模型映射" full>
            <TextArea rows={4} value={p.model_aliases_text || ''} onChange={(event) => patch({ model_aliases_text: event.target.value })} />
          </Field>
          <div className="admin-dialog-grid modal-grid">
            <Field label="文本上游协议">
              <Select value={policy.text_upstream_protocol} onChange={(event) => patchPolicy({ text_upstream_protocol: event.target.value })}>
                <option value="auto">自动</option>
                <option value="openai">OpenAI 兼容</option>
                <option value="responses">Responses</option>
                <option value="anthropic">Anthropic</option>
                <option value="gemini">Gemini</option>
              </Select>
            </Field>
            <Field label="思考强度">
              <Select value={policy.reasoning_effort} onChange={(event) => patchPolicy({ reasoning_effort: event.target.value })}>
                <option value="low">低</option>
                <option value="medium">中</option>
                <option value="high">高</option>
              </Select>
            </Field>
            <Field label="输出上限"><NumberInput value={policy.max_output_tokens} onChange={(event) => patchPolicy({ max_output_tokens: Number(event.target.value || 0) })} /></Field>
          </div>
        </div>
        <div className="admin-dialog-section">
          <div className="admin-dialog-section-head">
            <strong>缓存与退避</strong>
          </div>
          <div className="admin-dialog-grid modal-grid">
            <Field label="本地精确缓存">
              <Select value={policy.prompt_cache_mode} onChange={(event) => patchPolicy({ prompt_cache_mode: event.target.value })}>
                <option value="off">关闭</option>
                <option value="exact">开启</option>
              </Select>
            </Field>
            <Field label="上游缓存 Hint">
              <Select value={policy.prompt_cache_hints_mode} onChange={(event) => patchPolicy({ prompt_cache_hints_mode: event.target.value })}>
                <option value="off">关闭</option>
                <option value="auto">自动判断</option>
                <option value="passthrough">仅透传</option>
              </Select>
            </Field>
            <Field label="缓存提供方">
              <Select value={policy.prompt_cache_provider} onChange={(event) => patchPolicy({ prompt_cache_provider: event.target.value })}>
                <option value="auto">自动识别</option>
                <option value="openai">OpenAI</option>
                <option value="openrouter">OpenRouter</option>
                <option value="deepseek">DeepSeek</option>
                <option value="anthropic">Anthropic</option>
                <option value="gemini">Gemini</option>
                <option value="observe">仅观测</option>
                <option value="none">不支持</option>
              </Select>
            </Field>
            <Field label="基础冷却秒数"><NumberInput value={policy.route_cooldown_seconds} onChange={(event) => patchPolicy({ route_cooldown_seconds: Number(event.target.value || 0) })} /></Field>
            <Field label="冷却指数"><NumberInput step="0.1" value={policy.route_cooldown_multiplier} onChange={(event) => patchPolicy({ route_cooldown_multiplier: Number(event.target.value || 1) })} /></Field>
            <Field label="最大冷却秒数"><NumberInput value={policy.route_cooldown_max_seconds} onChange={(event) => patchPolicy({ route_cooldown_max_seconds: Number(event.target.value || 0) })} /></Field>
            <Field label="429 重试次数"><NumberInput value={policy.rate_limit_retry_attempts} onChange={(event) => patchPolicy({ rate_limit_retry_attempts: Number(event.target.value || 0) })} /></Field>
            <Field label="429 初始退避毫秒"><NumberInput value={policy.rate_limit_backoff_initial_ms} onChange={(event) => patchPolicy({ rate_limit_backoff_initial_ms: Number(event.target.value || 0) })} /></Field>
            <Field label="429 退避倍率"><NumberInput step="0.1" value={policy.rate_limit_backoff_multiplier} onChange={(event) => patchPolicy({ rate_limit_backoff_multiplier: Number(event.target.value || 1) })} /></Field>
            <Field label="429 最大退避毫秒"><NumberInput value={policy.rate_limit_backoff_max_ms} onChange={(event) => patchPolicy({ rate_limit_backoff_max_ms: Number(event.target.value || 0) })} /></Field>
          </div>
        </div>
        {status ? <div className={status.includes('失败') ? 'status-msg err' : 'status-msg'}>{status}</div> : null}
        {testResult ? <PoolTestView result={testResult} /> : null}
      </div>
    </Modal>
  );
}

function routeHost(value: string | undefined) {
  const text = String(value || '').trim();
  if (!text) return '';
  try {
    return new URL(text.split('#__route=', 1)[0]).host;
  } catch {
    return text.split('://', 2).pop()?.split('/', 1)[0] || text;
  }
}

function parseOptionalNumber(value: string) {
  const text = String(value || '').trim();
  if (!text) return undefined;
  const number = Number(text);
  return Number.isFinite(number) ? number : undefined;
}

function patchNumber(target: Partial<NonNullable<Pool['route_policy']>>, key: keyof NonNullable<Pool['route_policy']>, value: string) {
  const number = parseOptionalNumber(value);
  if (number !== undefined) target[key] = number as never;
}

function bulkTargetLabel(target: BulkEditTarget) {
  return target === 'selected' ? '已选择' : '当前筛选';
}

function BulkNumberField({
  label,
  value,
  step,
  onChange,
}: {
  label: string;
  value: string;
  step?: string;
  onChange: (value: string) => void;
}) {
  return (
    <Field label={label}>
      <TextInput type="number" step={step} value={value} onChange={(event) => onChange(event.target.value)} placeholder="保持不变" />
    </Field>
  );
}

function resolvePoolIndex(item: AdminProviderAccount) {
  const index = Number(item.pool_index);
  if (Number.isFinite(index) && index >= 0) return index;
  const routeIndex = Number(item.route_index);
  return Number.isFinite(routeIndex) && routeIndex > 0 ? routeIndex - 1 : 0;
}
