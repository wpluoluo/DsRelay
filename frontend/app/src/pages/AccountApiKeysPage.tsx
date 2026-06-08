import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Copy, Edit, Eye, KeyRound, Plus, RefreshCw, ShieldCheck, Trash2 } from 'lucide-react';
import { createAdminApiKey, deleteAdminApiKey, fetchAdminUsage, setAdminApiKeyEnabled, updateAdminApiKey } from '../api';
import { Badge, Button, Field, Modal, ModalActions, Select, TextInput } from '../components';
import {
  ColumnMenu,
  EmptyState,
  FilterToolbar,
  Pager,
  RowAction,
  RowActions,
  SearchField,
  TablePageLayout,
  ToolbarButtonRow,
  ToolsMenu,
} from '../components/admin';
import { queryClient } from '../state/queryClient';
import { useAccountCenter } from '../state/accountCenterContext';
import type { AdminApiKey } from '../types';
import { buildBusinessUserPayload, copyTextToClipboard, formatNumber, formatTokenCount, formatUsdCost, getBusinessUserId, getBusinessUserName, maskEmpty, readStorageJSON, writeStorageJSON } from '../utils';

type KeyDraft = {
  id?: string;
  user_id: string;
  name: string;
  enabled: boolean;
};

type StatusFilter = '' | 'enabled' | 'disabled';
type SubscriptionFilter = '' | 'active' | 'inactive';
type ColumnKey = 'owner' | 'subscription' | 'preview' | 'usage' | 'lastUsed' | 'status';

const DEFAULT_VISIBLE_COLUMNS: ColumnKey[] = ['owner', 'subscription', 'preview', 'usage', 'lastUsed', 'status'];
const STORAGE_KEY = 'account-api-keys-view-state';

