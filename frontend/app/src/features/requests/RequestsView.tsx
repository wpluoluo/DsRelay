import { useMutation } from '@tanstack/react-query';
import { ListChecks, Trash2 } from 'lucide-react';
import { clearRequestCache, clearRequests } from '../../api';
import { Badge, Button, Empty, Panel, PanelHead } from '../../components';
import { queryClient } from '../../state/queryClient';
import type { DashboardState, RequestEntry } from '../../types';
import { formatMs, formatNumber, maskEmpty } from '../../utils';

export function RequestsView({ state }: { state: DashboardState }) {
  const rows = [...(state.active_requests || []), ...(state.recent_requests || [])];
  return (
    <Panel>
      <PanelHead title={<><ListChecks size={18} />请求观测</>} action={<RequestActions />} />
      <div className="table-wrap">
        <table>
          <thead><tr><th>时间</th><th>状态</th><th>协议</th><th>模型</th><th>线路</th><th>耗时</th><th>Token</th></tr></thead>
          <tbody>
            {rows.length ? rows.slice(0, 80).map((entry, index) => <RequestRow key={`${entry.request_id || index}-${index}`} entry={entry} />) : <tr><td colSpan={7}><Empty>暂无请求数据。</Empty></td></tr>}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}

function RequestActions() {
  const clearMutation = useMutation({ mutationFn: clearRequests, onSuccess: () => queryClient.invalidateQueries({ queryKey: ['dashboard-state'] }) });
  const cacheMutation = useMutation({ mutationFn: clearRequestCache, onSuccess: () => queryClient.invalidateQueries({ queryKey: ['dashboard-state'] }) });
  return <div className="button-row"><Button onClick={() => clearMutation.mutate()}><Trash2 size={14} />清空请求</Button><Button onClick={() => cacheMutation.mutate()}><Trash2 size={14} />清空缓存</Button></div>;
}

function RequestRow({ entry }: { entry: RequestEntry }) {
  const status = entry.status_text || entry.status_code || (entry.error ? '异常' : entry.active ? '处理中' : '-');
  const tone = entry.error ? 'bad' : Number(entry.status_code || 0) >= 400 ? 'warn' : 'ok';
  return (
    <tr>
      <td><strong>{maskEmpty(entry.started_at)}</strong><small>{maskEmpty(entry.request_id)}</small></td>
      <td><Badge tone={tone}>{String(status)}</Badge></td>
      <td>{maskEmpty(entry.protocol || entry.path)}</td>
      <td><strong>{maskEmpty(entry.logical_model || entry.model)}</strong><small>{maskEmpty(entry.resolved_model)}</small></td>
      <td><strong>{maskEmpty(entry.selected_pool_name)}</strong><small>{maskEmpty(entry.route_url || entry.upstream_url)}</small></td>
      <td>{formatMs(entry.duration_ms)}</td>
      <td>{formatNumber(entry.prompt_tokens)} ↓ / {formatNumber(entry.completion_tokens)} ↑</td>
    </tr>
  );
}
