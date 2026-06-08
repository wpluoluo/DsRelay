import { useEffect, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Eye, RefreshCw, Server } from 'lucide-react';
import { fetchAdminProviderAccounts } from '../api';
import { Badge, Button, Field, Modal, ModalActions, Select, TextInput } from '../components';
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
import { formatByteCount, formatNumber, formatTokenCount, readStorageJSON, writeStorageJSON } from '../utils';

type StatusFilter = '' | 'enabled' | 'disabled';
type HealthFilter = '' | 'error' | 'used' | 'unused';
type AccountColumnKey = 'pool' | 'protocol' | 'models' | 'requests' | 'traffic' | 'status';

const DEFAULT_VISIBLE_COLUMNS: AccountColumnKey[] = ['pool', 'protocol', 'models', 'requests', 'traffic', 'status'];
const STORAGE_KEY = 'admin-provider-accounts-view-state';

export function AdminAccountsPage() {
  const accountsQuery = useQuery({ queryKey: ['admin-provider-accounts'], queryFn: fetchAdminProviderAccounts, refetchInterval: 10000 });
  const savedState = readStorageJSON(STORAGE_KEY, {
    search: '',
    statusFilter: '' as StatusFilter,
    healthFilter: '' as HealthFilter,
    poolFilter: '',
    protocolFilter: '',
    pageSize: 20,
    visibleColumns: DEFAULT_VISIBLE_COLUMNS,
  });

  const [search, setSearch] = useState(savedState.search);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>(savedState.statusFilter || '');
  const [healthFilter, setHealthFilter] = useState<HealthFilter>(savedState.healthFilter || '');
  const [poolFilter, setPoolFilter] = useState(savedState.poolFilter || '');
  const [protocolFilter, setProtocolFilter] = useState(savedState.protocolFilter || '');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(savedState.pageSize || 20);
  const [visibleColumns, setVisibleColumns] = useState<Set<AccountColumnKey>>(new Set(savedState.visibleColumns || DEFAULT_VISIBLE_COLUMNS));
  const [inspectAccount, setInspectAccount] = useState<AdminProviderAccount | null>(null);

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
  const enabledCount = items.filter((item) => item.enabled !== false).length;
  const requestTotal = items.reduce((sum, item) => sum + Number(item.request_count || 0), 0);
  const tokenTotal = items.reduce((sum, item) => sum + Number(item.total_tokens || 0), 0);
  const errorTotal = items.reduce((sum, item) => sum + Number(item.error_count || 0), 0);
  const usedRoutes = items.filter((item) => Number(item.request_count || 0) > 0).length;

  useEffect(() => {
    writeStorageJSON(STORAGE_KEY, {
      search,
      statusFilter,
      healthFilter,
      poolFilter,
      protocolFilter,
      pageSize,
      visibleColumns: Array.from(visibleColumns),
    });
  }, [healthFilter, pageSize, poolFilter, protocolFilter, search, statusFilter, visibleColumns]);

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

  return (
    <section className="grid-page">
      <div className="sub2-page-head">
        <div className="sub2-page-title">
          <strong>账号管理</strong>
        </div>
        <div className="sub2-inline-summary">
          <div className="sub2-inline-summary-item"><span>账号总数</span><strong>{formatNumber(items.length)}</strong><small>已使用 {formatNumber(usedRoutes)}</small></div>
          <div className="sub2-inline-summary-item"><span>启用线路</span><strong>{formatNumber(enabledCount)}</strong><small>停用 {formatNumber(items.length - enabledCount)}</small></div>
          <div className="sub2-inline-summary-item"><span>累计请求</span><strong>{formatNumber(requestTotal)}</strong><small>{formatTokenCount(tokenTotal)}</small></div>
          <div className="sub2-inline-summary-item"><span>异常请求</span><strong>{formatNumber(errorTotal)}</strong><small>最近请求</small></div>
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
                    { key: 'pool', label: '连接池', checked: visibleColumns.has('pool'), onToggle: () => toggleColumn('pool') },
                    { key: 'protocol', label: '协议', checked: visibleColumns.has('protocol'), onToggle: () => toggleColumn('protocol') },
                    { key: 'models', label: '模型', checked: visibleColumns.has('models'), onToggle: () => toggleColumn('models') },
                    { key: 'requests', label: '请求', checked: visibleColumns.has('requests'), onToggle: () => toggleColumn('requests') },
                    { key: 'traffic', label: '流量', checked: visibleColumns.has('traffic'), onToggle: () => toggleColumn('traffic') },
                    { key: 'status', label: '状态', checked: visibleColumns.has('status'), onToggle: () => toggleColumn('status') },
                  ]}
                />
                <ToolsMenu>
                  <button type="button" onClick={resetFilters}>
                    <span>清空筛选</span>
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
                </ToolsMenu>
              </ToolbarButtonRow>
            }
          >
            <SearchField value={search} placeholder="搜索账号 / 连接池 / 线路 / 模型" onChange={(value) => { setSearch(value); setPage(1); }} />
            <Select value={statusFilter} onChange={(event) => { setStatusFilter(event.target.value as StatusFilter); setPage(1); }}>
              <option value="">全部状态</option>
              <option value="enabled">启用</option>
              <option value="disabled">停用</option>
            </Select>
            <Select value={poolFilter} onChange={(event) => { setPoolFilter(event.target.value); setPage(1); }}>
              <option value="">全部连接池</option>
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
          <div className="table-wrap table-scroll">
            <table>
              <thead>
                <tr>
                  <th>账号</th>
                  {visibleColumns.has('pool') ? <th>连接池</th> : null}
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
                    <td>
                      <div className="sub2-cell-stack sub2-cell-stack-tight">
                        <strong>{item.provider_name || routeHost(item.route_url) || item.id}</strong>
                        <small>{item.route_url || '-'}</small>
                      </div>
                    </td>
                    {visibleColumns.has('pool') ? (
                      <td>
                        <div className="sub2-cell-stack sub2-cell-stack-tight">
                          <strong>{item.pool_name || '-'}</strong>
                          <small>优先级 {formatNumber(item.priority || 0)} · 线路 {formatNumber(item.route_index || 0)}</small>
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
                      </RowActions>
                    </td>
                  </tr>
                )) : (
                  <ListEmptyRow
                    colSpan={visibleColumns.size + 2}
                    title="暂无账号数据"
                    description="当前筛选条件下没有上游账号。"
                    action={<Button onClick={() => accountsQuery.refetch()}><RefreshCw size={14} />刷新</Button>}
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
                <span>连接池</span>
                <strong>{inspectAccount.pool_name || '-'}</strong>
                <small>优先级 {formatNumber(inspectAccount.priority || 0)} · 线路 {formatNumber(inspectAccount.route_index || 0)}</small>
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
                <Field label="线路 URL"><TextInput readOnly value={inspectAccount.route_url || '-'} /></Field>
                <Field label="协议"><TextInput readOnly value={inspectAccount.protocol || '-'} /></Field>
                <Field label="Key 数量"><TextInput readOnly value={String(inspectAccount.key_count || 0)} /></Field>
                <Field label="冷却秒数"><TextInput readOnly value={String(inspectAccount.cooldown_seconds || 0)} /></Field>
                <Field label="退避次数"><TextInput readOnly value={String(inspectAccount.backoff_attempts || 0)} /></Field>
                <Field label="最近请求"><TextInput readOnly value={inspectAccount.last_seen_at || '-'} /></Field>
              </div>
            </div>
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
    </section>
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
