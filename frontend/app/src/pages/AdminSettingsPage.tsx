import { Save, Settings } from 'lucide-react';
import { Button, Panel, PanelHead, Tabs } from '../components';
import { RoutingPanel } from '../features/config/RoutingPanel';
import { StrategyPanel } from '../features/config/StrategyPanel';
import { buildPageIntro } from '../navigation';
import { useDashboard } from '../state/dashboardContext';

type SettingsTab = 'routing' | 'strategy';

export function AdminSettingsPage() {
  const dashboard = useDashboard();
  const currentTab = (dashboard.configTab as SettingsTab) || 'routing';

  const items: Array<{ value: SettingsTab; label: string }> = [
    { value: 'routing', label: '模型与路由' },
    { value: 'strategy', label: '全局策略' },
  ];

  return (
    <section className="grid-page">
      {buildPageIntro('/admin/settings')}
      <Panel>
        <PanelHead
          title={<><Settings size={18} />系统设置</>}
        />
        <Tabs value={currentTab} onChange={(tab) => dashboard.setConfigTab(tab as any)} items={items} />
        {currentTab === 'routing' ? <RoutingPanel /> : null}
        {currentTab === 'strategy' ? <StrategyPanel draft={dashboard.draft} onPatch={dashboard.patchDraft} /> : null}
        <div className="save-strip">
          <span className={dashboard.status.includes('失败') ? 'bad-text' : ''}>{dashboard.status || '修改后点击保存并生效。'}</span>
          <Button tone="primary" disabled={dashboard.saving} onClick={dashboard.saveConfig}>
            <Save size={15} />
            {dashboard.saving ? '正在保存' : '保存并生效'}
          </Button>
        </div>
      </Panel>
    </section>
  );
}
