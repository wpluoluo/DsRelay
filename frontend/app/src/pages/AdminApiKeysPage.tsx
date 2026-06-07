import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Copy, Eye, Plus, RefreshCw, ShieldCheck } from 'lucide-react';
import { createAdminApiKey, fetchAdminApiKeys, fetchAdminUsers, setAdminApiKeyEnabled } from '../api';
import { Badge, Button, Field, Modal, ModalActions, Select, TextInput } from '../components';
import { ActionButton, FilterToolbar, ListEmptyRow, Pager, RowAction, RowActions, SearchField, TablePageLayout, ToolbarButtonRow, ToolsMenu } from '../components/admin';
import { queryClient } from '../state/queryClient';
import type { AdminApiKey } from '../types';
import { cn, formatNumber, maskEmpty, readStorageJSON, writeStorageJSON } from '../utils';

const STORAGE_KEY = 'admin-api-keys-view-state';

export function AdminApiKeysPage() {
  const keysQuery = useQuery({ queryKey: ['admin-api-keys'], queryFn: fetchAdminApiKeys, refetchInterval: 10000 });
  const usersQuery = useQuery({ queryKey: ['admin-users'], queryFn: fetchAdminUsers, refetchInterval: 10000 });
  const [draft, setDraft] = useState<{ user_id: string; name: string } | null>(null);
  const [generatedKey, setGeneratedKey] = useState('');
  const [copiedKeyId, setCopiedKeyId] = useState('');
  const [inspectKey, setInspectKey] = useState<AdminApiKey | null>(null);
  const savedState = readStorageJSON(STORAGE_KEY, {
    search: '',
    statusFilter: '',
    subscriptionFilter: '',
    pageSize: 20,
  });
  const [search, setSearch] = useState(savedState.search);
  const [statusFilter, setStatusFilter] = useState(savedState.statusFilter);
  const [subscriptionFilter, setSubscriptionFilter] = useState(savedState.subscriptionFilter || '');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(savedState.pageSize || 20);

  const createMutation = useMutation({
    mutationFn: createAdminApiKey,
    onSuccess: async (result) => {
      setGeneratedKey(result.generated_key || '');
      setDraft(null);
      await queryClient.invalidateQueries({ queryKey: ['admin-api-keys'] });
    },
  });

  const toggleMutation = useMutation({
    mutationFn: ({ keyId, enabled }: { keyId: string; enabled: boolean }) => setAdminApiKeyEnabled(keyId, enabled),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['admin-api-keys'] });
    },
  });

  const items = keysQuery.data?.items || [];
  const users = usersQuery.data?.items || [];

  const filteredItems = useMemo(() => {
    const keyword = search.trim().toLowerCase();
    return items.filter((item) => {
      if (keyword) {
        const haystack = [item.name, item.user_name, item.user_id, item.key_preview].map((value) => String(value || '').toLowerCase()).join(' ');
        if (!haystack.includes(keyword)) return false;
      }
      if (statusFilter) {
        const enabledValue = statusFilter === 'enabled';
        if ((item.enabled !== false) !== enabledValue) return false;
      }
      if (subscriptionFilter === 'active' && !item.subscription_active) return false;
      if (subscriptionFilter === 'inactive' && item.subscription_active) return false;
      return true;
    });
  }, [items, search, statusFilter, subscriptionFilter]);

  const totalPages = Math.max(1, Math.ceil(filteredItems.length / pageSize));
  const pagedItems = useMemo(() => {
    const start = (page - 1) * pageSize;
    return filteredItems.slice(start, start + pageSize);
  }, [filteredItems, page, pageSize]);
  const enabledCount = items.filter((item) => item.enabled !== false).length;
  const disabledCount = Math.max(0, items.length - enabledCount);
  const boundUsers = new Set(items.map((item) => item.user_id).filter(Boolean)).size;
  const unboundCount = Math.max(0, items.length - boundUsers);
  const activeSubscriptionCount = items.filter((item) => item.subscription_active).length;
  const inactiveSubscriptionCount = Math.max(0, items.length - activeSubscriptionCount);

  async function copyText(value: string, keyId?: string) {
    try {
      await navigator.clipboard.writeText(value);
      if (keyId) {
        setCopiedKeyId(keyId);
        window.setTimeout(() => setCopiedKeyId(''), 1200);
      }
    } catch {}
  }

  useEffect(() => {
    writeStorageJSON(STORAGE_KEY, { search, statusFilter, subscriptionFilter, pageSize });
  }, [pageSize, search, statusFilter, subscriptionFilter]);

  return (
    <section className="grid-page">
      <div className="sub2-page-head">
        <div className="sub2-page-title">
          <strong>用户 API Key</strong>
          <span>按用户维护业务 Key、订阅归属和启停状态，保持和 SUB2 一致的列表工作流。</span>
        </div>
        <div className="sub2-inline-summary">
          <div className="sub2-inline-summary-item"><span>业务 Key 总数</span><strong>{formatNumber(items.length)}</strong><small>当前列表全量</small></div>
          <div className="sub2-inline-summary-item"><span>启用 Key</span><strong>{formatNumber(enabledCount)}</strong><small>停用 {formatNumber(disabledCount)}</small></div>
          <div className="sub2-inline-summary-item"><span>绑定用户</span><strong>{formatNumber(boundUsers)}</strong><small>未覆盖 {formatNumber(unboundCount)} 个 Key</small></div>
          <div className="sub2-inline-summary-item"><span>有效订阅</span><strong>{formatNumber(activeSubscriptionCount)}</strong><small>无效 {formatNumber(inactiveSubscriptionCount)}</small></div>
        </div>
      </div>

      <TablePageLayout
        filters={
          <FilterToolbar
            right={
              <ToolbarButtonRow>
                <ActionButton onClick={() => keysQuery.refetch()}><RefreshCw size={15} />刷新</ActionButton>
                <ToolsMenu>
                    <button type="button" onClick={() => { setSearch(''); setStatusFilter(''); setSubscriptionFilter(''); setPage(1); }}>
                      <span>清空筛选</span>
                    </button>
                    <button type="button" onClick={() => { setSubscriptionFilter('active'); setPage(1); }}>
                      <span>仅看有效订阅</span>
                    </button>
                    <button type="button" onClick={() => { setPageSize(50); setPage(1); }}>
                      <span>切换 50 / 页</span>
                    </button>
                    <button type="button" onClick={() => { void keysQuery.refetch(); void usersQuery.refetch(); }}>
                      <span>同步用户与 Key</span>
                    </button>
                </ToolsMenu>
                <Button tone="primary" onClick={() => setDraft({ user_id: '', name: '' })}><Plus size={15} />生成 Key</Button>
              </ToolbarButtonRow>
            }
          >
            <SearchField value={search} placeholder="搜索名称 / 用户 / Key 预览" onChange={(value) => { setSearch(value); setPage(1); }} />
            <Select value={statusFilter} onChange={(event) => { setStatusFilter(event.target.value); setPage(1); }}>
              <option value="">全部状态</option>
              <option value="enabled">启用</option>
              <option value="disabled">停用</option>
            </Select>
            <Select value={subscriptionFilter} onChange={(event) => { setSubscriptionFilter(event.target.value); setPage(1); }}>
              <option value="">全部订阅</option>
              <option value="active">订阅有效</option>
              <option value="inactive">无可用订阅</option>
            </Select>
          </FilterToolbar>
        }
        table={
          <div className="table-wrap table-scroll table-keys">
            <table>
              <thead>
                <tr>
                  <th className="col-key-name">名称</th>
                  <th>用户</th>
                  <th>订阅</th>
                  <th className="col-key-value">Key 预览</th>
                  <th className="col-key-status">状态</th>
                  <th className="col-key-created">创建时间</th>
                  <th className="col-key-updated">更新时间</th>
                  <th className="col-key-actions">操作</th>
                </tr>
              </thead>
              <tbody>
                {pagedItems.length ? pagedItems.map((item) => (
                  <tr key={item.id}>
                    <td>
                      <div className="sub2-cell-stack">
                        <strong>{item.name}</strong>
                        <small>{item.id}</small>
                      </div>
                    </td>
                    <td>
                      <div className="sub2-cell-stack">
                        <strong>{maskEmpty(item.user_name || item.user_id)}</strong>
                        <small>{item.user_id || '未绑定用户 ID'}</small>
                      </div>
                    </td>
                    <td>
                      <div className="sub2-cell-stack sub2-cell-stack-tight">
                        <strong>{item.subscription_active ? (item.active_plan_name || '订阅有效') : '无可用订阅'}</strong>
                        <small>
                          {item.subscription_active
                            ? `${item.active_group_name || item.active_group_id || '未分组'} · ${item.active_subscription_status || 'active'}`
                            : (item.active_subscription_status || 'inactive')}
                        </small>
                      </div>
                    </td>
                    <td>
                      <div className="key-value-cell">
                        <code>{item.key_preview}</code>
                        <button type="button" className={copiedKeyId === item.id ? 'copied' : ''} onClick={() => copyText(item.key_preview, item.id)} aria-label="复制 Key 预览">
                          <Copy size={14} />
                        </button>
                      </div>
                    </td>
                    <td><Badge tone={item.enabled === false ? 'warn' : 'ok'}>{item.enabled === false ? '停用' : '启用'}</Badge></td>
                    <td>
                      <div className="sub2-cell-stack sub2-cell-stack-tight">
                        <strong>{formatTimestamp(item.created_at)}</strong>
                        <small>创建时间</small>
                      </div>
                    </td>
                    <td>
                      <div className="sub2-cell-stack sub2-cell-stack-tight">
                        <strong>{formatTimestamp(item.updated_at)}</strong>
                        <small>最近变更</small>
                      </div>
                    </td>
                    <td>
                      <RowActions>
                        <RowAction icon={Eye} label="详情" onClick={() => setInspectKey(item)} />
                        <RowAction
                          icon={ShieldCheck}
                          label={item.enabled === false ? '启用' : '停用'}
                          tone={item.enabled === false ? 'default' : 'warn'}
                          onClick={() => toggleMutation.mutate({ keyId: item.id, enabled: item.enabled === false })}
                        />
                      </RowActions>
                    </td>
                  </tr>
                )) : (
                  <ListEmptyRow
                    colSpan={8}
                    title="暂无业务 API Key"
                    description="当前还没有创建任何用户业务 Key。"
                    action={<Button tone="primary" onClick={() => setDraft({ user_id: '', name: '' })}>生成 Key</Button>}
                  />
                )}
              </tbody>
            </table>
          </div>
        }
        pagination={
          filteredItems.length ? (
            <Pager
              page={Math.min(page, totalPages)}
              pageSize={pageSize}
              total={filteredItems.length}
              onPageChange={(next) => setPage(Math.min(Math.max(1, next), totalPages))}
              onPageSizeChange={(next) => { setPageSize(next); setPage(1); }}
            />
          ) : null
        }
      />

      {generatedKey ? (
        <Modal
          title="Key 已生成"
          size="md"
          onClose={() => setGeneratedKey('')}
          footer={
            <ModalActions>
              <Button onClick={() => setGeneratedKey('')}>关闭</Button>
              <Button tone="primary" onClick={() => copyText(generatedKey)}>复制 Key</Button>
            </ModalActions>
          }
        >
          <div className="admin-dialog admin-dialog-result">
            <div className="admin-dialog-intro">
              <strong>请立即保存原始 Key</strong>
              <span>原始 Key 只展示这一次。关闭后列表里只保留预览值，不再回显完整内容。</span>
            </div>
            <div className="admin-dialog-summary">
              <div className="admin-dialog-summary-card">
                <span>展示方式</span>
                <strong>仅本次可见</strong>
                <small>关闭后不再回显</small>
              </div>
              <div className="admin-dialog-summary-card">
                <span>绑定能力</span>
                <strong>业务用户调用</strong>
                <small>参与订阅校验</small>
              </div>
              <div className="admin-dialog-summary-card">
                <span>建议动作</span>
                <strong>立刻复制保存</strong>
                <small>避免原始值丢失</small>
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
              <Button tone="primary" disabled={createMutation.isPending || !draft.user_id || !draft.name.trim()} onClick={() => createMutation.mutate(draft)}>
                生成
              </Button>
            </ModalActions>
          }
        >
          <div className="admin-dialog">
            <div className="admin-dialog-intro">
              <strong>为指定用户生成新的业务 Key</strong>
              <span>生成后会直接建立用户归属，后续请求会按这个 Key 做订阅可用性校验和消费归因。</span>
            </div>
            <div className="admin-dialog-summary">
              <div className="admin-dialog-summary-card">
                <span>业务 Key</span>
                <strong>{formatNumber(items.length)}</strong>
                <small>当前列表全量</small>
              </div>
              <div className="admin-dialog-summary-card">
                <span>有效订阅</span>
                <strong>{formatNumber(activeSubscriptionCount)}</strong>
                <small>已绑定 Key 覆盖</small>
              </div>
              <div className="admin-dialog-summary-card">
                <span>当前草稿</span>
                <strong>{draft.user_id ? '已选用户' : '待选用户'}</strong>
                <small>{draft.name?.trim() || '待填写名称'}</small>
              </div>
            </div>
            <div className="admin-dialog-section">
              <div className="admin-dialog-section-head">
                <strong>基础信息</strong>
                <span>先归属用户，再命名，再生成</span>
              </div>
              <div className="admin-dialog-grid modal-grid">
                <Field label="归属用户">
                  <Select value={draft.user_id} onChange={(e) => setDraft({ ...draft, user_id: e.target.value })}>
                    <option value="">请选择用户</option>
                    {users.map((user) => <option key={user.id} value={user.id}>{user.name}</option>)}
                  </Select>
                </Field>
                <Field label="Key 名称">
                  <TextInput value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
                </Field>
              </div>
            </div>
            <div className="admin-dialog-note">
              原始 Key 只会在生成成功后展示一次，建议在关闭前直接复制保存。
            </div>
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
              <span>查看业务 Key 的用户归属、订阅覆盖和时间信息，方便快速核验问题。</span>
            </div>
            <div className="admin-dialog-summary">
              <div className="admin-dialog-summary-card">
                <span>用户</span>
                <strong>{maskEmpty(inspectKey.user_name || inspectKey.user_id)}</strong>
                <small>{inspectKey.user_source_type || 'unknown'}</small>
              </div>
              <div className="admin-dialog-summary-card">
                <span>订阅</span>
                <strong>{inspectKey.subscription_active ? (inspectKey.active_plan_name || '订阅有效') : '无可用订阅'}</strong>
                <small>{inspectKey.active_group_name || inspectKey.active_group_id || '未分组'}</small>
              </div>
              <div className="admin-dialog-summary-card">
                <span>状态</span>
                <strong>{inspectKey.enabled === false ? '停用' : '启用'}</strong>
                <small>{inspectKey.key_preview}</small>
              </div>
            </div>
            <div className="admin-dialog-section">
              <div className="admin-dialog-section-head">
                <strong>归属信息</strong>
                <span>用户与订阅关系</span>
              </div>
              <div className="admin-dialog-grid">
                <Field label="用户 ID"><TextInput value={inspectKey.user_id || ''} readOnly /></Field>
                <Field label="用户名称"><TextInput value={inspectKey.user_name || ''} readOnly /></Field>
                <Field label="计划"><TextInput value={inspectKey.active_plan_name || inspectKey.active_plan_id || ''} readOnly /></Field>
                <Field label="分组"><TextInput value={inspectKey.active_group_name || inspectKey.active_group_id || ''} readOnly /></Field>
              </div>
            </div>
            <div className="admin-dialog-section">
              <div className="admin-dialog-section-head">
                <strong>时间信息</strong>
                <span>创建、更新与最近使用</span>
              </div>
              <div className="admin-dialog-grid">
                <Field label="创建时间"><TextInput value={formatTimestamp(inspectKey.created_at)} readOnly /></Field>
                <Field label="更新时间"><TextInput value={formatTimestamp(inspectKey.updated_at)} readOnly /></Field>
                <Field label="最近使用"><TextInput value={formatTimestamp(inspectKey.last_used_at)} readOnly /></Field>
                <Field label="订阅到期"><TextInput value={formatMaybeExpiry(inspectKey.active_subscription_expires_at)} readOnly /></Field>
              </div>
            </div>
          </div>
        </Modal>
      ) : null}
    </section>
  );
}

function formatTimestamp(value: number | null | undefined) {
  if (!value) return '-';
  const date = new Date(value * 1000);
  if (Number.isNaN(date.getTime())) return '-';
  return date.toLocaleString('zh-CN', { hour12: false });
}

function formatMaybeExpiry(value: number | string | null | undefined) {
  if (!value) return '-';
  if (typeof value === 'number') return formatTimestamp(value);
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString('zh-CN', { hour12: false });
}
