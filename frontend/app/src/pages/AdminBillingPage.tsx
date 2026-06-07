import { useEffect, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Download, Eye, MoreHorizontal, RefreshCw, Settings2 } from 'lucide-react';
import { fetchAdminBilling, fetchAdminOverview, fetchAdminUsage } from '../api';
import { Button, Field, Modal, ModalActions, TextArea, TextInput } from '../components';
import { ActionButton, ColumnMenu, EmptyState, FilterToolbar, Pager, RowAction, RowActions, SearchField, TablePageLayout, ToolbarButtonRow } from '../components/admin';
import type { AdminBillingAccountItem, AdminBillingGroupItem, AdminBillingOrderItem, AdminBillingPlanItem, AdminBillingSubscriptionItem, AdminUsageItem } from '../types';
import { formatByteCount, formatCost, formatNumber, formatTokenCount, formatUsdCost, maskEmpty, readStorageJSON, writeStorageJSON } from '../utils';

const STORAGE_KEY = 'admin-billing-view-state';

type BillingColumnKey = 'route' | 'tokens' | 'input' | 'output' | 'status';
type TimePresetKey = 'all' | '1h' | '6h' | '24h' | '7d';
type BillingSortKey = 'started_at_desc' | 'started_at_asc' | 'tokens_desc' | 'tokens_asc' | 'duration_desc';
type BillingScopeKey = 'usage' | 'account' | 'group' | 'plan' | 'subscription' | 'order';

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
  const now = new Date();
  const defaultDateTo = toDateTimeLocal(now);
  const defaultDateFrom = toDateTimeLocal(new Date(now.getTime() - 24 * 60 * 60 * 1000));
  const overviewQuery = useQuery({ queryKey: ['admin-overview'], queryFn: fetchAdminOverview, refetchInterval: 10000 });
  const savedState = readStorageJSON(STORAGE_KEY, {
    search: '',
    statusFilter: '',
    timePreset: 'all',
    dateFrom: defaultDateFrom,
    dateTo: defaultDateTo,
    sortBy: 'started_at_desc',
    pageSize: 20,
    visibleColumns: DEFAULT_VISIBLE_COLUMNS,
    scope: 'usage',
  });
  const [search, setSearch] = useState(savedState.search);
  const [statusFilter, setStatusFilter] = useState(savedState.statusFilter);
  const [timePreset, setTimePreset] = useState<TimePresetKey>(isTimePresetKey(savedState.timePreset) ? savedState.timePreset : 'all');
  const [dateFrom, setDateFrom] = useState(typeof savedState.dateFrom === 'string' ? savedState.dateFrom : defaultDateFrom);
  const [dateTo, setDateTo] = useState(typeof savedState.dateTo === 'string' ? savedState.dateTo : defaultDateTo);
  const [sortBy, setSortBy] = useState<BillingSortKey>(isBillingSortKey(savedState.sortBy) ? savedState.sortBy : 'started_at_desc');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(savedState.pageSize || 20);
  const [visibleColumns, setVisibleColumns] = useState<Set<BillingColumnKey>>(new Set(savedState.visibleColumns || DEFAULT_VISIBLE_COLUMNS));
  const [scope, setScope] = useState<BillingScopeKey>(isBillingScopeKey(savedState.scope) ? savedState.scope : 'usage');
  const [showTools, setShowTools] = useState(false);
  const [inspectUsage, setInspectUsage] = useState<AdminUsageItem | null>(null);
  const [inspectAggregate, setInspectAggregate] = useState<{ scope: BillingScopeKey; row: AdminBillingAccountItem | AdminBillingGroupItem | AdminBillingPlanItem | AdminBillingSubscriptionItem | AdminBillingOrderItem } | null>(null);
  const startedAfter = useMemo(() => resolveStartedAfter(timePreset, dateFrom), [dateFrom, timePreset]);
  const startedBefore = useMemo(() => resolveStartedBefore(timePreset, dateTo), [dateTo, timePreset]);
  const usageQuery = useQuery({
    queryKey: ['admin-usage', startedAfter, startedBefore],
    queryFn: () => fetchAdminUsage({ started_after: startedAfter, started_before: startedBefore }),
    refetchInterval: 10000,
  });
  const billingQuery = useQuery({
    queryKey: ['admin-billing', startedAfter, startedBefore],
    queryFn: () => fetchAdminBilling({ started_after: startedAfter, started_before: startedBefore }),
    refetchInterval: 10000,
  });
  const overview = overviewQuery.data || {};
  const items = usageQuery.data?.items || [];
  const billing = billingQuery.data;

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
      dateFrom,
      dateTo,
      sortBy,
      pageSize,
      visibleColumns: Array.from(visibleColumns),
      scope,
    });
  }, [dateFrom, dateTo, pageSize, scope, search, sortBy, statusFilter, timePreset, visibleColumns]);

  const billingSummary = billing?.summary || {};
  const billingAccounts = billing?.by_account || [];
  const billingGroups = billing?.by_group || [];
  const billingPlans = billing?.by_plan || [];
  const billingSubscriptions = billing?.by_subscription || [];
  const billingOrders = billing?.by_order || [];

  const aggregateRows = useMemo(() => {
    if (scope === 'account') return billingAccounts;
    if (scope === 'group') return billingGroups;
    if (scope === 'plan') return billingPlans;
    if (scope === 'subscription') return billingSubscriptions;
    if (scope === 'order') return billingOrders;
    return [];
  }, [billingAccounts, billingGroups, billingOrders, billingPlans, billingSubscriptions, scope]);

  const filteredAggregateRows = useMemo(() => {
    if (scope === 'usage') return [];
    const keyword = search.trim().toLowerCase();
    return aggregateRows.filter((item) => {
      if (!keyword) return true;
      const haystack = Object.values(item || {}).flatMap((value) => Array.isArray(value) ? value : [value]).map((value) => String(value || '').toLowerCase()).join(' ');
      if (!haystack.includes(keyword)) return false;
      if (statusFilter === 'ok' && Number((item as any).error_count || 0) > 0) return false;
      if (statusFilter === 'error' && Number((item as any).error_count || 0) <= 0) return false;
      return true;
    });
  }, [aggregateRows, scope, search, statusFilter]);

  const filteredRowsForPager = scope === 'usage' ? filteredItems : filteredAggregateRows;
  const scopedTotalPages = Math.max(1, Math.ceil(filteredRowsForPager.length / pageSize));
  const pagedAggregateRows = useMemo(() => {
    if (scope === 'usage') return [];
    const start = (page - 1) * pageSize;
    return filteredAggregateRows.slice(start, start + pageSize);
  }, [filteredAggregateRows, page, pageSize, scope]);

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
  const summaryRequestCount = Number(billingSummary.request_count || 0);
  const summaryErrorCount = Number(billingSummary.error_count || 0);
  const summaryTotalTokens = Number(billingSummary.total_tokens || 0);
  const summaryInputBytes = Number(billingSummary.input_bytes || 0);
  const summaryOutputBytes = Number(billingSummary.output_bytes || 0);
  const summaryCoveredRequests = Number(billingSummary.covered_request_count || 0);
  const summaryActiveSubscriptions = Number(billingSummary.active_subscription_count || 0);

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
      ...(scope === 'usage'
        ? [
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
          ]
        : [
            ['名称', '归属', '请求', 'Token', '请求字节', '响应字节', '标准成本', '用户计费', '账户计费', '异常'].join('\t'),
            ...filteredAggregateRows.map((row) => {
              const meta = resolveAggregateMeta(scope, row);
              return [
                meta.title,
                `${meta.owner} ${meta.ownerExtra}`.trim(),
                String(Number((row as any).request_count || 0)),
                String(Number((row as any).total_tokens || 0)),
                String(Number((row as any).input_bytes || 0)),
                String(Number((row as any).output_bytes || 0)),
                String(Number((row as any).total_cost || 0)),
                String(Number((row as any).actual_cost || 0)),
                String(Number((row as any).account_cost || 0)),
                String(Number((row as any).error_count || 0)),
              ].join('\t');
            }),
          ]),
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
      <div className="sub2-page-head">
        <div className="sub2-page-title">
          <strong>计费管理</strong>
          <span>基于真实请求、订阅和支付订单查看消费归因，保持和 SUB2 一致的计费分析视图。</span>
        </div>
        <div className="sub2-inline-summary">
          <div className="sub2-inline-summary-item"><span>请求总数</span><strong>{formatNumber(summaryRequestCount)}</strong><small>当前页 {formatNumber(filteredRowsForPager.length)}</small></div>
          <div className="sub2-inline-summary-item"><span>成功 / 异常</span><strong>{formatNumber(Math.max(0, summaryRequestCount - summaryErrorCount))} / {formatNumber(summaryErrorCount)}</strong><small>{TIME_PRESET_OPTIONS.find((option) => option.value === timePreset)?.label || '全部时间'}</small></div>
          <div className="sub2-inline-summary-item"><span>总 Token</span><strong>{formatTokenCount(summaryTotalTokens)}</strong><small>当前筛选 {formatTokenCount(totalTokens)}</small></div>
          <div className="sub2-inline-summary-item"><span>标准成本</span><strong>{formatUsdCost(billingSummary.total_cost || 0)}</strong><small>实际计费 {formatUsdCost(billingSummary.actual_cost || 0)}</small></div>
          <div className="sub2-inline-summary-item"><span>账户计费</span><strong>{formatUsdCost(billingSummary.account_cost || 0)}</strong><small>覆盖请求 {formatNumber(summaryCoveredRequests)}</small></div>
          <div className="sub2-inline-summary-item"><span>活跃订阅</span><strong>{formatNumber(summaryActiveSubscriptions)}</strong><small>总账户 {formatNumber(overview.account_count || 0)}</small></div>
        </div>
      </div>

      <TablePageLayout
        filters={
          <FilterToolbar
            right={
              <ToolbarButtonRow>
                <ActionButton onClick={() => { void overviewQuery.refetch(); void usageQuery.refetch(); }}><RefreshCw size={15} />刷新</ActionButton>
                <ActionButton onClick={() => { void billingQuery.refetch(); }} tone="ghost">账单聚合</ActionButton>
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
                    <button type="button" onClick={() => { setTimePreset('all'); setDateFrom(defaultDateFrom); setDateTo(defaultDateTo); setPage(1); setShowTools(false); }}>
                      <span>重置时间范围</span>
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
            <SearchField value={search} placeholder="搜索账户 / 模型 / 线路 / 请求 ID" onChange={(value) => { setSearch(value); setPage(1); }} />
            <select className="select" value={statusFilter} onChange={(event) => { setStatusFilter(event.target.value); setPage(1); }}>
              <option value="">全部状态</option>
              <option value="ok">成功</option>
              <option value="error">异常</option>
            </select>
            <select className="select" value={timePreset} onChange={(event) => { setTimePreset(event.target.value as TimePresetKey); setPage(1); }}>
              {TIME_PRESET_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
            </select>
            <input className="input" type="datetime-local" value={dateFrom} onChange={(event) => { setDateFrom(event.target.value); setTimePreset('all'); setPage(1); }} />
            <input className="input" type="datetime-local" value={dateTo} onChange={(event) => { setDateTo(event.target.value); setTimePreset('all'); setPage(1); }} />
            <select className="select" value={scope} onChange={(event) => { setScope(event.target.value as BillingScopeKey); setPage(1); }}>
              <option value="usage">请求明细</option>
              <option value="account">按账户</option>
              <option value="group">按分组</option>
              <option value="plan">按计划</option>
              <option value="subscription">按订阅</option>
              <option value="order">按订单</option>
            </select>
            <select className="select" value={sortBy} onChange={(event) => { setSortBy(event.target.value as BillingSortKey); setPage(1); }}>
              {SORT_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
            </select>
          </FilterToolbar>
        }
        table={
          <div className="table-wrap table-scroll">
            {scope === 'usage' ? (
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
                    <th>成本</th>
                    {visibleColumns.has('status') ? <th>状态</th> : null}
                    <th>操作</th>
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
                      <td><div className="sub2-cell-stack sub2-cell-stack-tight"><strong>{formatUsdCost(item.actual_cost || item.total_cost || 0)}</strong><small>标准 {formatUsdCost(item.total_cost || 0)} / 账户 {formatUsdCost(item.account_cost || 0)}</small></div></td>
                      {visibleColumns.has('status') ? <td><div className="sub2-cell-stack sub2-cell-stack-tight"><strong>{maskEmpty(item.error ? `${item.status_code || 0} · ${item.error}` : item.status_code || '-')}</strong><small>{item.local_cache_status || item.upstream_cache_status || '无缓存标记'}</small></div></td> : null}
                      <td>
                        <RowActions>
                          <RowAction icon={Eye} label="详情" onClick={() => setInspectUsage(item)} />
                        </RowActions>
                      </td>
                    </tr>
                  )) : (
                    <tr>
                      <td colSpan={5 + visibleColumns.size}>
                        <EmptyState title="暂无计费记录" description="当前基于真实请求的计费记录为空。" />
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            ) : (
              <AggregateBillingTable
                scope={scope}
                rows={pagedAggregateRows}
                onInspect={(row) => setInspectAggregate({ scope, row })}
              />
            )}
          </div>
        }
        pagination={
          filteredRowsForPager.length ? (
            <Pager
              page={Math.min(page, scopedTotalPages)}
              pageSize={pageSize}
              total={filteredRowsForPager.length}
              onPageChange={(next) => setPage(Math.min(Math.max(1, next), scopedTotalPages))}
              onPageSizeChange={(next) => { setPageSize(next); setPage(1); }}
            />
          ) : null
        }
      />

      {inspectUsage ? (
        <Modal
          title="请求账单详情"
          size="lg"
          onClose={() => setInspectUsage(null)}
          footer={<ModalActions><Button onClick={() => setInspectUsage(null)}>关闭</Button></ModalActions>}
        >
          <div className="admin-dialog">
            <div className="admin-dialog-intro">
              <strong>{inspectUsage.request_id}</strong>
              <span>查看这次请求的消费归因、线路、缓存与异常信息，便于核对真实计费来源。</span>
            </div>
            <div className="admin-dialog-summary">
              <div className="admin-dialog-summary-card">
                <span>账户</span>
                <strong>{inspectUsage.consumer_name || inspectUsage.consumer_id || '-'}</strong>
                <small>{inspectUsage.consumer_preview || inspectUsage.consumer_type || '-'}</small>
              </div>
              <div className="admin-dialog-summary-card">
                <span>模型</span>
                <strong>{inspectUsage.model || inspectUsage.resolved_model || '-'}</strong>
                <small>{inspectUsage.resolved_model || '-'}</small>
              </div>
              <div className="admin-dialog-summary-card">
                <span>成本</span>
                <strong>{formatUsdCost(inspectUsage.actual_cost || inspectUsage.total_cost || 0)}</strong>
                <small>账户 {formatUsdCost(inspectUsage.account_cost || 0)}</small>
              </div>
            </div>
            <div className="admin-dialog-section">
              <div className="admin-dialog-section-head">
                <strong>请求信息</strong>
                <span>这里展示计费最关键的时间、线路和订阅归因</span>
              </div>
              <div className="admin-dialog-grid">
                <Field label="开始时间"><TextInput readOnly value={inspectUsage.started_at || '-'} /></Field>
                <Field label="耗时"><TextInput readOnly value={`${formatNumber(inspectUsage.duration_ms || 0)} ms`} /></Field>
                <Field label="线路"><TextInput readOnly value={inspectUsage.pool_name || inspectUsage.route_url || '-'} /></Field>
                <Field label="订阅"><TextInput readOnly value={inspectUsage.subscription_id || '-'} /></Field>
                <Field label="计划"><TextInput readOnly value={inspectUsage.plan_name || inspectUsage.plan_id || '-'} /></Field>
                <Field label="分组"><TextInput readOnly value={inspectUsage.group_name || inspectUsage.group_id || '-'} /></Field>
              </div>
            </div>
            <div className="admin-dialog-section">
              <div className="admin-dialog-section-head">
                <strong>用量与缓存</strong>
                <span>请求量、响应量和缓存标记都在这里汇总</span>
              </div>
              <div className="admin-dialog-grid">
                <Field label="总 Token"><TextInput readOnly value={String(inspectUsage.total_tokens || 0)} /></Field>
                <Field label="请求字节"><TextInput readOnly value={String(inspectUsage.input_bytes || 0)} /></Field>
                <Field label="响应字节"><TextInput readOnly value={String(inspectUsage.output_bytes || 0)} /></Field>
                <Field label="缓存读取 Token"><TextInput readOnly value={String(inspectUsage.cache_read_tokens || 0)} /></Field>
                <Field label="缓存写入 Token"><TextInput readOnly value={String(inspectUsage.cache_write_tokens || 0)} /></Field>
                <Field label="缓存状态"><TextInput readOnly value={inspectUsage.local_cache_status || inspectUsage.upstream_cache_status || '无缓存标记'} /></Field>
              </div>
            </div>
            <Field label="异常信息" full>
              <TextArea readOnly rows={5} value={inspectUsage.error || '-'} />
            </Field>
          </div>
        </Modal>
      ) : null}

      {inspectAggregate ? (
        <Modal
          title="聚合账单详情"
          size="lg"
          onClose={() => setInspectAggregate(null)}
          footer={<ModalActions><Button onClick={() => setInspectAggregate(null)}>关闭</Button></ModalActions>}
        >
          <AggregateBillingDetail scope={inspectAggregate.scope} row={inspectAggregate.row} />
        </Modal>
      ) : null}
    </section>
  );
}

