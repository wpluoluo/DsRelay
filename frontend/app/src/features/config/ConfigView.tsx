import { Save } from 'lucide-react';
import { Button, Panel, PanelHead, Tabs } from '../../components';
import type { Pool, RuntimeConfig } from '../../types';
import type { ConfigTab } from './model';
import { PoolList } from './PoolList';
import { RoutingPanel } from './RoutingPanel';
import { StrategyPanel } from './StrategyPanel';

export function ConfigView(props: {
  draft: RuntimeConfig;
  pools: Pool[];
  configTab: ConfigTab;
  setConfigTab: (tab: ConfigTab) => void;
  status: string;
  saving: boolean;
  onPatch: (patch: Partial<RuntimeConfig>) => void;
  onSave: () => void;
  onOpenPool: (index: number | null) => void;
  onDeletePool: (index: number) => void;
  onMovePool: (index: number, direction: number) => void;
}) {
  return (
    <section className="config-layout config-layout-single">
      <Panel>
        <Tabs value={props.configTab} onChange={props.setConfigTab} items={[{ value: 'routes', label: '连接池' }, { value: 'routing', label: '模型与路由' }, { value: 'strategy', label: '策略' }]} />
        {props.configTab === 'routes' ? <PoolList pools={props.pools} onOpenPool={props.onOpenPool} onDeletePool={props.onDeletePool} onMovePool={props.onMovePool} /> : null}
        {props.configTab === 'routing' ? <RoutingPanel /> : null}
        {props.configTab === 'strategy' ? <StrategyPanel draft={props.draft} onPatch={props.onPatch} /> : null}
        <div className="save-strip">
          <span className={props.status.includes('失败') ? 'bad-text' : ''}>{props.status}</span>
          <Button tone="primary" disabled={props.saving} onClick={props.onSave}><Save size={15} />{props.saving ? '正在保存' : '保存并生效'}</Button>
        </div>
      </Panel>
    </section>
  );
}
