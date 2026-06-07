import { useMutation } from '@tanstack/react-query';
import { ListChecks, Trash2 } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { clearRequestCache, clearRequests } from '../../api';
import { Button, Select, TextInput } from '../../components';
import { ActionButton, EmptyState, FilterToolbar, TablePageLayout, ToolbarButtonRow } from '../../components/admin';
import { queryClient } from '../../state/queryClient';
import type { DashboardState, RequestEntry } from '../../types';
import { formatByteCount, formatMs, formatNumber, formatTokenCount, maskEmpty, summarizeLocalCacheStatus, summarizeUpstreamCacheStatus } from '../../utils';

export function RequestsView({ state }: { state: DashboardState }) {
  const [filters, setFilters] = useState({ scope: 'recent', start: '', end: '', requestId: '', model: '', protocol: '', remote: '' });
  const active = state.active_requests || [];
  const recent = state.recent_requests || [];
  const rows = useMemo(() => {
    const sourceRows = filters.scope === 'active' ? active : filters.scope === 'all' ? [...active, ...recent] : recent;
    const start = filters.start ? new Date(filters.start).getTime() : 0;
    const end = filters.end ? new Date(filters.end).getTime() : 0;
    return sourceRows.filter((entry) => {
      const started = entry.started_at ? new Date(String(entry.started_at).replace(',', '.')).getTime() : 0;
      if (start && started && started < start) return false;
      if (end && started && started > end) return false;
      if (filters.requestId && !String(entry.request_id || '').toLowerCase().includes(filters.requestId.toLowerCase())) return false;
      if (filters.model) {
        const hay = `${entry.logical_model || ''} ${entry.resolved_model || ''} ${entry.model || ''}`.toLowerCase();
        if (!hay.includes(filters.model.toLowerCase())) return false;
      }
      if (filters.protocol && !String(entry.protocol || '').toLowerCase().includes(filters.protocol.toLowerCase())) return false;
      if (filters.remote && !String(entry.remote || '').toLowerCase().includes(filters.remote.toLowerCase())) return false;
      return true;
    });
  }, [active, filters, recent]);
  const successCount = rows.filter((entry) => !entry.error && Number(entry.status_code || 0) < 400).length;
  const errorCount = rows.length - successCount;
  const totalTokens = rows.reduce((sum, entry) => sum + Number(entry.total_tokens || entry.prompt_tokens || 0) + Number(entry.completion_tokens || 0), 0);
  const totalDuration = rows.reduce((sum, entry) => sum + Number(entry.duration_ms || 0), 0);
  const avgDuration = rows.length ? Math.round(totalDuration / rows.length) : 0;
  return (
    <section className="grid-page">
      <div className="sub2-page-head">
        <div className="sub2-page-title">
          <strong>使用记录</strong>
          <span>按时间、模型、协议和线路查看请求明细。</span>
        </div>
        <div className="sub2-inline-summary">
          <div className="sub2-inline-summary-item"><span>当前结果</span><strong>{formatNumber(rows.length)}</strong><small>筛选后的请求数</small></div>
          <div className="sub2-inline-summary-item"><span>成功 / 异常</span><strong>{formatNumber(successCount)} / {formatNumber(errorCount)}</strong><small>当前窗口状态</small></div>
          <div className="sub2-inline-summary-item"><span>累计 Token</span><strong>{formatTokenCount(totalTokens)}</strong><small>当前筛选范围</small></div>
          <div className="sub2-inline-summary-item"><span>平均耗时</span><strong>{formatMs(avgDuration)}</strong><small>活跃 {formatNumber(active.length)}</small></div>
        </div>
      </div>
      <TablePageLayout
        filters={
          <FilterToolbar
            right={<RequestActions />}
          >
            <label className="filter-field"><span>范围</span><Select value={filters.scope} onChange={(e) => setFilters((current) => ({ ...current, scope: e.target.value }))}><option value="recent">最近请求</option><option value="active">活跃请求</option><option value="all">全部</option></Select></label>
            <label className="filter-field"><span>开始时间</span><TextInput type="datetime-local" value={filters.start} onChange={(e) => setFilters((current) => ({ ...current, start: e.target.value }))} /></label>
            <label className="filter-field"><span>结束时间</span><TextInput type="datetime-local" value={filters.end} onChange={(e) => setFilters((current) => ({ ...current, end: e.target.value }))} /></label>
            <label className="filter-field"><span>请求 ID</span><TextInput value={filters.requestId} onChange={(e) => setFilters((current) => ({ ...current, requestId: e.target.value }))} /></label>
            <label className="filter-field"><span>模型</span><TextInput value={filters.model} onChange={(e) => setFilters((current) => ({ ...current, model: e.target.value }))} /></label>
            <label className="filter-field"><span>协议</span><TextInput value={filters.protocol} onChange={(e) => setFilters((current) => ({ ...current, protocol: e.target.value }))} /></label>
            <label className="filter-field"><span>来源</span><TextInput value={filters.remote} onChange={(e) => setFilters((current) => ({ ...current, remote: e.target.value }))} /></label>
          </FilterToolbar>
        }
        table={
          <div className="table-wrap table-scroll table-requests">
            <table>
              <colgroup>
                <col className="col-req-time" />
                <col className="col-req-source" />
                <col className="col-req-route" />
                <col className="col-req-model" />
                <col className="col-req-metrics" />
                <col className="col-req-repairs" />
                <col className="col-req-status" />
              </colgroup>
              <thead><tr><th>时间</th><th>来源</th><th>线路</th><th>模型</th><th>指标</th><th>修复</th><th>状态</th></tr></thead>
              <tbody>
                {rows.length ? rows.slice(0, 80).map((entry, index) => <RequestRow key={`${entry.request_id || index}-${index}`} entry={entry} />) : <tr><td colSpan={7}><EmptyState title="暂无请求记录" description="当前筛选条件下没有请求记录。" /></td></tr>}
              </tbody>
            </table>
          </div>
        }
      />
    </section>
  );
}

