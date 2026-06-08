import { useQuery } from '@tanstack/react-query';
import { fetchAdminOverview, fetchAdminProtocols } from '../api';
import { Empty, Panel, PanelHead } from '../components';
import { buildPageIntro } from '../navigation';
import { useDashboard } from '../state/dashboardContext';
import { formatNumber, formatTokenCount } from '../utils';

export function AdminOpsPage() {
  const dashboard = useDashboard();
  const overviewQuery = useQuery({ queryKey: ['admin-overview'], queryFn: fetchAdminOverview, refetchInterval: 10000 });
  const protocolsQuery = useQuery({ queryKey: ['admin-protocols'], queryFn: fetchAdminProtocols, refetchInterval: 30000 });
  const overview = overviewQuery.data || {};
  const protocols = protocolsQuery.data?.items || [];
  const runtime = dashboard.state.runtime || {};
  const activeRequests = dashboard.state.active_requests || [];
  const recentRequests = dashboard.state.recent_requests || [];

  return (
    <section className="grid-page">
      {buildPageIntro('/admin/ops')}
      <div className="sub2-inline-summary">
        <div className="sub2-inline-summary-item"><span>运行时</span><strong>{runtime.pid || '-'}</strong><small>端口 {runtime.port || '-'}</small></div>
        <div className="sub2-inline-summary-item"><span>活动请求</span><strong>{formatNumber(activeRequests.length)}</strong><small>最近请求 {formatNumber(recentRequests.length)}</small></div>
        <div className="sub2-inline-summary-item"><span>协议数</span><strong>{formatNumber(protocols.length)}</strong><small>模型能力 {formatNumber(runtime.model_capability_count || 0)}</small></div>
        <div className="sub2-inline-summary-item"><span>近窗 Token</span><strong>{formatTokenCount(overview.total_tokens || 0)}</strong><small>错误 {formatNumber(overview.error_count || 0)}</small></div>
      </div>
      <Panel>
        <PanelHead title="协议能力" />
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>协议</th>
                <th>流式</th>
                <th>工具</th>
                <th>图片</th>
                <th>参数</th>
              </tr>
            </thead>
            <tbody>
              {protocols.length ? protocols.map((item) => (
                <tr key={item.key}>
                  <td><strong>{item.label || item.key}</strong></td>
                  <td>{item.supports_stream ? '支持' : '不支持'}</td>
                  <td>{item.supports_tools ? '支持' : '不支持'}</td>
                  <td>{item.supports_images ? '支持' : '不支持'}</td>
                  <td>{(item.parameter_keys || []).join(', ') || '-'}</td>
                </tr>
              )) : (
                <tr><td colSpan={5}><Empty>暂无协议信息。</Empty></td></tr>
              )}
            </tbody>
          </table>
        </div>
      </Panel>
    </section>
  );
}
