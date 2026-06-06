export function protocolText(value?: string) {
  if (value === 'openai') return 'OpenAI 兼容';
  if (value === 'responses') return 'Responses';
  if (value === 'anthropic') return 'Anthropic';
  if (value === 'gemini') return 'Gemini';
  return '自动';
}
