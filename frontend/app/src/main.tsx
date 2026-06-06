import React, { useEffect, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { QueryClient, QueryClientProvider, useMutation, useQuery } from '@tanstack/react-query';
import { Activity, Database, KeyRound, ListChecks, Network, RefreshCw, Save, Server, Settings, ShieldCheck, Trash2 } from 'lucide-react';
import { Button, Badge, Empty, Field, Metric, Modal, NumberInput, Panel, PanelHead, Select, Tabs, TextArea, TextInput, Toggle } from './components';
import { clearRequestCache, clearRequests, fetchDashboardState, fetchProxyKeys, mutateProxyKey, saveConfig, testPool } from './api';
import type { DashboardState, Pool, PoolTestResult, ProxyKeyPayload, RequestEntry, RuntimeConfig } from './types';
import { cn, countLines, formatMs, formatNumber, formatUptime, maskEmpty, splitLines, textFromLines } from './utils';
import './styles.css';

const queryClient = new QueryClient();

type ViewKey = 'overview' | 'requests' | 'logs' | 'config';
type ConfigTab = 'routes' | 'routing' | 'strategy';

const defaultPolicy = {
  reasoning_effort: 'medium',
  text_upstream_protocol: 'auto',
  prompt_cache_mode: 'exact',
  prompt_cache_hints_mode: 'auto',
  prompt_cache_provider: 'auto',
  prompt_cache_retention: '',
  max_output_tokens: 0,
  route_cooldown_seconds: 90,
  route_cooldown_multiplier: 2,
  route_cooldown_max_seconds: 900,
  rate_limit_retry_attempts: 0,
  rate_limit_backoff_initial_ms: 1000,
  rate_limit_backoff_multiplier: 2,
  rate_limit_backoff_max_ms: 4000,
};

function normalizePool(pool?: Pool): Pool {
  const p = pool || {};
  return {
    name: String(p.name || '').trim(),
    enabled: p.enabled !== false,
    priority: Number.isFinite(Number(p.priority)) ? Number(p.priority) : 100,
    urls: Array.isArray(p.urls) && p.urls.length ? p.urls : [''],
    keys: Array.isArray(p.keys) && p.keys.length ? p.keys.map((key) => ({ key: typeof key === 'string' ? key : String(key?.key || '') })) : [{ key: '' }],
    supported_models_text: String(p.supported_models_text || ''),
    model_aliases_text: String(p.model_aliases_text || ''),
    route_policy: { ...defaultPolicy, ...(p.route_policy || {}) },
  };
}

function configFromState(config?: RuntimeConfig): RuntimeConfig {
  return {
    pools: (config?.pools || []).map(normalizePool),
    request_timeout: config?.request_timeout ?? 600,
    stream_first_event_timeout_seconds: config?.stream_first_event_timeout_seconds ?? 30,
    force_upstream_chat_stream: config?.force_upstream_chat_stream !== false,
    enable_request_normalization: config?.enable_request_normalization !== false,
    max_completion_tokens: config?.max_completion_tokens ?? 0,
    inject_zh_system_prompt: config?.inject_zh_system_prompt !== false,
    proxy_system_prompt_zh: config?.proxy_system_prompt_zh || '',
    max_retries: config?.max_retries ?? 0,
    retry_backoff_ms: config?.retry_backoff_ms ?? 0,
    retry_max_backoff_ms: config?.retry_max_backoff_ms ?? 0,
    route_switch_window_seconds: config?.route_switch_window_seconds ?? 60,
    randomize_endpoints: config?.randomize_endpoints !== false,
    image_upstream_protocol: config?.image_upstream_protocol || 'auto',
    image_task_poll_timeout_seconds: config?.image_task_poll_timeout_seconds ?? 90,
    image_task_poll_interval_seconds: config?.image_task_poll_interval_seconds ?? 2,
    enable_model_probe: config?.enable_model_probe !== false,
    model_probe_timeout_seconds: config?.model_probe_timeout_seconds ?? 4,
    model_probe_ttl_seconds: config?.model_probe_ttl_seconds ?? 300,
    model_route_cache_ttl_seconds: config?.model_route_cache_ttl_seconds ?? 86400,
    enable_interruption_resume: config?.enable_interruption_resume !== false,
    interruption_resume_ttl_seconds: config?.interruption_resume_ttl_seconds ?? 3600,
    interruption_resume_max_chars: config?.interruption_resume_max_chars ?? 12000,
    interruption_resume_min_chars: config?.interruption_resume_min_chars ?? 40,
    enable_model_candidate_race: config?.enable_model_candidate_race !== false,
    model_candidate_race_limit: config?.model_candidate_race_limit ?? 3,
    model_candidate_race_timeout_seconds: config?.model_candidate_race_timeout_seconds ?? 8,
  };
}

function App() {
  const [view, setView] = useState<ViewKey>('overview');
  const [configTab, setConfigTab] = useState<ConfigTab>('routes');
  const [draft, setDraft] = useState<RuntimeConfig>({ pools: [] });
  const [dirty, setDirty] = useState(false);
  const [status, setStatus] = useState('');
  const [poolIndex, setPoolIndex] = useState<number | null>(null);
  const [poolDraft, setPoolDraft] = useState<Pool | null>(null);
  const [poolTest, setPoolTest] = useState<PoolTestResult | null>(null);

  const stateQuery = useQuery({
    queryKey: ['dashboard-state'],
    queryFn: fetchDashboardState,
    refetchInterval: 2500,
  });

  const keyQuery = useQuery({
    queryKey: ['proxy-keys'],
    queryFn: fetchProxyKeys,
    refetchInterval: 8000,
  });

  useEffect(() => {
    if (stateQuery.data?.config && !dirty) {
      setDraft(configFromState(stateQuery.data.config));
    }
  }, [stateQuery.data?.config, dirty]);

  const saveMutation = useMutation({
    mutationFn: saveConfig,
    onSuccess: (data) => {
      queryClient.setQueryData(['dashboard-state'], data);
      setDraft(configFromState(data.config));
      setDirty(false);
      setStatus('配置已保存并生效。');
    },
    onError: (error) => setStatus(error instanceof Error ? error.message : '保存失败'),
  });

  const state = stateQuery.data || {};
  const runtime = state.runtime || {};
  const config = state.config || {};
  const pools = (draft.pools || []).map(normalizePool);

  function patchDraft(patch: Partial<RuntimeConfig>) {
    setDraft((current) => ({ ...current, ...patch }));
    setDirty(true);
    setStatus('配置已修改，点击保存并生效。');
  }

  function updatePools(nextPools: Pool[]) {
    patchDraft({ pools: nextPools.map(normalizePool) });
  }

  function openPool(index: number | null) {
    setPoolTest(null);
    setPoolIndex(index);
    setPoolDraft(normalizePool(index == null ? undefined : pools[index]));
  }

  function savePoolDraft() {
    if (!poolDraft) return;
    const next = pools.slice();
    if (poolIndex == null) next.push(normalizePool(poolDraft));
    else next[poolIndex] = normalizePool(poolDraft);
    updatePools(next);
    setPoolDraft(null);
    setPoolIndex(null);
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">DR</div>
          <div><strong>DsRelay</strong><span>本地代理控制台</span></div>
        </div>
        <nav>
          <NavButton active={view === 'overview'} onClick={() => setView('overview')} icon={<Activity size={16} />} label="总览" />
          <NavButton active={view === 'requests'} onClick={() => setView('requests')} icon={<ListChecks size={16} />} label="请求观测" />
          <NavButton active={view === 'logs'} onClick={() => setView('logs')} icon={<Server size={16} />} label="运行日志" />
          <NavButton active={view === 'config'} onClick={() => setView('config')} icon={<Settings size={16} />} label="路由与策略" />
        </nav>
        <div className="sidebar-foot">
          <span>运行中 · {formatUptime(runtime.uptime_seconds)}</span>
          <small>PID {runtime.pid || '-'} · 端口 {runtime.port || '18765'}</small>
        </div>
      </aside>

      <main className="main">
        <header className="hero">
          <div>
            <p>本地代理</p>
            <h1>运行控制台</h1>
            <span className="endpoint">http://127.0.0.1:{runtime.port || '18765'}/v1</span>
          </div>
          <div className="hero-actions">
            <Badge tone={stateQuery.isError ? 'bad' : 'ok'}>{stateQuery.isError ? '连接异常' : '运行中'}</Badge>
            <Button onClick={() => stateQuery.refetch()}><RefreshCw size={15} />刷新</Button>
            <a className="btn btn-danger" href="/logout">退出登录</a>
          </div>
        </header>

        {view === 'overview' ? <Overview state={state} keys={keyQuery.data} /> : null}
        {view === 'requests' ? <RequestsView state={state} /> : null}
        {view === 'logs' ? <LogsView state={state} /> : null}
        {view === 'config' ? (
          <ConfigView
            draft={draft}
            pools={pools}
            configTab={configTab}
            setConfigTab={setConfigTab}
            status={status}
            saving={saveMutation.isPending}
            onPatch={patchDraft}
            onSave={() => saveMutation.mutate(draft)}
            onOpenPool={openPool}
            onDeletePool={(index) => updatePools(pools.filter((_, i) => i !== index))}
            onMovePool={(index, direction) => {
              const next = pools.slice();
              const target = index + direction;
              if (target < 0 || target >= next.length) return;
              [next[index], next[target]] = [next[target], next[index]];
              updatePools(next);
            }}
            keyPayload={keyQuery.data}
            refreshKeys={() => keyQuery.refetch()}
          />
        ) : null}
      </main>

      {poolDraft ? (
        <PoolModal
          pool={poolDraft}
          title={poolIndex == null ? '新增连接池' : '管理连接池'}
          testResult={poolTest}
          onChange={setPoolDraft}
          onClose={() => { setPoolDraft(null); setPoolIndex(null); }}
          onSave={savePoolDraft}
          onTest={async () => {
            if (poolIndex == null) return setPoolTest({ ok: false, message: '新连接池保存后再测试。' });
            setPoolTest(await testPool(poolIndex, poolDraft.name));
          }}
        />
      ) : null}
    </div>
  );
}

function NavButton({ active, onClick, icon, label }: { active: boolean; onClick: () => void; icon: React.ReactNode; label: string }) {
  return <button className={cn(active && 'active')} onClick={onClick}>{icon}<span>{label}</span></button>;
}

function Overview({ state, keys }: { state: DashboardState; keys?: ProxyKeyPayload }) {
  const runtime = state.runtime || {};
  const config = state.config || {};
  const pools = config.pools || [];
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

function RequestsView({ state }: { state: DashboardState }) {
  const rows = [...(state.active_requests || []), ...(state.recent_requests || [])];
  return (
    <Panel>
      <PanelHead title={<><ListChecks size={18} />请求观测</>} action={<RequestActions />} />
      <div className="table-wrap"><table><thead><tr><th>时间</th><th>状态</th><th>协议</th><th>模型</th><th>线路</th><th>耗时</th><th>Token</th></tr></thead><tbody>
        {rows.length ? rows.slice(0, 80).map((entry, index) => <RequestRow key={`${entry.request_id || index}-${index}`} entry={entry} />) : <tr><td colSpan={7}><Empty>暂无请求数据。</Empty></td></tr>}
      </tbody></table></div>
    </Panel>
  );
}

function RequestActions() {
  const clearMutation = useMutation({ mutationFn: clearRequests, onSuccess: () => queryClient.invalidateQueries({ queryKey: ['dashboard-state'] }) });
  const cacheMutation = useMutation({ mutationFn: clearRequestCache, onSuccess: () => queryClient.invalidateQueries({ queryKey: ['dashboard-state'] }) });
  return <div className="button-row"><Button onClick={() => clearMutation.mutate()}><Trash2 size={14} />清空请求</Button><Button onClick={() => cacheMutation.mutate()}><Trash2 size={14} />清空缓存</Button></div>;
}

function RequestRow({ entry }: { entry: RequestEntry }) {
  const status = entry.status_text || entry.status_code || (entry.error ? '异常' : entry.active ? '处理中' : '-');
  const tone = entry.error ? 'bad' : Number(entry.status_code || 0) >= 400 ? 'warn' : 'ok';
  return <tr>
    <td><strong>{maskEmpty(entry.started_at)}</strong><small>{maskEmpty(entry.request_id)}</small></td>
    <td><Badge tone={tone as any}>{String(status)}</Badge></td>
    <td>{maskEmpty(entry.protocol || entry.path)}</td>
    <td><strong>{maskEmpty(entry.logical_model || entry.model)}</strong><small>{maskEmpty(entry.resolved_model)}</small></td>
    <td><strong>{maskEmpty(entry.selected_pool_name)}</strong><small>{maskEmpty(entry.route_url || entry.upstream_url)}</small></td>
    <td>{formatMs(entry.duration_ms)}</td>
    <td>{formatNumber(entry.prompt_tokens)} ↓ / {formatNumber(entry.completion_tokens)} ↑</td>
  </tr>;
}

function LogsView({ state }: { state: DashboardState }) {
  return <Panel><PanelHead title={<><Server size={18} />运行日志</>} /><div className="log-list">{(state.recent_logs || []).length ? state.recent_logs!.map((line, i) => <code key={i}>{line}</code>) : <Empty>暂无日志。</Empty>}</div></Panel>;
}

function ConfigView(props: {
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
  keyPayload?: ProxyKeyPayload;
  refreshKeys: () => void;
}) {
  return <section className="config-layout">
    <Panel>
      <Tabs value={props.configTab} onChange={props.setConfigTab} items={[{ value: 'routes', label: '连接池' }, { value: 'routing', label: '模型与路由' }, { value: 'strategy', label: '策略' }]} />
      {props.configTab === 'routes' ? <PoolList {...props} /> : null}
      {props.configTab === 'routing' ? <RoutingPanel /> : null}
      {props.configTab === 'strategy' ? <StrategyPanel draft={props.draft} onPatch={props.onPatch} /> : null}
      <div className="save-strip"><span className={props.status.includes('失败') ? 'bad-text' : ''}>{props.status}</span><Button tone="primary" disabled={props.saving} onClick={props.onSave}><Save size={15} />{props.saving ? '正在保存' : '保存并生效'}</Button></div>
    </Panel>
    <Panel className="sticky-panel"><PanelHead title="入口 Key" /><ProxyKeys payload={props.keyPayload} refresh={props.refreshKeys} /></Panel>
  </section>;
}

function PoolList({ pools, onOpenPool, onDeletePool, onMovePool }: any) {
  return <div className="section-stack"><div className="split-head"><div><h4>连接池管理</h4><p>线路优先级、模型映射、协议和缓存策略都在这里维护。</p></div><Button tone="primary" onClick={() => onOpenPool(null)}>添加连接池</Button></div>{pools.length ? pools.map((pool: Pool, index: number) => <div className="pool-card" key={`${pool.name}-${index}`}><div><strong>{pool.name || `连接池 ${index + 1}`}</strong><p>{(pool.urls || []).join(' · ') || '未配置地址'}</p><div className="chip-row"><Badge tone={pool.enabled === false ? 'warn' : 'ok'}>{pool.enabled === false ? '停用' : '启用'}</Badge><Badge>优先级 {pool.priority ?? 100}</Badge><Badge>{protocolText(pool.route_policy?.text_upstream_protocol)}</Badge><Badge>{countLines(pool.supported_models_text)} 模型</Badge><Badge>{countLines(pool.model_aliases_text)} 映射</Badge></div></div><div className="button-row"><Button onClick={() => onMovePool(index, -1)}>上移</Button><Button onClick={() => onMovePool(index, 1)}>下移</Button><Button onClick={() => onOpenPool(index)}>管理</Button><Button tone="danger" onClick={() => onDeletePool(index)}>删除</Button></div></div>) : <Empty>暂无连接池。</Empty>}</div>;
}

function RoutingPanel() {
  return <div className="section-stack"><h4>线路模型与协议</h4><p className="subtle">模型映射和上游协议在线路里配置；模型参数按协议和模型默认能力自动处理。</p></div>;
}

function StrategyPanel({ draft, onPatch }: { draft: RuntimeConfig; onPatch: (patch: Partial<RuntimeConfig>) => void }) {
  const n = (key: keyof RuntimeConfig, fallback = 0) => Number(draft[key] ?? fallback);
  const b = (key: keyof RuntimeConfig) => Boolean(draft[key]);
  return <div className="form-grid">
    <Field label="请求超时（秒）"><NumberInput value={n('request_timeout', 600)} onChange={(e) => onPatch({ request_timeout: Number(e.target.value) })} /></Field>
    <Field label="流式首包超时（秒）"><NumberInput value={n('stream_first_event_timeout_seconds', 30)} onChange={(e) => onPatch({ stream_first_event_timeout_seconds: Number(e.target.value) })} /></Field>
    <Field label="全局兜底上限"><NumberInput value={n('max_completion_tokens', 0)} onChange={(e) => onPatch({ max_completion_tokens: Number(e.target.value) })} /></Field>
    <Field label="最大重试次数"><NumberInput value={n('max_retries', 0)} onChange={(e) => onPatch({ max_retries: Number(e.target.value) })} /></Field>
    <Field label="重试退避（毫秒）"><NumberInput value={n('retry_backoff_ms', 0)} onChange={(e) => onPatch({ retry_backoff_ms: Number(e.target.value) })} /></Field>
    <Field label="最大退避（毫秒）"><NumberInput value={n('retry_max_backoff_ms', 0)} onChange={(e) => onPatch({ retry_max_backoff_ms: Number(e.target.value) })} /></Field>
    <Field label="换路窗口（秒）"><NumberInput value={n('route_switch_window_seconds', 60)} onChange={(e) => onPatch({ route_switch_window_seconds: Number(e.target.value) })} /></Field>
    <Field label="模型探测超时（秒）"><NumberInput value={n('model_probe_timeout_seconds', 4)} onChange={(e) => onPatch({ model_probe_timeout_seconds: Number(e.target.value) })} /></Field>
    <Field label="模型列表缓存（秒）"><NumberInput value={n('model_probe_ttl_seconds', 300)} onChange={(e) => onPatch({ model_probe_ttl_seconds: Number(e.target.value) })} /></Field>
    <Field label="图片协议"><Select value={draft.image_upstream_protocol || 'auto'} onChange={(e) => onPatch({ image_upstream_protocol: e.target.value })}><option value="auto">自动</option><option value="openai">OpenAI</option><option value="google">Google</option><option value="dashscope">DashScope</option></Select></Field>
    <Field label="图片等待（秒）"><NumberInput value={n('image_task_poll_timeout_seconds', 90)} onChange={(e) => onPatch({ image_task_poll_timeout_seconds: Number(e.target.value) })} /></Field>
    <Field label="图片轮询间隔"><NumberInput value={n('image_task_poll_interval_seconds', 2)} onChange={(e) => onPatch({ image_task_poll_interval_seconds: Number(e.target.value) })} /></Field>
    <div className="toggle-grid"><Toggle label="随机轮换" checked={b('randomize_endpoints')} onChange={(v) => onPatch({ randomize_endpoints: v })} /><Toggle label="强制上游流式" checked={b('force_upstream_chat_stream')} onChange={(v) => onPatch({ force_upstream_chat_stream: v })} /><Toggle label="请求归一化" checked={b('enable_request_normalization')} onChange={(v) => onPatch({ enable_request_normalization: v })} /><Toggle label="中文提示注入" checked={b('inject_zh_system_prompt')} onChange={(v) => onPatch({ inject_zh_system_prompt: v })} /><Toggle label="模型探测" checked={b('enable_model_probe')} onChange={(v) => onPatch({ enable_model_probe: v })} /><Toggle label="候选竞速" checked={b('enable_model_candidate_race')} onChange={(v) => onPatch({ enable_model_candidate_race: v })} /><Toggle label="中断续接" checked={b('enable_interruption_resume')} onChange={(v) => onPatch({ enable_interruption_resume: v })} /></div>
    <Field label="中文系统提示" full><TextArea rows={5} value={draft.proxy_system_prompt_zh || ''} onChange={(e) => onPatch({ proxy_system_prompt_zh: e.target.value })} /></Field>
  </div>;
}

function PoolModal({ pool, title, testResult, onChange, onClose, onSave, onTest }: { pool: Pool; title: string; testResult: PoolTestResult | null; onChange: (pool: Pool) => void; onClose: () => void; onSave: () => void; onTest: () => void }) {
  const p = normalizePool(pool);
  const policy = { ...defaultPolicy, ...(p.route_policy || {}) };
  const patch = (next: Partial<Pool>) => onChange(normalizePool({ ...p, ...next }));
  const patchPolicy = (next: Record<string, unknown>) => patch({ route_policy: { ...policy, ...next } });
  return <Modal title={title} onClose={onClose} footer={<><Button onClick={onTest}>测试线路</Button><Button onClick={onClose}>取消</Button><Button tone="primary" onClick={onSave}>保存连接池</Button></>}>
    <div className="form-grid modal-grid">
      <Field label="名称"><TextInput value={p.name || ''} onChange={(e) => patch({ name: e.target.value })} /></Field>
      <Field label="优先级"><NumberInput value={p.priority ?? 100} onChange={(e) => patch({ priority: Number(e.target.value) })} /></Field>
      <Toggle label="启用连接池" checked={p.enabled !== false} onChange={(enabled) => patch({ enabled })} />
      <Field label="上游地址" full><TextArea rows={3} value={textFromLines(p.urls)} onChange={(e) => patch({ urls: splitLines(e.target.value) })} /></Field>
      <Field label="API Keys" full><TextArea rows={3} value={(p.keys || []).map((k) => k.key).join('\n')} onChange={(e) => patch({ keys: splitLines(e.target.value).map((key) => ({ key })) })} /></Field>
      <Field label="该线路支持模型" full><TextArea rows={4} value={p.supported_models_text || ''} onChange={(e) => patch({ supported_models_text: e.target.value })} /></Field>
      <Field label="该线路模型映射" full><TextArea rows={4} value={p.model_aliases_text || ''} onChange={(e) => patch({ model_aliases_text: e.target.value })} /></Field>
      <Field label="思考强度"><Select value={policy.reasoning_effort} onChange={(e) => patchPolicy({ reasoning_effort: e.target.value })}><option value="low">低</option><option value="medium">中</option><option value="high">高</option></Select></Field>
      <Field label="文本上游协议"><Select value={policy.text_upstream_protocol} onChange={(e) => patchPolicy({ text_upstream_protocol: e.target.value })}><option value="auto">自动</option><option value="openai">OpenAI 兼容</option><option value="responses">Responses</option><option value="anthropic">Anthropic</option><option value="gemini">Gemini</option></Select></Field>
      <Field label="本地精确缓存"><Select value={policy.prompt_cache_mode} onChange={(e) => patchPolicy({ prompt_cache_mode: e.target.value })}><option value="off">关闭</option><option value="exact">开启</option></Select></Field>
      <Field label="上游缓存 Hint"><Select value={policy.prompt_cache_hints_mode} onChange={(e) => patchPolicy({ prompt_cache_hints_mode: e.target.value })}><option value="off">关闭</option><option value="auto">自动判断</option><option value="passthrough">仅透传</option></Select></Field>
      <Field label="缓存提供方"><Select value={policy.prompt_cache_provider} onChange={(e) => patchPolicy({ prompt_cache_provider: e.target.value })}><option value="auto">自动识别</option><option value="openai">OpenAI</option><option value="openrouter">OpenRouter</option><option value="deepseek">DeepSeek</option><option value="anthropic">Anthropic</option><option value="gemini">Gemini</option><option value="observe">仅观测</option><option value="none">不支持</option></Select></Field>
      <Field label="输出上限"><NumberInput value={policy.max_output_tokens} onChange={(e) => patchPolicy({ max_output_tokens: Number(e.target.value) })} /></Field>
      <Field label="基础冷却秒数"><NumberInput value={policy.route_cooldown_seconds} onChange={(e) => patchPolicy({ route_cooldown_seconds: Number(e.target.value) })} /></Field>
      <Field label="冷却指数"><NumberInput step="0.1" value={policy.route_cooldown_multiplier} onChange={(e) => patchPolicy({ route_cooldown_multiplier: Number(e.target.value) })} /></Field>
      <Field label="最大冷却秒数"><NumberInput value={policy.route_cooldown_max_seconds} onChange={(e) => patchPolicy({ route_cooldown_max_seconds: Number(e.target.value) })} /></Field>
      <Field label="429重试次数"><NumberInput value={policy.rate_limit_retry_attempts} onChange={(e) => patchPolicy({ rate_limit_retry_attempts: Number(e.target.value) })} /></Field>
      <Field label="429初始退避毫秒"><NumberInput value={policy.rate_limit_backoff_initial_ms} onChange={(e) => patchPolicy({ rate_limit_backoff_initial_ms: Number(e.target.value) })} /></Field>
      <Field label="429退避倍率"><NumberInput step="0.1" value={policy.rate_limit_backoff_multiplier} onChange={(e) => patchPolicy({ rate_limit_backoff_multiplier: Number(e.target.value) })} /></Field>
      <Field label="429最大退避毫秒"><NumberInput value={policy.rate_limit_backoff_max_ms} onChange={(e) => patchPolicy({ rate_limit_backoff_max_ms: Number(e.target.value) })} /></Field>
    </div>
    {testResult ? <PoolTestView result={testResult} /> : null}
  </Modal>;
}

function ProxyKeys({ payload, refresh }: { payload?: ProxyKeyPayload; refresh: () => void }) {
  const [name, setName] = useState('NEWAPI');
  const [generated, setGenerated] = useState('');
  const mutation = useMutation({ mutationFn: mutateProxyKey, onSuccess: (data) => { setGenerated(data.generated_key || ''); queryClient.invalidateQueries({ queryKey: ['proxy-keys'] }); refresh(); } });
  return <div className="section-stack"><div className="inline-form"><TextInput value={name} onChange={(e) => setName(e.target.value)} /><Button tone="primary" onClick={() => mutation.mutate({ action: 'create', name })}><KeyRound size={14} />生成</Button></div>{generated ? <div className="copy-box"><code>{generated}</code><Button onClick={() => navigator.clipboard?.writeText(generated)}>复制</Button></div> : null}{(payload?.keys || []).map((key) => <div className="key-row" key={key.id}><div><strong>{key.name || 'NEWAPI'}</strong><small>{key.preview || '-'}</small></div><div className="button-row"><Button onClick={() => mutation.mutate({ action: 'update', id: key.id, enabled: !key.enabled })}>{key.enabled === false ? '启用' : '停用'}</Button><Button tone="danger" onClick={() => mutation.mutate({ action: 'delete', id: key.id })}>删除</Button></div></div>)}</div>;
}

function RouteTable({ rows }: { rows: any[] }) {
  return <div className="table-wrap"><table><thead><tr><th>线路</th><th>连接池</th><th>缓存</th><th>协议</th><th>冷却</th></tr></thead><tbody>{rows.length ? rows.map((row, i) => <tr key={`${row.route_url}-${i}`}><td><strong>{maskEmpty(row.route_url)}</strong><small>活跃粘滞 {row.active_affinity_count || 0}</small></td><td>{maskEmpty(row.pool_name)}<small>{row.route_status_text || '-'}</small></td><td>{row.route_policy?.prompt_cache_mode || '-'}</td><td>{protocolText(row.route_policy?.text_upstream_protocol)}</td><td>{row.route_policy?.route_cooldown_seconds || 0}s</td></tr>) : <tr><td colSpan={5}><Empty>暂无线路级观测数据。</Empty></td></tr>}</tbody></table></div>;
}

function PoolTestView({ result }: { result: PoolTestResult }) {
  return <div className="test-result"><Badge tone={result.summary_ok ? 'ok' : 'warn'}>{result.summary_ok ? '测试通过' : '测试未通过'}</Badge>{result.message ? <p>{result.message}</p> : null}{(result.results || []).map((route) => <div key={route.url} className="test-route"><strong>{route.url}</strong><small>{route.models_url}</small>{(route.keys || []).map((key, i) => <p key={i}><Badge tone={key.ok ? 'ok' : 'bad'}>{key.status_code ?? '-'}</Badge> {key.key_preview} · {formatMs(key.latency_ms)} · {key.message}</p>)}</div>)}</div>;
}

function Info({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return <div className="info-item"><span>{label}</span><strong className={mono ? 'mono' : ''}>{value}</strong></div>;
}

function protocolText(value?: string) {
  if (value === 'openai') return 'OpenAI 兼容';
  if (value === 'responses') return 'Responses';
  if (value === 'anthropic') return 'Anthropic';
  if (value === 'gemini') return 'Gemini';
  return '自动';
}

createRoot(document.getElementById('root')!).render(<QueryClientProvider client={queryClient}><App /></QueryClientProvider>);
