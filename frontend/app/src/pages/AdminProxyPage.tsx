import { useMemo, useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { Eye, RefreshCw, Trash2 } from 'lucide-react';
import { clearRequestCache, clearRequests } from '../api';
import { Button, Field, Modal, ModalActions, Panel, PanelHead, TextArea, TextInput } from '../components';
import { FilterToolbar, ListEmptyRow, RowAction, RowActions, SearchField, TablePageLayout, ToolbarButtonRow, ToolsMenu } from '../components/admin';
import { buildPageIntro } from '../navigation';
import { useDashboard } from '../state/dashboardContext';
import type { RouteObservability } from '../types';
import { formatNumber, formatPercent, formatTokenCount, maskEmpty } from '../utils';

type StatusFilter = '' | 'ok' | 'degraded' | 'cooling';

export function AdminProxyPage() {
  const dashboard = useDashboard();
  const routes = dashboard.state.route_observability || [];
  const recentLogs = dashboard.state.recent_logs || [];
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('');
  const [inspectRoute, setInspectRoute] = useState<RouteObservability | null>(null);

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

  const filteredRoutes = useMemo(() => {
    const keyword = search.trim().toLowerCase();
    return routes.filter((item) => {
      const degraded = item.cooling === true || Number(item.error_count || 0) > 0 || Number(item.status_429_count || 0) > 0;
      if (statusFilter === 'ok' && degraded) return false;
      if (statusFilter === 'degraded' && !degraded) return false;
      if (statusFilter === 'cooling' && item.cooling !== true) return false;
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

  const summary = useMemo(() => {
    const degradedCount = filteredRoutes.filter((item) => item.cooling === true || Number(item.error_count || 0) > 0 || Number(item.status_429_count || 0) > 0).length;
    const requestCount = filteredRoutes.reduce((sum, item) => sum + Number(item.request_count || 0), 0);
    const upstreamCacheHits = filteredRoutes.reduce((sum, item) => sum + Number(item.upstream_prompt_cache_hit_count || 0), 0);
    const stickySessions = filteredRoutes.reduce((sum, item) => sum + Number(item.active_affinity_count || 0), 0);
    return {
      degradedCount,
      requestCount,
      upstreamCacheHits,
      stickySessions,
    };
  }, [filteredRoutes]);

  return (
    <section className="grid-page">
      {buildPageIntro('/admin/proxies')}

      <TablePageLayout
        actions={(
          <div className="sub2-inline-summary">
            <div className="sub2-inline-summary-item"><span>线路观测</span><strong>{formatNumber(filteredRoutes.length)}</strong><small>异常 {formatNumber(summary.degradedCount)}</small></div>
            <div className="sub2-inline-summary-item"><span>请求</span><strong>{formatNumber(summary.requestCount)}</strong><small>当前筛选结果</small></div>
            <div className="sub2-inline-summary-item"><span>上游缓存命中</span><strong>{formatNumber(summary.upstreamCacheHits)}</strong><small>活跃亲和 {formatNumber(summary.stickySessions)}</small></div>
            <div className="sub2-inline-summary-item"><span>运行状态</span><strong>{dashboard.stateQuery.isError ? '连接异常' : '运行中'}</strong><small>{dashboard.status || '实时状态'}</small></div>
          </div>
        )}
        filters={(
          <FilterToolbar
            right={(
              <ToolbarButtonRow>
                <Button onClick={() => void dashboard.stateQuery.refetch()}><RefreshCw size={15} />刷新</Button>
                <Button onClick={() => clearRequestsMutation.mutate()} disabled={clearRequestsMutation.isPending}><Trash2 size={15} />清空请求</Button>
                <Button onClick={() => clearCacheMutation.mutate()} disabled={clearCacheMutation.isPending}><Trash2 size={15} />清空缓存</Button>
              </ToolbarButtonRow>
            )}
          >
            <SearchField value={search} placeholder="搜索线路 / 池 / 状态 / 原因" onChange={(value) => setSearch(value)} />
            <select className="select" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as StatusFilter)}>
              <option value="">全部状态</option>
              <option value="ok">正常</option>
              <option value="degraded">异常</option>
              <option value="cooling">冷却中</option>
            </select>
            <ToolsMenu>
              <button type="button" onClick={() => { setSearch(''); setStatusFilter(''); }}>
                <span>清空筛选</span>
              </button>
              <button type="button" onClick={() => setStatusFilter('degraded')}>
                <span>只看异常线路</span>
              </button>
              <button type="button" onClick={() => setStatusFilter('cooling')}>
                <span>只看冷却线路</span>
              </button>
            </ToolsMenu>
          </FilterToolbar>
        )}
        table={(
          <>
            <div className="table-wrap table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>线路</th>
                    <th>状态</th>
                    <th>请求</th>
                    <th>缓存</th>
                    <th>亲和</th>
                    <th>最近原因</th>
                    <th>操作</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredRoutes.length ? filteredRoutes.map((item, index) => {
                    const degraded = item.cooling === true || Number(item.error_count || 0) > 0 || Number(item.status_429_count || 0) > 0;
                    return (
                      <tr key={`${item.route_url || item.pool_name || index}`}>
                        <td>
                          <div className="sub2-cell-stack">
                            <strong>{item.pool_name || `线路 ${index + 1}`}</strong>
                            <small>{item.route_url || '-'}</small>
                          </div>
                        </td>
                        <td>
                          <div className="sub2-cell-stack sub2-cell-stack-tight">
                            <strong>{item.route_status_text || (degraded ? '异常' : '正常')}</strong>
                            <small>{item.cooling ? '冷却中' : item.route_status_note || '-'}</small>
                          </div>
                        </td>
                        <td>
                          <div className="sub2-cell-stack sub2-cell-stack-tight">
                            <strong>{formatNumber(item.request_count || 0)}</strong>
                            <small>成功 {formatNumber(item.success_count || 0)} / 异常 {formatNumber(item.error_count || 0)}</small>
                          </div>
                        </td>
                        <td>
                          <div className="sub2-cell-stack sub2-cell-stack-tight">
                            <strong>{formatPercent(item.upstream_prompt_cache_hit_rate || 0)}</strong>
                            <small>上游 {formatNumber(item.upstream_prompt_cache_hit_count || 0)} / 本地 {formatNumber(item.local_cache_hit_count || 0)}</small>
                          </div>
                        </td>
                        <td>
                          <div className="sub2-cell-stack sub2-cell-stack-tight">
                            <strong>{formatPercent(item.sticky_session_rate || 0)}</strong>
                            <small>活跃 {formatNumber(item.active_affinity_count || 0)} / 提示 {formatPercent(item.hint_applied_rate || 0)}</small>
                          </div>
                        </td>
                        <td>
                          <div className="sub2-cell-stack sub2-cell-stack-tight">
                            <strong>{maskEmpty(item.last_reason || item.route_status_note)}</strong>
                            <small>429 {formatNumber(item.status_429_count || 0)} / 连续失败 {formatNumber(item.consecutive_failures || 0)}</small>
                          </div>
                        </td>
                        <td>
                          <RowActions>
                            <RowAction icon={Eye} label="详情" onClick={() => setInspectRoute(item)} />
                          </RowActions>
                        </td>
                      </tr>
                    );
                  }) : (
                    <ListEmptyRow colSpan={7} title="暂无线路观测数据" />
                  )}
                </tbody>
              </table>
            </div>

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
                      <tr key={`${index}-${line.slice(0, 24)}`}>
                        <td><code>{line}</code></td>
                      </tr>
                    )) : (
                      <tr><td>暂无最近日志。</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            </Panel>
          </>
        )}
      />

      {inspectRoute ? (
        <Modal
          title="线路详情"
          size="lg"
          onClose={() => setInspectRoute(null)}
          footer={<ModalActions><Button onClick={() => setInspectRoute(null)}>关闭</Button></ModalActions>}
        >
          <div className="admin-dialog">
            <div className="admin-dialog-intro">
              <strong>{inspectRoute.pool_name || inspectRoute.route_url || '-'}</strong>
            </div>
            <div className="admin-dialog-summary">
              <div className="admin-dialog-summary-card"><span>请求</span><strong>{formatNumber(inspectRoute.request_count || 0)}</strong><small>成功 {formatNumber(inspectRoute.success_count || 0)}</small></div>
              <div className="admin-dialog-summary-card"><span>缓存命中</span><strong>{formatPercent(inspectRoute.upstream_prompt_cache_hit_rate || 0)}</strong><small>本地 {formatPercent(inspectRoute.local_cache_hit_rate || 0)}</small></div>
              <div className="admin-dialog-summary-card"><span>会话亲和</span><strong>{formatPercent(inspectRoute.sticky_session_rate || 0)}</strong><small>提示 {formatPercent(inspectRoute.hint_applied_rate || 0)}</small></div>
            </div>
            <div className="admin-dialog-grid">
              <Field label="线路"><TextInput readOnly value={inspectRoute.route_url || '-'} /></Field>
              <Field label="状态"><TextInput readOnly value={inspectRoute.route_status_text || '-'} /></Field>
              <Field label="状态说明"><TextInput readOnly value={inspectRoute.route_status_note || '-'} /></Field>
              <Field label="最近原因"><TextInput readOnly value={inspectRoute.last_reason || '-'} /></Field>
              <Field label="平均缓存读取"><TextInput readOnly value={formatTokenCount(inspectRoute.avg_cache_read_input_tokens || 0)} /></Field>
              <Field label="活跃亲和"><TextInput readOnly value={formatNumber(inspectRoute.active_affinity_count || 0)} /></Field>
              <Field label="本地缓存命中"><TextInput readOnly value={formatPercent(inspectRoute.local_cache_hit_rate || 0)} /></Field>
              <Field label="上游缓存命中"><TextInput readOnly value={formatPercent(inspectRoute.upstream_prompt_cache_hit_rate || 0)} /></Field>
            </div>
            <Field label="线路策略" full>
              <TextArea
                readOnly
                rows={10}
                value={JSON.stringify(inspectRoute.route_policy || {}, null, 2)}
              />
            </Field>
          </div>
        </Modal>
      ) : null}
    </section>
  );
}
