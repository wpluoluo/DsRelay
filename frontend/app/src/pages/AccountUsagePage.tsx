import { useEffect, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Download, RefreshCw } from 'lucide-react';
import { fetchAdminUsage } from '../api';
import { Button, Select, TextInput } from '../components';
import { EmptyState, FilterToolbar, Pager, SearchField, TablePageLayout, ToolbarButtonRow } from '../components/admin';
import { RequestRow } from '../features/requests/RequestsView';
import { useAccountCenter } from '../state/accountCenterContext';
import type { RequestEntry } from '../types';
import { formatMs, formatNumber, formatTokenCount, formatUsdCost, getBusinessUserId, readStorageJSON, writeStorageJSON } from '../utils';

const STORAGE_KEY = 'account-usage-view-state';

export function AccountUsagePage() {
  const { selectedUser, selectedUserId, apiKeys } = useAccountCenter();
  const usageQuery = useQuery({ queryKey: ['admin-usage'], queryFn: () => fetchAdminUsage(), refetchInterval: 10000 });
  const savedState = readStorageJSON(STORAGE_KEY, {
    start: '',
    end: '',
    model: '',
    status: 'all',
    apiKeyId: '',
    pageSize: 20,
  });
  const [filters, setFilters] = useState({
    start: savedState.start || '',
    end: savedState.end || '',
    model: savedState.model || '',
    status: savedState.status || 'all',
    apiKeyId: savedState.apiKeyId || '',
  });
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(savedState.pageSize || 20);

  const rows = useMemo<RequestEntry[]>(() => {
    const items = usageQuery.data?.items || [];
    const modelNeedle = filters.model.trim().toLowerCase();
    const start = filters.start ? new Date(filters.start).getTime() : 0;
    const end = filters.end ? new Date(filters.end).getTime() : 0;
    const currentKeyIds = new Set(apiKeys.filter((item) => !selectedUserId || getBusinessUserId(item) === selectedUserId).map((item) => item.id));
    return items
      .filter((row) => {
        if (selectedUserId && row.consumer_id !== selectedUserId) return false;
        if (filters.apiKeyId && String(row.api_key_id || '') !== filters.apiKeyId) return false;
        if (currentKeyIds.size && row.api_key_id && !currentKeyIds.has(String(row.api_key_id))) return false;
        const started = row.started_at ? new Date(String(row.started_at).replace(',', '.')).getTime() : 0;
        if (start && started && started < start) return false;
        if (end && started && started > end) return false;
        if (modelNeedle) {
          const hay = `${row.model || ''} ${row.resolved_model || ''} ${(row as any).inbound_endpoint || ''} ${row.route_url || ''}`.toLowerCase();
          if (!hay.includes(modelNeedle)) return false;
        }
        if (filters.status === 'success' && (row.error || Number(row.status_code || 0) >= 400)) return false;
        if (filters.status === 'error' && !row.error && Number(row.status_code || 0) < 400) return false;
        return true;
      })
      .map((row) => ({
        ...row,
        remote: row.consumer_name || row.consumer_preview || row.consumer_type || '当前用户',
        logical_model: row.model || row.resolved_model || '-',
        pool_name: row.pool_name || row.group_name || row.plan_name || '-',
        upstream_url: row.route_url || '',
        route_url: (row as any).inbound_endpoint || row.route_url || '',
        cache_read_input_tokens: Number(row.cache_read_tokens || 0),
        cache_creation_input_tokens: Number(row.cache_write_tokens || 0),
        local_response_cache_status: row.local_cache_status || 'miss',
        upstream_prompt_cache_status: row.upstream_cache_status || 'off',
        bytes_sent: Number(row.output_bytes || 0),
      }));
  }, [apiKeys, filters, selectedUserId, usageQuery.data?.items]);

  const pagedRows = useMemo(() => rows.slice((page - 1) * pageSize, page * pageSize), [rows, page, pageSize]);
  const totalPages = Math.max(1, Math.ceil(rows.length / pageSize));

  const stats = useMemo(() => {
    return rows.reduce(
      (acc, row) => {
        const prompt = Number(row.prompt_tokens || 0);
        const completion = Number(row.completion_tokens || 0);
        const total = Number(row.total_tokens || 0) || prompt + completion;
        acc.requests += 1;
        acc.tokens += total;
        acc.promptTokens += prompt;
        acc.completionTokens += completion;
        acc.cacheReadTokens += Number(row.cache_read_input_tokens || 0);
        acc.cacheWriteTokens += Number(row.cache_creation_input_tokens || 0);
        acc.duration += Number(row.duration_ms || 0);
        acc.actualCost += Number(row.actual_cost || 0) || Number(row.total_cost || 0) || 0;
        acc.totalCost += Number(row.total_cost || 0) || 0;
        return acc;
      },
      { requests: 0, tokens: 0, promptTokens: 0, completionTokens: 0, cacheReadTokens: 0, cacheWriteTokens: 0, duration: 0, actualCost: 0, totalCost: 0 },
    );
  }, [rows]);

  const averageDuration = stats.requests ? Math.round(stats.duration / stats.requests) : 0;

  useEffect(() => {
    writeStorageJSON(STORAGE_KEY, { ...filters, pageSize });
  }, [filters, pageSize]);

  function resetFilters() {
    setFilters({ start: '', end: '', model: '', status: 'all', apiKeyId: '' });
    setPage(1);
  }

  function exportCurrentView() {
    const lines = [
      ['时间', '模型', '请求Token', '回复Token', '缓存读取Token', '缓存写入Token', '消费', '耗时', '状态', '线路'].join('\t'),
      ...rows.map((row) => [
        row.started_at || '-',
        row.model || row.resolved_model || '-',
        String(Number(row.prompt_tokens || 0)),
        String(Number(row.completion_tokens || 0)),
        String(Number(row.cache_read_input_tokens || 0)),
        String(Number(row.cache_creation_input_tokens || 0)),
        String(Number(row.actual_cost || 0) || Number(row.total_cost || 0) || 0),
        String(row.duration_ms || 0),
        !row.error && Number(row.status_code || 0) < 400 ? '成功' : (row.error || row.status_code || '-'),
        (row as any).inbound_endpoint || row.route_url || '-',
      ].join('\t')),
    ].join('\n');
    const blob = new Blob([lines], { type: 'text/tab-separated-values;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'usage-records.tsv';
    link.click();
    URL.revokeObjectURL(url);
  }

  return (
    <section className="grid-page">
      <div className="sub2-page-head">
        <div className="sub2-page-title">
          <strong>使用记录</strong>
        </div>
        <div className="sub2-inline-summary">
          <div className="sub2-inline-summary-item"><span>当前用户</span><strong>{selectedUser?.name || '未选择用户'}</strong><small>{selectedUser?.group_name || selectedUser?.source_type || '-'}</small></div>
          <div className="sub2-inline-summary-item"><span>记录数</span><strong>{formatNumber(stats.requests)}</strong><small>当前筛选范围</small></div>
          <div className="sub2-inline-summary-item"><span>总 Token</span><strong>{formatTokenCount(stats.tokens)}</strong><small>请求 {formatTokenCount(stats.promptTokens)} / 回复 {formatTokenCount(stats.completionTokens)}</small></div>
          <div className="sub2-inline-summary-item"><span>总消费</span><strong>{formatUsdCost(stats.actualCost)}</strong><small>标准 {formatUsdCost(stats.totalCost)} / 平均耗时 {formatMs(averageDuration)}</small></div>
        </div>
      </div>

      <TablePageLayout
        filters={(
          <FilterToolbar
            right={(
              <ToolbarButtonRow>
                <Button onClick={() => void usageQuery.refetch()}><RefreshCw size={15} />刷新</Button>
                <Button onClick={resetFilters}>清空筛选</Button>
                <Button onClick={exportCurrentView}><Download size={15} />导出</Button>
              </ToolbarButtonRow>
            )}
          >
            <SearchField value={filters.model} placeholder="搜索模型 / 入口 / 线路" onChange={(value) => { setFilters((current) => ({ ...current, model: value })); setPage(1); }} />
            <Select value={filters.apiKeyId} onChange={(event) => { setFilters((current) => ({ ...current, apiKeyId: event.target.value })); setPage(1); }}>
              <option value="">全部 API Key</option>
              {apiKeys.filter((item) => !selectedUserId || getBusinessUserId(item) === selectedUserId).map((item) => (
                <option key={item.id} value={item.id}>{item.name}</option>
              ))}
            </Select>
            <Select value={filters.status} onChange={(event) => { setFilters((current) => ({ ...current, status: event.target.value })); setPage(1); }}>
              <option value="all">全部状态</option>
              <option value="success">成功</option>
              <option value="error">异常</option>
            </Select>
            <TextInput type="datetime-local" value={filters.start} onChange={(event) => { setFilters((current) => ({ ...current, start: event.target.value })); setPage(1); }} />
            <TextInput type="datetime-local" value={filters.end} onChange={(event) => { setFilters((current) => ({ ...current, end: event.target.value })); setPage(1); }} />
          </FilterToolbar>
        )}
        table={(
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
              <thead>
                <tr>
                  <th>时间</th>
                  <th>来源</th>
                  <th>线路</th>
                  <th>模型</th>
                  <th>指标</th>
                  <th>用户</th>
                  <th>状态</th>
                </tr>
              </thead>
              <tbody>
                {pagedRows.length ? pagedRows.map((entry, index) => (
                  <RequestRow key={`${entry.request_id || index}-${index}`} entry={entry} />
                )) : (
                  <tr>
                    <td colSpan={7}>
                      <EmptyState title="暂无使用记录" description={`当前用户 ${selectedUser?.name || ''} 在筛选条件下没有请求记录。`} />
                    </td>
                  </tr>
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
    </section>
  );
}
