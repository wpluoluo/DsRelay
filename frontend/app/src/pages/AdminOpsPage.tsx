import { useMemo } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { RefreshCw, Trash2 } from 'lucide-react';
import { clearRequestCache, clearRequests, fetchAdminOverview, fetchAdminProtocols } from '../api';
import { Button, Empty, Panel, PanelHead } from '../components';
import { RequestRow, type RequestTableColumnKey } from '../features/requests/RequestsView';
import { buildPageIntro } from '../navigation';
import { useDashboard } from '../state/dashboardContext';
import { formatNumber, formatTokenCount, formatUptime } from '../utils';

const LIVE_REQUEST_COLUMNS = new Set<RequestTableColumnKey>(['source', 'route', 'model', 'metrics', 'status']);

export function AdminOpsPage() {
  const dashboard = useDashboard();
  const overviewQuery = useQuery({ queryKey: ['admin-overview'], queryFn: fetchAdminOverview, refetchInterval: 10000 });
  const protocolsQuery = useQuery({ queryKey: ['admin-protocols'], queryFn: fetchAdminProtocols, refetchInterval: 30000 });
  const overview = overviewQuery.data || {};
  const protocols = protocolsQuery.data?.items || [];
  const runtime = dashboard.state.runtime || {};
  const runtimeStartedAt = String((runtime as Record<string, unknown>).started_at || '').trim();
  const activeRequests = dashboard.state.active_requests || [];
  const recentRequests = dashboard.state.recent_requests || [];
  const recentLogs = dashboard.state.recent_logs || [];
  const liveRequests = useMemo(() => [...activeRequests, ...recentRequests].slice(0, 12), [activeRequests, recentRequests]);

  const clearRequestsMutation = useMutation({
    mutationFn: clearRequests,
    onSuccess: async () => {
      await dashboard.stateQuery.refetch();
    },
  });
  const clearCacheMutation = useMutation({
    mutationFn: clearRequestCache,
    onSuccess: async () => {
      await dashboard.stateQuery.refetch();
    },
  });

  return (
    <section className="grid-page">
      {buildPageIntro('/admin/ops')}
      <div className="sub2-inline-summary">
        <div className="sub2-inline-summary-item"><span>运行时</span><strong>{runtime.pid || '-'}</strong><small>端口 {runtime.port || '-'}</small></div>
        <div className="sub2-inline-summary-item"><span>活动请求</span><strong>{formatNumber(activeRequests.length)}</strong><small>最近请求 {formatNumber(recentRequests.length)}</small></div>
        <div className="sub2-inline-summary-item"><span>协议数</span><strong>{formatNumber(protocols.length)}</strong><small>模型能力 {formatNumber(runtime.model_capability_count || 0)}</small></div>
        <div className="sub2-inline-summary-item"><span>近窗 Token</span><strong>{formatTokenCount(overview.total_tokens || 0)}</strong><small>错误 {formatNumber(overview.error_count || 0)}</small></div>
      </div>

      <Panel className="dashboard-card">
        <PanelHead
          title="运行态"
          action={(
            <div className="sub2-toolbar-row">
              <Button onClick={() => { void dashboard.stateQuery.refetch(); void overviewQuery.refetch(); void protocolsQuery.refetch(); }}><RefreshCw size={15} />刷新</Button>
              <Button onClick={() => clearRequestsMutation.mutate()} disabled={clearRequestsMutation.isPending}><Trash2 size={15} />清空请求</Button>
              <Button onClick={() => clearCacheMutation.mutate()} disabled={clearCacheMutation.isPending}><Trash2 size={15} />清空缓存</Button>
            </div>
          )}
        />
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>项目</th>
                <th>当前值</th>
                <th>补充</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>运行时长</td>
                <td><strong>{formatUptime(runtime.uptime_seconds || 0)}</strong></td>
                <td>{runtimeStartedAt || '-'}</td>
              </tr>
              <tr>
                <td>配置来源</td>
                <td><strong>{runtime.config_source || '-'}</strong></td>
                <td>{runtime.config_path || '-'}</td>
              </tr>
              <tr>
                <td>上游线路</td>
                <td><strong>{formatNumber(runtime.upstream_url_count || dashboard.state.upstream_url_count || 0)}</strong></td>
                <td>{(dashboard.state.upstream_urls || []).slice(0, 2).join(' / ') || '-'}</td>
              </tr>
              <tr>
                <td>能力缓存</td>
                <td><strong>{formatNumber(runtime.model_routing?.route_cache_entries || 0)}</strong></td>
                <td>模型列表 {formatNumber(runtime.model_routing?.model_list_cache_entries || 0)}</td>
              </tr>
              <tr>
                <td>重试策略</td>
                <td><strong>{formatNumber(runtime.retry_config?.max_retries || 0)}</strong></td>
                <td>退避 {formatNumber(runtime.retry_config?.backoff_ms || 0)} / {formatNumber(runtime.retry_config?.max_backoff_ms || 0)} ms</td>
              </tr>
            </tbody>
          </table>
        </div>
      </Panel>

      <Panel className="dashboard-card">
        <PanelHead title="最近请求" />
        <div className="table-wrap table-scroll table-requests">
          <table>
            <thead>
              <tr>
                <th>时间</th>
                <th>来源</th>
                <th>线路</th>
                <th>模型</th>
                <th>指标</th>
                <th>状态</th>
              </tr>
            </thead>
            <tbody>
              {liveRequests.length ? liveRequests.map((entry, index) => (
                <RequestRow key={`${entry.request_id || index}-${index}`} entry={entry} visibleColumns={LIVE_REQUEST_COLUMNS} />
              )) : (
                <tr><td colSpan={6}><Empty>暂无请求记录。</Empty></td></tr>
              )}
            </tbody>
          </table>
        </div>
      </Panel>

      <Panel className="dashboard-card">
        <PanelHead title="协议能力" />
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>协议</th>
                <th>流式</th>
                <th>工具</th>
                <th>图片</th>
                <th>参数</th>
              </tr>
            </thead>
            <tbody>
              {protocols.length ? protocols.map((item) => (
                <tr key={item.key}>
                  <td><strong>{item.label || item.key}</strong></td>
                  <td>{item.supports_stream ? '支持' : '不支持'}</td>
                  <td>{item.supports_tools ? '支持' : '不支持'}</td>
                  <td>{item.supports_images ? '支持' : '不支持'}</td>
                  <td>{(item.parameter_keys || []).join(', ') || '-'}</td>
                </tr>
              )) : (
                <tr><td colSpan={5}><Empty>暂无协议信息。</Empty></td></tr>
              )}
            </tbody>
          </table>
        </div>
      </Panel>

      <Panel className="dashboard-card">
        <PanelHead title="最近日志" />
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>内容</th>
              </tr>
            </thead>
            <tbody>
              {recentLogs.length ? recentLogs.slice(0, 20).map((line, index) => (
                <tr key={`${index}-${String(line).slice(0, 24)}`}>
                  <td><code>{String(line || '')}</code></td>
                </tr>
              )) : (
                <tr><td>暂无最近日志。</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </Panel>
    </section>
  );
}
