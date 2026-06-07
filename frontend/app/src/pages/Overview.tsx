import { Link } from '@tanstack/react-router';
import type React from 'react';
import { Activity, ArrowRight, Clock, Database, KeyRound, Network, Server, ShieldCheck, Zap } from 'lucide-react';
import { Info } from '../components/Info';
import { Empty, Panel, PanelHead } from '../components';
import { RouteTable } from '../features/routes/RouteTable';
import type { DashboardState, ProxyKeyPayload, RequestEntry, RouteObservability } from '../types';
import { formatMs, formatNumber, formatTokenCount, maskEmpty } from '../utils';

export function Overview({ state, keys }: { state: DashboardState; keys?: ProxyKeyPayload }) {
  const runtime = state.runtime || {};
  const config = state.config || {};
  const recent = state.recent_requests || [];
  const active = state.active_requests || [];
  const todayRows = recent.filter(isTodayRequest);
  const totalPrompt = sum(recent, 'prompt_tokens');
  const totalCompletion = sum(recent, 'completion_tokens');
  const todayPrompt = sum(todayRows, 'prompt_tokens');
  const todayCompletion = sum(todayRows, 'completion_tokens');
  const avgDuration = average(recent.map((row) => Number(row.duration_ms || 0)).filter(Boolean));
  const rpm = requestsPerMinute(recent);
  const tpm = tokensPerMinute(recent);
  const channelStats = summarizeChannels(state.route_observability || [], recent);
  const modelStats = summarizeModels(recent);
  const trend = summarizeTokenTrend(recent);
  const stats = (runtime.model_routing?.cache_stats || {}) as Record<string, number>;
  const runtimeAlerts = buildRuntimeAlerts({
    activeCount: active.length,
    state,
    stats,
    recentCount: recent.length,
  });

  return (
    <section className="dashboard-page">
      <div className="overview-command-strip">
        <div className="overview-command-main">
          <strong>代理运行面板</strong>
          <span>围绕线路、缓存、模型和入口状态的实时概览</span>
        </div>
        <div className="overview-command-actions">
          <Link to="/config" className="btn">线路与策略</Link>
          <Link to="/keys" className="btn">API Key</Link>
          <Link to="/requests" className="btn btn-primary">使用记录</Link>
        </div>
      </div>

      <div className="overview-ops-strip">
        <OpsStripItem label="配置来源" value={maskEmpty(config.config_source || runtime.config_source)} sub={maskEmpty(config.config_path || runtime.config_path)} />
        <OpsStripItem label="数据库" value={maskEmpty(runtime.model_routing?.db_label || config.db_label)} sub="当前运行时存储来源" />
        <OpsStripItem label="能力数" value={`${formatNumber(runtime.model_capability_count || config.model_capability_count || 0)} 条`} sub={`${formatNumber((runtime.capabilities || []).length)} 项运行能力`} />
        <OpsStripItem label="线路规模" value={`${formatNumber(state.pools_enabled_count ?? config.pools_enabled_count ?? 0)} / ${formatNumber(state.pools_count ?? config.pools_count ?? 0)}`} sub={`${formatNumber(state.upstream_url_count ?? runtime.upstream_url_count ?? 0)} 条上游链路`} />
      </div>

      {runtimeAlerts.length ? (
        <div className="overview-alert-list">
          {runtimeAlerts.map((item) => (
            <div key={item.title} className={`overview-alert ${item.tone}`}>
              <strong>{item.title}</strong>
              <span>{item.message}</span>
            </div>
          ))}
        </div>
      ) : null}

      <div className="dashboard-stats-grid">
        <DashboardStat icon={<KeyRound size={19} />} tone="blue" label="API Key" value={formatNumber(keys?.managed_key_count ?? runtime.proxy_api_key_managed_count ?? 0)} sub={`${formatNumber(keys?.managed_enabled_count ?? runtime.proxy_api_key_managed_enabled_count ?? 0)} 个启用`} />
        <DashboardStat icon={<Activity size={19} />} tone="green" label="今日请求" value={formatNumber(todayRows.length)} sub={`总记录 ${formatNumber(recent.length)} · 活跃 ${formatNumber(active.length)}`} />
        <DashboardStat icon={<Database size={19} />} tone="amber" label="今日 Token" value={formatTokenCount(todayPrompt + todayCompletion)} sub={`请求 ${formatTokenCount(todayPrompt)} / 回复 ${formatTokenCount(todayCompletion)}`} />
        <DashboardStat icon={<Clock size={19} />} tone="rose" label="平均响应" value={formatMs(avgDuration)} sub="最近请求平均耗时" />
        <DashboardStat icon={<Network size={19} />} tone="indigo" label="启用连接池" value={`${state.pools_enabled_count ?? config.pools_enabled_count ?? 0} / ${state.pools_count ?? config.pools_count ?? 0}`} sub={`${formatNumber(state.upstream_url_count ?? runtime.upstream_url_count ?? 0)} 条链路`} />
        <DashboardStat icon={<Zap size={19} />} tone="violet" label="吞吐能力" value={`${formatNumber(rpm)} RPM`} sub={`${formatNumber(tpm)} TPM`} />
        <DashboardStat icon={<ShieldCheck size={19} />} tone="cyan" label="上游缓存" value={formatNumber(stats.prompt_cache_hits)} sub={`写入 ${formatNumber(stats.prompt_cache_writes)}`} />
        <DashboardStat icon={<Server size={19} />} tone="slate" label="总 Token" value={formatTokenCount(totalPrompt + totalCompletion)} sub={`请求 ${formatTokenCount(totalPrompt)} / 回复 ${formatTokenCount(totalCompletion)}`} />
      </div>

      <div className="dashboard-charts-grid">
        <Panel className="dashboard-card">
          <PanelHead title={<><Network size={18} />渠道状态</>} action={<span className="subtle">{channelStats.length} 个渠道</span>} />
          <div className="overview-panel-tip">优先关注近期有流量或出现错误的线路，缓存命中按当前观测窗口折算。</div>
          <div className="channel-grid">
            {channelStats.length ? channelStats.slice(0, 8).map((item) => <ChannelCard key={item.name} item={item} />) : <Empty>暂无渠道状态。</Empty>}
          </div>
        </Panel>

        <Panel className="dashboard-card">
          <PanelHead title={<><Activity size={18} />模型分布</>} action={<span className="subtle">最近请求</span>} />
          <div className="overview-panel-tip">按逻辑模型聚合最近请求，帮助判断主流量落点和异常模型漂移。</div>
          <ModelDistribution rows={modelStats} />
        </Panel>
      </div>

      <div className="dashboard-charts-grid dashboard-charts-grid-bottom">
        <Panel className="dashboard-card">
          <PanelHead title={<><Database size={18} />Token 趋势</>} action={<span className="subtle">最近 7 天</span>} />
          <div className="overview-panel-tip">趋势图按日聚合总 Token，便于快速识别负载抬升和回落。</div>
          <TrendChart rows={trend} />
        </Panel>

        <Panel className="dashboard-card">
          <PanelHead title={<><Zap size={18} />快捷入口</>} />
          <div className="quick-actions">
            <QuickAction to="/keys" icon={<KeyRound size={20} />} title="管理 API Key" desc="生成、复制、禁用入口 Key" tone="blue" />
            <QuickAction to="/requests" icon={<Activity size={20} />} title="查看使用记录" desc="按线路、模型、缓存排查请求" tone="green" />
            <QuickAction to="/config" icon={<SettingsIcon />} title="配置渠道策略" desc="调整线路、优先级与退避策略" tone="amber" />
          </div>
        </Panel>
      </div>

      <div className="dashboard-main-grid">
        <Panel className="dashboard-card">
          <PanelHead title={<><Activity size={18} />最近使用记录</>} action={<Link to="/requests" className="panel-link">全部记录 <ArrowRight size={14} /></Link>} />
          <div className="overview-panel-tip">这里保留最近 6 条请求，用于快速判断模型、线路和状态是否一致。</div>
          <div className="recent-usage-list">
            {recent.slice(0, 6).map((row, index) => <RecentUsageItem key={`${row.request_id || index}-${index}`} row={row} />)}
            {!recent.length ? <Empty>暂无请求记录。</Empty> : null}
          </div>
        </Panel>

        <Panel className="dashboard-card">
          <PanelHead title={<><Network size={18} />线路级缓存与粘滞</>} action={<span className="subtle">线路 {(state.route_observability || []).length}</span>} />
          <div className="overview-panel-tip">这里只看当前前 8 条线路观测结果，完整详情进入线路页继续排查。</div>
          <RouteTable rows={(state.route_observability || []).slice(0, 8)} />
        </Panel>
      </div>

      <div className="dashboard-charts-grid dashboard-charts-grid-bottom">
        <Panel className="dashboard-card">
          <PanelHead title={<><Database size={18} />运行总览</>} action={<span className="subtle">按当前采样窗口统计</span>} />
          <div className="overview-summary-grid">
            <div className="overview-summary-item">
              <span>总请求</span>
              <strong>{formatNumber(recent.length)}</strong>
              <small>活跃 {formatNumber(active.length)}</small>
            </div>
            <div className="overview-summary-item">
              <span>请求 Token</span>
              <strong>{formatTokenCount(totalPrompt)}</strong>
              <small>回复 {formatTokenCount(totalCompletion)}</small>
            </div>
            <div className="overview-summary-item">
              <span>今日 Token</span>
              <strong>{formatTokenCount(todayPrompt + todayCompletion)}</strong>
              <small>请求 {formatTokenCount(todayPrompt)}</small>
            </div>
            <div className="overview-summary-item">
              <span>启用线路</span>
              <strong>{formatNumber(state.pools_enabled_count ?? config.pools_enabled_count ?? 0)}</strong>
              <small>总计 {formatNumber(state.pools_count ?? config.pools_count ?? 0)}</small>
            </div>
          </div>
        </Panel>

        <Panel className="dashboard-card">
          <PanelHead title={<><ShieldCheck size={18} />缓存概况</>} action={<span className="subtle">当前统计</span>} />
          <div className="overview-summary-grid overview-summary-grid-compact">
            <div className="overview-summary-item">
              <span>命中</span>
              <strong>{formatNumber(stats.prompt_cache_hits)}</strong>
              <small>上游缓存命中次数</small>
            </div>
            <div className="overview-summary-item">
              <span>写入</span>
              <strong>{formatNumber(stats.prompt_cache_writes)}</strong>
              <small>上游缓存写入次数</small>
            </div>
          </div>
        </Panel>
      </div>

      <Panel className="dashboard-card">
        <PanelHead title={<><ShieldCheck size={18} />配置与能力</>} />
        <div className="info-grid">
          <Info label="来源" value={config.config_source || runtime.config_source || '-'} />
          <Info label="路径" value={config.config_path || runtime.config_path || '-'} mono />
          <Info label="MySQL" value={String(runtime.model_routing?.db_label || config.db_label || '-')} mono />
          <Info label="模型能力" value={`${runtime.model_capability_count || config.model_capability_count || 0} 条`} />
        </div>
        <div className="cap-grid dashboard-cap-grid">{(runtime.capabilities || []).map((cap) => <span key={cap}>{cap}</span>)}</div>
      </Panel>
    </section>
  );
}

