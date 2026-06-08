import { Button, Field, Modal, NumberInput, Select, TextArea, TextInput, Toggle } from '../../components';
import type { Pool, PoolTestResult } from '../../types';
import { splitLines, textFromLines } from '../../utils';
import { PoolTestView } from '../routes/RouteTable';
import { defaultPolicy, normalizePool } from './model';

export function PoolModal({
  pool,
  title,
  testResult,
  onChange,
  onClose,
  onSave,
  onTest,
}: {
  pool: Pool;
  title: string;
  testResult: PoolTestResult | null;
  onChange: (pool: Pool) => void;
  onClose: () => void;
  onSave: () => void;
  onTest: () => void;
}) {
  const p = normalizePool(pool);
  const policy = { ...defaultPolicy, ...(p.route_policy || {}) };
  const patch = (next: Partial<Pool>) => onChange(normalizePool({ ...p, ...next }));
  const patchPolicy = (next: Record<string, unknown>) => patch({ route_policy: { ...policy, ...next } });
  return (
    <Modal title={title} onClose={onClose} footer={<><Button onClick={onTest}>测试线路</Button><Button onClick={onClose}>取消</Button><Button tone="primary" onClick={onSave}>保存账号</Button></>}>
      <div className="form-grid modal-grid">
        <Field label="名称"><TextInput value={p.name || ''} onChange={(e) => patch({ name: e.target.value })} /></Field>
        <Field label="优先级"><NumberInput value={p.priority ?? 100} onChange={(e) => patch({ priority: Number(e.target.value) })} /></Field>
        <Toggle label="启用账号" checked={p.enabled !== false} onChange={(enabled) => patch({ enabled })} />
        <Field label="上游地址" full><TextArea rows={3} value={textFromLines(p.urls)} onChange={(e) => patch({ urls: splitLines(e.target.value) })} /></Field>
        <Field label="API Key" full><TextArea rows={3} value={(p.keys || []).map((k) => k.key).join('\n')} onChange={(e) => patch({ keys: splitLines(e.target.value).map((key) => ({ key })) })} /></Field>
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
    </Modal>
  );
}
