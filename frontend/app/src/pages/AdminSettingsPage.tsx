import { Save, Settings, ShieldCheck } from 'lucide-react';
import { Button, Panel, PanelHead, Tabs } from '../components';
import { ProxyKeys } from '../features/keys/ProxyKeys';
import { RoutingPanel } from '../features/config/RoutingPanel';
import { StrategyPanel } from '../features/config/StrategyPanel';
import { buildPageIntro } from '../navigation';
import { useDashboard } from '../state/dashboardContext';

type SettingsTab = 'routing' | 'strategy' | 'keys';

export function AdminSettingsPage() {
  const dashboard = useDashboard();
  const payload = dashboard.keyQuery.data;
  const currentTab = (dashboard.configTab as SettingsTab) || 'routing';

  const items: Array<{ value: SettingsTab; label: string }> = [
    { value: 'routing', label: '模型与路由' },
    { value: 'strategy', label: '全局策略' },
    { value: 'keys', label: '入口 API Key' },
  ];

  return (
    <section className="grid-page">
      {buildPageIntro('/admin/settings')}
      <Panel>
        <PanelHead
          title={<><Settings size={18} />系统设置</>}
          action={<span className="subtle">按系统、路由和入口鉴权三类统一维护</span>}
        />
        <Tabs value={currentTab} onChange={(tab) => dashboard.setConfigTab(tab as any)} items={items} />
        {currentTab === 'routing' ? (
          <div className="section-stack">
            <div className="overview-alert-list">
              <div className="overview-alert info">
                <strong>模型与路由</strong>
                <span>维护默认模型、线路映射、协议归属和路由真值。具体渠道条目已经移到“渠道管理”。</span>
              </div>
            </div>
            <RoutingPanel />
          </div>
        ) : null}
        {currentTab === 'strategy' ? (
          <div className="section-stack">
            <div className="overview-alert-list">
              <div className="overview-alert info">
                <strong>全局策略</strong>
                <span>统一管理超时、重试、切换窗口、缓存提示和模型候选行为，属于系统级控制面。</span>
              </div>
            </div>
            <StrategyPanel draft={dashboard.draft} onPatch={dashboard.patchDraft} />
          </div>
        ) : null}
        {currentTab === 'keys' ? (
          <div className="section-stack">
            <div className="sub2-inline-summary">
              <div className="sub2-inline-summary-item"><span>托管入口 Key</span><strong>{payload?.managed_key_count || 0}</strong><small>本地维护</small></div>
              <div className="sub2-inline-summary-item"><span>当前可用</span><strong>{(payload?.managed_enabled_count || 0) + (payload?.env_key_count || 0)}</strong><small>入口鉴权可用</small></div>
              <div className="sub2-inline-summary-item"><span>环境变量</span><strong>{payload?.env_key_count || 0}</strong><small>来自 PROXY_API_KEYS</small></div>
              <div className="sub2-inline-summary-item"><span>托管已启用</span><strong>{payload?.managed_enabled_count || 0}</strong><small>当前参与鉴权</small></div>
            </div>
            <div className="overview-alert-list">
              <div className="overview-alert info">
                <strong>入口 API Key</strong>
                <span>这里只处理代理入口鉴权。用户 API Key 属于用户资产，放在“我的账户 / API 密钥”与后台用户体系中管理。</span>
              </div>
            </div>
            <ProxyKeys payload={payload} refresh={() => dashboard.keyQuery.refetch()} />
          </div>
        ) : null}
        <div className="save-strip">
          <span className={dashboard.status.includes('失败') ? 'bad-text' : ''}>{dashboard.status || '修改后点击保存并生效。'}</span>
          <Button tone="primary" disabled={dashboard.saving} onClick={dashboard.saveConfig}>
            <Save size={15} />
            {dashboard.saving ? '正在保存' : '保存并生效'}
          </Button>
        </div>
      </Panel>
      <Panel>
        <PanelHead title={<><ShieldCheck size={18} />设置说明</>} />
        <div className="overview-alert-list">
          <div className="overview-alert info">
            <strong>设置边界</strong>
            <span>系统设置只保留系统级参数。渠道本体放在“渠道管理”，用户资产与订阅不从这里进入。</span>
          </div>
          <div className="overview-alert info">
            <strong>保存方式</strong>
            <span>路由、策略和入口鉴权仍然共用一套保存动作，避免不同页签之间出现配置漂移。</span>
          </div>
        </div>
      </Panel>
    </section>
  );
}