function OpsStripItem({ label, value, sub }: { label: string; value: string; sub: string }) {
  return (
    <div className="overview-ops-item">
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{sub}</small>
    </div>
  );
}

function DashboardStat({ icon, tone, label, value, sub }: { icon: React.ReactNode; tone: string; label: string; value: string | number; sub: string }) {
  return (
    <div className="dashboard-stat">
      <div className={`dashboard-stat-icon ${tone}`}>{icon}</div>
      <div className="dashboard-stat-body">
        <span>{label}</span>
        <strong>{value}</strong>
        <small>{sub}</small>
      </div>
    </div>
  );
}

function ChannelCard({ item }: { item: ReturnType<typeof summarizeChannels>[number] }) {
  const total = Math.max(1, item.requests + item.errors);
  const okRate = Math.round((item.requests / total) * 100);
  return (
    <div className="channel-card">
      <div className="channel-card-head">
        <strong>{item.name}</strong>
        <span className={item.errors ? 'status-dot warn' : 'status-dot ok'}>{item.errors ? '有异常' : '正常'}</span>
      </div>
      <div className="channel-card-body">
        <MetricLine label="请求" value={formatNumber(item.requests)} />
        <MetricLine label="错误" value={formatNumber(item.errors)} />
        <MetricLine label="缓存" value={`${formatNumber(Math.round(item.cacheRate))}%`} />
      </div>
      <div className="mini-progress"><span style={{ width: `${okRate}%` }} /></div>
    </div>
  );
}

