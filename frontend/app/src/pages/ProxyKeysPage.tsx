import { KeyRound } from 'lucide-react';
import { Panel, PanelHead } from '../components';
import { ProxyKeys } from '../features/keys/ProxyKeys';
import { useDashboard } from '../state/dashboardContext';

export function ProxyKeysPage() {
  const { keyQuery } = useDashboard();
  const payload = keyQuery.data;
  const enabled = (payload?.managed_enabled_count || 0) + (payload?.env_key_count || 0);
  return (
    <Panel className="key-page-panel">
      <PanelHead title={<><KeyRound size={18} />API Key 管理</>} action={<span className="subtle">{enabled ? `${enabled} 个入口 Key 可用` : '未配置入口 Key'}</span>} />
      <ProxyKeys payload={payload} refresh={() => keyQuery.refetch()} />
    </Panel>
  );
}
