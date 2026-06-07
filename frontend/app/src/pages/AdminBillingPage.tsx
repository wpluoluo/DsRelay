import { useEffect, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Activity, Database, Download, MoreHorizontal, RefreshCw, Settings2, TriangleAlert, Users, Wallet } from 'lucide-react';
import { fetchAdminOverview, fetchAdminUsage } from '../api';
import { Metric } from '../components';
import { ActionButton, ColumnMenu, EmptyState, FilterToolbar, Pager, SearchField, TablePageLayout, ToolbarButtonRow } from '../components/admin';
import type { AdminUsageItem } from '../types';
import { formatByteCount, formatNumber, formatTokenCount, maskEmpty, readStorageJSON, writeStorageJSON } from '../utils';

const STORAGE_KEY = 'admin-billing-view-state';

type BillingColumnKey = 'route' | 'tokens' | 'input' | 'output' | 'status';
type TimePresetKey = 'all' | '1h' | '6h' | '24h' | '7d';
type BillingSortKey = 'started_at_desc' | 'started_at_asc' | 'tokens_desc' | 'tokens_asc' | 'duration_desc';

const DEFAULT_VISIBLE_COLUMNS: BillingColumnKey[] = ['route', 'tokens', 'input', 'output', 'status'];
const TIME_PRESET_OPTIONS: Array<{ value: TimePresetKey; label: string }> = [
  { value: 'all', label: '全部时间' },
  { value: '1h', label: '近 1 小时' },
  { value: '6h', label: '近 6 小时' },
  { value: '24h', label: '近 24 小时' },
  { value: '7d', label: '近 7 天' },
];
const SORT_OPTIONS: Array<{ value: BillingSortKey; label: string }> = [
  { value: 'started_at_desc', label: '最新优先' },
  { value: 'started_at_asc', label: '最早优先' },
  { value: 'tokens_desc', label: 'Token 从高到低' },
  { value: 'tokens_asc', label: 'Token 从低到高' },
  { value: 'duration_desc', label: '耗时从高到低' },
];
const TIME_PRESET_SET = new Set<TimePresetKey>(TIME_PRESET_OPTIONS.map((option) => option.value));
const SORT_SET = new Set<BillingSortKey>(SORT_OPTIONS.map((option) => option.value));