function MetricLine({ label, value }: { label: string; value: string }) {
  return <div className="metric-line"><span>{label}</span><strong>{value}</strong></div>;
}

function ModelDistribution({ rows }: { rows: Array<{ model: string; requests: number; tokens: number; share: number }> }) {
  if (!rows.length) return <Empty>暂无模型分布。</Empty>;
  return (
    <div className="distribution-list">
      {rows.slice(0, 8).map((row) => (
        <div className="distribution-row" key={row.model}>
          <div className="distribution-main"><strong>{row.model}</strong><span>{formatNumber(row.requests)} 次 · {formatTokenCount(row.tokens)}</span></div>
          <div className="distribution-bar"><span style={{ width: `${row.share}%` }} /></div>
          <em>{Math.round(row.share)}%</em>
        </div>
      ))}
    </div>
  );
}

function TrendChart({ rows }: { rows: Array<{ label: string; tokens: number }> }) {
  const max = Math.max(1, ...rows.map((row) => row.tokens));
  return (
    <div className="trend-bars">
      {rows.map((row) => (
        <div className="trend-bar-item" key={row.label}>
          <div className="trend-bar"><span style={{ height: `${Math.max(4, (row.tokens / max) * 100)}%` }} /></div>
          <small>{row.label}</small>
        </div>
      ))}
    </div>
  );
}

