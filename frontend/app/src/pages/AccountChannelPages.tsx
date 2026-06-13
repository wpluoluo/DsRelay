import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Eye, RefreshCw } from 'lucide-react';
import { fetchAccountUsage, updateAccountProfile } from '../api';
import { Badge, Button, Field, Modal, ModalActions, Select, TextArea, TextInput } from '../components';
import { ColumnMenu, FilterToolbar, ListEmptyRow, Pager, RowAction, RowActions, SearchField, TablePageLayout, ToolbarButtonRow, ToolsMenu } from '../components/admin';
import { buildPageIntro } from '../navigation';
import { useAccountCenter } from '../state/accountCenterContext';
import { useDashboard } from '../state/dashboardContext';
import type { AdminChannel, AdminChannelPricing, RouteObservability } from '../types';
import { formatByteCount, formatNumber, formatPercent, formatTokenCount, formatUsdCost, maskEmpty, readStorageJSON, writeStorageJSON } from '../utils';

type StatusFilter = '' | 'enabled' | 'disabled';
type RouteStatusFilter = '' | 'ok' | 'degraded';
type AvailableChannelColumnKey = 'platform' | 'groups' | 'models' | 'pricing' | 'status';
type AvailableChannelFilterKey = 'group' | 'status';
type MonitorColumnKey = 'status' | 'requests' | 'cache' | 'sessions' | 'reason';
type MonitorFilterKey = 'status';
type ProfileDraft = {
  name: string;
  email: string;
  username: string;
  password: string;
};

const DEFAULT_AVAILABLE_VISIBLE_COLUMNS: AvailableChannelColumnKey[] = ['platform', 'groups', 'models', 'pricing', 'status'];
const DEFAULT_AVAILABLE_VISIBLE_FILTERS: AvailableChannelFilterKey[] = ['group', 'status'];
const DEFAULT_MONITOR_VISIBLE_COLUMNS: MonitorColumnKey[] = ['status', 'requests', 'cache', 'sessions', 'reason'];
const DEFAULT_MONITOR_VISIBLE_FILTERS: MonitorFilterKey[] = ['status'];
const AVAILABLE_CHANNELS_STORAGE_KEY = 'account-available-channels-view-state';
const ACCOUNT_MONITOR_STORAGE_KEY = 'account-monitor-view-state';