export function AdminBillingPage() {
  const overviewQuery = useQuery({ queryKey: ['admin-overview'], queryFn: fetchAdminOverview, refetchInterval: 10000 });
  const usageQuery = useQuery({ queryKey: ['admin-usage'], queryFn: fetchAdminUsage, refetchInterval: 10000 });
  const overview = overviewQuery.data || {};
  const items = usageQuery.data?.items || [];
  const savedState = readStorageJSON(STORAGE_KEY, {
    search: '',
    statusFilter: '',
    timePreset: 'all',
    sortBy: 'started_at_desc',
    pageSize: 20,
    visibleColumns: DEFAULT_VISIBLE_COLUMNS,
  });
  const [search, setSearch] = useState(savedState.search);
  const [statusFilter, setStatusFilter] = useState(savedState.statusFilter);
  const [timePreset, setTimePreset] = useState<TimePresetKey>(isTimePresetKey(savedState.timePreset) ? savedState.timePreset : 'all');
  const [sortBy, setSortBy] = useState<BillingSortKey>(isBillingSortKey(savedState.sortBy) ? savedState.sortBy : 'started_at_desc');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(savedState.pageSize || 20);
  const [visibleColumns, setVisibleColumns] = useState<Set<BillingColumnKey>>(new Set(savedState.visibleColumns || DEFAULT_VISIBLE_COLUMNS));
  const [showTools, setShowTools] = useState(false);

  const filteredItems = useMemo(() => {
    const keyword = search.trim().toLowerCase();
    const minStartedAt = resolvePresetStart(timePreset);
    const scopedItems = items.filter((item) => {
      if (minStartedAt !== null) {
        const startedAt = parseStartedAt(item.started_at);
        if (startedAt === null || startedAt < minStartedAt) return false;
      }
      if (keyword) {
        const haystack = [
          item.request_id,
          item.consumer_name,
          item.consumer_id,
          item.model,
          item.resolved_model,
          item.pool_name,
          item.route_url,
          item.error,
        ]
          .map((value) => String(value || '').toLowerCase())
          .join(' ');
        if (!haystack.includes(keyword)) return false;
      }
      if (statusFilter === 'ok') {
        if ((item.status_code || 0) >= 400 || item.error) return false;
      }
      if (statusFilter === 'error') {
        if ((item.status_code || 0) < 400 && !item.error) return false;
      }
      return true;
    });
    return [...scopedItems].sort((left, right) => compareUsageRows(left, right, sortBy));
  }, [items, search, sortBy, statusFilter, timePreset]);

  const totalPages = Math.max(1, Math.ceil(filteredItems.length / pageSize));
  const pagedItems = useMemo(() => {
    const start = (page - 1) * pageSize;
    return filteredItems.slice(start, start + pageSize);
  }, [filteredItems, page, pageSize]);

  useEffect(() => {
    writeStorageJSON(STORAGE_KEY, {
      search,
      statusFilter,
      timePreset,
      sortBy,
      pageSize,
      visibleColumns: Array.from(visibleColumns),
    });
  }, [pageSize, search, sortBy, statusFilter, timePreset, visibleColumns]);

  const successCount = filteredItems.filter((item) => (item.status_code || 0) < 400 && !item.error).length;
  const errorCount = filteredItems.length - successCount;
  const totalInputBytes = filteredItems.reduce((sum, item) => sum + Number(item.input_bytes || 0), 0);
  const totalOutputBytes = filteredItems.reduce((sum, item) => sum + Number(item.output_bytes || 0), 0);
  const totalTokens = filteredItems.reduce((sum, item) => sum + Number(item.total_tokens || 0), 0);
  const averageDuration = filteredItems.length
    ? Math.round(filteredItems.reduce((sum, item) => sum + Number(item.duration_ms || 0), 0) / filteredItems.length)
    : 0;
  const cacheTaggedCount = filteredItems.filter((item) => Boolean(item.local_cache_status || item.upstream_cache_status || Number(item.cache_read_tokens || 0))).length;
  const latestStartedAt = filteredItems.reduce<number | null>((latest, item) => {
    const current = parseStartedAt(item.started_at);
    if (current === null) return latest;
    if (latest === null || current > latest) return current;
    return latest;
  }, null);

  function toggleColumn(key: BillingColumnKey) {
    setVisibleColumns((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  function exportCurrentView() {
    const lines = [
      ['时间', '用户', '模型', '线路', 'Token', '请求字节', '响应字节', '状态'].join('\t'),
      ...filteredItems.map((item) => [
        item.started_at || '-',
        item.consumer_name || item.consumer_id || '-',
        item.model || item.resolved_model || '-',
        item.pool_name || item.route_url || '-',
        String(item.total_tokens || 0),
        String(item.input_bytes || 0),
        String(item.output_bytes || 0),
        String(item.error ? `${item.status_code || 0} · ${item.error}` : item.status_code || '-'),
      ].join('\t')),
    ].join('\n');
    const blob = new Blob([lines], { type: 'text/tab-separated-values;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'billing-usage.tsv';
    link.click();
    URL.revokeObjectURL(url);
  }

  return (
    <section className="grid-page">
      <div className="metrics-row">
        <Metric label="用户数" value={formatNumber(overview.user_count || 0)} />
        <Metric label="分组数" value={formatNumber(overview.group_count || 0)} />
        <Metric label="总 Token" value={formatTokenCount(overview.total_tokens || 0)} />
        <Metric label="错误请求" value={formatNumber(overview.error_count || 0)} />
      </div>
      <div className="key-stat-grid">
        <div className="key-stat"><div className="key-stat-icon blue"><Activity size={18} /></div><div><span>当前结果</span><strong>{formatNumber(filteredItems.length)}</strong><small>筛选后的请求数</small></div></div>
        <div className="key-stat"><div className="key-stat-icon green"><Wallet size={18} /></div><div><span>成功</span><strong>{formatNumber(successCount)}</strong><small>{filteredItems.length ? `${Math.round((successCount / filteredItems.length) * 100)}%` : '0%'}</small></div></div>
        <div className="key-stat"><div className="key-stat-icon amber"><Database size={18} /></div><div><span>筛选 Token</span><strong>{formatTokenCount(totalTokens)}</strong><small>当前筛选范围</small></div></div>
        <div className="key-stat"><div className="key-stat-icon rose"><TriangleAlert size={18} /></div><div><span>异常</span><strong>{formatNumber(errorCount)}</strong><small>{filteredItems.length ? `${Math.round((errorCount / filteredItems.length) * 100)}%` : '0%'}</small></div></div>
      </div>
      <div className="key-stat-grid">
        <div className="key-stat"><div className="key-stat-icon blue"><Users size={18} /></div><div><span>总用户</span><strong>{formatNumber(overview.user_count || 0)}</strong><small>来自管理总览</small></div></div>
        <div className="key-stat"><div className="key-stat-icon green"><Database size={18} /></div><div><span>累计 Token</span><strong>{formatTokenCount(overview.total_tokens || 0)}</strong><small>全局视角</small></div></div>
        <div className="key-stat"><div className="key-stat-icon amber"><Activity size={18} /></div><div><span>请求字节</span><strong>{formatByteCount(totalInputBytes)}</strong><small>当前筛选累计</small></div></div>
        <div className="key-stat"><div className="key-stat-icon slate"><Wallet size={18} /></div><div><span>响应字节</span><strong>{formatByteCount(totalOutputBytes)}</strong><small>当前筛选累计</small></div></div>
      </div>
      <div className="admin-ops-strip">
        <div className="admin-ops-item">
          <span>当前筛选</span>
          <strong>{statusFilter === 'ok' ? '仅成功' : statusFilter === 'error' ? '仅异常' : '全部请求'}</strong>
          <small>{search ? `关键词：${search}` : '未设置关键词'}</small>
        </div>
        <div className="admin-ops-item">
          <span>时间视角</span>
          <strong>{TIME_PRESET_OPTIONS.find((option) => option.value === timePreset)?.label || '全部时间'}</strong>
          <small>{latestStartedAt ? `最新请求 ${formatDateTime(latestStartedAt)}` : '当前无时间数据'}</small>
        </div>
        <div className="admin-ops-item">
          <span>排序方式</span>
          <strong>{SORT_OPTIONS.find((option) => option.value === sortBy)?.label || '最新优先'}</strong>
          <small>便于做排障、计费和高耗排查</small>
        </div>
        <div className="admin-ops-item">
          <span>缓存标记</span>
          <strong>{formatNumber(cacheTaggedCount)} 条</strong>
          <small>带本地或上游缓存信息</small>
        </div>
      </div>
      <div className="admin-ops-strip">
        <div className="admin-ops-item">
          <span>数据来源</span>
          <strong>真实 usage 请求</strong>
          <small>按请求、模型、线路和缓存状态聚合</small>
        </div>
        <div className="admin-ops-item">
          <span>字节规模</span>
          <strong>{formatByteCount(totalInputBytes + totalOutputBytes)}</strong>
          <small>请求与响应合计体积</small>
        </div>
        <div className="admin-ops-item">
          <span>平均耗时</span>
          <strong>{formatNumber(averageDuration)} ms</strong>
          <small>当前筛选结果均值</small>
        </div>
        <div className="admin-ops-item">
          <span>列表容量</span>
          <strong>{formatNumber(pageSize)} 条 / 页</strong>
          <small>匹配结果 {formatNumber(filteredItems.length)} 条</small>
        </div>
      </div>

      <TablePageLayout
        filters={
          <FilterToolbar
            right={
              <ToolbarButtonRow>
                <ActionButton onClick={() => { void overviewQuery.refetch(); void usageQuery.refetch(); }}><RefreshCw size={15} />刷新</ActionButton>
                <ColumnMenu
                  label="列设置"
                  items={[
                    { key: 'route', label: '线路', checked: visibleColumns.has('route'), onToggle: () => toggleColumn('route') },
                    { key: 'tokens', label: 'Token', checked: visibleColumns.has('tokens'), onToggle: () => toggleColumn('tokens') },
                    { key: 'input', label: '请求字节', checked: visibleColumns.has('input'), onToggle: () => toggleColumn('input') },
                    { key: 'output', label: '响应字节', checked: visibleColumns.has('output'), onToggle: () => toggleColumn('output') },
                    { key: 'status', label: '状态', checked: visibleColumns.has('status'), onToggle: () => toggleColumn('status') },
                  ]}
                />
                <details className="sub2-menu" open={showTools} onToggle={(event) => setShowTools((event.target as HTMLDetailsElement).open)}>
                  <summary>
                    <MoreHorizontal size={14} />
                    <span>更多工具</span>
                  </summary>
                  <div className="sub2-menu-panel">
                    <button type="button" onClick={() => { setSearch(''); setStatusFilter(''); setPage(1); setShowTools(false); }}>
                      <span>清空筛选</span>
                    </button>
                    <button type="button" onClick={() => { setTimePreset('24h'); setSortBy('tokens_desc'); setPage(1); setShowTools(false); }}>
                      <span>切到 24 小时高耗排行</span>
                    </button>
                    <button type="button" onClick={() => { setPageSize(50); setPage(1); setShowTools(false); }}>
                      <span>切换 50 / 页</span>
                    </button>
                    <button type="button" onClick={() => { exportCurrentView(); setShowTools(false); }}>
                      <span>导出当前视图</span>
                      <Download size={14} />
                    </button>
                    <button type="button" onClick={() => { setVisibleColumns(new Set(DEFAULT_VISIBLE_COLUMNS)); setShowTools(false); }}>
                      <span>重置列视图</span>
                      <Settings2 size={14} />
                    </button>
                  </div>
                </details>
              </ToolbarButtonRow>
            }
          >
            <SearchField value={search} placeholder="搜索用户 / 模型 / 线路 / 请求 ID" onChange={(value) => { setSearch(value); setPage(1); }} />
            <select className="select" value={statusFilter} onChange={(event) => { setStatusFilter(event.target.value); setPage(1); }}>
              <option value="">全部状态</option>
              <option value="ok">成功</option>
              <option value="error">异常</option>
            </select>
            <select className="select" value={timePreset} onChange={(event) => { setTimePreset(event.target.value as TimePresetKey); setPage(1); }}>
              {TIME_PRESET_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
            </select>
            <select className="select" value={sortBy} onChange={(event) => { setSortBy(event.target.value as BillingSortKey); setPage(1); }}>
              {SORT_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
            </select>
          </FilterToolbar>
        }
        table={
          <div className="table-wrap table-scroll">
            <table>
              <thead>
                <tr>
                  <th>时间</th>
                  <th>用户</th>
                  <th>模型</th>
                  {visibleColumns.has('route') ? <th>线路</th> : null}
                  {visibleColumns.has('tokens') ? <th>Token</th> : null}
                  {visibleColumns.has('input') ? <th>请求字节</th> : null}
                  {visibleColumns.has('output') ? <th>响应字节</th> : null}
                  {visibleColumns.has('status') ? <th>状态</th> : null}
                </tr>
              </thead>
              <tbody>
                {pagedItems.length ? pagedItems.map((item) => (
                  <tr key={item.request_id}>
                    <td><div className="sub2-cell-stack sub2-cell-stack-tight"><strong>{item.started_at || '-'}</strong><small>{item.request_id || '-'}</small></div></td>
                    <td><div className="sub2-cell-stack"><strong>{item.consumer_name || '-'}</strong><small>{item.consumer_preview || item.consumer_id || '-'}</small></div></td>
                    <td><div className="sub2-cell-stack"><strong>{item.model || '-'}</strong><small>{item.resolved_model || '-'}</small></div></td>
                    {visibleColumns.has('route') ? <td><div className="sub2-cell-stack"><strong>{item.pool_name || '-'}</strong><small>{item.route_url || '-'}</small></div></td> : null}
                    {visibleColumns.has('tokens') ? <td><div className="sub2-cell-stack sub2-cell-stack-tight"><strong>{formatTokenCount(item.total_tokens || 0)}</strong><small>读 {formatNumber(item.cache_read_tokens || 0)} / 写 {formatNumber(item.cache_write_tokens || 0)}</small></div></td> : null}
                    {visibleColumns.has('input') ? <td><strong className="sub2-number-cell">{formatByteCount(item.input_bytes || 0)}</strong></td> : null}
                    {visibleColumns.has('output') ? <td><strong className="sub2-number-cell">{formatByteCount(item.output_bytes || 0)}</strong></td> : null}
                    {visibleColumns.has('status') ? <td><div className="sub2-cell-stack sub2-cell-stack-tight"><strong>{maskEmpty(item.error ? `${item.status_code || 0} · ${item.error}` : item.status_code || '-')}</strong><small>{item.local_cache_status || item.upstream_cache_status || '无缓存标记'}</small></div></td> : null}
                  </tr>
                )) : (
                  <tr>
                    <td colSpan={3 + visibleColumns.size}>
                      <EmptyState title="暂无计费记录" description="当前基于真实请求的计费记录为空。" />
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
    </section>
  );
}

function resolvePresetStart(preset: TimePresetKey): number | null {
  if (preset === 'all') return null;
  const now = Date.now();
  if (preset === '1h') return now - 60 * 60 * 1000;
  if (preset === '6h') return now - 6 * 60 * 60 * 1000;
  if (preset === '24h') return now - 24 * 60 * 60 * 1000;
  return now - 7 * 24 * 60 * 60 * 1000;
}

function parseStartedAt(value?: string): number | null {
  if (!value) return null;
  const timestamp = Date.parse(value);
  return Number.isNaN(timestamp) ? null : timestamp;
}

function compareUsageRows(left: AdminUsageItem, right: AdminUsageItem, sortBy: BillingSortKey) {
  if (sortBy === 'started_at_asc') {
    return compareNumbers(parseStartedAt(left.started_at), parseStartedAt(right.started_at));
  }
  if (sortBy === 'tokens_desc') {
    return compareNumbers(Number(right.total_tokens || 0), Number(left.total_tokens || 0));
  }
  if (sortBy === 'tokens_asc') {
    return compareNumbers(Number(left.total_tokens || 0), Number(right.total_tokens || 0));
  }
  if (sortBy === 'duration_desc') {
    return compareNumbers(Number(right.duration_ms || 0), Number(left.duration_ms || 0));
  }
  return compareNumbers(parseStartedAt(right.started_at), parseStartedAt(left.started_at));
}

function compareNumbers(left: number | null, right: number | null) {
  const normalizedLeft = left ?? -1;
  const normalizedRight = right ?? -1;
  return normalizedLeft - normalizedRight;
}

function formatDateTime(timestamp: number) {
  return new Date(timestamp).toLocaleString('zh-CN', { hour12: false });
}

function isTimePresetKey(value: unknown): value is TimePresetKey {
  return typeof value === 'string' && TIME_PRESET_SET.has(value as TimePresetKey);
}

function isBillingSortKey(value: unknown): value is BillingSortKey {
  return typeof value === 'string' && SORT_SET.has(value as BillingSortKey);
}
