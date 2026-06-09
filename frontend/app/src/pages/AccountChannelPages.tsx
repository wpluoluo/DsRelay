import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Eye, RefreshCw } from 'lucide-react';
import { fetchAccountUsage } from '../api';
import { Badge, Button, Field, Modal, ModalActions, Select, TextArea, TextInput } from '../components';
import { EmptyState, FilterToolbar, Pager, RowAction, RowActions, SearchField, TablePageLayout, ToolbarButtonRow } from '../components/admin';
import { buildPageIntro } from '../navigation';
import { useAccountCenter } from '../state/accountCenterContext';
import { useDashboard } from '../state/dashboardContext';
import type { AdminChannel, AdminChannelPricing, RouteObservability } from '../types';
import { formatByteCount, formatMs, formatNumber, formatTokenCount, formatUsdCost, maskEmpty } from '../utils';

type StatusFilter = '' | 'enabled' | 'disabled';
type RouteStatusFilter = '' | 'ok' | 'degraded';

export function AccountAvailableChannelsPage() {
  const { account, groups, visiblePlans, visibleAvailableChannels, reload } = useAccountCenter();
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('');
  const [groupFilter, setGroupFilter] = useState('');
  const [inspectChannel, setInspectChannel] = useState<AdminChannel | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);

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
      ].map((value) => String(value || '').toLowerCase()).join(' ');
      return haystack.includes(keyword);
    });
  }, [allowedGroupIds, groupFilter, search, statusFilter, visibleAvailableChannels]);

  const totalPages = Math.max(1, Math.ceil(channelRows.length / pageSize));
  const pagedRows = channelRows.slice((page - 1) * pageSize, page * pageSize);
  const activeCount = channelRows.filter((item) => item.enabled !== false).length;
  const pricingCount = channelRows.reduce((sum, item) => sum + Number(item.pricing_count || item.model_pricing?.length || 0), 0);

  return (
    <section className="grid-page">
      {buildPageIntro('/available-channels')}
      <TablePageLayout
        actions={(
          <div className="sub2-inline-summary">
            <div className="sub2-inline-summary-item"><span>账户</span><strong>{account?.name || '-'}</strong><small>{account?.group_name || account?.source_type || '-'}</small></div>
            <div className="sub2-inline-summary-item"><span>可用渠道</span><strong>{formatNumber(activeCount)}</strong><small>当前筛选 {formatNumber(channelRows.length)}</small></div>
            <div className="sub2-inline-summary-item"><span>可购计划</span><strong>{formatNumber(visiblePlans.length)}</strong><small>启用计划</small></div>
            <div className="sub2-inline-summary-item"><span>价格规则</span><strong>{formatNumber(pricingCount)}</strong><small>模型计费</small></div>
          </div>
        )}
        filters={(
          <FilterToolbar
            right={(
              <ToolbarButtonRow>
                <Button onClick={() => void reload()}><RefreshCw size={15} />刷新</Button>
              </ToolbarButtonRow>
            )}
          >
            <SearchField value={search} placeholder="搜索渠道 / 平台 / 分组 / 模型" onChange={(value) => { setSearch(value); setPage(1); }} />
            <Select value={groupFilter} onChange={(event) => { setGroupFilter(event.target.value); setPage(1); }}>
              <option value="">全部分组</option>
              {groups.filter((group) => !allowedGroupIds.length || allowedGroupIds.includes(group.id)).map((group) => (
                <option key={group.id} value={group.id}>{group.name}</option>
              ))}
            </Select>
            <Select value={statusFilter} onChange={(event) => { setStatusFilter(event.target.value as StatusFilter); setPage(1); }}>
              <option value="">全部状态</option>
              <option value="enabled">启用</option>
              <option value="disabled">停用</option>
            </Select>
          </FilterToolbar>
        )}
        table={(
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>渠道</th>
                  <th>平台</th>
                  <th>分组</th>
                  <th>支持模型</th>
                  <th>计费</th>
                  <th>状态</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {pagedRows.length ? pagedRows.map((item) => (
                  <tr key={item.id}>
                    <td><div className="sub2-cell-stack"><strong>{item.name}</strong><small>{item.description || item.id}</small></div></td>
                    <td>{item.platform || '-'}</td>
                    <td><div className="sub2-cell-stack sub2-cell-stack-tight"><strong>{formatNumber(item.group_count || item.group_ids?.length || 0)}</strong><small>{item.group_names?.join(' / ') || '-'}</small></div></td>
                    <td><PricingModels rows={item.model_pricing || []} /></td>
                    <td><strong className="sub2-number-cell">{formatNumber(item.pricing_count || item.model_pricing?.length || 0)}</strong></td>
                    <td><Badge tone={item.enabled === false ? 'warn' : 'ok'}>{item.enabled === false ? '停用' : '启用'}</Badge></td>
                    <td>
                      <RowActions>
                        <RowAction icon={Eye} label="详情" onClick={() => setInspectChannel(item)} />
                      </RowActions>
                    </td>
                  </tr>
                )) : (
                  <tr><td colSpan={7}><EmptyState title="暂无可用渠道" /></td></tr>
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
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<RouteStatusFilter>('');
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
      ].map((value) => String(value || '').toLowerCase()).join(' ');
      return haystack.includes(keyword);
    });
  }, [routes, search, statusFilter]);
  const activeCount = rows.filter((item) => !item.cooling && Number(item.error_count || 0) === 0).length;
  const degradedCount = rows.length - activeCount;
  const totalRequests = rows.reduce((sum, item) => sum + Number(item.request_count || 0), 0);
  const cacheHitRequests = rows.reduce((sum, item) => sum + Number(item.upstream_prompt_cache_hit_count || 0), 0);

  return (
    <section className="grid-page">
      {buildPageIntro('/monitor')}
      <TablePageLayout
        actions={(
          <div className="sub2-inline-summary">
            <div className="sub2-inline-summary-item"><span>线路数</span><strong>{formatNumber(rows.length)}</strong><small>正常 {formatNumber(activeCount)}</small></div>
            <div className="sub2-inline-summary-item"><span>异常线路</span><strong>{formatNumber(degradedCount)}</strong><small>冷却 / 失败</small></div>
            <div className="sub2-inline-summary-item"><span>请求数</span><strong>{formatNumber(totalRequests)}</strong><small>观测窗口</small></div>
            <div className="sub2-inline-summary-item"><span>缓存命中</span><strong>{formatNumber(cacheHitRequests)}</strong><small>上游读取</small></div>
          </div>
        )}
        filters={(
          <FilterToolbar>
            <SearchField value={search} placeholder="搜索线路 / 池 / 状态" onChange={setSearch} />
            <Select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as RouteStatusFilter)}>
              <option value="">全部状态</option>
              <option value="ok">正常</option>
              <option value="degraded">异常</option>
            </Select>
          </FilterToolbar>
        )}
        table={(
          <div className="table-wrap table-scroll">
            <table>
              <thead>
                <tr>
                  <th>线路</th>
                  <th>状态</th>
                  <th>请求</th>
                  <th>缓存</th>
                  <th>会话</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {rows.length ? rows.map((item, index) => {
                  const degraded = item.cooling === true || Number(item.error_count || 0) > 0;
                  return (
                    <tr key={`${item.route_url || item.pool_name || index}`}>
                      <td><div className="sub2-cell-stack"><strong>{item.pool_name || item.route_url || `线路 ${index + 1}`}</strong><small>{item.route_url || '-'}</small></div></td>
                      <td><Badge tone={degraded ? 'warn' : 'ok'}>{item.route_status_text || (degraded ? '异常' : '正常')}</Badge></td>
                      <td><div className="sub2-cell-stack sub2-cell-stack-tight"><strong>{formatNumber(item.request_count || 0)}</strong><small>成功 {formatNumber(item.success_count || 0)} / 异常 {formatNumber(item.error_count || 0)}</small></div></td>
                      <td><div className="sub2-cell-stack sub2-cell-stack-tight"><strong>{formatNumber(item.upstream_prompt_cache_hit_count || 0)}</strong><small>本地 {formatNumber(item.local_cache_hit_count || 0)}</small></div></td>
                      <td><div className="sub2-cell-stack sub2-cell-stack-tight"><strong>{formatNumber(item.session_count || 0)}</strong><small>亲和 {formatNumber(item.sticky_session_count || 0)}</small></div></td>
                      <td><RowActions><RowAction icon={Eye} label="详情" onClick={() => setInspectRoute(item)} /></RowActions></td>
                    </tr>
                  );
                }) : (
                  <tr><td colSpan={6}><EmptyState title="暂无渠道状态数据" /></td></tr>
                )}
              </tbody>
            </table>
          </div>
        )}
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
              <Field label="最近原因"><TextInput readOnly value={inspectRoute.last_reason || '-'} /></Field>
              <Field label="平均缓存读取"><TextInput readOnly value={formatTokenCount(inspectRoute.avg_cache_read_input_tokens || 0)} /></Field>
              <Field label="亲和率"><TextInput readOnly value={`${formatNumber(inspectRoute.sticky_session_rate || 0)}%`} /></Field>
              <Field label="提示率"><TextInput readOnly value={`${formatNumber(inspectRoute.hint_applied_rate || 0)}%`} /></Field>
            </div>
          </div>
        </Modal>
      ) : null}
    </section>
  );
}

