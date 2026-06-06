import { Badge, Empty } from '../../components';
import { formatMs, maskEmpty } from '../../utils';
import type { PoolTestResult, RouteObservability } from '../../types';
import { protocolText } from './routeFormat';

export function RouteTable({ rows }: { rows: RouteObservability[] }) {
  return (
    <div className="table-wrap">
      <table>
        <thead><tr><th>线路</th><th>连接池</th><th>缓存</th><th>协议</th><th>冷却</th></tr></thead>
        <tbody>
          {rows.length ? rows.map((row, i) => (
            <tr key={`${row.route_url}-${i}`}>
              <td><strong>{maskEmpty(row.route_url)}</strong><small>活跃粘滞 {row.active_affinity_count || 0}</small></td>
              <td>{maskEmpty(row.pool_name)}<small>{row.route_status_text || '-'}</small></td>
              <td>{row.route_policy?.prompt_cache_mode || '-'}</td>
              <td>{protocolText(row.route_policy?.text_upstream_protocol)}</td>
              <td>{row.route_policy?.route_cooldown_seconds || 0}s</td>
            </tr>
          )) : <tr><td colSpan={5}><Empty>暂无线路级观测数据。</Empty></td></tr>}
        </tbody>
      </table>
    </div>
  );
}

export function PoolTestView({ result }: { result: PoolTestResult }) {
  return (
    <div className="test-result">
      <Badge tone={result.summary_ok ? 'ok' : 'warn'}>{result.summary_ok ? '测试通过' : '测试未通过'}</Badge>
      {result.message ? <p>{result.message}</p> : null}
      {(result.results || []).map((route) => (
        <div key={route.url} className="test-route">
          <strong>{route.url}</strong>
          <small>{route.models_url}</small>
          {(route.keys || []).map((key, i) => (
            <p key={i}><Badge tone={key.ok ? 'ok' : 'bad'}>{key.status_code ?? '-'}</Badge> {key.key_preview} · {formatMs(key.latency_ms)} · {key.message}</p>
          ))}
        </div>
      ))}
    </div>
  );
}
