import { useEffect, useMemo, useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { Check, Clipboard, Copy, Edit3, Eye, KeyRound, MoreHorizontal, Plus, RefreshCw, Terminal, Trash2 } from 'lucide-react';
import { mutateProxyKey } from '../../api';
import { Badge, Button, Empty, Field, Modal, Select, TextInput } from '../../components';
import { ActionButton, EmptyState, FilterToolbar, Pager, SearchField, TablePageLayout, ToolbarButtonRow } from '../../components/admin';
import { queryClient } from '../../state/queryClient';
import type { ProxyKey, ProxyKeyPayload } from '../../types';
import { formatNumber, maskEmpty, readStorageJSON, writeStorageJSON } from '../../utils';

type KeyFilter = {
  search: string;
  status: 'all' | 'enabled' | 'disabled';
};

const STORAGE_KEY = 'proxy-keys-view-state';

export function ProxyKeys({ payload, refresh }: { payload?: ProxyKeyPayload; refresh: () => void }) {
  const savedState = readStorageJSON<{ search: string; status: KeyFilter['status']; pageSize: number }>(STORAGE_KEY, { search: '', status: 'all', pageSize: 20 });
  const [filter, setFilter] = useState<KeyFilter>({ search: savedState.search, status: savedState.status });
  const [createOpen, setCreateOpen] = useState(false);
  const [editKey, setEditKey] = useState<ProxyKey | null>(null);
  const [useKey, setUseKey] = useState<ProxyKey | null>(null);
  const [formName, setFormName] = useState('NEWAPI');
  const [generated, setGenerated] = useState('');
  const [status, setStatus] = useState('');
  const [copied, setCopied] = useState('');
  const [toggleTarget, setToggleTarget] = useState<ProxyKey | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<ProxyKey | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(savedState.pageSize || 20);
  const [showTools, setShowTools] = useState(false);

  const keys = payload?.keys || [];
  const enabledCount = payload?.managed_enabled_count ?? keys.filter((key) => key.enabled !== false).length;
  const disabledCount = Math.max(0, keys.length - enabledCount);
  const envCount = payload?.env_key_count ?? 0;
  const endpoint = `${window.location.origin.replace(/\/+$/, '')}/v1`;
  const filteredKeys = useMemo(() => filterKeys(keys, filter), [keys, filter]);
  const totalPages = Math.max(1, Math.ceil(filteredKeys.length / pageSize));
  const pagedKeys = useMemo(() => {
    const start = (page - 1) * pageSize;
    return filteredKeys.slice(start, start + pageSize);
  }, [filteredKeys, page, pageSize]);

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

  useEffect(() => {
    writeStorageJSON(STORAGE_KEY, { search: filter.search, status: filter.status, pageSize });
  }, [filter.search, filter.status, pageSize]);

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
    setGenerated('');
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

      <TablePageLayout
        actions={<EndpointStrip endpoint={endpoint} copied={copied} onCopy={copyText} />}
        filters={
          <FilterToolbar
            right={
              <ToolbarButtonRow>
                <ActionButton onClick={refresh} disabled={mutation.isPending}><RefreshCw size={15} />刷新</ActionButton>
                <details className="sub2-menu" open={showTools} onToggle={(event) => setShowTools((event.target as HTMLDetailsElement).open)}>
                  <summary>
                    <MoreHorizontal size={14} />
                    <span>更多工具</span>
                  </summary>
                  <div className="sub2-menu-panel">
                    <button type="button" onClick={() => { setFilter({ search: '', status: 'all' }); setPage(1); setShowTools(false); }}>
                      <span>清空筛选</span>
                    </button>
                    <button type="button" onClick={() => { setPageSize(50); setPage(1); setShowTools(false); }}>
                      <span>切换 50 / 页</span>
                    </button>
                    <button type="button" onClick={() => { setUseKey(null); setGenerated(''); setShowTools(false); }}>
                      <span>收起使用面板</span>
                    </button>
                  </div>
                </details>
                <Button tone="primary" onClick={openCreate}><Plus size={15} />创建 API Key</Button>
              </ToolbarButtonRow>
            }
          >
            <SearchField
              value={filter.search}
              placeholder="搜索名称、预览、ID"
              onChange={(value) => { setFilter((current) => ({ ...current, search: value })); setPage(1); }}
            />
            <Select
              value={filter.status}
              onChange={(event) => { setFilter((current) => ({ ...current, status: event.target.value as KeyFilter['status'] })); setPage(1); }}
            >
              <option value="all">全部状态</option>
              <option value="enabled">启用中</option>
              <option value="disabled">已停用</option>
            </Select>
          </FilterToolbar>
        }
        table={
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
                {pagedKeys.length ? pagedKeys.map((key) => (
                  <tr key={key.id || key.preview}>
                    <td>
                      <div className="sub2-cell-stack">
                        <strong>{key.name || 'NEWAPI'}</strong>
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
                    <td><div className="sub2-cell-stack sub2-cell-stack-tight"><strong>{key.created_at || '-'}</strong><small>创建时间</small></div></td>
                    <td><div className="sub2-cell-stack sub2-cell-stack-tight"><strong>{key.updated_at || '-'}</strong><small>最近变更</small></div></td>
                    <td>
                      <div className="key-table-actions">
                        <button type="button" onClick={() => setUseKey(key)} title="使用方式"><Terminal size={15} /><span>使用</span></button>
                        <button type="button" onClick={() => openEdit(key)} title="编辑名称"><Edit3 size={15} /><span>编辑</span></button>
                        <button type="button" onClick={() => setToggleTarget(key)} title={key.enabled === false ? '启用' : '停用'}><Eye size={15} /><span>{key.enabled === false ? '启用' : '停用'}</span></button>
                        <button type="button" className="danger" onClick={() => setDeleteTarget(key)} title="删除"><Trash2 size={15} /><span>删除</span></button>
                      </div>
                    </td>
                  </tr>
                )) : <tr><td colSpan={6}><EmptyState title="暂无 API Key" description="当前没有可展示的入口 Key，先创建一个。" action={<Button tone="primary" onClick={openCreate}>创建 API Key</Button>} /></td></tr>}
              </tbody>
            </table>
          </div>
        }
        pagination={
          filteredKeys.length ? (
            <Pager
              page={Math.min(page, totalPages)}
              pageSize={pageSize}
              total={filteredKeys.length}
              onPageChange={(next) => setPage(Math.min(Math.max(1, next), totalPages))}
              onPageSizeChange={(next) => { setPageSize(next); setPage(1); }}
            />
          ) : null
        }
      />

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

      {useKey ? <UseKeyModal apiKey={(useKey as any).key || useKey.preview || ''} endpoint={endpoint} name={useKey.name || 'NEWAPI'} onClose={() => setUseKey(null)} onCopy={copyText} copied={copied} /> : null}

      {toggleTarget ? (
        <Modal
          title={toggleTarget.enabled === false ? '确认启用入口 Key' : '确认停用入口 Key'}
          onClose={() => setToggleTarget(null)}
          footer={<><Button onClick={() => setToggleTarget(null)}>取消</Button><Button tone={toggleTarget.enabled === false ? 'primary' : 'danger'} disabled={mutation.isPending} onClick={() => mutation.mutate({ action: 'update', id: toggleTarget.id, enabled: toggleTarget.enabled === false }, { onSuccess: () => setToggleTarget(null) })}>确认</Button></>}
        >
          <div className="section-stack">
            <p className="subtle">{toggleTarget.enabled === false ? '启用后该入口 Key 会重新参与入口鉴权。' : '停用后该入口 Key 立即失效，但记录仍保留。'}</p>
            <code>{toggleTarget.name || 'NEWAPI'}</code>
          </div>
        </Modal>
      ) : null}

      {deleteTarget ? (
        <Modal
          title="确认删除入口 Key"
          onClose={() => setDeleteTarget(null)}
          footer={<><Button onClick={() => setDeleteTarget(null)}>取消</Button><Button tone="danger" disabled={mutation.isPending} onClick={() => mutation.mutate({ action: 'delete', id: deleteTarget.id }, { onSuccess: () => setDeleteTarget(null) })}>确认删除</Button></>}
        >
          <div className="section-stack">
            <p className="subtle">删除后该入口 Key 将从当前托管列表移除。</p>
            <code>{deleteTarget.name || 'NEWAPI'}</code>
          </div>
        </Modal>
      ) : null}
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