function RequestActions() {
  const clearMutation = useMutation({ mutationFn: clearRequests, onSuccess: () => queryClient.invalidateQueries({ queryKey: ['dashboard-state'] }) });
  const cacheMutation = useMutation({ mutationFn: clearRequestCache, onSuccess: () => queryClient.invalidateQueries({ queryKey: ['dashboard-state'] }) });
  return <ToolbarButtonRow><ActionButton onClick={() => clearMutation.mutate()}><Trash2 size={14} />清空请求</ActionButton><ActionButton onClick={() => cacheMutation.mutate()}><Trash2 size={14} />清空缓存</ActionButton></ToolbarButtonRow>;
}

function RequestRow({ entry }: { entry: RequestEntry }) {
  const isTerminal = Boolean(entry.error || entry.client_gone || entry.status_code);
  const status = isTerminal
    ? (entry.error ? '异常' : entry.client_gone ? '客户端断开' : entry.status_code || '-')
    : (entry.status_text || (entry.active ? '处理中' : '-'));
  const tone = entry.error ? 'bad' : Number(entry.status_code || 0) >= 400 ? 'warn' : 'ok';
  const statusTone = entry.error || Number(entry.status_code || 0) >= 400 ? 'err' : entry.status_code ? 'ok' : 'warn';
  const poolName = entry.pool_name || entry.selected_pool_name || '-';
  const keyIndex = entry.api_key_index == null && entry.selected_key_index == null ? '-' : `Key ${Number(entry.api_key_index ?? entry.selected_key_index) + 1}`;
  const routeIndex = entry.selected_route_index == null ? '-' : `线路 ${Number(entry.selected_route_index) + 1}`;
  const routePoolSize = Number(entry.route_pool_size || 0);
  const routeAttemptCount = Number(entry.attempt_route_count || 0);
  const logicalModel = entry.logical_model || entry.model || '-';
  const resolvedModel = entry.resolved_model || logicalModel || '-';
  const inputBytes = Number(entry.input_bytes || 0);
  const outputBytes = Number(entry.bytes_sent || 0);
  const cacheReadBytes = Number(entry.cache_read_bytes || 0);
  const promptTokens = Number(entry.prompt_tokens || 0);
  const completionTokens = Number(entry.completion_tokens || 0);
  const totalTokens = Number(entry.total_tokens || 0) || promptTokens + completionTokens;
  const cacheReadTokens = Number(entry.cache_read_input_tokens || 0);
  const cacheCreationTokens = Number(entry.cache_creation_input_tokens || 0);
  const cacheStatus = String(entry.local_response_cache_status || entry.cache_status || (entry.local_response_cache_hit || entry.cache_hit ? 'hit' : 'miss'));
  const upstreamCacheStatus = String(entry.upstream_prompt_cache_status || entry.upstream_cache_status || 'off');
  const localCacheText = summarizeLocalCacheStatus(cacheStatus, entry.local_response_cache_hit || entry.cache_hit);
  const upstreamCacheText = summarizeUpstreamCacheStatus(upstreamCacheStatus, cacheReadTokens);
  const actualRouteUrl = String(entry.route_url || entry.upstream_url || '');
  return (
    <tr>
      <td><div className="request-stack"><div className="request-cell-title">{maskEmpty(entry.started_at)}</div><div className="request-cell-sub request-mono">{maskEmpty(entry.request_id)}</div></div></td>
      <td><div className="request-stack"><div className="request-cell-title">{maskEmpty(entry.remote)}</div><div className="request-cell-sub">重试 {entry.retry_count || 0} · 候选 {routePoolSize || 1}{routeAttemptCount ? ` · 已试 ${routeAttemptCount}` : ''}</div></div></td>
      <td><div className="request-stack"><div className="request-line-main">{poolName} · {routeIndex} · {keyIndex}</div><div className="request-line-path request-ellipsis">{maskEmpty(actualRouteUrl)}</div></div></td>
      <td><div className="request-stack"><div className="request-cell-title request-ellipsis">{logicalModel}</div><div className="request-cell-sub request-ellipsis">{resolvedModel}</div><div className="request-cell-sub">{poolName}</div></div></td>
      <td>
        <div className="request-metric-list">
          <div className="request-chip-row">
            <span className="request-chip ok">{formatMs(entry.duration_ms)}</span>
            <span className="request-chip">请求字节 {formatByteCount(inputBytes)}</span>
            <span className="request-chip">响应字节 {formatByteCount(outputBytes)}</span>
          </div>
          <div className="request-token-line">
            <span className="token-flow in">↓ {formatTokenCount(promptTokens)}</span>
            <span className="token-flow out">↑ {formatTokenCount(completionTokens)}</span>
            <CacheHover
              promptTokens={promptTokens}
              completionTokens={completionTokens}
              cacheReadTokens={cacheReadTokens}
              cacheCreationTokens={cacheCreationTokens}
              upstreamCacheText={upstreamCacheText}
              localCacheText={localCacheText}
              cacheReadBytes={cacheReadBytes}
              totalTokens={totalTokens}
            />
          </div>
        </div>
      </td>
      <td><div className="request-stack"><div className="request-cell-sub">请求 {entry.request_repairs || 0} · DSML {entry.sanitized_markers || 0} · 工具 {entry.repaired_tool_args || 0}</div></div></td>
      <td className="request-status-cell"><div className="request-chip-row"><span className={`request-chip ${statusTone}`}>状态 {String(status)}</span>{entry.error ? <span className="request-chip err">异常</span> : null}</div>{entry.error ? <div className="request-cell-sub request-ellipsis request-error">{entry.error}</div> : null}</td>
    </tr>
  );
}

