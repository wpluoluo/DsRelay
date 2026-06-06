import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { KeyRound } from 'lucide-react';
import { mutateProxyKey } from '../../api';
import { Button, TextInput } from '../../components';
import { queryClient } from '../../state/queryClient';
import type { ProxyKeyPayload } from '../../types';

export function ProxyKeys({ payload, refresh }: { payload?: ProxyKeyPayload; refresh: () => void }) {
  const [name, setName] = useState('NEWAPI');
  const [generated, setGenerated] = useState('');
  const mutation = useMutation({
    mutationFn: mutateProxyKey,
    onSuccess: (data) => {
      setGenerated(data.generated_key || '');
      queryClient.invalidateQueries({ queryKey: ['proxy-keys'] });
      refresh();
    },
  });
  return (
    <div className="section-stack">
      <div className="inline-form">
        <TextInput value={name} onChange={(e) => setName(e.target.value)} />
        <Button tone="primary" onClick={() => mutation.mutate({ action: 'create', name })}><KeyRound size={14} />生成</Button>
      </div>
      {generated ? <div className="copy-box"><code>{generated}</code><Button onClick={() => navigator.clipboard?.writeText(generated)}>复制</Button></div> : null}
      {(payload?.keys || []).map((key) => (
        <div className="key-row" key={key.id}>
          <div><strong>{key.name || 'NEWAPI'}</strong><small>{key.preview || '-'}</small></div>
          <div className="button-row">
            <Button onClick={() => mutation.mutate({ action: 'update', id: key.id, enabled: !key.enabled })}>{key.enabled === false ? '启用' : '停用'}</Button>
            <Button tone="danger" onClick={() => mutation.mutate({ action: 'delete', id: key.id })}>删除</Button>
          </div>
        </div>
      ))}
    </div>
  );
}
