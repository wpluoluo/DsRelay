import { useMemo, useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { Copy, Eye, KeyRound, MoreHorizontal, Plus, RefreshCw, ShieldCheck, TerminalSquare } from 'lucide-react';
import { createAdminApiKey, setAdminApiKeyEnabled } from '../api';
import { Badge, Button, Field, Modal, ModalActions, Select, TextInput } from '../components';
import { EmptyState, FilterToolbar, Pager, RowAction, RowActions, SearchField, TablePageLayout, ToolbarButtonRow } from '../components/admin';
import { queryClient } from '../state/queryClient';
import { useAccountCenter } from '../state/accountCenterContext';
import { formatNumber, maskEmpty } from '../utils';

export function AccountApiKeysPage() {
  const { selectedUserId, selectedUser, users, apiKeys, reload } = useAccountCenter();
  const [draft, setDraft] = useState<{ account_id: string; name: string } | null>(null);
  const [generatedKey, setGeneratedKey] = useState('');
  const [copiedKeyId, setCopiedKeyId] = useState('');
  const [copiedGuideValue, setCopiedGuideValue] = useState('');
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [showTools, setShowTools] = useState(false);
  const [showGuide, setShowGuide] = useState(false);
  const [inspectKey, setInspectKey] = useState<any | null>(null);
  const [toggleTarget, setToggleTarget] = useState<any | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);

  const createMutation = useMutation({
    mutationFn: createAdminApiKey,
    onSuccess: async (result) => {
      setGeneratedKey(result.generated_key || '');
      setDraft(null);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['admin-api-keys'] }),
        reload(),
      ]);
    },
  });

  const toggleMutation = useMutation({
    mutationFn: ({ keyId, enabled }: { keyId: string; enabled: boolean }) => setAdminApiKeyEnabled(keyId, enabled),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['admin-api-keys'] }),
        reload(),
      ]);
    },
  });

  const rows = useMemo(() => {
    const keyword = search.trim().toLowerCase();
    return apiKeys.filter((item) => {
      if (selectedUserId && item.account_id !== selectedUserId) return false;
      if (statusFilter && String(item.enabled !== false ? 'enabled' : 'disabled') !== statusFilter) return false;
      if (!keyword) return true;
      const hay = `${item.name || ''} ${item.key_preview || ''} ${item.active_plan_name || ''}`.toLowerCase();
      return hay.includes(keyword);
    });
  }, [apiKeys, search, selectedUserId, statusFilter]);

  const totalPages = Math.max(1, Math.ceil(rows.length / pageSize));
  const pagedRows = rows.slice((page - 1) * pageSize, page * pageSize);
  const activeRows = rows.filter((item) => item.enabled !== false);
  const coveredRows = rows.filter((item) => item.subscription_active);
  const uncoveredRows = rows.filter((item) => !item.subscription_active);

  async function copyText(value: string, keyId?: string) {
    try {
      await navigator.clipboard.writeText(value);
      if (keyId) {
        setCopiedKeyId(keyId);
        window.setTimeout(() => setCopiedKeyId(''), 1200);
      } else {
        setCopiedGuideValue(value);
        window.setTimeout(() => setCopiedGuideValue(''), 1200);
      }
    } catch {}
  }

  return (
    <section className="grid-page">
      <div className="sub2-page-head">
        <div className="sub2-page-title">
          <strong>我的 API Key</strong>
          <span>管理当前用户名下的调用 Key。这里使用用户中心语义，不再混用后台账号对象。</span>
        </div>
        <div className="sub2-inline-summary">
          <div className="sub2-inline-summary-item"><span>当前用户</span><strong>{selectedUser?.name || '未选择用户'}</strong><small>{selectedUser?.group_name || selectedUser?.source_type || '请选择用户'}</small></div>
          <div className="sub2-inline-summary-item"><span>Key 数量</span><strong>{formatNumber(rows.length)}</strong><small>启用 {formatNumber(activeRows.length)}</small></div>
          <div className="sub2-inline-summary-item"><span>订阅覆盖</span><strong>{formatNumber(coveredRows.length)}</strong><small>未覆盖 {formatNumber(uncoveredRows.length)}</small></div>
          <div className="sub2-inline-summary-item"><span>最近生成</span><strong>{generatedKey ? '已生成' : '无'}</strong><small>{generatedKey ? '原始 Key 待复制' : '暂无新 Key'}</small></div>
        </div>
      </div>

      <TablePageLayout
        filters={(
          <FilterToolbar
            right={
              <ToolbarButtonRow>
                <Button onClick={() => void reload()}><RefreshCw size={15} />刷新</Button>
                <details className="sub2-menu" open={showTools} onToggle={(event) => setShowTools((event.target as HTMLDetailsElement).open)}>
                  <summary>
                    <MoreHorizontal size={14} />
                    <span>更多工具</span>
                  </summary>
                  <div className="sub2-menu-panel">
                    <button type="button" onClick={() => { setSearch(''); setStatusFilter(''); setPage(1); setShowTools(false); }}>
                      <span>清空筛选</span>
                    </button>
                    <button type="button" onClick={() => { setShowGuide(true); setShowTools(false); }}>
                      <span>接入说明</span>
                    </button>
                  </div>
                </details>
                <Button tone="primary" onClick={() => setDraft({ account_id: selectedUserId || users[0]?.id || '', name: '' })}><Plus size={15} />生成 Key</Button>
              </ToolbarButtonRow>
            }
          >
            <SearchField value={search} placeholder="搜索 Key 名称 / 预览 / 计划" onChange={(value) => { setSearch(value); setPage(1); }} />
            <Select value={statusFilter} onChange={(event) => { setStatusFilter(event.target.value); setPage(1); }}>
              <option value="">全部状态</option>
              <option value="enabled">启用</option>
              <option value="disabled">停用</option>
            </Select>
          </FilterToolbar>
        )}
        table={(
          <div className="table-wrap table-scroll table-keys">
            <table>
              <thead>
                <tr>
                  <th>名称</th>
                  <th>账户</th>
                  <th>订阅</th>
                  <th>Key 预览</th>
                  <th>最近使用</th>
                  <th>状态</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {pagedRows.length ? pagedRows.map((item) => (
                  <tr key={item.id}>
                    <td><div className="sub2-cell-stack"><strong>{item.name}</strong><small>{item.id}</small></div></td>
                    <td><div className="sub2-cell-stack"><strong>{maskEmpty(item.account_name || item.account_id)}</strong><small>{item.account_id}</small></div></td>
                    <td><div className="sub2-cell-stack"><strong>{item.subscription_active ? (item.active_plan_name || '订阅有效') : '无可用订阅'}</strong><small>{item.active_group_name || item.active_group_id || item.active_subscription_status || '-'}</small></div></td>
                    <td>
                      <div className="key-value-cell">
                        <code>{item.key_preview}</code>
                        <button type="button" className={copiedKeyId === item.id ? 'copied' : ''} onClick={() => copyText(item.key_preview, item.id)} aria-label="复制 Key 预览">
                          <Copy size={14} />
                        </button>
                      </div>
                    </td>
                    <td><div className="sub2-cell-stack sub2-cell-stack-tight"><strong>{formatTimestamp(item.last_used_at)}</strong><small>{item.updated_at ? `更新 ${formatTimestamp(item.updated_at)}` : '暂无更新'}</small></div></td>
                    <td><Badge tone={item.enabled === false ? 'warn' : 'ok'}>{item.enabled === false ? '停用' : '启用'}</Badge></td>
                    <td>
                      <RowActions>
                        <RowAction icon={Eye} label="详情" onClick={() => setInspectKey(item)} />
                        <RowAction icon={item.enabled === false ? ShieldCheck : KeyRound} label={item.enabled === false ? '启用' : '停用'} tone={item.enabled === false ? 'default' : 'warn'} onClick={() => setToggleTarget(item)} />
                        <RowAction icon={TerminalSquare} label="接入" onClick={() => setShowGuide(true)} />
                      </RowActions>
                    </td>
                  </tr>
                )) : (
                  <tr>
                    <td colSpan={7}>
                      <EmptyState title="暂无 API Key" description="当前用户还没有可用的 API Key。" />
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
        pagination={rows.length ? (
          <Pager
            page={Math.min(page, totalPages)}
            pageSize={pageSize}
            total={rows.length}
            onPageChange={(next) => setPage(Math.min(Math.max(1, next), totalPages))}
            onPageSizeChange={(next) => { setPageSize(next); setPage(1); }}
          />
        ) : null}
      />

      {generatedKey ? (
        <Modal
          title="Key 已生成"
          size="md"
          onClose={() => setGeneratedKey('')}
          footer={
            <ModalActions>
              <Button onClick={() => setGeneratedKey('')}>关闭</Button>
              <Button onClick={() => setShowGuide(true)}>接入说明</Button>
              <Button tone="primary" onClick={() => copyText(generatedKey)}>复制 Key</Button>
            </ModalActions>
          }
        >
          <div className="admin-dialog admin-dialog-result">
            <div className="admin-dialog-intro">
              <strong>请立即保存原始 Key</strong>
              <span>该原始 Key 只展示一次。关闭后列表只保留预览值。</span>
            </div>
            <div className="admin-dialog-summary">
              <div className="admin-dialog-summary-card">
                <span>绑定用户</span>
                <strong>{selectedUser?.name || '当前用户'}</strong>
                <small>{selectedUser?.group_name || selectedUser?.source_type || '平台用户'}</small>
              </div>
              <div className="admin-dialog-summary-card">
                <span>订阅校验</span>
                <strong>已接入</strong>
                <small>请求会校验当前用户订阅</small>
              </div>
              <div className="admin-dialog-summary-card">
                <span>建议动作</span>
                <strong>立刻复制保存</strong>
                <small>关闭后不再回显原始值</small>
              </div>
            </div>
            <div className="generated-key-box generated-key-floating">
              <div className="generated-key-title">原始 Key</div>
              <div className="generated-key-row">
                <div className="generated-key-value">{generatedKey}</div>
                <Button onClick={() => copyText(generatedKey)}>复制</Button>
              </div>
            </div>
          </div>
        </Modal>
      ) : null}

      {draft ? (
        <Modal
          title="生成用户 API Key"
          size="md"
          onClose={() => setDraft(null)}
          footer={
            <ModalActions>
              <Button onClick={() => setDraft(null)}>取消</Button>
              <Button tone="primary" disabled={createMutation.isPending || !draft.account_id || !draft.name.trim()} onClick={() => createMutation.mutate(draft)}>
                生成
              </Button>
            </ModalActions>
          }
        >
            <div className="admin-dialog">
              <div className="admin-dialog-intro">
                <strong>生成当前用户 Key</strong>
                <span>生成后立即展示原始值，后续只保留预览。</span>
              </div>
            <div className="admin-dialog-grid modal-grid">
              <Field label="归属用户">
                <Select value={draft.account_id} onChange={(e) => setDraft({ ...draft, account_id: e.target.value })}>
                  <option value="">请选择用户</option>
                  {users.map((user) => <option key={user.id} value={user.id}>{user.name}</option>)}
                </Select>
              </Field>
              <Field label="Key 名称">
                <TextInput value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
              </Field>
            </div>
          </div>
        </Modal>
      ) : null}

      {showGuide ? (
        <Modal title="API Key 接入说明" size="lg" onClose={() => setShowGuide(false)} footer={<ModalActions><Button onClick={() => setShowGuide(false)}>关闭</Button></ModalActions>}>
          <div className="admin-dialog">
            <div className="admin-dialog-intro">
              <strong>OpenAI 兼容接入</strong>
              <span>设置业务 Key 和统一 Base URL，按标准 `chat/completions` 发请求。</span>
            </div>
            <div className="admin-dialog-summary">
              <div className="admin-dialog-summary-card">
                <span>当前用户</span>
                <strong>{selectedUser?.name || '未选择用户'}</strong>
                <small>{selectedUser?.group_name || selectedUser?.source_type || '平台用户'}</small>
              </div>
              <div className="admin-dialog-summary-card">
                <span>Base URL</span>
                <strong>{window.location.origin}</strong>
                <small>统一代理入口</small>
              </div>
              <div className="admin-dialog-summary-card">
                <span>展示值</span>
                <strong>{generatedKey ? '原始 Key' : '预览 Key'}</strong>
                <small>{generatedKey ? '本次生成结果' : '列表只保留预览'}</small>
              </div>
            </div>
            <div className="use-key-summary">
              <KeyRound size={16} />
              <code>{generatedKey || rows[0]?.key_preview || '先生成或选择一个 Key'}</code>
            </div>
            <div className="account-guide-note">
              推荐环境变量：`OPENAI_API_KEY` 使用当前用户 Key，`OPENAI_BASE_URL` 指向 `{window.location.origin}/v1`。
            </div>
            <CodeBlock
              title="macOS / Linux"
              code={`export OPENAI_API_KEY=YOUR_API_KEY\nexport OPENAI_BASE_URL=${window.location.origin}/v1`}
              copied={copiedGuideValue === `export OPENAI_API_KEY=YOUR_API_KEY\nexport OPENAI_BASE_URL=${window.location.origin}/v1`}
              onCopy={() => copyText(`export OPENAI_API_KEY=YOUR_API_KEY\nexport OPENAI_BASE_URL=${window.location.origin}/v1`)}
            />
            <CodeBlock
              title="PowerShell"
              code={`$env:OPENAI_API_KEY=\"YOUR_API_KEY\"\n$env:OPENAI_BASE_URL=\"${window.location.origin}/v1\"`}
              copied={copiedGuideValue === `$env:OPENAI_API_KEY=\"YOUR_API_KEY\"\n$env:OPENAI_BASE_URL=\"${window.location.origin}/v1\"`}
              onCopy={() => copyText(`$env:OPENAI_API_KEY=\"YOUR_API_KEY\"\n$env:OPENAI_BASE_URL=\"${window.location.origin}/v1\"`)}
            />
            <CodeBlock
              title="curl 测试"
              code={`curl ${window.location.origin}/v1/chat/completions \\\n  -H "Authorization: Bearer YOUR_API_KEY" \\\n  -H "Content-Type: application/json" \\\n  -d "{\\"model\\":\\"deepseek-v4-flash\\",\\"messages\\":[{\\"role\\":\\"user\\",\\"content\\":\\"hello\\"}]}"`}
              copied={copiedGuideValue === `curl ${window.location.origin}/v1/chat/completions -H "Authorization: Bearer YOUR_API_KEY"`}
              onCopy={() => copyText(`curl ${window.location.origin}/v1/chat/completions -H "Authorization: Bearer YOUR_API_KEY"`)}
            />
            <CodeBlock
              title="Base URL"
              code={`${window.location.origin}/v1`}
              copied={copiedGuideValue === `${window.location.origin}/v1`}
              onCopy={() => copyText(`${window.location.origin}/v1`)}
            />
          </div>
        </Modal>
      ) : null}

      {inspectKey ? (
        <Modal
          title="Key 详情"
          size="md"
          onClose={() => setInspectKey(null)}
          footer={<ModalActions><Button onClick={() => setInspectKey(null)}>关闭</Button></ModalActions>}
        >
          <div className="admin-dialog">
            <div className="admin-dialog-intro">
              <strong>{inspectKey.name}</strong>
              <span>这里可以直接核对当前用户 Key 的订阅覆盖和启用状态。</span>
            </div>
            <div className="admin-dialog-summary">
              <div className="admin-dialog-summary-card">
                <span>用户</span>
                <strong>{maskEmpty(inspectKey.account_name || inspectKey.account_id)}</strong>
                <small>{inspectKey.account_id}</small>
              </div>
              <div className="admin-dialog-summary-card">
                <span>订阅</span>
                <strong>{inspectKey.subscription_active ? (inspectKey.active_plan_name || '订阅有效') : '无可用订阅'}</strong>
                <small>{inspectKey.active_subscription_status || '-'}</small>
              </div>
              <div className="admin-dialog-summary-card">
                <span>状态</span>
                <strong>{inspectKey.enabled === false ? '停用' : '启用'}</strong>
                <small>{inspectKey.key_preview}</small>
              </div>
            </div>
            <div className="admin-dialog-grid">
              <Field label="分组"><TextInput readOnly value={inspectKey.active_group_name || inspectKey.active_group_id || '-'} /></Field>
              <Field label="计划"><TextInput readOnly value={inspectKey.active_plan_name || inspectKey.active_plan_id || '-'} /></Field>
              <Field label="创建时间"><TextInput readOnly value={formatTimestamp(inspectKey.created_at)} /></Field>
              <Field label="最近使用"><TextInput readOnly value={formatTimestamp(inspectKey.last_used_at)} /></Field>
            </div>
          </div>
        </Modal>
      ) : null}

      {toggleTarget ? (
        <Modal
          title={toggleTarget.enabled === false ? '确认启用 Key' : '确认停用 Key'}
          size="md"
          onClose={() => setToggleTarget(null)}
          footer={
            <ModalActions>
              <Button onClick={() => setToggleTarget(null)}>取消</Button>
              <Button
                tone={toggleTarget.enabled === false ? 'primary' : 'danger'}
                disabled={toggleMutation.isPending}
                onClick={() => toggleMutation.mutate({ keyId: toggleTarget.id, enabled: toggleTarget.enabled === false }, { onSuccess: () => setToggleTarget(null) })}
              >
                确认
              </Button>
            </ModalActions>
          }
        >
          <div className="admin-dialog">
            <div className="admin-dialog-intro">
              <strong>{toggleTarget.name}</strong>
              <span>{toggleTarget.enabled === false ? '启用后该 Key 可以继续用于业务请求。' : '停用后该 Key 将立即不能再发起新请求。'}</span>
            </div>
          </div>
        </Modal>
      ) : null}
    </section>
  );
}

function CodeBlock({ title, code, copied, onCopy }: { title: string; code: string; copied: boolean; onCopy: () => void }) {
  return (
    <div className="code-block">
      <div className="code-block-head">
        <span>{title}</span>
        <button type="button" className={copied ? 'copied' : ''} onClick={onCopy}>复制</button>
      </div>
      <pre><code>{code}</code></pre>
    </div>
  );
}

function formatTimestamp(value: number | null | undefined) {
  if (!value) return '-';
  const date = new Date(value * 1000);
  if (Number.isNaN(date.getTime())) return '-';
  return date.toLocaleString('zh-CN', { hour12: false });
}