function QuickAction({ to, icon, title, desc, tone }: { to: string; icon: React.ReactNode; title: string; desc: string; tone: string }) {
  return (
    <Link to={to} className="quick-action">
      <span className={`quick-action-icon ${tone}`}>{icon}</span>
      <span className="quick-action-copy"><strong>{title}</strong><small>{desc}</small></span>
      <ArrowRight size={16} />
    </Link>
  );
}

function RecentUsageItem({ row }: { row: RequestEntry }) {
  const tokens = Number(row.total_tokens || 0) || Number(row.prompt_tokens || 0) + Number(row.completion_tokens || 0);
  const ok = !row.error && (!row.status_code || Number(row.status_code) < 400);
  return (
    <div className="recent-usage-item">
      <div className="recent-usage-icon"><Activity size={17} /></div>
      <div className="recent-usage-main">
        <strong>{maskEmpty(row.logical_model || row.model || row.resolved_model)}</strong>
        <span>{maskEmpty(row.started_at)} · {maskEmpty(row.pool_name || row.selected_pool_name)}</span>
      </div>
      <div className="recent-usage-meta">
        <strong>{formatTokenCount(tokens)}</strong>
        <span className={ok ? 'ok' : 'bad'}>{row.status_text || row.status_code || (row.error ? '异常' : '完成')}</span>
      </div>
    </div>
  );
}

function SettingsIcon() {
  return <Network size={20} />;
}

function sum(rows: RequestEntry[], key: string) {
  return rows.reduce((total, row) => total + Number(row[key] || 0), 0);
}

function average(values: number[]) {
  if (!values.length) return 0;
  return Math.round(values.reduce((a, b) => a + b, 0) / values.length);
}

function isTodayRequest(row: RequestEntry) {
  const timestamp = Date.parse(String(row.started_at || '').replace(',', '.'));
  if (!Number.isFinite(timestamp)) return false;
  const now = new Date();
  const date = new Date(timestamp);
  return date.getFullYear() === now.getFullYear() && date.getMonth() === now.getMonth() && date.getDate() === now.getDate();
}

function requestsPerMinute(rows: RequestEntry[]) {
  if (rows.length < 2) return rows.length;
  const times = rows.map((row) => Date.parse(String(row.started_at || '').replace(',', '.'))).filter(Number.isFinite).sort((a, b) => a - b);
  if (times.length < 2) return rows.length;
  const minutes = Math.max(1, (times[times.length - 1] - times[0]) / 60000);
  return Math.round(rows.length / minutes);
}

function tokensPerMinute(rows: RequestEntry[]) {
  const total = rows.reduce((acc, row) => acc + Number(row.total_tokens || row.prompt_tokens || 0) + Number(row.completion_tokens || 0), 0);
  const minutes = observedMinutes(rows);
  return Math.round(total / minutes);
}