export function AccountAvailableChannelsPage() {
  const { groups, visibleAvailableChannels, reload } = useAccountCenter();
  const savedState = readStorageJSON(AVAILABLE_CHANNELS_STORAGE_KEY, {
    search: '',
    statusFilter: '' as StatusFilter,
    groupFilter: '',
    pageSize: 20,
    visibleColumns: DEFAULT_AVAILABLE_VISIBLE_COLUMNS,
    visibleFilters: DEFAULT_AVAILABLE_VISIBLE_FILTERS,
  });

  const [search, setSearch] = useState(savedState.search || '');
  const [statusFilter, setStatusFilter] = useState<StatusFilter>(savedState.statusFilter || '');
  const [groupFilter, setGroupFilter] = useState(savedState.groupFilter || '');
  const [inspectChannel, setInspectChannel] = useState<AdminChannel | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(savedState.pageSize || 20);
  const [visibleColumns, setVisibleColumns] = useState<Set<AvailableChannelColumnKey>>(new Set(savedState.visibleColumns || DEFAULT_AVAILABLE_VISIBLE_COLUMNS));
  const [visibleFilters, setVisibleFilters] = useState<Set<AvailableChannelFilterKey>>(new Set(savedState.visibleFilters || DEFAULT_AVAILABLE_VISIBLE_FILTERS));

  const allowedGroupIds = groups.map((group) => group.id);
  const channelRows = useMemo(() => {
    const keyword = search.trim().toLowerCase();
    return visibleAvailableChannels.filter((item) => {
      const channelGroupIds = item.group_ids || [];
      const visibleByGroup = !allowedGroupIds.length || !channelGroupIds.length || channelGroupIds.some((groupId) => allowedGroupIds.includes(groupId));
      if (!visibleByGroup) return false;
      if (statusFilter === 'enabled' && item.enabled === false) return false;
      if (statusFilter === 'disabled' && item.enabled !== false) return false;
      if (groupFilter && !channelGroupIds.includes(groupFilter)) return false;
      if (!keyword) return true;
      const haystack = [
        item.name,
        item.description,
        item.platform,
        item.billing_model_source,
        ...(item.group_names || []),
        ...(item.model_pricing || []).map((price) => price.model),
      ]
        .map((value) => String(value || '').toLowerCase())
        .join(' ');
      return haystack.includes(keyword);
    });
  }, [allowedGroupIds, groupFilter, search, statusFilter, visibleAvailableChannels]);

  const totalPages = Math.max(1, Math.ceil(channelRows.length / pageSize));
  const pagedRows = useMemo(() => {
    const start = (page - 1) * pageSize;
    return channelRows.slice(start, start + pageSize);
  }, [channelRows, page, pageSize]);
  useEffect(() => {
    writeStorageJSON(AVAILABLE_CHANNELS_STORAGE_KEY, {
      search,
      statusFilter,
      groupFilter,
      pageSize,
      visibleColumns: Array.from(visibleColumns),
      visibleFilters: Array.from(visibleFilters),
    });
  }, [groupFilter, pageSize, search, statusFilter, visibleColumns, visibleFilters]);

  function toggleColumn(key: AvailableChannelColumnKey) {
    setVisibleColumns((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  function toggleFilter(key: AvailableChannelFilterKey) {
    setVisibleFilters((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  return (
    <section className="grid-page">
      {buildPageIntro('/available-channels')}

      <TablePageLayout
        filters={(
          <FilterToolbar
            right={(
              <ToolbarButtonRow>
                <Button onClick={() => void reload()}><RefreshCw size={15} />刷新</Button>
                <ToolsMenu label="筛选设置" icon={false}>
                  <button type="button" onClick={() => toggleFilter('group')}>
                    <span>分组</span>
                    <strong>{visibleFilters.has('group') ? '✓' : ''}</strong>
                  </button>
                  <button type="button" onClick={() => toggleFilter('status')}>
                    <span>状态</span>
                    <strong>{visibleFilters.has('status') ? '✓' : ''}</strong>
                  </button>
                </ToolsMenu>
                <ColumnMenu
                  label="列设置"
                  items={[
                    { key: 'platform', label: '平台', checked: visibleColumns.has('platform'), onToggle: () => toggleColumn('platform') },
                    { key: 'groups', label: '分组', checked: visibleColumns.has('groups'), onToggle: () => toggleColumn('groups') },
                    { key: 'models', label: '支持模型', checked: visibleColumns.has('models'), onToggle: () => toggleColumn('models') },
                    { key: 'pricing', label: '计费', checked: visibleColumns.has('pricing'), onToggle: () => toggleColumn('pricing') },
                    { key: 'status', label: '状态', checked: visibleColumns.has('status'), onToggle: () => toggleColumn('status') },
                  ]}
                />
                <ToolsMenu>
                  <button type="button" onClick={() => { setSearch(''); setStatusFilter(''); setGroupFilter(''); setPage(1); }}>
                    <span>清空筛选</span>
                  </button>
                  <button type="button" onClick={() => { setStatusFilter('enabled'); setPage(1); }}>
                    <span>仅看启用渠道</span>
                  </button>
                  <button type="button" onClick={() => { setPageSize(50); setPage(1); }}>
                    <span>切换 50 / 页</span>
                  </button>
                </ToolsMenu>
              </ToolbarButtonRow>
            )}
          >
            <SearchField value={search} placeholder="搜索渠道 / 平台 / 分组 / 模型" onChange={(value) => { setSearch(value); setPage(1); }} />
            {visibleFilters.has('group') ? (
              <Select value={groupFilter} onChange={(event) => { setGroupFilter(event.target.value); setPage(1); }}>
                <option value="">全部分组</option>
                {groups
                  .filter((group) => !allowedGroupIds.length || allowedGroupIds.includes(group.id))
                  .map((group) => <option key={group.id} value={group.id}>{group.name}</option>)}
              </Select>
            ) : null}
            {visibleFilters.has('status') ? (
              <Select value={statusFilter} onChange={(event) => { setStatusFilter(event.target.value as StatusFilter); setPage(1); }}>
                <option value="">全部状态</option>
                <option value="enabled">启用</option>
                <option value="disabled">停用</option>
              </Select>
            ) : null}
          </FilterToolbar>
        )}
        table={(
          <div className="table-wrap table-scroll">
            <table>
              <thead>
                <tr>
                  <th>渠道</th>
                  {visibleColumns.has('platform') ? <th>平台</th> : null}
                  {visibleColumns.has('groups') ? <th>分组</th> : null}
                  {visibleColumns.has('models') ? <th>支持模型</th> : null}
                  {visibleColumns.has('pricing') ? <th>计费</th> : null}
                  {visibleColumns.has('status') ? <th>状态</th> : null}
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {pagedRows.length ? pagedRows.map((item) => (
                  <tr key={item.id}>
                    <td>
                      <div className="sub2-cell-stack">
                        <strong>{item.name}</strong>
                        <small>{item.description || item.id}</small>
                      </div>
                    </td>
                    {visibleColumns.has('platform') ? <td>{item.platform || '-'}</td> : null}
                    {visibleColumns.has('groups') ? (
                      <td>
                        <div className="sub2-cell-stack sub2-cell-stack-tight">
                          <strong>{formatNumber(item.group_count || item.group_ids?.length || 0)}</strong>
                          <small>{item.group_names?.join(' / ') || '-'}</small>
                        </div>
                      </td>
                    ) : null}
                    {visibleColumns.has('models') ? <td><PricingModels rows={item.model_pricing || []} /></td> : null}
                    {visibleColumns.has('pricing') ? <td><strong className="sub2-number-cell">{formatNumber(item.pricing_count || item.model_pricing?.length || 0)}</strong></td> : null}
                    {visibleColumns.has('status') ? <td><Badge tone={item.enabled === false ? 'warn' : 'ok'}>{item.enabled === false ? '停用' : '启用'}</Badge></td> : null}
                    <td>
                      <RowActions>
                        <RowAction icon={Eye} label="详情" onClick={() => setInspectChannel(item)} />
                      </RowActions>
                    </td>
                  </tr>
                )) : (
                  <ListEmptyRow colSpan={visibleColumns.size + 2} title="暂无可用渠道" />
                )}
              </tbody>
            </table>
          </div>
        )}
        pagination={channelRows.length ? (
          <Pager
            page={Math.min(page, totalPages)}
            pageSize={pageSize}
            total={channelRows.length}
            onPageChange={(next) => setPage(Math.min(Math.max(1, next), totalPages))}
            onPageSizeChange={(next) => { setPageSize(next); setPage(1); }}
          />
        ) : null}
      />

      {inspectChannel ? (
        <Modal
          title="渠道详情"
          size="lg"
          onClose={() => setInspectChannel(null)}
          footer={<ModalActions><Button onClick={() => setInspectChannel(null)}>关闭</Button></ModalActions>}
        >
          <div className="admin-dialog">
            <div className="admin-dialog-intro"><strong>{inspectChannel.name}</strong></div>
            <div className="admin-dialog-summary">
              <div className="admin-dialog-summary-card"><span>平台</span><strong>{inspectChannel.platform || '-'}</strong><small>{inspectChannel.billing_model_source || '-'}</small></div>
              <div className="admin-dialog-summary-card"><span>分组</span><strong>{formatNumber(inspectChannel.group_count || 0)}</strong><small>{inspectChannel.group_names?.join(' / ') || '-'}</small></div>
              <div className="admin-dialog-summary-card"><span>价格规则</span><strong>{formatNumber(inspectChannel.pricing_count || 0)}</strong><small>套餐 {formatNumber(inspectChannel.plan_count || 0)}</small></div>
            </div>
            <Field label="描述" full><TextArea readOnly rows={3} value={inspectChannel.description || '-'} /></Field>
            <Field label="模型价格" full><TextArea readOnly rows={8} value={pricingText(inspectChannel.model_pricing || []) || '-'} /></Field>
          </div>
        </Modal>
      ) : null}
    </section>
  );
}

export function AccountMonitorPage() {
  const dashboard = useDashboard();
  const savedState = readStorageJSON(ACCOUNT_MONITOR_STORAGE_KEY, {
    search: '',
    statusFilter: '' as RouteStatusFilter,
    pageSize: 20,
    visibleColumns: DEFAULT_MONITOR_VISIBLE_COLUMNS,
    visibleFilters: DEFAULT_MONITOR_VISIBLE_FILTERS,
  });

  const [search, setSearch] = useState(savedState.search || '');
  const [statusFilter, setStatusFilter] = useState<RouteStatusFilter>(savedState.statusFilter || '');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(savedState.pageSize || 20);
  const [visibleColumns, setVisibleColumns] = useState<Set<MonitorColumnKey>>(new Set(savedState.visibleColumns || DEFAULT_MONITOR_VISIBLE_COLUMNS));
  const [visibleFilters, setVisibleFilters] = useState<Set<MonitorFilterKey>>(new Set(savedState.visibleFilters || DEFAULT_MONITOR_VISIBLE_FILTERS));
  const [inspectRoute, setInspectRoute] = useState<RouteObservability | null>(null);

  const routes = dashboard.state.route_observability || [];
  const rows = useMemo(() => {
    const keyword = search.trim().toLowerCase();
    return routes.filter((item) => {
      const errorCount = Number(item.error_count || 0);
      const cooling = item.cooling === true;
      if (statusFilter === 'ok' && (errorCount > 0 || cooling)) return false;
      if (statusFilter === 'degraded' && errorCount <= 0 && !cooling) return false;
      if (!keyword) return true;
      const haystack = [
        item.pool_name,
        item.route_url,
        item.route_status_text,
        item.route_status_note,
        item.last_reason,
      ]
        .map((value) => String(value || '').toLowerCase())
        .join(' ');
      return haystack.includes(keyword);
    });
  }, [routes, search, statusFilter]);

  const totalPages = Math.max(1, Math.ceil(rows.length / pageSize));
  const pagedRows = useMemo(() => {
    const start = (page - 1) * pageSize;
    return rows.slice(start, start + pageSize);
  }, [page, pageSize, rows]);
  useEffect(() => {
    writeStorageJSON(ACCOUNT_MONITOR_STORAGE_KEY, {
      search,
      statusFilter,
      pageSize,
      visibleColumns: Array.from(visibleColumns),
      visibleFilters: Array.from(visibleFilters),
    });
  }, [pageSize, search, statusFilter, visibleColumns, visibleFilters]);

  function toggleColumn(key: MonitorColumnKey) {
    setVisibleColumns((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  function toggleFilter(key: MonitorFilterKey) {
    setVisibleFilters((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  return (
    <section className="grid-page">
      {buildPageIntro('/monitor')}

      <TablePageLayout
        filters={(
          <FilterToolbar
            right={(
              <ToolbarButtonRow>
                <Button onClick={() => void dashboard.stateQuery.refetch()}><RefreshCw size={15} />刷新</Button>
                <ToolsMenu label="筛选设置" icon={false}>
                  <button type="button" onClick={() => toggleFilter('status')}>
                    <span>状态</span>
                    <strong>{visibleFilters.has('status') ? '✓' : ''}</strong>
                  </button>
                </ToolsMenu>
                <ColumnMenu
                  label="列设置"
                  items={[
                    { key: 'status', label: '状态', checked: visibleColumns.has('status'), onToggle: () => toggleColumn('status') },
                    { key: 'requests', label: '请求', checked: visibleColumns.has('requests'), onToggle: () => toggleColumn('requests') },
                    { key: 'cache', label: '缓存', checked: visibleColumns.has('cache'), onToggle: () => toggleColumn('cache') },
                    { key: 'sessions', label: '会话', checked: visibleColumns.has('sessions'), onToggle: () => toggleColumn('sessions') },
                    { key: 'reason', label: '说明', checked: visibleColumns.has('reason'), onToggle: () => toggleColumn('reason') },
                  ]}
                />
                <ToolsMenu>
                  <button type="button" onClick={() => { setSearch(''); setStatusFilter(''); setPage(1); }}>
                    <span>清空筛选</span>
                  </button>
                  <button type="button" onClick={() => { setStatusFilter('degraded'); setPage(1); }}>
                    <span>仅看异常线路</span>
                  </button>
                  <button type="button" onClick={() => { setPageSize(50); setPage(1); }}>
                    <span>切换 50 / 页</span>
                  </button>
                </ToolsMenu>
              </ToolbarButtonRow>
            )}
          >
            <SearchField value={search} placeholder="搜索线路 / 池 / 状态" onChange={(value) => { setSearch(value); setPage(1); }} />
            {visibleFilters.has('status') ? (
              <Select value={statusFilter} onChange={(event) => { setStatusFilter(event.target.value as RouteStatusFilter); setPage(1); }}>
                <option value="">全部状态</option>
                <option value="ok">正常</option>
                <option value="degraded">异常</option>
              </Select>
            ) : null}
          </FilterToolbar>
        )}
        table={(
          <div className="table-wrap table-scroll">
            <table>
              <thead>
                <tr>
                  <th>线路</th>
                  {visibleColumns.has('status') ? <th>状态</th> : null}
                  {visibleColumns.has('requests') ? <th>请求</th> : null}
                  {visibleColumns.has('cache') ? <th>缓存</th> : null}
                  {visibleColumns.has('sessions') ? <th>会话</th> : null}
                  {visibleColumns.has('reason') ? <th>说明</th> : null}
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {pagedRows.length ? pagedRows.map((item, index) => {
                  const degraded = item.cooling === true || Number(item.error_count || 0) > 0;
                  return (
                    <tr key={`${item.route_url || item.pool_name || index}`}>
                      <td>
                        <div className="sub2-cell-stack">
                          <strong>{item.pool_name || item.route_url || `线路 ${index + 1}`}</strong>
                          <small>{item.route_url || '-'}</small>
                        </div>
                      </td>
                      {visibleColumns.has('status') ? <td><Badge tone={degraded ? 'warn' : 'ok'}>{item.route_status_text || (degraded ? '异常' : '正常')}</Badge></td> : null}
                      {visibleColumns.has('requests') ? (
                        <td>
                          <div className="sub2-cell-stack sub2-cell-stack-tight">
                            <strong>{formatNumber(item.request_count || 0)}</strong>
                            <small>成功 {formatNumber(item.success_count || 0)} / 异常 {formatNumber(item.error_count || 0)}</small>
                          </div>
                        </td>
                      ) : null}
                      {visibleColumns.has('cache') ? (
                        <td>
                          <div className="sub2-cell-stack sub2-cell-stack-tight">
                            <strong>{formatNumber(item.upstream_prompt_cache_hit_count || 0)}</strong>
                            <small>本地 {formatNumber(item.local_cache_hit_count || 0)}</small>
                          </div>
                        </td>
                      ) : null}
                      {visibleColumns.has('sessions') ? (
                        <td>
                          <div className="sub2-cell-stack sub2-cell-stack-tight">
                            <strong>{formatNumber(item.session_count || 0)}</strong>
                            <small>亲和 {formatNumber(item.sticky_session_count || 0)}</small>
                          </div>
                        </td>
                      ) : null}
                      {visibleColumns.has('reason') ? (
                        <td>
                          <div className="sub2-cell-stack sub2-cell-stack-tight">
                            <strong>{maskEmpty(item.last_reason || item.route_status_note)}</strong>
                            <small>{item.cooling ? '冷却中' : item.route_status_note || '-'}</small>
                          </div>
                        </td>
                      ) : null}
                      <td>
                        <RowActions>
                          <RowAction icon={Eye} label="详情" onClick={() => setInspectRoute(item)} />
                        </RowActions>
                      </td>
                    </tr>
                  );
                }) : (
                  <ListEmptyRow colSpan={visibleColumns.size + 2} title="暂无渠道状态数据" />
                )}
              </tbody>
            </table>
          </div>
        )}
        pagination={rows.length ? (
          <Pager
            page={Math.min(page, totalPages)}
            pageSize={pageSize}
            total={rows.length}
            onPageChange={(next) => setPage(Math.min(Math.max(1, next), totalPages))}
            onPageSizeChange={(next) => { setPageSize(next); setPage(1); }}
          />
        ) : null}
      />

      {inspectRoute ? (
        <Modal
          title="线路状态"
          size="lg"
          onClose={() => setInspectRoute(null)}
          footer={<ModalActions><Button onClick={() => setInspectRoute(null)}>关闭</Button></ModalActions>}
        >
          <div className="admin-dialog">
            <div className="admin-dialog-intro"><strong>{inspectRoute.pool_name || inspectRoute.route_url || '-'}</strong></div>
            <div className="admin-dialog-summary">
              <div className="admin-dialog-summary-card"><span>请求</span><strong>{formatNumber(inspectRoute.request_count || 0)}</strong><small>异常 {formatNumber(inspectRoute.error_count || 0)}</small></div>
              <div className="admin-dialog-summary-card"><span>上游缓存</span><strong>{formatNumber(inspectRoute.upstream_prompt_cache_hit_count || 0)}</strong><small>{formatNumber(inspectRoute.upstream_prompt_cache_request_count || 0)} 次请求</small></div>
              <div className="admin-dialog-summary-card"><span>本地缓存</span><strong>{formatNumber(inspectRoute.local_cache_hit_count || 0)}</strong><small>跳过 {formatNumber(inspectRoute.local_cache_bypass_count || 0)}</small></div>
            </div>
            <div className="admin-dialog-grid">
              <Field label="线路"><TextInput readOnly value={inspectRoute.route_url || '-'} /></Field>
              <Field label="状态"><TextInput readOnly value={inspectRoute.route_status_text || '-'} /></Field>
              <Field label="状态说明"><TextInput readOnly value={inspectRoute.route_status_note || '-'} /></Field>
              <Field label="最近原因"><TextInput readOnly value={inspectRoute.last_reason || '-'} /></Field>
              <Field label="平均缓存读取"><TextInput readOnly value={formatTokenCount(inspectRoute.avg_cache_read_input_tokens || 0)} /></Field>
              <Field label="亲和率"><TextInput readOnly value={formatPercent(inspectRoute.sticky_session_rate || 0)} /></Field>
              <Field label="提示率"><TextInput readOnly value={formatPercent(inspectRoute.hint_applied_rate || 0)} /></Field>
              <Field label="429 次数"><TextInput readOnly value={formatNumber(inspectRoute.status_429_count || 0)} /></Field>
            </div>
          </div>
        </Modal>
      ) : null}
    </section>
  );
}

export function AccountProfilePage() {
  const { account, apiKeys, subscriptions, orders, visiblePlans, visibleAvailableChannels, reload } = useAccountCenter();
  const usageQuery = useQuery({ queryKey: ['account-usage'], queryFn: () => fetchAccountUsage(), refetchInterval: 30000, retry: false });
  const [draft, setDraft] = useState<ProfileDraft | null>(null);
  const usageRows = usageQuery.data?.items || [];
  const totalTokens = usageRows.reduce((sum, item) => sum + Number(item.total_tokens || 0), 0);
  const totalInputBytes = usageRows.reduce((sum, item) => sum + Number(item.input_bytes || 0), 0);
  const totalOutputBytes = usageRows.reduce((sum, item) => sum + Number(item.output_bytes || 0), 0);
  const totalCost = usageRows.reduce((sum, item) => sum + Number(item.actual_cost || item.total_cost || 0), 0);
  const activeSubscriptions = subscriptions.filter((item) => item.status === 'active');
  const enabledKeys = apiKeys.filter((item) => item.enabled !== false);
  const updateMutation = useMutation({
    mutationFn: updateAccountProfile,
    onSuccess: async () => {
      setDraft(null);
      await reload();
      await usageQuery.refetch();
    },
  });

  const profileRows = useMemo(() => ([
    { category: '账户资料', label: '账户名称', value: account?.name || '-', note: account?.id || '-' },
    { category: '账户资料', label: '邮箱', value: account?.email || '-', note: account?.username || '-' },
    { category: '账户资料', label: '角色', value: account?.role || '-', note: account?.status || '-' },
    { category: '账户资料', label: '分组', value: account?.group_name || account?.group_id || '-', note: account?.source_type || '-' },
    { category: '额度配置', label: '余额', value: formatUsdCost(Number(account?.balance_cents || 0) / 100, 2), note: `并发 ${formatNumber(account?.concurrency_limit || 0)}` },
    { category: '额度配置', label: 'RPM', value: formatNumber(account?.rpm_limit || 0), note: account?.password_set ? '已设置密码' : '未设置密码' },
    { category: '消费概览', label: '请求数', value: formatNumber(usageRows.length), note: `订单 ${formatNumber(orders.length)}` },
    { category: '消费概览', label: '总 Token', value: formatTokenCount(totalTokens), note: `有效订阅 ${formatNumber(activeSubscriptions.length)}` },
    { category: '消费概览', label: '输入字节', value: formatByteCount(totalInputBytes), note: `输出 ${formatByteCount(totalOutputBytes)}` },
    { category: '消费概览', label: '消费金额', value: formatUsdCost(totalCost), note: `最近使用 ${maskEmpty(account?.last_seen_at)}` },
    { category: '业务资源', label: 'API 密钥', value: formatNumber(apiKeys.length), note: `启用 ${formatNumber(enabledKeys.length)}` },
    { category: '业务资源', label: '可购计划', value: formatNumber(visiblePlans.length), note: `可用渠道 ${formatNumber(visibleAvailableChannels.length)}` },
  ]), [account, activeSubscriptions.length, apiKeys.length, enabledKeys.length, orders.length, totalCost, totalInputBytes, totalOutputBytes, totalTokens, usageRows.length, visibleAvailableChannels.length, visiblePlans.length]);

  function openEdit() {
    setDraft({
      name: account?.name || '',
      email: account?.email || '',
      username: account?.username || '',
      password: '',
    });
  }

  function submitProfile() {
    if (!draft) return;
    updateMutation.mutate({
      name: draft.name,
      email: draft.email,
      username: draft.username,
      ...(draft.password.trim() ? { password: draft.password } : {}),
    });
  }

  return (
    <section className="grid-page">
      {buildPageIntro('/profile')}

      <TablePageLayout
        filters={(
          <FilterToolbar
            right={(
              <ToolbarButtonRow>
                <Button onClick={() => { void reload(); void usageQuery.refetch(); }}><RefreshCw size={15} />刷新</Button>
                <Button tone="primary" onClick={openEdit}>编辑资料</Button>
              </ToolbarButtonRow>
            )}
          />
        )}
        table={(
          <div className="table-wrap table-scroll">
            <table>
              <thead>
                <tr>
                  <th>分类</th>
                  <th>项目</th>
                  <th>当前值</th>
                  <th>说明</th>
                </tr>
              </thead>
              <tbody>
                {profileRows.length ? profileRows.map((item) => (
                  <tr key={`${item.category}-${item.label}`}>
                    <td>{item.category}</td>
                    <td>{item.label}</td>
                    <td><strong>{item.value}</strong></td>
                    <td>{item.note}</td>
                  </tr>
                )) : (
                  <ListEmptyRow colSpan={4} title="暂无账户资料" />
                )}
              </tbody>
            </table>
          </div>
        )}
      />

      {draft ? (
        <Modal
          title="编辑资料"
          size="lg"
          onClose={() => setDraft(null)}
          footer={(
            <ModalActions>
              <Button onClick={() => setDraft(null)}>取消</Button>
              <Button tone="primary" disabled={updateMutation.isPending || !(draft.name.trim() || draft.email.trim() || draft.username.trim())} onClick={submitProfile}>
                保存
              </Button>
            </ModalActions>
          )}
        >
          <div className="admin-dialog">
            <div className="admin-dialog-intro">
              <strong>{account?.id || '当前账户'}</strong>
            </div>
            <div className="admin-dialog-grid modal-grid">
              <Field label="账户名称"><TextInput value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} /></Field>
              <Field label="邮箱"><TextInput type="email" value={draft.email} onChange={(event) => setDraft({ ...draft, email: event.target.value })} /></Field>
              <Field label="用户名"><TextInput value={draft.username} onChange={(event) => setDraft({ ...draft, username: event.target.value })} /></Field>
              <Field label="新密码"><TextInput type="password" value={draft.password} onChange={(event) => setDraft({ ...draft, password: event.target.value })} /></Field>
            </div>
          </div>
        </Modal>
      ) : null}
    </section>
  );
}

function PricingModels({ rows }: { rows: AdminChannelPricing[] }) {
  const models = rows.map((item) => item.model).filter(Boolean);
  if (!models.length) return <span className="table-muted">-</span>;
  return (
    <div className="sub2-cell-stack sub2-cell-stack-tight">
      <strong>{models.slice(0, 2).join(' / ')}</strong>
      <small>{models.length > 2 ? `另 ${formatNumber(models.length - 2)} 个模型` : '模型价格'}</small>
    </div>
  );
}

function pricingText(rows: AdminChannelPricing[]) {
  return rows
    .map((item) => `${item.model}: 输入 ${item.input_price ?? 0}, 输出 ${item.output_price ?? 0}, 缓存写入 ${item.cache_write_price ?? 0}, 缓存读取 ${item.cache_read_price ?? 0}`)
    .join('\n');
}
