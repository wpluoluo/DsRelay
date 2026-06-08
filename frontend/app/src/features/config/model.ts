import type { Pool, RuntimeConfig } from '../../types';

export type ViewKey = 'overview' | 'requests' | 'logs' | 'config';
export type ConfigTab = 'routes' | 'routing' | 'strategy' | 'keys';

export const defaultPolicy = {
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

export function normalizePool(pool?: Pool): Pool {
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

export function configFromState(config?: RuntimeConfig): RuntimeConfig {
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