export function AccountProfilePage() {
  const { account, apiKeys, subscriptions, orders, visiblePlans, visibleAvailableChannels } = useAccountCenter();
  const usageQuery = useQuery({ queryKey: ['account-usage'], queryFn: () => fetchAccountUsage(), refetchInterval: 30000, retry: false });
  const userKeys = apiKeys;
  const userSubscriptions = subscriptions;
  const userOrders = orders;
  const usageRows = usageQuery.data?.items || [];
  const totalTokens = usageRows.reduce((sum, item) => sum + Number(item.total_tokens || 0), 0);
  const totalBytes = usageRows.reduce((sum, item) => sum + Number(item.input_bytes || 0) + Number(item.output_bytes || 0), 0);
  const totalCost = usageRows.reduce((sum, item) => sum + Number(item.actual_cost || item.total_cost || 0), 0);
  const activeSubscriptions = userSubscriptions.filter((item) => item.status === 'active');

  return (
    <section className="grid-page">
      {buildPageIntro('/profile')}
      <div className="sub2-inline-summary">
        <div className="sub2-inline-summary-item"><span>余额</span><strong>{formatUsdCost(Number(account?.balance_cents || 0) / 100, 2)}</strong><small>并发 {formatNumber(account?.concurrency_limit || 0)}</small></div>
        <div className="sub2-inline-summary-item"><span>API Key</span><strong>{formatNumber(userKeys.length)}</strong><small>启用 {formatNumber(userKeys.filter((item) => item.enabled !== false).length)}</small></div>
        <div className="sub2-inline-summary-item"><span>订阅</span><strong>{formatNumber(activeSubscriptions.length)}</strong><small>总数 {formatNumber(userSubscriptions.length)}</small></div>
        <div className="sub2-inline-summary-item"><span>使用记录</span><strong>{formatNumber(usageRows.length)}</strong><small>{formatTokenCount(totalTokens)}</small></div>
      </div>
      <div className="dashboard-main-grid">
        <div className="panel">
          <div className="panel-head"><h3>账户资料</h3></div>
          <div className="info-grid">
            <div className="metric-line"><span>用户名称</span><strong>{account?.name || '-'}</strong></div>
            <div className="metric-line"><span>邮箱</span><strong>{account?.email || '-'}</strong></div>
            <div className="metric-line"><span>用户名</span><strong>{account?.username || '-'}</strong></div>
            <div className="metric-line"><span>角色</span><strong>{account?.role || '-'}</strong></div>
            <div className="metric-line"><span>状态</span><strong>{account?.status || '-'}</strong></div>
            <div className="metric-line"><span>分组</span><strong>{account?.group_name || account?.group_id || '-'}</strong></div>
            <div className="metric-line"><span>RPM</span><strong>{formatNumber(account?.rpm_limit || 0)}</strong></div>
            <div className="metric-line"><span>密码</span><strong>{account?.password_set ? '已设置' : '未设置'}</strong></div>
          </div>
        </div>
        <div className="panel">
          <div className="panel-head"><h3>消费概览</h3></div>
          <div className="info-grid">
            <div className="metric-line"><span>请求数</span><strong>{formatNumber(usageRows.length)}</strong></div>
            <div className="metric-line"><span>Token</span><strong>{formatTokenCount(totalTokens)}</strong></div>
            <div className="metric-line"><span>字节数</span><strong>{formatByteCount(totalBytes)}</strong></div>
            <div className="metric-line"><span>消费</span><strong>{formatUsdCost(totalCost)}</strong></div>
            <div className="metric-line"><span>订单</span><strong>{formatNumber(userOrders.length)}</strong></div>
            <div className="metric-line"><span>可购计划</span><strong>{formatNumber(visiblePlans.length)}</strong></div>
            <div className="metric-line"><span>可用渠道</span><strong>{formatNumber(visibleAvailableChannels.length)}</strong></div>
            <div className="metric-line"><span>最近使用</span><strong>{maskEmpty(account?.last_seen_at)}</strong></div>
          </div>
        </div>
      </div>
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
