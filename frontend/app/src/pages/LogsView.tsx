import { useMemo, useState } from 'react';
import { Eye } from 'lucide-react';
import { Button, Field, Modal, ModalActions, TextArea, TextInput } from '../components';
import { EmptyState, RowAction, RowActions, TablePageLayout } from '../components/admin';
import type { DashboardState, RequestEntry } from '../types';
import { formatNumber, maskEmpty } from '../utils';

type ParsedLogRow = {
  raw: string;
  time: string;
  level: string;
  requestId: string;
  route: string;
  pool: string;
  keyText: string;
  model: string;
  status: string;
  eventTitle: string;
  message: string;
  recent?: RequestEntry;
};

export function LogsView({ state }: { state: DashboardState }) {
  const lines = [...(state.recent_logs || [])].reverse();
  const recentMap = buildRecentRequestMap(state.recent_requests || []);
  const rows = useMemo(() => lines.map((line) => parseLogRow(String(line || ''), recentMap)), [lines, recentMap]);
  const [inspectRow, setInspectRow] = useState<ParsedLogRow | null>(null);
  const errorCount = rows.filter((row) => row.level === 'ERROR').length;
  const warningCount = rows.filter((row) => row.level === 'WARNING').length;
  const requestLinkedCount = rows.filter((row) => Boolean(row.requestId)).length;

  return (
    <section className="grid-page">
      <div className="sub2-page-head">
        <div className="sub2-page-title">
          <strong>运行日志</strong>
          <span>保留最近日志并关联请求上下文，便于直接排查线路和状态。</span>
        </div>
        <div className="sub2-inline-summary">
          <div className="sub2-inline-summary-item"><span>日志总数</span><strong>{formatNumber(rows.length)}</strong><small>最近运行日志</small></div>
          <div className="sub2-inline-summary-item"><span>关联请求</span><strong>{formatNumber(requestLinkedCount)}</strong><small>可回溯 request_id</small></div>
          <div className="sub2-inline-summary-item"><span>告警</span><strong>{formatNumber(warningCount)}</strong><small>WARNING 级别</small></div>
          <div className="sub2-inline-summary-item"><span>错误</span><strong>{formatNumber(errorCount)}</strong><small>ERROR 级别</small></div>
        </div>
      </div>
      <TablePageLayout
        table={
          <div className="table-wrap table-scroll table-logs">
            <table>
              <colgroup>
                <col className="col-log-time" />
                <col className="col-log-level" />
                <col className="col-log-request" />
                <col className="col-log-event" />
                <col className="col-log-route" />
                <col className="col-log-model" />
                <col className="col-log-message" />
                <col className="col-key-actions" />
              </colgroup>
              <thead><tr><th>时间</th><th>级别</th><th>请求</th><th>事件</th><th>线路</th><th>模型</th><th>消息</th><th>操作</th></tr></thead>
              <tbody>
                {rows.length ? rows.map((row, index) => (
                  <tr key={`${index}-${row.raw}`}>
                    <td><div className="request-cell-title no-wrap">{row.time}</div></td>
                    <td><span className={`request-chip log-level-chip ${levelTone(row.level)}`}>{row.level}</span></td>
                    <td><div className="request-cell-sub request-mono log-request-id">{maskEmpty(row.requestId)}</div></td>
                    <td><div className="log-event"><div className="log-event-title">{row.eventTitle}</div><div className="log-subtle">状态 {row.status}</div></div></td>
                    <td><div className="log-event"><div className="log-event-title">{row.pool}</div><div className="log-route">{row.keyText}</div></div></td>
                    <td><div className="log-event"><div className="log-event-title">{row.model}</div><div className="log-route">{row.route}</div>{row.recent ? <div className="request-chip-row"><RouteScopeChip entry={row.recent} /></div> : null}</div></td>
                    <td><div className="log-message">{row.message || row.raw}</div></td>
                    <td>
                      <RowActions>
                        <RowAction icon={Eye} label="详情" onClick={() => setInspectRow(row)} />
                      </RowActions>
                    </td>
                  </tr>
                )) : <tr><td colSpan={8}><EmptyState title="暂无日志" /></td></tr>}
              </tbody>
            </table>
          </div>
        }
      />

      {inspectRow ? (
        <Modal
          title="日志详情"
          size="lg"
          onClose={() => setInspectRow(null)}
          footer={<ModalActions><Button onClick={() => setInspectRow(null)}>关闭</Button></ModalActions>}
        >
          <div className="admin-dialog">
            <div className="admin-dialog-intro">
              <strong>{inspectRow.eventTitle}</strong>
              <span>查看当前日志的完整文本，以及它关联到的请求上下文。</span>
            </div>
            <div className="admin-dialog-grid">
              <Field label="时间"><TextInput readOnly value={inspectRow.time} /></Field>
              <Field label="级别"><TextInput readOnly value={inspectRow.level} /></Field>
              <Field label="请求 ID"><TextInput readOnly value={inspectRow.requestId || '-'} /></Field>
              <Field label="状态"><TextInput readOnly value={inspectRow.status || '-'} /></Field>
              <Field label="连接池"><TextInput readOnly value={inspectRow.pool || '-'} /></Field>
              <Field label="模型"><TextInput readOnly value={inspectRow.model || '-'} /></Field>
            </div>
            <Field label="消息正文" full>
              <TextArea readOnly rows={8} value={inspectRow.message || inspectRow.raw} />
            </Field>
            <Field label="原始日志" full>
              <TextArea readOnly rows={6} value={inspectRow.raw} />
            </Field>
          </div>
        </Modal>
      ) : null}
    </section>
  );
}

