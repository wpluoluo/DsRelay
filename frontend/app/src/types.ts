export type RoutePolicy = {
  reasoning_effort?: string;
  text_upstream_protocol?: string;
  prompt_cache_mode?: string;
  prompt_cache_hints_mode?: string;
  prompt_cache_provider?: string;
  prompt_cache_retention?: string;
  max_output_tokens?: number;
  route_cooldown_seconds?: number;
  route_cooldown_multiplier?: number;
  route_cooldown_max_seconds?: number;
  rate_limit_retry_attempts?: number;
  rate_limit_backoff_initial_ms?: number;
  rate_limit_backoff_multiplier?: number;
  rate_limit_backoff_max_ms?: number;
};

export type PoolKey = { key: string };

export type Pool = {
  name?: string;
  enabled?: boolean;
  priority?: number;
  urls?: string[];
  keys?: PoolKey[];
  supported_models_text?: string;
  model_aliases_text?: string;
  route_policy?: RoutePolicy;
};

export type RuntimeConfig = {
  pools?: Pool[];
  pools_count?: number;
  pools_enabled_count?: number;
  proxy_api_keys?: ProxyKey[];
  proxy_api_key_count?: number;
  proxy_api_key_env_count?: number;
  proxy_api_key_enabled_count?: number;
  request_timeout?: number;
  stream_first_event_timeout_seconds?: number;
  force_upstream_chat_stream?: boolean;
  enable_request_normalization?: boolean;
  max_completion_tokens?: number;
  inject_zh_system_prompt?: boolean;
  proxy_system_prompt_zh?: string;
  max_retries?: number;
  retry_backoff_ms?: number;
  retry_max_backoff_ms?: number;
  route_switch_window_seconds?: number;
  randomize_endpoints?: boolean;
  image_upstream_protocol?: string;
  image_task_poll_timeout_seconds?: number;
  image_task_poll_interval_seconds?: number;
  enable_model_probe?: boolean;
  model_probe_timeout_seconds?: number;
  model_probe_ttl_seconds?: number;
  model_route_cache_ttl_seconds?: number;
  enable_interruption_resume?: boolean;
  interruption_resume_ttl_seconds?: number;
  interruption_resume_max_chars?: number;
  interruption_resume_min_chars?: number;
  enable_model_candidate_race?: boolean;
  model_candidate_race_limit?: number;
  model_candidate_race_timeout_seconds?: number;
  model_capability_count?: number;
  config_source?: string;
  db_label?: string;
  config_path?: string;
};

export type RuntimeSnapshot = {
  capabilities?: string[];
  pid?: number;
  port?: number;
  uptime_seconds?: number;
  upstream_url_count?: number;
  upstream_urls?: string[];
  model_capability_count?: number;
  retry_config?: Record<string, unknown>;
  image_generation?: Record<string, unknown>;
  model_routing?: Record<string, any>;
  route_policies?: Record<string, RoutePolicy>;
  proxy_api_key_count?: number;
  proxy_api_key_env_count?: number;
  proxy_api_key_managed_count?: number;
  proxy_api_key_managed_enabled_count?: number;
  config_source?: string;
  db_label?: string;
  config_path?: string;
};

export type RequestEntry = Record<string, any> & {
  request_id?: string;
  started_at?: string;
  duration_ms?: number;
  status_code?: number;
  error?: string;
  stream?: boolean;
  protocol?: string;
  path?: string;
  method?: string;
  remote?: string;
  upstream_url?: string;
  route_url?: string;
  selected_pool_name?: string;
  selected_route_index?: number;
  selected_key_index?: number;
  route_pool_size?: number;
  attempt_route_count?: number;
  logical_model?: string;
  resolved_model?: string;
  prompt_tokens?: number;
  completion_tokens?: number;
  cache_status?: string;
  upstream_cache_status?: string;
};

export type RouteObservability = Record<string, any> & {
  route_url?: string;
  pool_name?: string;
  route_policy?: RoutePolicy;
  route_status_text?: string;
  route_status_note?: string;
  active_affinity_count?: number;
};

export type DashboardState = {
  ok?: boolean;
  config?: RuntimeConfig;
  runtime?: RuntimeSnapshot;
  upstream_url?: string;
  upstream_urls?: string[];
  upstream_url_count?: number;
  active_requests?: RequestEntry[];
  recent_requests?: RequestEntry[];
  recent_logs?: string[];
  route_observability?: RouteObservability[];
  pools_count?: number;
  pools_enabled_count?: number;
};

export type ProxyKey = {
  id?: string;
  name?: string;
  preview?: string;
  enabled?: boolean;
  created_at?: string;
  updated_at?: string;
};

export type ProxyKeyPayload = {
  ok?: boolean;
  keys?: ProxyKey[];
  generated_key?: string;
  env_key_count?: number;
  managed_key_count?: number;
  managed_enabled_count?: number;
};

export type PoolTestResult = {
  ok?: boolean;
  message?: string;
  pool_name?: string;
  summary_ok?: boolean;
  tested_at?: string;
  results?: Array<{
    url?: string;
    models_url?: string;
    keys?: Array<{
      key_preview?: string;
      ok?: boolean;
      status_code?: number | null;
      latency_ms?: number;
      message?: string;
    }>;
  }>;
};
