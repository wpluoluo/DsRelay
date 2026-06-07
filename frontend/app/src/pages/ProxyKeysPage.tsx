import { KeyRound } from 'lucide-react';
import { Panel, PanelHead } from '../components';
import { ProxyKeys } from '../features/keys/ProxyKeys';
import { useDashboard } from '../state/dashboardContext';
import { formatNumber } from '../utils';

export function ProxyKeysPage() {
  const { keyQuery } = useDashboard();
  const payload = keyQuery.data;
  const enabled = (payload?.managed_enabled_count || 0) + (payload?.env_key_count || 0);
  const managed = payload?.managed_key_count || 0;
  const envCount = payload?.env_key_count || 0;
  const localOnly = Math.max(0, managed - (payload?.managed_enabled_count || 0));
  return (
    <Panel className="key-page-panel">
      <PanelHead title={<><KeyRound size={18} />入口 API Key</>} action={<span className="subtle">{enabled ? `${enabled} 个入口 Key 可用` : '未配置入口 Key'}</span>} />
      <div className="sub2-key-page">
        <div className="sub2-inline-summary">
          <div className="sub2-inline-summary-item"><span>托管入口 Key</span><strong>{formatNumber(managed)}</strong><small>本地维护</small></div>
          <div className="sub2-inline-summary-item"><span>当前可用</span><strong>{formatNumber(enabled)}</strong><small>可用于入口鉴权</small></div>
          <div className="sub2-inline-summary-item"><span>环境变量</span><strong>{formatNumber(envCount)}</strong><small>来自 PROXY_API_KEYS</small></div>
          <div className="sub2-inline-summary-item"><span>未启用托管</span><strong>{formatNumber(localOnly)}</strong><small>保留但不参与鉴权</small></div>
        </div>
      </div>
      <ProxyKeys payload={payload} refresh={() => keyQuery.refetch()} />
    </Panel>
  );
}