function AggregateBillingTable({
  scope,
  rows,
  onInspect,
}: {
  scope: BillingScopeKey;
  rows: Array<AdminBillingAccountItem | AdminBillingGroupItem | AdminBillingPlanItem | AdminBillingSubscriptionItem | AdminBillingOrderItem>;
  onInspect: (row: AdminBillingAccountItem | AdminBillingGroupItem | AdminBillingPlanItem | AdminBillingSubscriptionItem | AdminBillingOrderItem) => void;
}) {
  if (!rows.length) {
    return <EmptyState title="暂无聚合账单" description="当前筛选条件下没有聚合结果。" />;
  }
  return (
    <table>
      <thead>
        <tr>
          <th>{scope === 'account' ? '账户' : scope === 'group' ? '分组' : scope === 'plan' ? '计划' : scope === 'subscription' ? '订阅' : '订单'}</th>
          <th>归属</th>
          <th>请求</th>
          <th>Token</th>
          <th>请求字节</th>
          <th>响应字节</th>
          <th>标准成本</th>
          <th>实际计费</th>
          <th>账户计费</th>
          <th>异常</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => {
          const meta = resolveAggregateMeta(scope, row);
          return (
            <tr key={meta.key}>
              <td><div className="sub2-cell-stack"><strong>{meta.title}</strong><small>{meta.subtitle}</small></div></td>
              <td><div className="sub2-cell-stack sub2-cell-stack-tight"><strong>{meta.owner}</strong><small>{meta.ownerExtra}</small></div></td>
              <td><strong className="sub2-number-cell">{formatNumber(Number((row as any).request_count || 0))}</strong></td>
              <td><strong className="sub2-number-cell">{formatTokenCount(Number((row as any).total_tokens || 0))}</strong></td>
              <td><strong className="sub2-number-cell">{formatByteCount(Number((row as any).input_bytes || 0))}</strong></td>
              <td><strong className="sub2-number-cell">{formatByteCount(Number((row as any).output_bytes || 0))}</strong></td>
              <td><strong className="sub2-number-cell">{formatUsdCost(Number((row as any).total_cost || 0))}</strong></td>
              <td><strong className="sub2-number-cell">{formatUsdCost(Number((row as any).actual_cost || 0))}</strong></td>
              <td><strong className="sub2-number-cell">{formatUsdCost(Number((row as any).account_cost || 0))}</strong></td>
              <td><strong className="sub2-number-cell">{formatNumber(Number((row as any).error_count || 0))}</strong></td>
              <td>
                <RowActions>
                  <RowAction icon={Eye} label="详情" onClick={() => onInspect(row)} />
                </RowActions>
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function resolveAggregateMeta(
  scope: BillingScopeKey,
  row: AdminBillingAccountItem | AdminBillingGroupItem | AdminBillingPlanItem | AdminBillingSubscriptionItem | AdminBillingOrderItem,
) {
  if (scope === 'account') {
    const item = row as AdminBillingAccountItem;
    return {
      key: item.account_id,
      title: item.account_name || item.account_id,
      subtitle: item.account_id,
      owner: (item.group_names || []).join(' / ') || '-',
      ownerExtra: (item.plan_names || []).join(' / ') || '-',
    };
  }
  if (scope === 'group') {
    const item = row as AdminBillingGroupItem;
    return {
      key: item.group_id || item.group_name || 'group',
      title: item.group_name || item.group_id || '未分组',
      subtitle: item.group_id || '-',
      owner: `${formatNumber(item.account_ids?.length || 0)} 账户`,
      ownerExtra: `${formatNumber(item.subscription_ids?.length || 0)} 订阅`,
    };
  }
  if (scope === 'plan') {
    const item = row as AdminBillingPlanItem;
    return {
      key: item.plan_id || item.plan_name || 'plan',
      title: item.plan_name || item.plan_id || '未关联计划',
      subtitle: item.plan_id || '-',
      owner: item.group_name || item.group_id || '-',
      ownerExtra: `计划价格 ${formatCost(Number(item.plan_price_cents || 0) / 100, 2)}`,
    };
  }
  if (scope === 'subscription') {
    const item = row as AdminBillingSubscriptionItem;
    return {
      key: item.subscription_id,
      title: item.plan_name || item.subscription_id,
      subtitle: item.subscription_id,
      owner: item.account_name || item.account_id || '-',
      ownerExtra: `${item.group_name || item.group_id || '-'} · ${item.status || '-'}`,
    };
  }
  const item = row as AdminBillingOrderItem;
  return {
    key: item.order_id,
    title: item.order_id,
    subtitle: item.channel_name || item.channel_id || '-',
    owner: item.account_name || item.account_id || '-',
    ownerExtra: `${item.plan_name || item.plan_id || '-'} · ${item.status || '-'}`,
  };
}

function AggregateBillingDetail({
  scope,
  row,
}: {
  scope: BillingScopeKey;
  row: AdminBillingAccountItem | AdminBillingGroupItem | AdminBillingPlanItem | AdminBillingSubscriptionItem | AdminBillingOrderItem;
}) {
  const meta = resolveAggregateMeta(scope, row);
  return (
    <div className="admin-dialog">
      <div className="admin-dialog-intro">
        <strong>{meta.title}</strong>
        <span>查看该聚合对象在当前时间范围内的请求量、成本和归属信息。</span>
      </div>
      <div className="admin-dialog-summary">
        <div className="admin-dialog-summary-card">
          <span>归属</span>
          <strong>{meta.owner}</strong>
          <small>{meta.ownerExtra}</small>
        </div>
        <div className="admin-dialog-summary-card">
          <span>请求</span>
          <strong>{formatNumber(Number((row as any).request_count || 0))}</strong>
          <small>异常 {formatNumber(Number((row as any).error_count || 0))}</small>
        </div>
        <div className="admin-dialog-summary-card">
          <span>总 Token</span>
          <strong>{formatTokenCount(Number((row as any).total_tokens || 0))}</strong>
          <small>账户计费 {formatUsdCost(Number((row as any).account_cost || 0))}</small>
        </div>
      </div>
      <div className="admin-dialog-section">
        <div className="admin-dialog-section-head">
          <strong>核心指标</strong>
          <span>和当前列表中的汇总保持一致，但集中展示便于核账</span>
        </div>
        <div className="admin-dialog-grid">
          <Field label="请求字节"><TextInput readOnly value={String(Number((row as any).input_bytes || 0))} /></Field>
          <Field label="响应字节"><TextInput readOnly value={String(Number((row as any).output_bytes || 0))} /></Field>
          <Field label="标准成本"><TextInput readOnly value={String(Number((row as any).total_cost || 0))} /></Field>
          <Field label="实际计费"><TextInput readOnly value={String(Number((row as any).actual_cost || 0))} /></Field>
          <Field label="账户计费"><TextInput readOnly value={String(Number((row as any).account_cost || 0))} /></Field>
          <Field label="补充标识"><TextInput readOnly value={meta.subtitle || '-'} /></Field>
        </div>
      </div>
      <Field label="原始数据" full>
        <TextArea readOnly rows={10} value={JSON.stringify(row, null, 2)} />
      </Field>
    </div>
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

function isBillingScopeKey(value: unknown): value is BillingScopeKey {
  return typeof value === 'string' && ['usage', 'account', 'group', 'plan', 'subscription', 'order'].includes(value);
}

function toDateTimeLocal(date: Date) {
  const pad = (value: number) => String(value).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function resolveStartedAfter(preset: TimePresetKey, dateFrom: string) {
  const presetStart = resolvePresetStart(preset);
  if (presetStart !== null) return new Date(presetStart).toISOString();
  return dateFrom ? new Date(dateFrom).toISOString() : '';
}

function resolveStartedBefore(preset: TimePresetKey, dateTo: string) {
  if (preset !== 'all') return new Date().toISOString();
  return dateTo ? new Date(dateTo).toISOString() : '';
}
