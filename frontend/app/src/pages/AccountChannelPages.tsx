import { useQuery } from '@tanstack/react-query';
import { fetchAdminPaymentChannels } from '../api';
import { Panel, PanelHead } from '../components';
import { buildPageIntro } from '../navigation';
import { useAccountCenter } from '../state/accountCenterContext';
import { useDashboard } from '../state/dashboardContext';
import { formatNumber } from '../utils';

export function AccountAvailableChannelsPage() {
  const { visibleChannels, visiblePlans } = useAccountCenter();
  const channelsQuery = useQuery({ queryKey: ['admin-payment-channels'], queryFn: fetchAdminPaymentChannels, refetchInterval: 30000 });
  const configuredChannels = channelsQuery.data?.items || [];
  return (
    <section className="grid-page">
      {buildPageIntro('/available-channels')}
      <div className="sub2-inline-summary">
        <div className="sub2-inline-summary-item"><span>可见渠道</span><strong>{formatNumber(visibleChannels.length)}</strong><small>用户范围</small></div>
        <div className="sub2-inline-summary-item"><span>可购计划</span><strong>{formatNumber(visiblePlans.length)}</strong><small>当前可见</small></div>
        <div className="sub2-inline-summary-item"><span>后台已配通道</span><strong>{formatNumber(configuredChannels.length)}</strong><small>管理后台口径</small></div>
      </div>
      <Panel>
        <PanelHead title="当前可用渠道" />
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>名称</th>
                <th>提供方</th>
                <th>状态</th>
              </tr>
            </thead>
            <tbody>
              {visibleChannels.length ? visibleChannels.map((item: any, index) => (
                <tr key={`${item.id || item.name || index}`}>
                  <td>{item.name || item.id || `渠道 ${index + 1}`}</td>
                  <td>{item.provider || '-'}</td>
                  <td>{item.enabled === false ? '停用' : '可用'}</td>
                </tr>
              )) : (
                <tr><td colSpan={3}>当前用户暂无可用渠道。</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </Panel>
    </section>
  );
}

export function AccountMonitorPage() {
  const dashboard = useDashboard();
  const routes = dashboard.state.route_observability || [];
  return (
    <section className="grid-page">
      {buildPageIntro('/monitor')}
      <Panel>
        <PanelHead title="渠道状态" />
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>线路</th>
                <th>状态</th>
                <th>请求</th>
                <th>异常</th>
              </tr>
            </thead>
            <tbody>
              {routes.length ? routes.map((item, index) => (
                <tr key={`${item.route_url || item.pool_name || index}`}>
                  <td>{item.pool_name || item.route_url || `线路 ${index + 1}`}</td>
                  <td>{item.route_status_text || '-'}</td>
                  <td>{formatNumber(item.request_count || 0)}</td>
                  <td>{formatNumber(item.error_count || 0)}</td>
                </tr>
              )) : (
                <tr><td colSpan={4}>暂无渠道状态数据。</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </Panel>
    </section>
  );
}

export function AccountProfilePage() {
  const { selectedUser } = useAccountCenter();
  return (
    <section className="grid-page">
      {buildPageIntro('/profile')}
      <Panel>
        <PanelHead title="个人资料" />
        <div className="info-grid">
          <div className="metric-line"><span>用户名称</span><strong>{selectedUser?.name || '-'}</strong></div>
          <div className="metric-line"><span>来源类型</span><strong>{selectedUser?.source_type || '-'}</strong></div>
          <div className="metric-line"><span>分组</span><strong>{selectedUser?.group_name || selectedUser?.group_id || '-'}</strong></div>
          <div className="metric-line"><span>角色</span><strong>{selectedUser?.role || '-'}</strong></div>
          <div className="metric-line"><span>状态</span><strong>{selectedUser?.status || '-'}</strong></div>
          <div className="metric-line"><span>备注</span><strong>{selectedUser?.note || '-'}</strong></div>
        </div>
      </Panel>
    </section>
  );
}
