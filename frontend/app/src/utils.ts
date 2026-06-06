export function cn(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(' ');
}

export function formatNumber(value: unknown): string {
  const number = Number(value || 0);
  if (!Number.isFinite(number)) return '0';
  return number.toLocaleString('zh-CN');
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
