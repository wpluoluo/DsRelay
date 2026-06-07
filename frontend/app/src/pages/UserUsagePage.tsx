import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Download, Eye, MoreHorizontal, RefreshCw } from 'lucide-react';
import { fetchAdminUsage } from '../api';
import { Button, Field, Modal, ModalActions, Select, TextArea, TextInput } from '../components';
import { EmptyState, FilterToolbar, Pager, RowAction, RowActions, SearchField, TablePageLayout, ToolbarButtonRow } from '../components/admin';
import { useUserCenter } from '../state/userCenterContext';
import { formatMs, formatNumber, formatTokenCount, formatUsdCost } from '../utils';

export function UserUsagePage() {
  const { selectedUser, selectedUserId } = useUserCenter();
  const usageQuery = useQuery({ queryKey: ['admin-usage'], queryFn: () => fetchAdminUsage(), refetchInterval: 10000 });
  const [filters, setFilters] = useState({ start: '', end: '', model: '', status: 'all' });
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [showTools, setShowTools] = useState(false);
  const [inspectRow, setInspectRow] = useState<any | null>(null);
  const rows = usageQuery.data?.items || [];

  const filteredRows = useMemo(() => {
    const modelNeedle = filters.model.trim().toLowerCase();
    const start = filters.start ? new Date(filters.start).getTime() : 0;
    const end = filters.end ? new Date(filters.end).getTime() : 0;
    return rows.filter((row) => {
      if (selectedUserId && row.consumer_id !== selectedUserId) return false;
      const started = row.started_at ? new Date(String(row.started_at).replace(',', '.')).getTime() : 0;
      if (start && started && started < start) return false;
      if (end && started && started > end) return false;
      if (modelNeedle) {
        const hay = `${row.model || ''} ${row.resolved_model || ''} ${row.route_url || ''}`.toLowerCase();
        if (!hay.includes(modelNeedle)) return false;
      }
      if (filters.status === 'success' && (row.error || Number(row.status_code || 0) >= 400)) return false;
      if (filters.status === 'error' && !row.error && Number(row.status_code || 0) < 400) return false;
      return true;
    });
  }, [filters, rows, selectedUserId]);

  const pagedRows = useMemo(() => filteredRows.slice((page - 1) * pageSize, page * pageSize), [filteredRows, page, pageSize]);
  const totalPages = Math.max(1, Math.ceil(filteredRows.length / pageSize));

  const summary = useMemo(() => {
    return filteredRows.reduce(
      (acc, row) => {
        const prompt = Number(row.prompt_tokens || 0);
        const completion = Number(row.completion_tokens || 0);
        const total = Number(row.total_tokens || 0) || prompt + completion;
        acc.requests += 1;
        acc.tokens += total;
        acc.duration += Number(row.duration_ms || 0);
        acc.actualCost += Number(row.actual_cost || 0) || Number(row.total_cost || 0) || 0;
        acc.totalCost += Number(row.total_cost || 0) || 0;
        return acc;
      },
      { requests: 0, tokens: 0, duration: 0, actualCost: 0, totalCost: 0 },
    );
  }, [filteredRows]);

  const averageDuration = summary.requests ? Math.round(summary.duration / summary.requests) : 0;

  function exportCurrentView() {
    const lines = [
      ['时间', '模型', 'Token', '消费', '耗时', '状态', '线路'].join('\t'),
      ...filteredRows.map((row) => {
        const prompt = Number(row.prompt_tokens || 0);
        const completion = Number(row.completion_tokens || 0);
        const total = Number(row.total_tokens || 0) || prompt + completion;
        const actualCost = Number(row.actual_cost || 0) || Number(row.total_cost || 0) || 0;
        const ok = !row.error && Number(row.status_code || 0) < 400;
        return [
          row.started_at || '-',
          row.model || row.resolved_model || '-',
          String(total),
          String(actualCost),
          String(row.duration_ms || 0),
          ok ? '成功' : (row.error || row.status_code || '-'),
          row.route_url || '-',
        ].join('\t');
      }),
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
          <span>按用户账户查看请求记录、计费、耗时和异常状态。</span>
        </div>
        <div className="sub2-inline-summary">
          <div className="sub2-inline-summary-item"><span>当前账户</span><strong>{selectedUser?.name || '未选择用户'}</strong><small>{selectedUser?.group_name || selectedUser?.source_type || '请选择用户'}</small></div>
          <div className="sub2-inline-summary-item"><span>记录数</span><strong>{formatNumber(summary.requests)}</strong><small>当前筛选结果</small></div>
          <div className="sub2-inline-summary-item"><span>总 Token</span><strong>{formatTokenCount(summary.tokens)}</strong><small>请求与回复累计</small></div>
          <div className="sub2-inline-summary-item"><span>实际消费</span><strong>{formatUsdCost(summary.actualCost)}</strong><small>标准成本 {formatUsdCost(summary.totalCost)}</small></div>
          <div className="sub2-inline-summary-item"><span>平均耗时</span><strong>{formatMs(averageDuration)}</strong><small>按当前筛选计算</small></div>
        </div>
      </div>

      <TablePageLayout
        filters={(
          <FilterToolbar
            right={
              <ToolbarButtonRow>
                <Button onClick={() => void usageQuery.refetch()}><RefreshCw size={15} />刷新</Button>
                <details className="sub2-menu" open={showTools} onToggle={(event) => setShowTools((event.target as HTMLDetailsElement).open)}>
                  <summary>
                    <MoreHorizontal size={14} />
                    <span>更多工具</span>
                  </summary>
                  <div className="sub2-menu-panel">
                    <button type="button" onClick={() => { setFilters({ start: '', end: '', model: '', status: 'all' }); setPage(1); setShowTools(false); }}>
                      <span>清空筛选</span>
                    </button>
                    <button type="button" onClick={() => { exportCurrentView(); setShowTools(false); }}>
                      <span>导出当前视图</span>
                      <Download size={14} />
                    </button>
                  </div>
                </details>
              </ToolbarButtonRow>
            }
          >
            <SearchField value={filters.model} placeholder="搜索模型 / 线路" onChange={(value) => { setFilters((current) => ({ ...current, model: value })); setPage(1); }} />
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
          <div className="table-wrap table-scroll">
            <table>
              <thead>
                <tr>
                  <th>时间</th>
                  <th>模型</th>
                  <th>Token</th>
                  <th>消费</th>
                  <th>耗时</th>
                  <th>状态</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {pagedRows.length ? pagedRows.map((row, index) => {
                  const prompt = Number(row.prompt_tokens || 0);
                  const completion = Number(row.completion_tokens || 0);
                  const total = Number(row.total_tokens || 0) || prompt + completion;
                  const actualCost = Number(row.actual_cost || 0) || Number(row.total_cost || 0) || 0;
                  const totalCost = Number(row.total_cost || 0) || 0;
                  const ok = !row.error && Number(row.status_code || 0) < 400;
                  return (
                    <tr key={`${row.request_id || index}-${index}`}>
                      <td><div className="sub2-cell-stack sub2-cell-stack-tight"><strong>{row.started_at || '-'}</strong><small>{row.request_id || '-'}</small></div></td>
                      <td><div className="sub2-cell-stack sub2-cell-stack-tight"><strong>{row.model || '-'}</strong><small>{row.resolved_model || row.route_url || '-'}</small></div></td>
                      <td><div className="sub2-cell-stack sub2-cell-stack-tight"><strong>{formatTokenCount(total)}</strong><small>请求 {formatTokenCount(prompt)} / 回复 {formatTokenCount(completion)}</small></div></td>
                      <td><div className="sub2-cell-stack sub2-cell-stack-tight"><strong>{formatUsdCost(actualCost)}</strong><small>标准 {formatUsdCost(totalCost)}</small></div></td>
                      <td><strong className="sub2-number-cell">{formatMs(row.duration_ms || 0)}</strong></td>
                      <td><span className={ok ? 'badge badge-ok' : 'badge badge-warn'}>{ok ? '成功' : (row.error ? '异常' : (row.status_code || '-'))}</span></td>
                      <td>
                        <RowActions>
                          <RowAction icon={Eye} label="详情" onClick={() => setInspectRow(row)} />
                        </RowActions>
                      </td>
                    </tr>
                  );
                }) : (
                  <tr>
                    <td colSpan={7}>
                      <EmptyState title="暂无使用记录" description="当前筛选条件下没有可显示的请求记录。" />
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
        pagination={filteredRows.length ? (
          <Pager
            page={Math.min(page, totalPages)}
            pageSize={pageSize}
            total={filteredRows.length}
            onPageChange={(next) => setPage(Math.min(Math.max(1, next), totalPages))}
            onPageSizeChange={(next) => { setPageSize(next); setPage(1); }}
          />
        ) : null}
      />

      {inspectRow ? (
        <Modal
          title="请求详情"
          size="lg"
          onClose={() => setInspectRow(null)}
          footer={<ModalActions><Button onClick={() => setInspectRow(null)}>关闭</Button></ModalActions>}
        >
          <div className="admin-dialog">
            <div className="admin-dialog-intro">
              <strong>{inspectRow.request_id || '未命名请求'}</strong>
              <span>这里可以核对单次请求的模型、线路、计费和异常信息。</span>
            </div>
            <div className="admin-dialog-summary">
              <div className="admin-dialog-summary-card">
                <span>模型</span>
                <strong>{inspectRow.model || inspectRow.resolved_model || '-'}</strong>
                <small>{inspectRow.resolved_model || '-'}</small>
              </div>
              <div className="admin-dialog-summary-card">
                <span>消费</span>
                <strong>{formatUsdCost(Number(inspectRow.actual_cost || 0) || Number(inspectRow.total_cost || 0) || 0)}</strong>
                <small>标准 {formatUsdCost(Number(inspectRow.total_cost || 0) || 0)}</small>
              </div>
              <div className="admin-dialog-summary-card">
                <span>状态</span>
                <strong>{!inspectRow.error && Number(inspectRow.status_code || 0) < 400 ? '成功' : '异常'}</strong>
                <small>{inspectRow.route_url || '-'}</small>
              </div>
            </div>
            <div className="admin-dialog-grid">
              <Field label="开始时间"><TextInput readOnly value={inspectRow.started_at || '-'} /></Field>
              <Field label="耗时"><TextInput readOnly value={`${formatNumber(inspectRow.duration_ms || 0)} ms`} /></Field>
              <Field label="总 Token"><TextInput readOnly value={String(Number(inspectRow.total_tokens || 0) || Number(inspectRow.prompt_tokens || 0) + Number(inspectRow.completion_tokens || 0))} /></Field>
              <Field label="线路"><TextInput readOnly value={inspectRow.route_url || '-'} /></Field>
              <Field label="请求 Token"><TextInput readOnly value={String(inspectRow.prompt_tokens || 0)} /></Field>
              <Field label="回复 Token"><TextInput readOnly value={String(inspectRow.completion_tokens || 0)} /></Field>
            </div>
            <Field label="异常信息" full>
              <TextArea readOnly rows={6} value={inspectRow.error || '-'} />
            </Field>
          </div>
        </Modal>
      ) : null}
    </section>
  );
}
