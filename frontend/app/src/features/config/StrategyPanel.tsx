import { Field, NumberInput, Select, TextArea, Toggle } from '../../components';
import type { RuntimeConfig } from '../../types';

export function StrategyPanel({ draft, onPatch }: { draft: RuntimeConfig; onPatch: (patch: Partial<RuntimeConfig>) => void }) {
  const n = (key: keyof RuntimeConfig, fallback = 0) => Number(draft[key] ?? fallback);
  const b = (key: keyof RuntimeConfig) => Boolean(draft[key]);
  return (
    <div className="form-grid">
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
      <div className="toggle-grid">
        <Toggle label="随机轮换" checked={b('randomize_endpoints')} onChange={(v) => onPatch({ randomize_endpoints: v })} />
        <Toggle label="强制上游流式" checked={b('force_upstream_chat_stream')} onChange={(v) => onPatch({ force_upstream_chat_stream: v })} />
        <Toggle label="请求归一化" checked={b('enable_request_normalization')} onChange={(v) => onPatch({ enable_request_normalization: v })} />
        <Toggle label="中文提示注入" checked={b('inject_zh_system_prompt')} onChange={(v) => onPatch({ inject_zh_system_prompt: v })} />
        <Toggle label="模型探测" checked={b('enable_model_probe')} onChange={(v) => onPatch({ enable_model_probe: v })} />
        <Toggle label="候选竞速" checked={b('enable_model_candidate_race')} onChange={(v) => onPatch({ enable_model_candidate_race: v })} />
        <Toggle label="中断续接" checked={b('enable_interruption_resume')} onChange={(v) => onPatch({ enable_interruption_resume: v })} />
      </div>
      <Field label="中文系统提示" full><TextArea rows={5} value={draft.proxy_system_prompt_zh || ''} onChange={(e) => onPatch({ proxy_system_prompt_zh: e.target.value })} /></Field>
    </div>
  );
}
