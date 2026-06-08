export function cn(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(' ');
}

export function formatNumber(value: unknown): string {
  const number = Number(value || 0);
  if (!Number.isFinite(number)) return '0';
  return number.toLocaleString('zh-CN');
}

export function formatTokenCount(value: unknown): string {
  return `${formatNumber(value)} Token`;
}

export function formatCost(value: unknown, fractionDigits = 4): string {
  const number = Number(value || 0);
  if (!Number.isFinite(number)) return '0.0000';
  return number.toFixed(fractionDigits);
}

export function formatUsdCost(value: unknown, fractionDigits = 4): string {
  return `$${formatCost(value, fractionDigits)}`;
}

export function formatByteCount(value: unknown): string {
  return formatNumber(value);
}

export function formatMs(value: unknown): string {
  const number = Number(value || 0);
  if (!Number.isFinite(number) || number <= 0) return '0 ms';
  return `${formatNumber(number)} ms`;
}

export function formatUptime(seconds: unknown): string {
  const total = Math.max(0, Number(seconds || 0));
  const days = Math.floor(total / 86400);
  const hours = Math.floor((total % 86400) / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  if (days) return `${days}天 ${hours}小时`;
  if (hours) return `${hours}小时 ${minutes}分`;
  return `${minutes}分`;
}

export function countLines(text: unknown): number {
  return String(text || '')
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean).length;
}

export function maskEmpty(value: unknown): string {
  const text = String(value ?? '').trim();
  return text || '-';
}

export function getBusinessUserId(item: Record<string, unknown> | null | undefined): string {
  if (!item) return '';
  return String(item.user_id || item.consumer_id || item.account_id || '').trim();
}

export function getBusinessUserName(item: Record<string, unknown> | null | undefined): string {
  if (!item) return '-';
  const id = getBusinessUserId(item);
  return maskEmpty(item.user_name || item.consumer_name || item.account_name || id);
}

export function getBusinessUserKey(item: Record<string, unknown> | null | undefined): string {
  if (!item) return '';
  return String(item.user_key || item.consumer_preview || item.external_key || '').trim();
}

export function buildBusinessUserPayload(userId: string, payload: Record<string, unknown> = {}): Record<string, unknown> {
  return { ...payload, user_id: userId };
}

export function splitLines(value: unknown): string[] {
  return String(value || '')
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
}

export function textFromLines(lines: unknown): string {
  if (!Array.isArray(lines)) return '';
  return lines.map((line) => String(line || '').trim()).filter(Boolean).join('\n');
}

export function summarizeUpstreamCacheStatus(status: unknown, readTokens: unknown): string {
  const normalized = String(status || '').toLowerCase();
  if (Number(readTokens || 0) > 0 || normalized === 'hit') return '命中';
  if (normalized === 'hinted') return '已提示';
  if (normalized === 'miss') return '未命中';
  if (normalized === 'passthrough') return '透传';
  if (normalized === 'off') return '关闭';
  if (normalized === 'eligible') return '未命中';
  return status ? String(status) : '关闭';
}

export function summarizeLocalCacheStatus(status: unknown, hit: unknown): string {
  const normalized = String(status || '').toLowerCase();
  if (hit || normalized === 'hit') return '命中';
  if (normalized.startsWith('bypass')) return '跳过';
  if (normalized === 'off' || normalized === 'disabled') return '关闭';
  if (normalized === 'miss') return '未命中';
  return status ? String(status) : '未命中';
}

export function readStorageJSON<T>(key: string, fallback: T): T {
  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) return fallback;
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}

export function writeStorageJSON(key: string, value: unknown) {
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {}
}

export async function copyTextToClipboard(value: string): Promise<boolean> {
  const text = String(value || '');
  if (!text) return false;
  try {
    if (navigator.clipboard?.writeText && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {}
  try {
    const element = document.createElement('textarea');
    element.value = text;
    element.setAttribute('readonly', 'true');
    element.style.position = 'fixed';
    element.style.left = '-9999px';
    element.style.top = '0';
    document.body.appendChild(element);
    element.focus();
    element.select();
    const ok = document.execCommand('copy');
    document.body.removeChild(element);
    return ok;
  } catch {
    return false;
  }
}
