import { Activity, Tag } from 'lucide-react';
import { Panel, PanelHead } from '../components';
import { PoolList } from '../features/config/PoolList';
import { buildPageIntro } from '../navigation';
import { useDashboard } from '../state/dashboardContext';
import { formatNumber } from '../utils';

export function AdminChannelsPricingPage() {
  const dashboard = useDashboard();
  const enabledCount = dashboard.pools.filter((pool) => pool.enabled !== false).length;

  return (
    <section className="grid-page">
      {buildPageIntro('/admin/channels/pricing')}
      <Panel>
        <PanelHead
          title={<><Tag size={18} />渠道定价</>}
          action={<span className="subtle">按渠道维护优先级、模型映射、协议和地址。</span>}
        />
        <div className="section-stack">
          <div className="sub2-inline-summary">
            <div className="sub2-inline-summary-item"><span>渠道总数</span><strong>{formatNumber(dashboard.pools.length)}</strong><small>当前连接池</small></div>
            <div className="sub2-inline-summary-item"><span>已启用</span><strong>{formatNumber(enabledCount)}</strong><small>停用 {formatNumber(Math.max(0, dashboard.pools.length - enabledCount))}</small></div>
          </div>
          <PoolList
            pools={dashboard.pools}
            onOpenPool={dashboard.openPool}
            onDeletePool={dashboard.deletePool}
            onMovePool={dashboard.movePool}
          />
        </div>
      </Panel>
    </section>
  );
}

export function AdminChannelsMonitorPage() {
  const dashboard = useDashboard();
  const enabledCount = dashboard.pools.filter((pool) => pool.enabled !== false).length;
  const disabledCount = Math.max(0, dashboard.pools.length - enabledCount);

  return (
    <section className="grid-page">
      {buildPageIntro('/admin/channels/monitor')}
      <Panel>
        <PanelHead
          title={<><Activity size={18} />渠道监控</>}
          action={<span className="subtle">先对齐 SUB2 的监控入口，当前承接基础渠道状态观察。</span>}
        />
        <div className="sub2-inline-summary">
          <div className="sub2-inline-summary-item"><span>启用渠道</span><strong>{formatNumber(enabledCount)}</strong><small>当前参与调度</small></div>
          <div className="sub2-inline-summary-item"><span>停用渠道</span><strong>{formatNumber(disabledCount)}</strong><small>不参与调度</small></div>
          <div className="sub2-inline-summary-item"><span>最近状态</span><strong>{dashboard.status || '待保存'}</strong><small>来自当前运行态</small></div>
        </div>
      </Panel>
    </section>
  );
}
