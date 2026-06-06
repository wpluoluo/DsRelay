import { useMemo, useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { Check, Clipboard, Copy, Edit3, Eye, KeyRound, Plus, RefreshCw, Terminal, Trash2 } from 'lucide-react';
import { mutateProxyKey } from '../../api';
import { Badge, Button, Empty, Field, Modal, Select, TextInput } from '../../components';
import { queryClient } from '../../state/queryClient';
import type { ProxyKey, ProxyKeyPayload } from '../../types';
import { formatNumber, maskEmpty } from '../../utils';

type KeyFilter = {
  search: string;
  status: 'all' | 'enabled' | 'disabled';
};

export function ProxyKeys({ payload, refresh }: { payload?: ProxyKeyPayload; refresh: () => void }) {
  const [filter, setFilter] = useState<KeyFilter>({ search: '', status: 'all' });
  const [createOpen, setCreateOpen] = useState(false);
  const [editKey, setEditKey] = useState<ProxyKey | null>(null);
  const [useKey, setUseKey] = useState<ProxyKey | null>(null);
  const [formName, setFormName] = useState('NEWAPI');
  const [generated, setGenerated] = useState('');
  const [status, setStatus] = useState('');
  const [copied, setCopied] = useState('');

  const keys = payload?.keys || [];
  const enabledCount = payload?.managed_enabled_count ?? keys.filter((key) => key.enabled !== false).length;
  const disabledCount = Math.max(0, keys.length - enabledCount);
  const envCount = payload?.env_key_count ?? 0;
  const endpoint = `${window.location.origin.replace(/\/+$/, '')}/v1`;
  const filteredKeys = useMemo(() => filterKeys(keys, filter), [keys, filter]);

  const mutation = useMutation({
    mutationFn: mutateProxyKey,
    onSuccess: (data) => {
      if (data.generated_key) {
        setGenerated(data.generated_key);
        setUseKey({ name: formName.trim() || 'NEWAPI', key: data.generated_key, preview: maskKey(data.generated_key), enabled: true } as any);
      }
      queryClient.invalidateQueries({ queryKey: ['proxy-keys'] });
      refresh();
      setStatus('API Key 操作已生效。');
      setCreateOpen(false);
      setEditKey(null);
    },
    onError: (error) => setStatus(error instanceof Error ? error.message : 'API Key 操作失败'),
  });

  async function copyText(text: string, message: string, id: string) {
    if (!text) return;
    await navigator.clipboard?.writeText(text);
    setCopied(id);
    setStatus(message);
    window.setTimeout(() => setCopied((current) => (current === id ? '' : current)), 1800);
  }

  function openCreate() {
    setGenerated('');
    setFormName('NEWAPI');
    setCreateOpen(true);
  }

  function openEdit(key: ProxyKey) {
    setFormName(key.name || 'NEWAPI');
    setEditKey(key);
  }

  function submitCreate() {
    mutation.mutate({ action: 'create', name: formName.trim() || 'NEWAPI' });
  }

  function submitEdit() {
    if (!editKey?.id) return;
    mutation.mutate({ action: 'update', id: editKey.id, name: formName.trim() || 'NEWAPI' });
  }

  return (
    <div className="sub2-key-page">
      <div className="key-stat-grid">
        <KeyStat label="托管 Key" value={keys.length} sub="本地配置管理" tone="blue" />
        <KeyStat label="启用中" value={enabledCount} sub="可用于入口鉴权" tone="green" />
        <KeyStat label="已停用" value={disabledCount} sub="保留但不可用" tone="amber" />
        <KeyStat label="环境变量" value={envCount} sub="PROXY_API_KEYS" tone="slate" />
      </div>

      <div className="table-page-layout sub2-key-layout">
        <div className="layout-section-fixed">
          <div className="key-toolbar">
            <div className="key-filters">
              <TextInput value={filter.search} onChange={(event) => setFilter((current) => ({ ...current, search: event.target.value }))} placeholder="搜索名称、预览、ID" />
              <Select value={filter.status} onChange={(event) => setFilter((current) => ({ ...current, status: event.target.value as KeyFilter['status'] }))}>
                <option value="all">全部状态</option>
                <option value="enabled">启用中</option>
                <option value="disabled">已停用</option>
              </Select>
            </div>
            <div className="key-toolbar-actions">
              <Button onClick={refresh} disabled={mutation.isPending}><RefreshCw size={15} />刷新</Button>
              <Button tone="primary" onClick={openCreate}><Plus size={15} />创建 API Key</Button>
            </div>
          </div>
        </div>

        <EndpointStrip endpoint={endpoint} copied={copied} onCopy={copyText} />

        <div className="layout-section-scrollable">
          <div className="table-wrap table-scroll table-keys">
            <table>
              <colgroup>
                <col className="col-key-name" />
                <col className="col-key-value" />
                <col className="col-key-status" />
                <col className="col-key-created" />
                <col className="col-key-updated" />
                <col className="col-key-actions" />
              </colgroup>
              <thead>
                <tr><th>名称</th><th>API Key</th><th>状态</th><th>创建时间</th><th>更新时间</th><th>操作</th></tr>
              </thead>
              <tbody>
                {filteredKeys.length ? filteredKeys.map((key) => (
                  <tr key={key.id || key.preview}>
                    <td>
                      <div className="key-table-name">
                        <span><KeyRound size={15} />{key.name || 'NEWAPI'}</span>
                        <small className="request-mono">{key.id || '-'}</small>
                      </div>
                    </td>
                    <td>
                      <div className="key-value-cell">
                        <code>{(key as any).key || key.preview || '无预览'}</code>
                        <button type="button" className={copied === `preview-${key.id}` ? 'copied' : ''} onClick={() => copyText(String((key as any).key || key.preview || ''), 'Key 已复制。', `preview-${key.id}`)} title="复制 API Key">
                          {copied === `preview-${key.id}` ? <Check size={14} /> : <Clipboard size={14} />}
                        </button>
                      </div>
                    </td>
                    <td><span className={`badge ${key.enabled === false ? 'badge-warn' : 'badge-ok'}`}>{key.enabled === false ? '已停用' : '启用中'}</span></td>
                    <td><span className="table-muted">{key.created_at || '-'}</span></td>
                    <td><span className="table-muted">{key.updated_at || '-'}</span></td>
                    <td>
                      <div className="key-table-actions">
                        <button type="button" onClick={() => setUseKey(key)} title="使用方式"><Terminal size={15} /><span>使用</span></button>
                        <button type="button" onClick={() => openEdit(key)} title="编辑名称"><Edit3 size={15} /><span>编辑</span></button>
                        <button type="button" onClick={() => mutation.mutate({ action: 'update', id: key.id, enabled: key.enabled === false })} title={key.enabled === false ? '启用' : '停用'}><Eye size={15} /><span>{key.enabled === false ? '启用' : '停用'}</span></button>
                        <button type="button" className="danger" onClick={() => { if (confirm(`确认删除 API Key「${key.name || 'NEWAPI'}」？`)) mutation.mutate({ action: 'delete', id: key.id }); }} title="删除"><Trash2 size={15} /><span>删除</span></button>
                      </div>
                    </td>
                  </tr>
                )) : <tr><td colSpan={6}><Empty>暂无 API Key。点击右上角创建一个。</Empty></td></tr>}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {generated ? (
        <div className="generated-key-box generated-key-floating">
          <div className="generated-key-title">新 API Key 只显示一次</div>
          <div className="generated-key-row">
            <code className="generated-key-value">{generated}</code>
            <Button onClick={() => copyText(generated, '新 API Key 已复制。', 'generated')}><Copy size={14} />复制原始 Key</Button>
          </div>
        </div>
      ) : null}

      {status ? <div className={mutation.isError ? 'status-msg err' : 'status-msg'}>{status}</div> : null}

      {createOpen ? (
        <KeyFormModal
          title="创建 API Key"
          name={formName}
          busy={mutation.isPending}
          onName={setFormName}
          onClose={() => setCreateOpen(false)}
          onSubmit={submitCreate}
        />
      ) : null}

      {editKey ? (
        <KeyFormModal
          title="编辑 API Key"
          name={formName}
          busy={mutation.isPending}
          onName={setFormName}
          onClose={() => setEditKey(null)}
          onSubmit={submitEdit}
        />
      ) : null}

      {useKey ? <UseKeyModal apiKey={(useKey as any).key || generated || useKey.preview || ''} endpoint={endpoint} name={useKey.name || 'NEWAPI'} onClose={() => setUseKey(null)} onCopy={copyText} copied={copied} /> : null}
    </div>
  );
}

function EndpointStrip({ endpoint, copied, onCopy }: { endpoint: string; copied: string; onCopy: (text: string, message: string, id: string) => void }) {
  return (
    <div className="layout-section-fixed endpoint-strip">
      <span>默认端点</span>
      <code onClick={() => onCopy(endpoint, '端点已复制。', 'endpoint')}>{endpoint}</code>
      <button type="button" className={copied === 'endpoint' ? 'copied' : ''} onClick={() => onCopy(endpoint, '端点已复制。', 'endpoint')} title="复制端点">
        {copied === 'endpoint' ? <Check size={14} /> : <Clipboard size={14} />}
      </button>
      <a href={`https://www.tcptest.cn/http/${encodeURIComponent(endpoint)}`} target="_blank" rel="noreferrer">测速</a>
    </div>
  );
}

function KeyStat({ label, value, sub, tone }: { label: string; value: number; sub: string; tone: string }) {
  return (
    <div className="key-stat">
      <div className={`key-stat-icon ${tone}`}><KeyRound size={18} /></div>
      <div><span>{label}</span><strong>{formatNumber(value)}</strong><small>{sub}</small></div>
    </div>
  );
}

function KeyFormModal({ title, name, busy, onName, onClose, onSubmit }: { title: string; name: string; busy: boolean; onName: (value: string) => void; onClose: () => void; onSubmit: () => void }) {
  return (
    <Modal
      title={title}
      onClose={onClose}
      footer={<><Button onClick={onClose}>取消</Button><Button tone="primary" disabled={busy} onClick={onSubmit}>保存</Button></>}
    >
      <div className="section-stack">
        <Field label="名称" note="用于在列表中识别这个入口 Key。">
          <TextInput value={name} autoFocus onChange={(event) => onName(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') onSubmit(); }} placeholder="例如 NEWAPI / Codex / Claude" />
        </Field>
      </div>
    </Modal>
  );
}

function UseKeyModal({ apiKey, endpoint, name, copied, onClose, onCopy }: { apiKey: string; endpoint: string; name: string; copied: string; onClose: () => void; onCopy: (text: string, message: string, id: string) => void }) {
  const base = endpoint.replace(/\/v1\/?$/, '');
  const openai = `OPENAI_API_KEY=${apiKey}\nOPENAI_BASE_URL=${endpoint}`;
  const powershell = `$env:OPENAI_API_KEY=\"${apiKey}\"\n$env:OPENAI_BASE_URL=\"${endpoint}\"`;
  const curl = `curl ${endpoint}/chat/completions \\\n  -H \"Authorization: Bearer ${apiKey}\" \\\n  -H \"Content-Type: application/json\" \\\n  -d '{\"model\":\"deepseek-v4-flash\",\"messages\":[{\"role\":\"user\",\"content\":\"ping\"}]}'`;
  const opencode = JSON.stringify({ provider: { local: { npm: '@ai-sdk/openai-compatible', name, options: { baseURL: `${base}/v1`, apiKey } } } }, null, 2);
  return (
    <Modal title="使用 API Key" onClose={onClose} footer={<Button onClick={onClose}>关闭</Button>}>
      <div className="use-key-modal">
        <div className="use-key-summary">
          <Badge tone={apiKey.startsWith('sk-') ? 'ok' : 'warn'}>{apiKey.startsWith('sk-') ? '原始 Key' : '预览 Key'}</Badge>
          <code>{apiKey || '当前记录只有预览，创建后只显示一次原始 Key。'}</code>
        </div>
        <CodeBlock title="macOS / Linux" code={openai} copied={copied === 'use-unix'} onCopy={() => onCopy(openai, '环境变量已复制。', 'use-unix')} />
        <CodeBlock title="PowerShell" code={powershell} copied={copied === 'use-ps'} onCopy={() => onCopy(powershell, 'PowerShell 配置已复制。', 'use-ps')} />
        <CodeBlock title="curl 测试" code={curl} copied={copied === 'use-curl'} onCopy={() => onCopy(curl, 'curl 示例已复制。', 'use-curl')} />
        <CodeBlock title="opencode.json" code={opencode} copied={copied === 'use-opencode'} onCopy={() => onCopy(opencode, 'opencode 配置已复制。', 'use-opencode')} />
      </div>
    </Modal>
  );
}

function CodeBlock({ title, code, copied, onCopy }: { title: string; code: string; copied: boolean; onCopy: () => void }) {
  return (
    <div className="code-block">
      <div className="code-block-head"><span>{title}</span><button type="button" className={copied ? 'copied' : ''} onClick={onCopy}>{copied ? <Check size={14} /> : <Clipboard size={14} />}{copied ? '已复制' : '复制'}</button></div>
      <pre><code>{code}</code></pre>
    </div>
  );
}

function filterKeys(keys: ProxyKey[], filter: KeyFilter) {
  const needle = filter.search.trim().toLowerCase();
  return keys.filter((key) => {
    if (filter.status === 'enabled' && key.enabled === false) return false;
    if (filter.status === 'disabled' && key.enabled !== false) return false;
    if (!needle) return true;
    const text = `${key.name || ''} ${key.preview || ''} ${key.id || ''}`.toLowerCase();
    return text.includes(needle);
  });
}

function maskKey(value: string) {
  if (!value) return '';
  if (value.length <= 16) return value;
  return `${value.slice(0, 10)}...${value.slice(-6)}`;
}