function parseLogRow(text: string, recentMap: Record<string, RequestEntry>): ParsedLogRow {
  const time = text.match(/^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3})/)?.[1] || '-';
  const level = text.match(/\[(INFO|WARNING|ERROR|DEBUG)\]/)?.[1] || 'INFO';
  const requestId = text.match(/request_id=([a-zA-Z0-9_-]+)/)?.[1] || '';
  const recent = requestId ? recentMap[requestId] : undefined;
  const route = routeSummaryForEntry(recent) || text.match(/线路=([^\s]+)/)?.[1] || text.match(/上游=([^\s]+)/)?.[1] || '-';
  const pool = recent?.pool_name || recent?.selected_pool_name || text.match(/连接池=([^\s]+)/)?.[1] || '-';
  const keySwitch = text.match(/([a-f0-9]{8,12})->([a-f0-9]{8,12})/i);
  const keyText = keySwitch ? `${keySwitch[1]} -> ${keySwitch[2]}` : '-';
  const model = recent?.requested_model || text.match(/逻辑模型=([^\s]+)/)?.[1] || text.match(/模型=([^\s]+)/)?.[1] || '-';
  const status = text.match(/状态=([^\s]+)/)?.[1] || (text.includes('等待上游首包中') ? '等待首包' : '-');
  const eventTitle = eventTitleForLog(text);
  const message = text.replace(/^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3})\s*/, '').replace(/\[(INFO|WARNING|ERROR|DEBUG)\]\s*/, '').trim();
  return { raw: text, time, level, requestId, route, pool, keyText, model, status, eventTitle, message, recent };
}

function buildRecentRequestMap(rows: RequestEntry[]) {
  const result: Record<string, RequestEntry> = {};
  for (const row of rows) {
    if (row.request_id) result[row.request_id] = row;
  }
  return result;
}

function routeSummaryForEntry(entry?: RequestEntry) {
  if (!entry) return '';
  return String(entry.route_url || entry.upstream_url || '');
}

function eventTitleForLog(text: string) {
  if (text.includes('入站请求')) return '入站请求';
  if (text.includes('模型候选')) return '模型候选';
  if (text.includes('切换Key')) return '切换 Key';
  if (text.includes('上游尝试摘要')) return '尝试摘要';
  if (text.includes('上游=')) return '上游响应';
  return '运行日志';
}

function levelTone(level: string) {
  if (level === 'ERROR') return 'error';
  if (level === 'WARNING') return 'warn';
  if (level === 'DEBUG') return 'debug';
  return 'info';
}

function RouteScopeChip({ entry }: { entry: RequestEntry }) {
  const status = String(entry.route_resolution || '');
  if (status === 'exact') return <span className="request-chip ok">当前链路</span>;
  if (status === 'base_only') return <span className="request-chip accent">当前基线</span>;
  if (status === 'base_only_ambiguous') return <span className="request-chip warn">当前基线(待确认)</span>;
  return <span className="request-chip">历史链路</span>;
}
