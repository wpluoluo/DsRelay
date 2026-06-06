import { Server } from 'lucide-react';
import { Empty, Panel, PanelHead } from '../components';
import type { DashboardState } from '../types';

export function LogsView({ state }: { state: DashboardState }) {
  return (
    <Panel>
      <PanelHead title={<><Server size={18} />运行日志</>} />
      <div className="log-list">{(state.recent_logs || []).length ? state.recent_logs!.map((line, i) => <code key={i}>{line}</code>) : <Empty>暂无日志。</Empty>}</div>
    </Panel>
  );
}
