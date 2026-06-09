import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Copy, Edit, Eye, Plus, RefreshCw, ShieldCheck, Trash2 } from 'lucide-react';
import { createAccountApiKey, deleteAccountApiKey, fetchAccountUsage, setAccountApiKeyEnabled, updateAccountApiKey } from '../api';
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
import type { AdminApiKey, AdminGroup } from '../types';
import { copyTextToClipboard, formatNumber, formatTokenCount, formatUsdCost, readStorageJSON, writeStorageJSON } from '../utils';

type KeyDraft = {
  id?: string;
  group_id: string;
  name: string;
  enabled: boolean;
};

type StatusFilter = '' | 'enabled' | 'disabled';
type SubscriptionFilter = '' | 'active' | 'inactive';
type ColumnKey = 'group' | 'subscription' | 'preview' | 'usage' | 'lastUsed' | 'status';

const DEFAULT_VISIBLE_COLUMNS: ColumnKey[] = ['group', 'subscription', 'preview', 'usage', 'lastUsed', 'status'];
const STORAGE_KEY = 'account-api-keys-view-state';

export function AccountApiKeysPage() {
  const { account, groups, apiKeys, reload } = useAccountCenter();
  const usageQuery = useQuery({ queryKey: ['account-usage'], queryFn: () => fetchAccountUsage(), refetchInterval: 10000, retry: false });
  const savedState = readStorageJSON(STORAGE_KEY, {
    search: '',
    statusFilter: '' as StatusFilter,
    subscriptionFilter: '' as SubscriptionFilter,
    groupFilter: '',
    pageSize: 20,
    visibleColumns: DEFAULT_VISIBLE_COLUMNS,
  });

  const [draft, setDraft] = useState<KeyDraft | null>(null);
  const [generatedKey, setGeneratedKey] = useState('');
  const [copiedKeyId, setCopiedKeyId] = useState('');
  const [search, setSearch] = useState(savedState.search);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>(savedState.statusFilter || '');
  const [subscriptionFilter, setSubscriptionFilter] = useState<SubscriptionFilter>(savedState.subscriptionFilter || '');
  const [groupFilter, setGroupFilter] = useState(savedState.groupFilter || '');
  const [inspectKey, setInspectKey] = useState<AdminApiKey | null>(null);
  const [toggleTarget, setToggleTarget] = useState<AdminApiKey | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<AdminApiKey | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(savedState.pageSize || 20);
  const [visibleColumns, setVisibleColumns] = useState<Set<ColumnKey>>(new Set(savedState.visibleColumns || DEFAULT_VISIBLE_COLUMNS));

  const createMutation = useMutation({
    mutationFn: createAccountApiKey,
    onSuccess: async (result) => {
      setGeneratedKey(result.generated_key || '');
      setDraft(null);
      await refreshKeyData();
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ keyId, payload }: { keyId: string; payload: Record<string, unknown> }) => updateAccountApiKey(keyId, payload),
    onSuccess: async () => {
      setDraft(null);
      await refreshKeyData();
    },
  });

  const toggleMutation = useMutation({
    mutationFn: ({ keyId, enabled }: { keyId: string; enabled: boolean }) => setAccountApiKeyEnabled(keyId, enabled),
    onSuccess: async () => {
      setToggleTarget(null);
      await refreshKeyData();
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (keyId: string) => deleteAccountApiKey(keyId),
    onSuccess: async () => {
      setDeleteTarget(null);
      await refreshKeyData();
    },
  });

  const rows = useMemo(() => {
    const keyword = search.trim().toLowerCase();
    return apiKeys.filter((item) => {
      if (statusFilter) {
        const enabledValue = statusFilter === 'enabled';
        if ((item.enabled !== false) !== enabledValue) return false;
      }
      if (subscriptionFilter === 'active' && !item.subscription_active) return false;
      if (subscriptionFilter === 'inactive' && item.subscription_active) return false;
      if (groupFilter && keyGroupId(item) !== groupFilter) return false;
      if (!keyword) return true;
      const hay = [
        item.name,
        item.key_preview,
        keyGroupName(item, groups),
        item.active_plan_name,
        item.active_group_name,
      ]
        .map((value) => String(value || '').toLowerCase())
        .join(' ');
      return hay.includes(keyword);
    });
  }, [apiKeys, groupFilter, groups, search, statusFilter, subscriptionFilter]);

  const totalPages = Math.max(1, Math.ceil(rows.length / pageSize));
  const pagedRows = rows.slice((page - 1) * pageSize, page * pageSize);
  const activeRows = rows.filter((item) => item.enabled !== false);
  const coveredRows = rows.filter((item) => item.subscription_active);
  const uncoveredRows = rows.filter((item) => !item.subscription_active);
  const selectedUserKeys = apiKeys.length;
  const usageByKey = useMemo(() => {
    const usage = new Map<string, { requests: number; tokens: number; cost: number; last_used_at: string }>();
    for (const item of usageQuery.data?.items || []) {
      const keyId = String(item.api_key_id || '').trim();
      if (!keyId) continue;
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
  }, [usageQuery.data?.items]);

  useEffect(() => {
    writeStorageJSON(STORAGE_KEY, {
      search,
      statusFilter,
      subscriptionFilter,
      groupFilter,
      pageSize,
      visibleColumns: Array.from(visibleColumns),
    });
  }, [groupFilter, pageSize, search, statusFilter, subscriptionFilter, visibleColumns]);

  function openCreate() {
    setDraft({ group_id: defaultKeyGroupId(account, groups), name: '', enabled: true });
  }

  function openEdit(item: AdminApiKey) {
    setDraft({
      id: item.id,
      group_id: keyGroupId(item),
      name: item.name || '',
      enabled: item.enabled !== false,
    });
  }

  function submitDraft() {
    if (!draft) return;
    const payload = { name: draft.name, enabled: draft.enabled, group_id: draft.group_id };
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
      queryClient.invalidateQueries({ queryKey: ['account-api-keys'] }),
      queryClient.invalidateQueries({ queryKey: ['account-usage'] }),
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
          <div className="sub2-inline-summary-item"><span>账户</span><strong>{account?.name || '-'}</strong><small>{account?.group_name || account?.source_type || '-'}</small></div>
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
                    { key: 'group', label: 'Key 分组', checked: visibleColumns.has('group'), onToggle: () => toggleColumn('group') },
                    { key: 'subscription', label: '订阅', checked: visibleColumns.has('subscription'), onToggle: () => toggleColumn('subscription') },
                    { key: 'preview', label: 'Key 预览', checked: visibleColumns.has('preview'), onToggle: () => toggleColumn('preview') },
                    { key: 'usage', label: '使用记录', checked: visibleColumns.has('usage'), onToggle: () => toggleColumn('usage') },
                    { key: 'lastUsed', label: '最近使用', checked: visibleColumns.has('lastUsed'), onToggle: () => toggleColumn('lastUsed') },
                    { key: 'status', label: '状态', checked: visibleColumns.has('status'), onToggle: () => toggleColumn('status') },
                  ]}
                />
                <ToolsMenu>
                  <button type="button" onClick={() => { setSearch(''); setStatusFilter(''); setSubscriptionFilter(''); setGroupFilter(''); setPage(1); }}>
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
                <Button tone="primary" onClick={openCreate}><Plus size={15} />添加 Key</Button>
              </ToolbarButtonRow>
            }
          >
            <SearchField value={search} placeholder="搜索名称 / Key / 计划" onChange={(value) => { setSearch(value); setPage(1); }} />
            <Select value={groupFilter} onChange={(event) => { setGroupFilter(event.target.value); setPage(1); }}>
              <option value="">全部分组</option>
              {groups.map((group) => <option key={group.id} value={group.id}>{group.name}</option>)}
            </Select>
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
                  {visibleColumns.has('group') ? <th>Key 分组</th> : null}
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
                    {visibleColumns.has('group') ? (
                      <td><div className="sub2-cell-stack"><strong>{keyGroupName(item, groups)}</strong><small>{keyGroupId(item) || '-'}</small></div></td>
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
                    <td className="row-actions-cell">
                      <RowActions>
                        <RowAction icon={Eye} label="详情" onClick={() => setInspectKey(item)} />
                        <RowAction icon={Edit} label="编辑" onClick={() => openEdit(item)} />
                        <ToolsMenu label="更多">
                          <button type="button" onClick={() => setToggleTarget(item)}><span>{item.enabled === false ? '启用' : '停用'}</span><ShieldCheck size={14} /></button>
                          <button type="button" className="danger" onClick={() => setDeleteTarget(item)}><span>删除</span><Trash2 size={14} /></button>
                        </ToolsMenu>
                      </RowActions>
                    </td>
                  </tr>
                );
                }) : (
                  <tr>
                    <td colSpan={visibleColumns.size + 2}>
                      <EmptyState title="暂无 API Key" action={<Button tone="primary" onClick={openCreate}>添加 Key</Button>} />
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
          title={draft.id ? '编辑 API Key' : '添加 API Key'}
          size="md"
          onClose={() => setDraft(null)}
          footer={
            <ModalActions>
              <Button onClick={() => setDraft(null)}>取消</Button>
              <Button
                tone="primary"
                disabled={createMutation.isPending || updateMutation.isPending || !draft.name.trim()}
                onClick={submitDraft}
              >
                保存
              </Button>
            </ModalActions>
          }
        >
          <div className="admin-dialog">
            <div className="admin-dialog-grid modal-grid">
              <Field label="Key 分组">
                <Select value={draft.group_id} onChange={(e) => setDraft({ ...draft, group_id: e.target.value })}>
                  <option value="">不绑定分组</option>
                  {keyGroupOptions(account, groups).map((group) => <option key={group.id} value={group.id}>{group.name}</option>)}
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
                <span>Key 分组</span>
                <strong>{keyGroupName(inspectKey, groups)}</strong>
                <small>{keyGroupId(inspectKey) || '-'}</small>
              </div>
              <div className="admin-dialog-summary-card">
                <span>订阅</span>
                <strong>{inspectKey.subscription_active ? (inspectKey.active_plan_name || '订阅有效') : '无可用订阅'}</strong>
                <small>{inspectKey.active_subscription_status || '-'}</small>
              </div>
            </div>
            <div className="admin-dialog-grid">
              <Field label="状态"><TextInput readOnly value={inspectKey.enabled === false ? '停用' : '启用'} /></Field>
              <Field label="Key 预览"><TextInput readOnly value={inspectKey.key_preview || '-'} /></Field>
              <Field label="订阅分组"><TextInput readOnly value={inspectKey.active_group_name || inspectKey.active_group_id || '-'} /></Field>
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

function keyGroupId(item: AdminApiKey | null | undefined): string {
  return String(item?.group_id || '').trim();
}

function keyGroupName(item: AdminApiKey | null | undefined, groups: AdminGroup[]): string {
  const groupId = keyGroupId(item);
  if (!groupId) return '不绑定分组';
  return String(item?.group_name || groups.find((group) => group.id === groupId)?.name || groupId);
}

function keyGroupOptions(account: { allowed_group_ids?: string[]; user_allowed_group_ids?: string[] } | null | undefined, groups: AdminGroup[]): AdminGroup[] {
  const allowedIds = account?.allowed_group_ids || account?.user_allowed_group_ids || [];
  if (!allowedIds.length) return groups;
  return groups.filter((group) => allowedIds.includes(group.id));
}

function defaultKeyGroupId(account: { group_id?: string; group_ids?: string[]; allowed_group_ids?: string[]; user_allowed_group_ids?: string[] } | null | undefined, groups: AdminGroup[]): string {
  const options = keyGroupOptions(account, groups);
  if (options.length === 1) return options[0].id;
  const userGroups = account?.group_ids || (account?.group_id ? [account.group_id] : []);
  const firstUsable = userGroups.find((groupId) => options.some((group) => group.id === groupId));
  return firstUsable || '';
}
