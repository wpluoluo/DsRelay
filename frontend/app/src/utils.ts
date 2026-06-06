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
