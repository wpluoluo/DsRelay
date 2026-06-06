import { Database, Network, ShieldCheck } from 'lucide-react';
import { Info } from '../components/Info';
import { Metric, Panel, PanelHead } from '../components';
import { RouteTable } from '../features/routes/RouteTable';
import type { DashboardState, ProxyKeyPayload } from '../types';
import { formatNumber } from '../utils';

export function Overview({ state, keys }: { state: DashboardState; keys?: ProxyKeyPayload }) {
  const runtime = state.runtime || {};
  const config = state.config || {};
  const stats = (runtime.model_routing?.cache_stats || {}) as Record<string, number>;
  return (
    <section className="grid-page">
      <div className="metrics-row">
        <Metric label="启用连接池" value={`${state.pools_enabled_count ?? config.pools_enabled_count ?? 0} / ${state.pools_count ?? config.pools_count ?? 0}`} sub={`${state.upstream_url_count ?? 0} 条链路`} />
        <Metric label="入口 Key" value={keys?.managed_enabled_count ?? runtime.proxy_api_key_managed_enabled_count ?? 0} sub={`环境 ${keys?.env_key_count ?? runtime.proxy_api_key_env_count ?? 0}`} />
        <Metric label="路由缓存" value={formatNumber(runtime.model_routing?.route_cache_entries)} sub={`命中 ${formatNumber(stats.model_route_hits)}`} />
        <Metric label="请求缓存" value={formatNumber(stats.prompt_cache_hits)} sub={`写入 ${formatNumber(stats.prompt_cache_writes)}`} />
      </div>
      <Panel>
        <PanelHead title={<><Network size={18} />线路级缓存与粘滞</>} action={<span className="subtle">线路 {(state.route_observability || []).length}</span>} />
        <RouteTable rows={state.route_observability || []} />
      </Panel>
      <Panel>
        <PanelHead title={<><ShieldCheck size={18} />能力清单</>} />
        <div className="cap-grid">{(runtime.capabilities || []).map((cap) => <span key={cap}>{cap}</span>)}</div>
      </Panel>
      <Panel>
        <PanelHead title={<><Database size={18} />配置来源</>} />
        <div className="info-grid">
          <Info label="来源" value={config.config_source || runtime.config_source || '-'} />
          <Info label="路径" value={config.config_path || runtime.config_path || '-'} mono />
          <Info label="MySQL" value={String(runtime.model_routing?.db_label || config.db_label || '-')} mono />
          <Info label="模型能力" value={`${runtime.model_capability_count || config.model_capability_count || 0} 条`} />
        </div>
      </Panel>
    </section>
  );
}
