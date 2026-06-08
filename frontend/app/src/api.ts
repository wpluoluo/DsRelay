import type {
  AdminGroup,
  AdminApiKey,
  AdminListPayload,
  AdminBillingPayload,
  AdminOverviewPayload,
  AdminProtocolProfile,
  AdminPaymentChannel,
  AdminPaymentChannelTemplatePayload,
  AdminPaymentOrder,
  AdminContentPayload,
  AdminContentItem,
  AdminProviderAccount,
  AdminUser,
  AdminSubscriptionPlan,
  AdminUsageItem,
  AdminUserSubscription,
  DashboardState,
  PoolTestResult,
  RuntimeConfig,
} from './types';

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    cache: 'no-store',
    headers: init?.body ? { 'Content-Type': 'application/json', ...(init.headers || {}) } : init?.headers,
    ...init,
  });
  const text = await response.text();
  let payload: any = {};
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = { ok: false, message: text };
    }
  }
  if (!response.ok) {
    throw new Error(payload?.message || payload?.error?.message || `HTTP ${response.status}`);
  }
  return payload as T;
}

export function fetchDashboardState(): Promise<DashboardState> {
  return requestJson<DashboardState>('/debug/state');
}

export function saveConfig(config: RuntimeConfig): Promise<DashboardState> {
  return requestJson<DashboardState>('/debug/config', {
    method: 'POST',
    body: JSON.stringify(config),
  });
}

export function clearRequests(): Promise<{ ok: boolean; message?: string }> {
  return requestJson('/debug/requests/clear', { method: 'POST' });
}

export function clearRequestCache(): Promise<{ ok: boolean; message?: string }> {
  return requestJson('/debug/request-cache/clear', { method: 'POST' });
}

export function testPool(poolIndex: number, poolName?: string): Promise<PoolTestResult> {
  return requestJson<PoolTestResult>('/debug/pools/test', {
    method: 'POST',
    body: JSON.stringify({ pool_index: poolIndex, pool_name: poolName || '' }),
  });
}

export function fetchAdminOverview(): Promise<AdminOverviewPayload> {
  return requestJson<AdminOverviewPayload>('/admin/overview');
}

export function fetchAdminProtocols(): Promise<AdminListPayload<AdminProtocolProfile>> {
  return requestJson<AdminListPayload<AdminProtocolProfile>>('/admin/protocols');
}

export function fetchAdminProviderAccounts(): Promise<AdminListPayload<AdminProviderAccount>> {
  return requestJson<AdminListPayload<AdminProviderAccount>>('/admin/accounts');
}

export function fetchAdminUsers(): Promise<AdminListPayload<AdminUser>> {
  return requestJson<AdminListPayload<AdminUser>>('/admin/users');
}