function CacheHover({
  promptTokens,
  completionTokens,
  cacheReadTokens,
  cacheCreationTokens,
  upstreamCacheText,
  localCacheText,
  cacheReadBytes,
  totalTokens,
}: {
  promptTokens: number;
  completionTokens: number;
  cacheReadTokens: number;
  cacheCreationTokens: number;
  upstreamCacheText: string;
  localCacheText: string;
  cacheReadBytes: number;
  totalTokens: number;
}) {
  const triggerRef = useRef<HTMLSpanElement | null>(null);
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState({ top: 0, left: 0 });

  useEffect(() => {
    if (!open) return;

    const updatePosition = () => {
      const rect = triggerRef.current?.getBoundingClientRect();
      if (!rect) return;
      const panelWidth = 238;
      const gap = 12;
      const viewportWidth = window.innerWidth;
      const left = Math.min(Math.max(12, rect.left + rect.width / 2 - panelWidth / 2), viewportWidth - panelWidth - 12);
      setPosition({
        left,
        top: rect.bottom + gap,
      });
    };

    updatePosition();
    window.addEventListener('scroll', updatePosition, true);
    window.addEventListener('resize', updatePosition);
    return () => {
      window.removeEventListener('scroll', updatePosition, true);
      window.removeEventListener('resize', updatePosition);
    };
  }, [open]);

  return (
    <span
      ref={triggerRef}
      className="cache-hover"
      aria-label="缓存明细"
      tabIndex={0}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onFocus={() => setOpen(true)}
      onBlur={() => setOpen(false)}
    >
      <svg width="12" height="12" viewBox="0 0 20 20" fill="none" aria-hidden="true"><circle cx="10" cy="10" r="7" stroke="currentColor" strokeWidth="1.6" /><path d="M10 6.5v4.2M10 13.6v.1" stroke="currentColor" strokeWidth="2" strokeLinecap="round" /></svg>
      {open ? createPortal(
        <span className="cache-hover-panel cache-hover-panel-fixed" style={{ top: `${position.top}px`, left: `${position.left}px` }}>
          <span className="cache-tip-title">Token 明细</span>
          <CacheTipRow label="请求 Token" value={formatTokenCount(promptTokens)} />
          <CacheTipRow label="回复 Token" value={formatTokenCount(completionTokens)} />
          <CacheTipRow label="缓存读取 Token" value={formatTokenCount(cacheReadTokens)} />
          <CacheTipRow label="缓存写入 Token" value={formatTokenCount(cacheCreationTokens)} />
          <CacheTipRow label="上游缓存" value={upstreamCacheText} />
          <CacheTipRow label="本地缓存" value={localCacheText} />
          <CacheTipRow label="本地读取字节" value={formatByteCount(cacheReadBytes)} />
          <span className="cache-tip-row cache-tip-total"><span className="cache-tip-label">总 Token</span><span className="cache-tip-value">{formatTokenCount(totalTokens)}</span></span>
        </span>,
        document.body,
      ) : null}
    </span>
  );
}

function CacheTipRow({ label, value }: { label: string; value: string }) {
  return <span className="cache-tip-row"><span className="cache-tip-label">{label}</span><span className="cache-tip-value">{value}</span></span>;
}