export function AccountApiKeysPage() {
  const { selectedUserId, selectedUser, users, apiKeys, reload } = useAccountCenter();
  const usageQuery = useQuery({ queryKey: ['admin-usage'], queryFn: () => fetchAdminUsage(), refetchInterval: 10000 });
  const savedState = readStorageJSON(STORAGE_KEY, {
    search: '',
    statusFilter: '' as StatusFilter,
    subscriptionFilter: '' as SubscriptionFilter,
    pageSize: 20,
    visibleColumns: DEFAULT_VISIBLE_COLUMNS,
  });

  const [draft, setDraft] = useState<KeyDraft | null>(null);
  const [generatedKey, setGeneratedKey] = useState('');
  const [copiedKeyId, setCopiedKeyId] = useState('');
  const [search, setSearch] = useState(savedState.search);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>(savedState.statusFilter || '');
  const [subscriptionFilter, setSubscriptionFilter] = useState<SubscriptionFilter>(savedState.subscriptionFilter || '');
  const [inspectKey, setInspectKey] = useState<AdminApiKey | null>(null);
  const [toggleTarget, setToggleTarget] = useState<AdminApiKey | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<AdminApiKey | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(savedState.pageSize || 20);
  const [visibleColumns, setVisibleColumns] = useState<Set<ColumnKey>>(new Set(savedState.visibleColumns || DEFAULT_VISIBLE_COLUMNS));

  const createMutation = useMutation({
    mutationFn: createAdminApiKey,
    onSuccess: async (result) => {
      setGeneratedKey(result.generated_key || '');
      setDraft(null);
      await refreshKeyData();
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ keyId, payload }: { keyId: string; payload: Record<string, unknown> }) => updateAdminApiKey(keyId, payload),
    onSuccess: async () => {
      setDraft(null);
      await refreshKeyData();
    },
  });

  const toggleMutation = useMutation({
    mutationFn: ({ keyId, enabled }: { keyId: string; enabled: boolean }) => setAdminApiKeyEnabled(keyId, enabled),
    onSuccess: async () => {
      setToggleTarget(null);
      await refreshKeyData();
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (keyId: string) => deleteAdminApiKey(keyId),
    onSuccess: async () => {
      setDeleteTarget(null);
      await refreshKeyData();
    },
  });

  const rows = useMemo(() => {
    const keyword = search.trim().toLowerCase();
    return apiKeys.filter((item) => {
      if (selectedUserId && getBusinessUserId(item) !== selectedUserId) return false;
      if (statusFilter) {
        const enabledValue = statusFilter === 'enabled';
        if ((item.enabled !== false) !== enabledValue) return false;
      }
      if (subscriptionFilter === 'active' && !item.subscription_active) return false;
      if (subscriptionFilter === 'inactive' && item.subscription_active) return false;
      if (!keyword) return true;
      const hay = [
        item.name,
        getBusinessUserName(item),
        getBusinessUserId(item),
        item.key_preview,
        item.active_plan_name,
        item.active_group_name,
      ]
        .map((value) => String(value || '').toLowerCase())
        .join(' ');
      return hay.includes(keyword);
    });
  }, [apiKeys, search, selectedUserId, statusFilter, subscriptionFilter]);

  const totalPages = Math.max(1, Math.ceil(rows.length / pageSize));
  const pagedRows = rows.slice((page - 1) * pageSize, page * pageSize);
  const activeRows = rows.filter((item) => item.enabled !== false);
  const coveredRows = rows.filter((item) => item.subscription_active);
  const uncoveredRows = rows.filter((item) => !item.subscription_active);
  const selectedUserKeys = selectedUserId ? apiKeys.filter((item) => getBusinessUserId(item) === selectedUserId).length : apiKeys.length;
  const usageByKey = useMemo(() => {
    const usage = new Map<string, { requests: number; tokens: number; cost: number; last_used_at: string }>();
    for (const item of usageQuery.data?.items || []) {
      const keyId = String(item.api_key_id || '').trim();
      if (!keyId) continue;
      if (selectedUserId && item.consumer_id !== selectedUserId) continue;
      const current = usage.get(keyId) || { requests: 0, tokens: 0, cost: 0, last_used_at: '' };
      current.requests += 1;
      current.tokens += Number(item.total_tokens || 0) || Number(item.prompt_tokens || 0) + Number(item.completion_tokens || 0);
      current.cost += Number(item.actual_cost || 0) || Number(item.total_cost || 0) || 0;
      if (!current.last_used_at || String(item.started_at || '') > current.last_used_at) {
        current.last_used_at = String(item.started_at || '');
      }
      usage.set(keyId, current);
    }
    return usage;
  }, [selectedUserId, usageQuery.data?.items]);

  useEffect(() => {
    writeStorageJSON(STORAGE_KEY, {
      search,
      statusFilter,
      subscriptionFilter,
      pageSize,
      visibleColumns: Array.from(visibleColumns),
    });
  }, [pageSize, search, statusFilter, subscriptionFilter, visibleColumns]);

  function openCreate() {
    setDraft({ user_id: selectedUserId || users[0]?.id || '', name: '', enabled: true });
  }

  function openEdit(item: AdminApiKey) {
    setDraft({
      id: item.id,
      user_id: getBusinessUserId(item) || selectedUserId || '',
      name: item.name || '',
      enabled: item.enabled !== false,
    });
  }

  function submitDraft() {
    if (!draft) return;
    const payload = buildBusinessUserPayload(draft.user_id, { name: draft.name, enabled: draft.enabled });
    if (draft.id) {
      updateMutation.mutate({ keyId: draft.id, payload });
      return;
    }
    createMutation.mutate(payload);
  }

  function toggleColumn(key: ColumnKey) {
    setVisibleColumns((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  async function refreshKeyData() {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['admin-api-keys'] }),
      reload(),
    ]);
  }

  async function copyText(value: string, keyId?: string) {
    try {
      const ok = await copyTextToClipboard(value);
      if (!ok) return;
      if (keyId) {
        setCopiedKeyId(keyId);
        window.setTimeout(() => setCopiedKeyId(''), 1200);
      }
    } catch {}
  }

  return (
    <section className="grid-page">
      <div className="sub2-page-head">
        <div className="sub2-page-title">
          <strong>API 密钥</strong>
        </div>
        <div className="sub2-inline-summary">
          <div className="sub2-inline-summary-item"><span>当前用户</span><strong>{selectedUser?.name || '未选择用户'}</strong><small>{selectedUser?.group_name || selectedUser?.source_type || '-'}</small></div>
          <div className="sub2-inline-summary-item"><span>Key 数量</span><strong>{formatNumber(selectedUserKeys)}</strong><small>当前筛选 {formatNumber(rows.length)}</small></div>
          <div className="sub2-inline-summary-item"><span>启用 Key</span><strong>{formatNumber(activeRows.length)}</strong><small>停用 {formatNumber(rows.length - activeRows.length)}</small></div>
          <div className="sub2-inline-summary-item"><span>订阅覆盖</span><strong>{formatNumber(coveredRows.length)}</strong><small>未覆盖 {formatNumber(uncoveredRows.length)}</small></div>
        </div>
      </div>

      <TablePageLayout
        filters={(
          <FilterToolbar
            right={
              <ToolbarButtonRow>
                <Button onClick={() => void reload()}><RefreshCw size={15} />刷新</Button>
                <ColumnMenu
                  label="列设置"
                  items={[
                    { key: 'owner', label: '归属用户', checked: visibleColumns.has('owner'), onToggle: () => toggleColumn('owner') },
                    { key: 'subscription', label: '订阅', checked: visibleColumns.has('subscription'), onToggle: () => toggleColumn('subscription') },
                    { key: 'preview', label: 'Key 预览', checked: visibleColumns.has('preview'), onToggle: () => toggleColumn('preview') },
                    { key: 'usage', label: '使用记录', checked: visibleColumns.has('usage'), onToggle: () => toggleColumn('usage') },
                    { key: 'lastUsed', label: '最近使用', checked: visibleColumns.has('lastUsed'), onToggle: () => toggleColumn('lastUsed') },
                    { key: 'status', label: '状态', checked: visibleColumns.has('status'), onToggle: () => toggleColumn('status') },
                  ]}
                />
                <ToolsMenu>
                  <button type="button" onClick={() => { setSearch(''); setStatusFilter(''); setSubscriptionFilter(''); setPage(1); }}>
                    <span>清空筛选</span>
                  </button>
                  <button type="button" onClick={() => { setSubscriptionFilter('active'); setPage(1); }}>
                    <span>仅看有效订阅</span>
                  </button>
                  <button type="button" onClick={() => { setStatusFilter('disabled'); setPage(1); }}>
                    <span>仅看停用 Key</span>
                  </button>
                  <button type="button" onClick={() => { setPageSize(50); setPage(1); }}>
                    <span>切换 50 / 页</span>
                  </button>
                </ToolsMenu>
                <Button tone="primary" onClick={openCreate}><Plus size={15} />创建 Key</Button>
              </ToolbarButtonRow>
            }
          >
            <SearchField value={search} placeholder="搜索名称 / 用户 / Key / 计划" onChange={(value) => { setSearch(value); setPage(1); }} />
            <Select value={statusFilter} onChange={(event) => { setStatusFilter(event.target.value as StatusFilter); setPage(1); }}>
              <option value="">全部状态</option>
              <option value="enabled">启用</option>
              <option value="disabled">停用</option>
            </Select>
            <Select value={subscriptionFilter} onChange={(event) => { setSubscriptionFilter(event.target.value as SubscriptionFilter); setPage(1); }}>
              <option value="">全部订阅</option>
              <option value="active">订阅有效</option>
              <option value="inactive">无可用订阅</option>
            </Select>
          </FilterToolbar>
        )}
        table={(
          <div className="table-wrap table-scroll table-keys">
            <table>
              <thead>
                <tr>
                  <th>名称</th>
                  {visibleColumns.has('owner') ? <th>用户</th> : null}
                  {visibleColumns.has('subscription') ? <th>订阅</th> : null}
                  {visibleColumns.has('preview') ? <th>Key 预览</th> : null}
                  {visibleColumns.has('usage') ? <th>使用记录</th> : null}
                  {visibleColumns.has('lastUsed') ? <th>最近使用</th> : null}
                  {visibleColumns.has('status') ? <th>状态</th> : null}
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {pagedRows.length ? pagedRows.map((item) => {
                  const liveUsage = usageByKey.get(item.id);
                  const usage = liveUsage || {
                    requests: Number(item.request_count || 0),
                    tokens: Number(item.total_tokens || 0),
                    cost: Number(item.actual_cost || 0) || Number(item.total_cost || 0),
                    last_used_at: item.last_used_request_at || '',
                  };
                  return (
                  <tr key={item.id}>
                    <td><div className="sub2-cell-stack"><strong>{item.name}</strong><small>{item.id}</small></div></td>
                    {visibleColumns.has('owner') ? (
                      <td><div className="sub2-cell-stack"><strong>{getBusinessUserName(item)}</strong><small>{getBusinessUserId(item)}</small></div></td>
                    ) : null}
                    {visibleColumns.has('subscription') ? (
                      <td><div className="sub2-cell-stack"><strong>{item.subscription_active ? (item.active_plan_name || '订阅有效') : '无可用订阅'}</strong><small>{item.active_group_name || item.active_group_id || item.active_subscription_status || '-'}</small></div></td>
                    ) : null}
                    {visibleColumns.has('preview') ? (
                      <td>
                        <div className="key-value-cell">
                          <code>{item.key_preview}</code>
                          <button type="button" className={copiedKeyId === item.id ? 'copied' : ''} onClick={() => copyText(item.key_preview, item.id)} aria-label="复制 Key 预览">
                            <Copy size={14} />
                          </button>
                        </div>
                      </td>
                    ) : null}
                    {visibleColumns.has('usage') ? (
                      <td>
                        <div className="sub2-cell-stack sub2-cell-stack-tight">
                          <strong>{formatNumber(usage.requests)} 次</strong>
                          <small>{formatTokenCount(usage.tokens)} · {formatUsdCost(usage.cost)}</small>
                        </div>
                      </td>
                    ) : null}
                    {visibleColumns.has('lastUsed') ? (
                      <td><div className="sub2-cell-stack sub2-cell-stack-tight"><strong>{usage.last_used_at || item.last_used_request_at || formatTimestamp(item.last_used_at)}</strong><small>{item.updated_at ? `更新 ${formatTimestamp(item.updated_at)}` : '暂无更新'}</small></div></td>
                    ) : null}
                    {visibleColumns.has('status') ? (
                      <td><Badge tone={item.enabled === false ? 'warn' : 'ok'}>{item.enabled === false ? '停用' : '启用'}</Badge></td>
                    ) : null}
                    <td>
                      <RowActions>
                        <RowAction icon={Eye} label="详情" onClick={() => setInspectKey(item)} />
                        <RowAction icon={Edit} label="编辑" onClick={() => openEdit(item)} />
                        <RowAction icon={item.enabled === false ? ShieldCheck : KeyRound} label={item.enabled === false ? '启用' : '停用'} tone={item.enabled === false ? 'default' : 'warn'} onClick={() => setToggleTarget(item)} />
                        <RowAction icon={Trash2} label="删除" tone="danger" onClick={() => setDeleteTarget(item)} />
                      </RowActions>
                    </td>
                  </tr>
                );
                }) : (
                  <tr>
                    <td colSpan={visibleColumns.size + 2}>
                      <EmptyState title="暂无 API Key" description="当前筛选条件下没有 API Key。" action={<Button tone="primary" onClick={openCreate}>创建 Key</Button>} />
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
              <Button tone="primary" onClick={() => copyText(generatedKey)}>复制 Key</Button>
            </ModalActions>
          }
        >
          <div className="admin-dialog admin-dialog-result">
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
          title={draft.id ? '编辑 API Key' : '创建 API Key'}
          size="md"
          onClose={() => setDraft(null)}
          footer={
            <ModalActions>
              <Button onClick={() => setDraft(null)}>取消</Button>
              <Button
                tone="primary"
                disabled={createMutation.isPending || updateMutation.isPending || !draft.user_id || !draft.name.trim()}
                onClick={submitDraft}
              >
                保存
              </Button>
            </ModalActions>
          }
        >
          <div className="admin-dialog">
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
              <Field label="状态">
                <Select value={draft.enabled ? 'enabled' : 'disabled'} onChange={(e) => setDraft({ ...draft, enabled: e.target.value === 'enabled' })}>
                  <option value="enabled">启用</option>
                  <option value="disabled">停用</option>
                </Select>
              </Field>
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
            </div>
            <div className="admin-dialog-summary">
              <div className="admin-dialog-summary-card">
                <span>用户</span>
                <strong>{getBusinessUserName(inspectKey)}</strong>
                <small>{getBusinessUserId(inspectKey)}</small>
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
          title={toggleTarget.enabled === false ? '启用 Key' : '停用 Key'}
          size="md"
          onClose={() => setToggleTarget(null)}
          footer={
            <ModalActions>
              <Button onClick={() => setToggleTarget(null)}>取消</Button>
              <Button
                tone={toggleTarget.enabled === false ? 'primary' : 'danger'}
                disabled={toggleMutation.isPending}
                onClick={() => toggleMutation.mutate({ keyId: toggleTarget.id, enabled: toggleTarget.enabled === false })}
              >
                确认
              </Button>
            </ModalActions>
          }
        >
          <div className="admin-dialog">
            <div className="admin-dialog-intro">
              <strong>{toggleTarget.name}</strong>
            </div>
          </div>
        </Modal>
      ) : null}

      {deleteTarget ? (
        <Modal
          title="删除 API Key"
          size="md"
          onClose={() => setDeleteTarget(null)}
          footer={
            <ModalActions>
              <Button onClick={() => setDeleteTarget(null)}>取消</Button>
              <Button tone="danger" disabled={deleteMutation.isPending} onClick={() => deleteMutation.mutate(deleteTarget.id)}>
                删除
              </Button>
            </ModalActions>
          }
        >
          <div className="admin-dialog">
            <div className="admin-dialog-intro">
              <strong>{deleteTarget.name}</strong>
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
