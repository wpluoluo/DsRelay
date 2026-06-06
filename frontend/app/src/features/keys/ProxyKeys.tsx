import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { Copy, Edit3, KeyRound, Plus, Trash2 } from 'lucide-react';
import { mutateProxyKey } from '../../api';
import { Badge, Button, Empty, TextInput } from '../../components';
import { queryClient } from '../../state/queryClient';
import type { ProxyKey, ProxyKeyPayload } from '../../types';

export function ProxyKeys({ payload, refresh }: { payload?: ProxyKeyPayload; refresh: () => void }) {
  const [name, setName] = useState('NEWAPI');
  const [generated, setGenerated] = useState('');
  const [status, setStatus] = useState('');
  const [renamingId, setRenamingId] = useState('');
  const [renameValue, setRenameValue] = useState('');
  const mutation = useMutation({
    mutationFn: mutateProxyKey,
    onSuccess: (data) => {
      if (data.generated_key) setGenerated(data.generated_key);
      queryClient.invalidateQueries({ queryKey: ['proxy-keys'] });
      refresh();
      setStatus('入口 Key 操作已生效。');
      setRenamingId('');
    },
    onError: (error) => setStatus(error instanceof Error ? error.message : '入口 Key 操作失败'),
  });
  const keys = payload?.keys || [];
  const managedCount = keys.length;
  const enabledCount = payload?.managed_enabled_count ?? keys.filter((key) => key.enabled !== false).length;
  const envCount = payload?.env_key_count ?? 0;

  async function copyText(text: string, message: string) {
    if (!text) return;
    await navigator.clipboard?.writeText(text);
    setStatus(message);
  }

  function startRename(key: ProxyKey) {
    setRenamingId(key.id || '');
    setRenameValue(key.name || 'NEWAPI');
  }

  function submitRename(key: ProxyKey) {
    const nextName = renameValue.trim() || 'NEWAPI';
    mutation.mutate({ action: 'update', id: key.id, name: nextName });
  }

  return (
    <div className="key-manager">
      <div className="key-summary">
        <Badge>托管 {managedCount}</Badge>
        <Badge tone={enabledCount ? 'ok' : 'warn'}>启用 {enabledCount}</Badge>
        <Badge>环境变量 {envCount}</Badge>
      </div>
      <div className="inline-form">
        <TextInput value={name} onChange={(e) => setName(e.target.value)} placeholder="Key 名称，例如 NEWAPI" />
        <Button tone="primary" disabled={mutation.isPending} onClick={() => mutation.mutate({ action: 'create', name })}><Plus size={14} />生成入口 Key</Button>
      </div>
      {generated ? (
        <div className="generated-key-box">
          <div className="generated-key-title">新 Key 只显示一次</div>
          <div className="generated-key-row">
            <code className="generated-key-value">{generated}</code>
            <Button onClick={() => copyText(generated, '新 Key 已复制。')}><Copy size={14} />复制</Button>
          </div>
        </div>
      ) : null}
      <div className="key-list">
        {keys.length ? keys.map((key) => (
          <div className="key-card" key={key.id}>
            <div className="key-card-head">
              <div className="key-main">
                {renamingId === key.id ? (
                  <div className="key-rename-row">
                    <TextInput value={renameValue} onChange={(event) => setRenameValue(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') submitRename(key); if (event.key === 'Escape') setRenamingId(''); }} />
                    <Button disabled={mutation.isPending} onClick={() => submitRename(key)}>保存</Button>
                    <Button onClick={() => setRenamingId('')}>取消</Button>
                  </div>
                ) : <div className="key-name"><KeyRound size={14} />{key.name || 'NEWAPI'}</div>}
                <div className="key-meta">
                  <span className={`pool-badge ${key.enabled === false ? 'off' : 'ok'}`}>{key.enabled === false ? '已停用' : '启用中'}</span>
                  <span>创建 {key.created_at || '-'}</span>
                  <span>更新 {key.updated_at || '-'}</span>
                </div>
              </div>
              <div className="key-actions">
                <Button onClick={() => copyText(String((key as any).key || key.preview || ''), 'Key 预览已复制。')}><Copy size={14} />复制预览</Button>
                <Button onClick={() => startRename(key)}><Edit3 size={14} />改名</Button>
                <Button disabled={mutation.isPending} onClick={() => mutation.mutate({ action: 'update', id: key.id, enabled: key.enabled === false })}>{key.enabled === false ? '启用' : '停用'}</Button>
                <Button tone="danger" disabled={mutation.isPending} onClick={() => { if (confirm(`确认删除入口 Key「${key.name || 'NEWAPI'}」？`)) mutation.mutate({ action: 'delete', id: key.id }); }}><Trash2 size={14} />删除</Button>
              </div>
            </div>
            <div className="key-preview"><span className="key-preview-value">{(key as any).key || key.preview || '无预览'}</span></div>
          </div>
        )) : <Empty>暂无托管入口 Key。生成一个后，把明文填到 NEWAPI 渠道的请求头里。</Empty>}
      </div>
      {status ? <div className={mutation.isError ? 'status-msg err' : 'status-msg'}>{status}</div> : null}
    </div>
  );
}
