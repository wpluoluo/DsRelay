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
  config_source?: string;
  db_label?: string;
  config_path?: string;
};

export type RequestEntry = Record<string, any> & {
  request_id?: string;
  started_at?: string;
  duration_ms?: number;
  status_code?: number;
  status_text?: string;
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
  api_key_index?: number;
  retry_count?: number;
  route_pool_size?: number;
  attempt_route_count?: number;
  pool_name?: string;
  logical_model?: string;
  model?: string;
  resolved_model?: string;
  prompt_tokens?: number;
  completion_tokens?: number;
  total_tokens?: number;
  input_bytes?: number;
  bytes_sent?: number;
  cache_read_bytes?: number;
  cache_read_input_tokens?: number;
  cache_creation_input_tokens?: number;
  local_response_cache_hit?: boolean;
  local_response_cache_status?: string;
  upstream_prompt_cache_status?: string;
  request_repairs?: number;
  sanitized_markers?: number;
  repaired_tool_args?: number;
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
  request_count?: number;
  success_count?: number;
  error_count?: number;
  status_429_count?: number;
  local_cache_hit_rate?: number;
  local_cache_hit_count?: number;
  local_cache_miss_count?: number;
  local_cache_bypass_count?: number;
  local_cache_eligible_count?: number;
  upstream_prompt_cache_hit_rate?: number;
  upstream_prompt_cache_hit_count?: number;
  upstream_prompt_cache_request_count?: number;
  avg_cache_read_input_tokens?: number;
  sticky_session_count?: number;
  session_count?: number;
  sticky_session_rate?: number;
  hint_applied_count?: number;
  hint_applied_rate?: number;
  consecutive_failures?: number;
  last_reason?: string;
  cooling?: boolean;
  historical_only?: boolean;
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

export type AdminOverviewPayload = {
  ok?: boolean;
  account_count?: number;
  group_count?: number;
  protocol_count?: number;
  request_count?: number;
  total_tokens?: number;
  input_bytes?: number;
  output_bytes?: number;
  error_count?: number;
  top_accounts?: AdminAccount[];
  top_groups?: AdminGroup[];
};

export type AdminProtocolProfile = {
  key: string;
  label: string;
  supports_tools?: boolean;
  supports_stream?: boolean;
  supports_system_prompt?: boolean;
  supports_images?: boolean;
  parameter_keys?: string[];
};

export type AdminAccount = {
  id: string;
  pool_name?: string;
  route_url?: string;
  route_index?: number;
  provider_name?: string;
  priority?: number;
  key_count?: number;
  protocol?: string;
  cooldown_seconds?: number;
  backoff_attempts?: number;
  models?: string[];
  name: string;
  source_type: string;
  preview?: string;
  external_key?: string;
  role?: string;
  status?: string;
  balance_cents?: number;
  concurrency_limit?: number;
  allowed_group_ids?: string[];
  extra?: Record<string, unknown>;
  enabled?: boolean;
  note?: string;
  request_count?: number;
  error_count?: number;
  prompt_tokens?: number;
  completion_tokens?: number;
  total_tokens?: number;
  input_bytes?: number;
  output_bytes?: number;
  last_seen_at?: string;
  group_id?: string;
  group_name?: string;
  subscription_active?: boolean;
  active_subscription_id?: string;
  active_plan_id?: string;
  active_plan_name?: string;
  active_group_id?: string;
  active_group_name?: string;
  active_subscription_status?: string;
  active_subscription_expires_at?: number | string | null;
  active_subscription_price_cents?: number;
};

export type AdminUser = {
  id: string;
  name: string;
  preview?: string;
  source_type?: string;
  role?: string;
  note?: string;
  balance_cents?: number;
  concurrency_limit?: number;
  allowed_group_ids?: string[];
  group_id?: string;
  group_name?: string;
  enabled?: boolean;
  status?: string;
  request_count?: number;
  last_seen_at?: string;
  key_count?: number;
  active_key_count?: number;
  subscription_count?: number;
  active_subscription_count?: number;
  subscription_active?: boolean;
  active_plan_name?: string;
  active_group_id?: string;
  active_group_name?: string;
};

export type AdminGroup = {
  id: string;
  name: string;
  description?: string;
  platform?: string;
  is_exclusive?: boolean;
  rate_multiplier?: number;
  extra?: Record<string, unknown>;
  enabled?: boolean;
  sort_order?: number;
  account_count?: number;
  request_count?: number;
  error_count?: number;
  total_tokens?: number;
  input_bytes?: number;
  output_bytes?: number;
};

export type AdminUsageItem = {
  request_id: string;
  started_at?: string;
  consumer_id?: string;
  consumer_name?: string;
  consumer_type?: string;
  consumer_preview?: string;
  subscription_id?: string;
  plan_id?: string;
  plan_name?: string;
  group_id?: string;
  group_name?: string;
  plan_price_cents?: number;
  model?: string;
  resolved_model?: string;
  pool_name?: string;
  route_url?: string;
  status_code?: number;
  duration_ms?: number;
  prompt_tokens?: number;
  completion_tokens?: number;
  total_tokens?: number;
  input_bytes?: number;
  output_bytes?: number;
  cache_read_tokens?: number;
  cache_write_tokens?: number;
  local_cache_status?: string;
  upstream_cache_status?: string;
  error?: string;
  total_cost?: number;
  actual_cost?: number;
  account_cost?: number;
};

export type AdminBillingSummary = {
  request_count?: number;
  error_count?: number;
  prompt_tokens?: number;
  completion_tokens?: number;
  total_tokens?: number;
  input_bytes?: number;
  output_bytes?: number;
  cache_read_tokens?: number;
  cache_write_tokens?: number;
  amount_cents?: number;
  total_cost?: number;
  actual_cost?: number;
  account_cost?: number;
  active_subscription_count?: number;
  covered_request_count?: number;
};

export type AdminBillingAccountItem = {
  account_id: string;
  account_name?: string;
  consumer_type?: string;
  group_ids?: string[];
  group_names?: string[];
  plan_ids?: string[];
  plan_names?: string[];
  subscription_ids?: string[];
  request_count?: number;
  error_count?: number;
  prompt_tokens?: number;
  completion_tokens?: number;
  total_tokens?: number;
  input_bytes?: number;
  output_bytes?: number;
  cache_read_tokens?: number;
  cache_write_tokens?: number;
  amount_cents?: number;
  total_cost?: number;
  actual_cost?: number;
  account_cost?: number;
};

export type AdminBillingGroupItem = {
  group_id?: string;
  group_name?: string;
  account_ids?: string[];
  plan_ids?: string[];
  subscription_ids?: string[];
  request_count?: number;
  error_count?: number;
  total_tokens?: number;
  input_bytes?: number;
  output_bytes?: number;
  amount_cents?: number;
  total_cost?: number;
  actual_cost?: number;
  account_cost?: number;
};

export type AdminBillingPlanItem = {
  plan_id?: string;
  plan_name?: string;
  group_id?: string;
  group_name?: string;
  plan_price_cents?: number;
  account_ids?: string[];
  subscription_ids?: string[];
  request_count?: number;
  error_count?: number;
  total_tokens?: number;
  input_bytes?: number;
  output_bytes?: number;
  amount_cents?: number;
  total_cost?: number;
  actual_cost?: number;
  account_cost?: number;
};

export type AdminBillingSubscriptionItem = {
  subscription_id: string;
  status?: string;
  account_id?: string;
  account_name?: string;
  plan_id?: string;
  plan_name?: string;
  group_id?: string;
  group_name?: string;
  price_cents?: number;
  started_at?: number | string | null;
  expires_at?: number | string | null;
  request_count?: number;
  error_count?: number;
  total_tokens?: number;
  input_bytes?: number;
  output_bytes?: number;
  amount_cents?: number;
  total_cost?: number;
  actual_cost?: number;
  account_cost?: number;
};

export type AdminBillingOrderItem = {
  order_id: string;
  subscription_id?: string;
  account_id?: string;
  account_name?: string;
  plan_id?: string;
  plan_name?: string;
  group_id?: string;
  group_name?: string;
  channel_id?: string;
  channel_name?: string;
  provider?: string;
  status?: string;
  amount_cents?: number;
  request_count?: number;
  error_count?: number;
  total_tokens?: number;
  input_bytes?: number;
  output_bytes?: number;
  total_cost?: number;
  actual_cost?: number;
  account_cost?: number;
};

export type AdminBillingPayload = {
  ok?: boolean;
  summary?: AdminBillingSummary;
  by_account?: AdminBillingAccountItem[];
  by_group?: AdminBillingGroupItem[];
  by_plan?: AdminBillingPlanItem[];
  by_subscription?: AdminBillingSubscriptionItem[];
  by_order?: AdminBillingOrderItem[];
  recent_request_total?: number;
  started_after?: string;
  started_before?: string;
};

export type AdminListPayload<T> = {
  ok?: boolean;
  items?: T[];
  total?: number;
};

export type AdminApiKey = {
  id: string;
  account_id: string;
  account_name?: string;
  account_source_type?: string;
  account_enabled?: boolean;
  account_note?: string;
  name: string;
  key_preview: string;
  enabled?: boolean;
  last_used_at?: number | null;
  created_at?: number;
  updated_at?: number;
  subscription_active?: boolean;
  active_subscription_id?: string;
  active_plan_id?: string;
  active_plan_name?: string;
  active_group_id?: string;
  active_group_name?: string;
  active_subscription_status?: string;
  active_subscription_expires_at?: number | string | null;
};

export type AdminSubscriptionPlan = {
  id: string;
  name: string;
  group_id?: string;
  group_name?: string;
  price_cents?: number;
  rate_multiplier?: number;
  final_price_cents?: number;
  validity_days?: number;
  daily_limit?: number;
  weekly_limit?: number;
  monthly_limit?: number;
  enabled?: boolean;
  note?: string;
};

export type AdminAccountSubscription = {
  id: string;
  account_id: string;
  account_name?: string;
  plan_id: string;
  plan_name?: string;
  group_id?: string;
  group_name?: string;
  price_cents?: number;
  rate_multiplier?: number;
  status?: string;
  started_at?: number;
  expires_at?: number | null;
  daily_used?: number;
  weekly_used?: number;
  monthly_used?: number;
  daily_limit?: number;
  weekly_limit?: number;
  monthly_limit?: number;
};

export type AdminPaymentFulfillmentLog = {
  id: string;
  order_id: string;
  subscription_id?: string;
  action?: string;
  actor_type?: string;
  actor_id?: string;
  note_text?: string;
  payload?: Record<string, unknown>;
  created_at?: number;
};

export type AdminPaymentChannel = {
  id: string;
  name: string;
  provider: string;
  enabled?: boolean;
  config?: Record<string, unknown>;
  allowed_group_ids?: string[];
  allowed_protocols?: string[];
  allowed_platforms?: string[];
};

export type AdminPaymentChannelTemplatePayload = {
  ok?: boolean;
  provider?: string;
  config?: Record<string, unknown>;
};

export type AdminPaymentOrder = {
  id: string;
  account_id: string;
  account_name?: string;
  plan_id: string;
  plan_name?: string;
  group_id?: string;
  group_name?: string;
  channel_id?: string;
  channel_name?: string;
  provider?: string;
  subscription_id?: string;
  amount_cents?: number;
  plan_price_cents?: number;
  base_price_cents?: number;
  final_price_cents?: number;
  rate_multiplier?: number;
  currency?: string;
  status?: string;
  provider_order_id?: string;
  resume_token?: string;
  paid_at?: number | null;
  payload?: Record<string, unknown>;
  provider_payload?: Record<string, unknown>;
  fulfillment_logs?: AdminPaymentFulfillmentLog[];
};

export type AdminContentItem = {
  id: string;
  title: string;
  status?: string;
  summary?: string;
  content?: string;
  note?: string;
  created_at?: number;
  updated_at?: number;
};

export type AdminContentPayload = {
  ok?: boolean;
  bucket?: string;
  label?: string;
  items?: AdminContentItem[];
  total?: number;
};
