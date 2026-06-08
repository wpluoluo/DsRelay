import { Panel, PanelHead } from '../components';
import { buildPageIntro } from '../navigation';
import { useDashboard } from '../state/dashboardContext';
import { formatNumber } from '../utils';

export function AdminProxyPage() {
  const dashboard = useDashboard();
  const routes = dashboard.state.route_observability || [];

  return (
    <section className="grid-page">
      {buildPageIntro('/admin/proxies')}
      <div className="sub2-inline-summary">
        <div className="sub2-inline-summary-item"><span>线路观测</span><strong>{formatNumber(routes.length)}</strong><small>当前可见线路</small></div>
        <div className="sub2-inline-summary-item"><span>当前状态</span><strong>{dashboard.status || '待保存'}</strong><small>运行态摘要</small></div>
      </div>
      <Panel>
        <PanelHead title="线路观测" />
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>线路</th>
                <th>请求</th>
                <th>成功</th>
                <th>异常</th>
                <th>状态</th>
              </tr>
            </thead>
            <tbody>
              {routes.length ? routes.map((item, index) => (
                <tr key={`${item.route_url || item.pool_name || index}`}>
                  <td>
                    <div className="sub2-cell-stack sub2-cell-stack-tight">
                      <strong>{item.pool_name || `线路 ${index + 1}`}</strong>
                      <small>{item.route_url || '-'}</small>
                    </div>
                  </td>
                  <td>{formatNumber(item.request_count || 0)}</td>
                  <td>{formatNumber(item.success_count || 0)}</td>
                  <td>{formatNumber(item.error_count || 0)}</td>
                  <td>{item.route_status_text || item.last_reason || '-'}</td>
                </tr>
              )) : (
                <tr><td colSpan={5}>暂无线路观测数据。</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </Panel>
    </section>
  );
}
