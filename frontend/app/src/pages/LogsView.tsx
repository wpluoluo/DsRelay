import { Server } from 'lucide-react';
import { Empty, Panel, PanelHead } from '../components';
import type { DashboardState, RequestEntry } from '../types';
import { maskEmpty } from '../utils';

export function LogsView({ state }: { state: DashboardState }) {
  const lines = [...(state.recent_logs || [])].reverse();
  const recentMap = buildRecentRequestMap(state.recent_requests || []);
  return (
    <Panel>
      <PanelHead title={<><Server size={18} />运行日志</>} />
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
          </colgroup>
          <thead><tr><th>时间</th><th>级别</th><th>请求</th><th>事件</th><th>线路</th><th>模型</th><th>消息</th></tr></thead>
          <tbody>
            {lines.length ? lines.map((line, index) => <LogRow key={`${index}-${line}`} line={line} recentMap={recentMap} />) : <tr><td colSpan={7}><Empty>暂无日志。</Empty></td></tr>}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}

function LogRow({ line, recentMap }: { line: string; recentMap: Record<string, RequestEntry> }) {
  const text = String(line || '');
  const time = text.match(/^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3})/)?.[1] || '-';
  const level = text.match(/\[(INFO|WARNING|ERROR|DEBUG)\]/)?.[1] || 'INFO';
  const requestId = text.match(/request_id=([a-zA-Z0-9_-]+)/)?.[1] || '';
  const recent = requestId ? recentMap[requestId] : undefined;
  const route = routeSummaryForEntry(recent) || text.match(/线路=([^\s]+)/)?.[1] || text.match(/上游=([^\s]+)/)?.[1] || '-';
  const pool = recent?.pool_name || recent?.selected_pool_name || text.match(/连接池=([^\s]+)/)?.[1] || '-';
  const keySwitch = text.match(/([a-f0-9]{8,12})->([a-f0-9]{8,12})/i);
  const keyText = keySwitch ? `${keySwitch[1]} -> ${keySwitch[2]}` : '-';
  const model = text.match(/逻辑模型=([^\s]+)/)?.[1] || text.match(/模型=([^\s]+)/)?.[1] || '-';
  const status = text.match(/状态=([^\s]+)/)?.[1] || (text.includes('等待上游首包中') ? '等待首包' : '-');
  const eventTitle = eventTitleForLog(text);
  const message = text.replace(/^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3})\s*/, '').replace(/\[(INFO|WARNING|ERROR|DEBUG)\]\s*/, '').trim();
  return (
    <tr>
      <td><div className="request-cell-title no-wrap">{time}</div></td>
      <td><span className={`request-chip log-level-chip ${levelTone(level)}`}>{level}</span></td>
      <td><div className="request-cell-sub request-mono log-request-id">{maskEmpty(requestId)}</div></td>
      <td><div className="log-event"><div className="log-event-title">{eventTitle}</div><div className="log-subtle">状态 {status}</div></div></td>
      <td><div className="log-event"><div className="log-event-title">{pool}</div><div className="log-route">{keyText}</div></div></td>
      <td><div className="log-event"><div className="log-event-title">{model}</div><div className="log-route">{route}</div>{recent ? <div className="request-chip-row"><RouteScopeChip entry={recent} /></div> : null}</div></td>
      <td><div className="log-message">{message || text}</div></td>
    </tr>
  );
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