export function createAdminUser(payload: Record<string, unknown>): Promise<{ ok?: boolean; item?: AdminUser }> {
  return requestJson<{ ok?: boolean; item?: AdminUser }>('/admin/users', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function updateAdminUser(userId: string, payload: Record<string, unknown>): Promise<{ ok?: boolean; item?: AdminUser }> {
  return requestJson<{ ok?: boolean; item?: AdminUser }>(`/admin/users/${userId}`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function setAdminUserEnabled(userId: string, enabled: boolean): Promise<{ ok?: boolean; item?: AdminUser }> {
  return requestJson<{ ok?: boolean; item?: AdminUser }>(`/admin/users/${userId}/enabled`, {
    method: 'POST',
    body: JSON.stringify({ enabled }),
  });
}

export function resetAdminUserExternalKey(userId: string): Promise<{ ok?: boolean; item?: AdminUser }> {
  return requestJson<{ ok?: boolean; item?: AdminUser }>(`/admin/users/${userId}/reset-key`, {
    method: 'POST',
  });
}

export function deleteAdminUser(userId: string): Promise<{ ok?: boolean; id?: string }> {
  return requestJson<{ ok?: boolean; id?: string }>(`/admin/users/${userId}`, {
    method: 'DELETE',
  });
}

export function fetchAdminGroups(): Promise<AdminListPayload<AdminGroup>> {
  return requestJson<AdminListPayload<AdminGroup>>('/admin/groups');
}

export function saveAdminGroup(payload: Record<string, unknown>): Promise<{ ok?: boolean; item?: AdminGroup }> {
  return requestJson<{ ok?: boolean; item?: AdminGroup }>('/admin/groups', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function fetchAdminUsage(params?: { started_after?: string; started_before?: string }): Promise<AdminListPayload<AdminUsageItem>> {
  const query = new URLSearchParams();
  if (params?.started_after) query.set('started_after', params.started_after);
  if (params?.started_before) query.set('started_before', params.started_before);
  const suffix = query.toString() ? `?${query.toString()}` : '';
  return requestJson<AdminListPayload<AdminUsageItem>>(`/admin/usage${suffix}`);
}

export function fetchAdminBilling(params?: { started_after?: string; started_before?: string }): Promise<AdminBillingPayload> {
  const query = new URLSearchParams();
  if (params?.started_after) query.set('started_after', params.started_after);
  if (params?.started_before) query.set('started_before', params.started_before);
  const suffix = query.toString() ? `?${query.toString()}` : '';
  return requestJson<AdminBillingPayload>(`/admin/billing${suffix}`);
}

export function fetchAdminApiKeys(): Promise<AdminListPayload<AdminApiKey>> {
  return requestJson<AdminListPayload<AdminApiKey>>('/admin/api-keys');
}

export function createAdminApiKey(payload: Record<string, unknown>): Promise<{ ok?: boolean; item?: AdminApiKey; generated_key?: string }> {
  return requestJson<{ ok?: boolean; item?: AdminApiKey; generated_key?: string }>('/admin/api-keys', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function updateAdminApiKey(keyId: string, payload: Record<string, unknown>): Promise<{ ok?: boolean; item?: AdminApiKey }> {
  return requestJson<{ ok?: boolean; item?: AdminApiKey }>(`/admin/api-keys/${keyId}`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function setAdminApiKeyEnabled(keyId: string, enabled: boolean): Promise<{ ok?: boolean }> {
  return requestJson<{ ok?: boolean }>(`/admin/api-keys/${keyId}/enabled`, {
    method: 'POST',
    body: JSON.stringify({ enabled }),
  });
}

export function deleteAdminApiKey(keyId: string): Promise<{ ok?: boolean; id?: string }> {
  return requestJson<{ ok?: boolean; id?: string }>(`/admin/api-keys/${keyId}`, {
    method: 'DELETE',
  });
}

export function fetchAdminSubscriptionPlans(): Promise<AdminListPayload<AdminSubscriptionPlan>> {
  return requestJson<AdminListPayload<AdminSubscriptionPlan>>('/admin/subscription-plans');
}

export function saveAdminSubscriptionPlan(payload: Record<string, unknown>): Promise<{ ok?: boolean; item?: AdminSubscriptionPlan }> {
  return requestJson<{ ok?: boolean; item?: AdminSubscriptionPlan }>('/admin/subscription-plans', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function fetchAdminUserSubscriptions(): Promise<AdminListPayload<AdminUserSubscription>> {
  return requestJson<AdminListPayload<AdminUserSubscription>>('/admin/subscriptions');
}

export function assignAdminUserSubscription(payload: Record<string, unknown>): Promise<{ ok?: boolean; item?: AdminUserSubscription }> {
  return requestJson<{ ok?: boolean; item?: AdminUserSubscription }>('/admin/subscriptions/assign', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function extendAdminUserSubscription(subscriptionId: string, days: number): Promise<{ ok?: boolean; item?: AdminUserSubscription }> {
  return requestJson<{ ok?: boolean; item?: AdminUserSubscription }>(`/admin/subscriptions/${subscriptionId}/extend`, {
    method: 'POST',
    body: JSON.stringify({ days }),
  });
}

export function revokeAdminUserSubscription(subscriptionId: string): Promise<{ ok?: boolean; item?: AdminUserSubscription }> {
  return requestJson<{ ok?: boolean; item?: AdminUserSubscription }>(`/admin/subscriptions/${subscriptionId}`, {
    method: 'DELETE',
  });
}

export function resetAdminUserSubscriptionQuota(subscriptionId: string, payload: { daily: boolean; weekly: boolean; monthly: boolean }): Promise<{ ok?: boolean; item?: AdminUserSubscription }> {
  return requestJson<{ ok?: boolean; item?: AdminUserSubscription }>(`/admin/subscriptions/${subscriptionId}/reset-quota`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function fetchAdminPaymentChannels(): Promise<AdminListPayload<AdminPaymentChannel>> {
  return requestJson<AdminListPayload<AdminPaymentChannel>>('/admin/payment-channels');
}

export function saveAdminPaymentChannel(payload: Record<string, unknown>): Promise<{ ok?: boolean; item?: AdminPaymentChannel }> {
  return requestJson<{ ok?: boolean; item?: AdminPaymentChannel }>('/admin/payment-channels', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function fetchAdminPaymentChannelTemplate(provider: string): Promise<AdminPaymentChannelTemplatePayload> {
  const query = new URLSearchParams({ provider }).toString();
  return requestJson<AdminPaymentChannelTemplatePayload>(`/admin/payment-channels/template?${query}`);
}

export function fetchAdminPaymentOrders(): Promise<AdminListPayload<AdminPaymentOrder>> {
  return requestJson<AdminListPayload<AdminPaymentOrder>>('/admin/payment-orders');
}

export function createAdminPaymentOrder(payload: Record<string, unknown>): Promise<{ ok?: boolean; item?: AdminPaymentOrder; provider_payload?: Record<string, unknown> }> {
  return requestJson<{ ok?: boolean; item?: AdminPaymentOrder; provider_payload?: Record<string, unknown> }>('/admin/payment-orders', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function updateAdminPaymentOrderStatus(orderId: string, payload: Record<string, unknown>): Promise<{ ok?: boolean; item?: AdminPaymentOrder }> {
  return requestJson<{ ok?: boolean; item?: AdminPaymentOrder }>(`/admin/payment-orders/${orderId}/status`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function fetchAdminContent(path: '/admin/announcements' | '/admin/risk-control' | '/admin/redeem' | '/admin/promo-codes' | '/admin/affiliates/invites' | '/admin/affiliates/rebates' | '/admin/affiliates/transfers'): Promise<AdminContentPayload> {
  return requestJson<AdminContentPayload>(path);
}

export function saveAdminContent(
  path: '/admin/announcements' | '/admin/risk-control' | '/admin/redeem' | '/admin/promo-codes' | '/admin/affiliates/invites' | '/admin/affiliates/rebates' | '/admin/affiliates/transfers',
  payload: Partial<AdminContentItem>,
): Promise<{ ok?: boolean; bucket?: string; item?: AdminContentItem }> {
  return requestJson<{ ok?: boolean; bucket?: string; item?: AdminContentItem }>(path, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function fulfillAdminPaymentOrder(orderId: string, payload: Record<string, unknown>): Promise<{ ok?: boolean; item?: AdminPaymentOrder }> {
  return requestJson<{ ok?: boolean; item?: AdminPaymentOrder }>(`/payment/webhook/${orderId}`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}
