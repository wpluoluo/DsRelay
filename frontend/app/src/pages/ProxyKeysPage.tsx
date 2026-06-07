import { KeyRound, ShieldCheck, Terminal, Vault } from 'lucide-react';
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
      <PanelHead title={<><KeyRound size={18} />API Key 管理</>} action={<span className="subtle">{enabled ? `${enabled} 个入口 Key 可用` : '未配置入口 Key'}</span>} />
      <div className="sub2-key-page">
        <div className="key-stat-grid">
          <div className="key-stat">
            <div className="key-stat-icon blue"><Vault size={18} /></div>
            <div><span>托管入口 Key</span><strong>{formatNumber(managed)}</strong><small>本地维护</small></div>
          </div>
          <div className="key-stat">
            <div className="key-stat-icon green"><ShieldCheck size={18} /></div>
            <div><span>当前可用</span><strong>{formatNumber(enabled)}</strong><small>可用于入口鉴权</small></div>
          </div>
          <div className="key-stat">
            <div className="key-stat-icon amber"><Terminal size={18} /></div>
            <div><span>环境变量</span><strong>{formatNumber(envCount)}</strong><small>来自 PROXY_API_KEYS</small></div>
          </div>
          <div className="key-stat">
            <div className="key-stat-icon slate"><KeyRound size={18} /></div>
            <div><span>当前状态</span><strong>{enabled ? '已配置' : '未配置'}</strong><small>入口控制面</small></div>
          </div>
        </div>
        <div className="admin-ops-strip">
          <div className="admin-ops-item">
            <span>入口鉴权</span>
            <strong>{enabled ? '已启用' : '未启用'}</strong>
            <small>{enabled ? `当前 ${formatNumber(enabled)} 个入口 Key 可用` : '当前没有可用入口 Key'}</small>
          </div>
          <div className="admin-ops-item">
            <span>托管状态</span>
            <strong>{formatNumber(managed)} 个托管</strong>
            <small>其中未启用 {formatNumber(localOnly)} 个</small>
          </div>
          <div className="admin-ops-item">
            <span>环境注入</span>
            <strong>{formatNumber(envCount)} 个</strong>
            <small>来自 PROXY_API_KEYS</small>
          </div>
          <div className="admin-ops-item">
            <span>列表同步</span>
            <strong>实时刷新</strong>
            <small>操作后立即回刷代理运行状态</small>
          </div>
        </div>
      </div>
      <ProxyKeys payload={payload} refresh={() => keyQuery.refetch()} />
    </Panel>
  );
}
