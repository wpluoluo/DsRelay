import type { DashboardState, PoolTestResult, ProxyKeyPayload, RuntimeConfig } from './types';

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

export function fetchProxyKeys(): Promise<ProxyKeyPayload> {
  return requestJson<ProxyKeyPayload>('/debug/proxy-keys');
}

export function mutateProxyKey(payload: Record<string, unknown>): Promise<ProxyKeyPayload> {
  return requestJson<ProxyKeyPayload>('/debug/proxy-keys', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function testPool(poolIndex: number, poolName?: string): Promise<PoolTestResult> {
  return requestJson<PoolTestResult>('/debug/pools/test', {
    method: 'POST',
    body: JSON.stringify({ pool_index: poolIndex, pool_name: poolName || '' }),
  });
}
