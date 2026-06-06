import { Badge, Empty } from '../../components';
import { formatMs, maskEmpty } from '../../utils';
import type { PoolTestResult, RouteObservability } from '../../types';
import { protocolText } from './routeFormat';

export function RouteTable({ rows }: { rows: RouteObservability[] }) {
  return (
    <div className="table-wrap">
      <table>
        <thead><tr><th>线路</th><th>连接池</th><th>请求</th><th>缓存</th><th>粘滞</th><th>Hint</th><th>错误</th></tr></thead>
        <tbody>
          {rows.length ? rows.map((row, i) => <RouteRow key={`${row.route_url}-${i}`} row={row} />) : <tr><td colSpan={7}><Empty>暂无线路级观测数据。</Empty></td></tr>}
        </tbody>
      </table>
    </div>
  );
}

function RouteRow({ row }: { row: RouteObservability }) {
  const requestCount = Number(row.request_count || 0);
  const successCount = Number(row.success_count || 0);
  const errorCount = Number(row.error_count || 0);
  const status429Count = Number(row.status_429_count || 0);
  const localHitRate = Number(row.local_cache_hit_rate || 0);
  const localHits = Number(row.local_cache_hit_count || 0);
  const localMisses = Number(row.local_cache_miss_count || 0);
  const localBypasses = Number(row.local_cache_bypass_count || 0);
  const localEligible = Number(row.local_cache_eligible_count || 0);
  const upstreamRate = Number(row.upstream_prompt_cache_hit_rate || 0);
  const upstreamHits = Number(row.upstream_prompt_cache_hit_count || 0);
  const upstreamRequests = Number(row.upstream_prompt_cache_request_count || 0);
  const avgCacheRead = Number(row.avg_cache_read_input_tokens || 0);
  const stickyRate = Number(row.sticky_session_rate || 0);
  const hintRate = Number(row.hint_applied_rate || 0);
  const policy = row.route_policy || {};
  const configuredCooldown = Number(policy.route_cooldown_seconds || 0);
  const effectiveCooldown = Number((policy as any).effective_route_cooldown_seconds || configuredCooldown || 0);
  const cooldownMax = Number(policy.route_cooldown_max_seconds || 0);
  let cooldownLabel = configuredCooldown ? `冷却 ${configuredCooldown}s` : '冷却 -';
  if (effectiveCooldown && effectiveCooldown !== configuredCooldown) cooldownLabel += ` · 生效 ${effectiveCooldown}s`;
  if (cooldownMax) cooldownLabel += ` · 上限 ${cooldownMax}s`;
  return (
    <tr>
      <td><div className="request-stack"><div className="request-cell-title request-ellipsis">{maskEmpty(row.route_url)}</div><div className="request-cell-sub">活跃粘滞 {row.active_affinity_count || 0}</div></div></td>
      <td><div className="request-stack"><div className="request-cell-title">{maskEmpty(row.pool_name)}</div><div className="request-chip-row"><span className={`request-chip ${row.cooling ? 'warn' : 'ok'}`}>{row.cooling ? '冷却中' : '可用'}</span><span className="request-chip">{row.route_status_text || (row.historical_only ? '历史链路' : '当前线路')}</span></div><div className="request-cell-sub">{cooldownLabel}</div>{row.route_status_note ? <div className="request-cell-sub">{row.route_status_note}</div> : null}<div className="request-cell-sub">{protocolText(policy.text_upstream_protocol)}</div></div></td>
      <td><div className="request-stack"><div className="request-cell-title">{requestCount}</div><div className="request-cell-sub">成功 {successCount} · 错误 {errorCount}</div></div></td>
      <td><div className="request-stack"><div className="request-cell-title">{(upstreamRate * 100).toFixed(1)}%</div><div className="request-cell-sub">前缀缓存 {upstreamHits}/{upstreamRequests} · 平均读 {Math.round(avgCacheRead)} token</div><div className="request-cell-sub">本地 {localHits}/{localEligible} · 未命中 {localMisses} · 绕过 {localBypasses} · {(localHitRate * 100).toFixed(1)}%</div></div></td>
      <td><div className="request-stack"><div className="request-cell-title">{row.sticky_session_count || 0}/{row.session_count || 0}</div><div className="request-cell-sub">粘滞率 {(stickyRate * 100).toFixed(1)}%</div></div></td>
      <td><div className="request-stack"><div className="request-cell-title">{row.hint_applied_count || 0}</div><div className="request-cell-sub">生效率 {(hintRate * 100).toFixed(1)}%</div></div></td>
      <td><div className="request-stack"><div className="request-cell-title">429 {status429Count}</div><div className="request-cell-sub">失败链 {row.consecutive_failures || 0}{row.last_reason ? ` · ${row.last_reason}` : ''}</div></div></td>
    </tr>
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