function observedMinutes(rows: RequestEntry[]) {
  const times = rows.map((row) => Date.parse(String(row.started_at || '').replace(',', '.'))).filter(Number.isFinite).sort((a, b) => a - b);
  if (times.length < 2) return 1;
  return Math.max(1, (times[times.length - 1] - times[0]) / 60000);
}

function summarizeChannels(routes: RouteObservability[], requests: RequestEntry[]) {
  const map = new Map<string, { name: string; requests: number; errors: number; cacheRate: number }>();
  for (const route of routes) {
    const name = String(route.pool_name || route.route_url || '未归类');
    map.set(name, {
      name,
      requests: Number(route.request_count || route.success_count || 0),
      errors: Number(route.error_count || route.status_429_count || 0),
      cacheRate: Number(route.upstream_prompt_cache_hit_rate || route.local_cache_hit_rate || 0) * 100,
    });
  }
  for (const row of requests) {
    const name = String(row.pool_name || row.selected_pool_name || '未归类');
    const current = map.get(name) || { name, requests: 0, errors: 0, cacheRate: 0 };
    current.requests += 1;
    if (row.error || Number(row.status_code || 0) >= 400) current.errors += 1;
    map.set(name, current);
  }
  return Array.from(map.values()).sort((a, b) => b.requests - a.requests);
}

function summarizeModels(rows: RequestEntry[]) {
  const map = new Map<string, { model: string; requests: number; tokens: number }>();
  for (const row of rows) {
    const model = String(row.logical_model || row.model || row.resolved_model || '未归类');
    const current = map.get(model) || { model, requests: 0, tokens: 0 };
    current.requests += 1;
    current.tokens += Number(row.total_tokens || 0) || Number(row.prompt_tokens || 0) + Number(row.completion_tokens || 0);
    map.set(model, current);
  }
  const total = Math.max(1, Array.from(map.values()).reduce((acc, row) => acc + row.requests, 0));
  return Array.from(map.values()).sort((a, b) => b.requests - a.requests).map((row) => ({ ...row, share: (row.requests / total) * 100 }));
}

function summarizeTokenTrend(rows: RequestEntry[]) {
  const days = Array.from({ length: 7 }, (_, index) => {
    const date = new Date();
    date.setDate(date.getDate() - (6 - index));
    const key = date.toISOString().slice(0, 10);
    return { key, label: `${date.getMonth() + 1}/${date.getDate()}`, tokens: 0 };
  });
  const dayMap = new Map(days.map((day) => [day.key, day]));
  for (const row of rows) {
    const date = new Date(String(row.started_at || '').replace(',', '.'));
    if (Number.isNaN(date.getTime())) continue;
    const key = date.toISOString().slice(0, 10);
    const target = dayMap.get(key);
    if (target) target.tokens += Number(row.total_tokens || 0) || Number(row.prompt_tokens || 0) + Number(row.completion_tokens || 0);
  }
  return days;
}

function buildRuntimeAlerts({
  activeCount,
  state,
  stats,
  recentCount,
}: {
  activeCount: number;
  state: DashboardState;
  stats: Record<string, number>;
  recentCount: number;
}) {
  const alerts: Array<{ title: string; message: string; tone: 'info' | 'warn' | 'bad' }> = [];
  const enabledPools = Number(state.pools_enabled_count ?? state.config?.pools_enabled_count ?? 0);
  const totalPools = Number(state.pools_count ?? state.config?.pools_count ?? 0);
  if (activeCount > 0) {
    alerts.push({ title: '存在活跃请求', message: `当前有 ${formatNumber(activeCount)} 条请求正在处理中，可结合使用记录页查看首包和上游耗时。`, tone: 'info' });
  }
  if (enabledPools === 0 && totalPools > 0) {
    alerts.push({ title: '线路未启用', message: `当前共有 ${formatNumber(totalPools)} 条线路，但启用数为 0。`, tone: 'bad' });
  }
  if (recentCount > 0 && Number(stats.prompt_cache_hits || 0) === 0) {
    alerts.push({ title: '缓存尚未命中', message: '当前采样窗口内未观察到缓存命中，建议继续核对模型路由和上游缓存条件。', tone: 'warn' });
  }
  return alerts;
}
