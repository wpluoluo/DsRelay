import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Copy, Edit, Eye, ExternalLink, Plus, RefreshCw, ShieldCheck, Trash2 } from 'lucide-react';
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
import { buildPageIntro } from '../navigation';
import { queryClient } from '../state/queryClient';
import { useAccountCenter } from '../state/accountCenterContext';
import type { AdminApiKey, AdminChannel, AdminGroup } from '../types';
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
type FilterKey = 'group' | 'status' | 'subscription';
type UseKeyClient = 'codex' | 'claude' | 'gemini' | 'opencode';
type UseKeyShell = 'unix' | 'powershell' | 'windows';
type UseKeyFile = { id: string; path: string; content: string; hint?: string };

const DEFAULT_VISIBLE_COLUMNS: ColumnKey[] = ['group', 'subscription', 'preview', 'usage', 'lastUsed', 'status'];
const DEFAULT_VISIBLE_FILTERS: FilterKey[] = ['group', 'status', 'subscription'];
const STORAGE_KEY = 'account-api-keys-view-state';
const RAW_KEY_STORAGE = 'account-api-key-raw-secrets';

export function AccountApiKeysPage() {
  const { account, groups, apiKeys, reload, visibleAvailableChannels } = useAccountCenter();
  const usageQuery = useQuery({ queryKey: ['account-usage'], queryFn: () => fetchAccountUsage(), refetchInterval: 10000, retry: false });
  const savedState = readStorageJSON(STORAGE_KEY, {
    search: '',
    statusFilter: '' as StatusFilter,
    subscriptionFilter: '' as SubscriptionFilter,
    groupFilter: '',
    pageSize: 20,
    visibleColumns: DEFAULT_VISIBLE_COLUMNS,
    visibleFilters: DEFAULT_VISIBLE_FILTERS,
  });

  const [draft, setDraft] = useState<KeyDraft | null>(null);
  const [generatedKey, setGeneratedKey] = useState('');
  const [generatedKeyId, setGeneratedKeyId] = useState('');
  const [copiedKeyId, setCopiedKeyId] = useState('');
  const [search, setSearch] = useState(savedState.search);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>(savedState.statusFilter || '');
  const [subscriptionFilter, setSubscriptionFilter] = useState<SubscriptionFilter>(savedState.subscriptionFilter || '');
  const [groupFilter, setGroupFilter] = useState(savedState.groupFilter || '');
  const [inspectKey, setInspectKey] = useState<AdminApiKey | null>(null);
  const [useKeyTarget, setUseKeyTarget] = useState<AdminApiKey | null>(null);
  const [useKeyClient, setUseKeyClient] = useState<UseKeyClient>('codex');
  const [useKeyShell, setUseKeyShell] = useState<UseKeyShell>('powershell');
  const [copiedSnippetId, setCopiedSnippetId] = useState('');
  const [toggleTarget, setToggleTarget] = useState<AdminApiKey | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<AdminApiKey | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(savedState.pageSize || 20);
  const [visibleColumns, setVisibleColumns] = useState<Set<ColumnKey>>(new Set(savedState.visibleColumns || DEFAULT_VISIBLE_COLUMNS));
  const [visibleFilters, setVisibleFilters] = useState<Set<FilterKey>>(new Set(savedState.visibleFilters || DEFAULT_VISIBLE_FILTERS));

  const createMutation = useMutation({
    mutationFn: createAccountApiKey,
    onSuccess: async (result) => {
      if (result.item?.id && result.generated_key) {
        storeRawKeySecret(result.item.id, result.generated_key);
      }
      setGeneratedKeyId(result.item?.id || '');
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
  const apiBaseUrl = useMemo(() => {
    if (typeof window === 'undefined') return '/v1';
    return `${window.location.origin.replace(/\/+$/, '')}/v1`;
  }, []);
  const defaultModel = useMemo(() => getDefaultAccountModel(visibleAvailableChannels), [visibleAvailableChannels]);
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
      visibleFilters: Array.from(visibleFilters),
    });
  }, [groupFilter, pageSize, search, statusFilter, subscriptionFilter, visibleColumns, visibleFilters]);

  useEffect(() => {
    if (!useKeyTarget) return;
    setUseKeyClient('codex');
    setUseKeyShell('powershell');
    setCopiedSnippetId('');
  }, [useKeyTarget?.id]);

  function openCreate() {
    setDraft({ group_id: defaultKeyGroupId(account, groups), name: '默认业务 Key', enabled: true });
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
    const trimmedName = draft.name.trim();
    const payload = { ...(trimmedName ? { name: trimmedName } : {}), enabled: draft.enabled, group_id: draft.group_id };
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

  function toggleFilter(key: FilterKey) {
    setVisibleFilters((current) => {
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

  async function copyUseKeyContent(file: UseKeyFile) {
    const ok = await copyTextToClipboard(file.content);
    if (!ok) return;
    setCopiedSnippetId(file.id);
    window.setTimeout(() => setCopiedSnippetId((current) => (current === file.id ? '' : current)), 1500);
  }

  const currentUseKeySecret = useMemo(
    () => (useKeyTarget ? readRawKeySecret(useKeyTarget.id) : ''),
    [useKeyTarget],
  );
  const useKeyFiles = useMemo(
    () => buildUseKeyFiles({ client: useKeyClient, shell: useKeyShell, apiBaseUrl, apiKey: currentUseKeySecret, defaultModel }),
    [apiBaseUrl, currentUseKeySecret, defaultModel, useKeyClient, useKeyShell],
  );

  return (
    <section className="grid-page">
      {buildPageIntro('/keys')}

      <TablePageLayout
        actions={(
          <div className="endpoint-strip">
            <span>接口入口</span>
            <code title={apiBaseUrl}>{apiBaseUrl}</code>
            <button type="button" onClick={() => copyText(apiBaseUrl)} aria-label="复制接口入口">
              <Copy size={14} />
            </button>
            <a href={apiBaseUrl} target="_blank" rel="noreferrer" aria-label="打开接口入口">
              <ExternalLink size={14} />
            </a>
          </div>
        )}
        filters={(
          <FilterToolbar
            right={
              <ToolbarButtonRow>
                <Button onClick={() => void reload()}><RefreshCw size={15} />刷新</Button>
                <ToolsMenu label="筛选设置" icon={false}>
                  <button type="button" onClick={() => toggleFilter('group')}>
                    <span>分组</span>
                    <strong>{visibleFilters.has('group') ? '✓' : ''}</strong>
                  </button>
                  <button type="button" onClick={() => toggleFilter('status')}>
                    <span>状态</span>
                    <strong>{visibleFilters.has('status') ? '✓' : ''}</strong>
                  </button>
                  <button type="button" onClick={() => toggleFilter('subscription')}>
                    <span>订阅</span>
                    <strong>{visibleFilters.has('subscription') ? '✓' : ''}</strong>
                  </button>
                </ToolsMenu>
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
            {visibleFilters.has('group') ? (
              <Select value={groupFilter} onChange={(event) => { setGroupFilter(event.target.value); setPage(1); }}>
                <option value="">全部分组</option>
                {groups.map((group) => <option key={group.id} value={group.id}>{group.name}</option>)}
              </Select>
            ) : null}
            {visibleFilters.has('status') ? (
              <Select value={statusFilter} onChange={(event) => { setStatusFilter(event.target.value as StatusFilter); setPage(1); }}>
                <option value="">全部状态</option>
                <option value="enabled">启用</option>
                <option value="disabled">停用</option>
              </Select>
            ) : null}
            {visibleFilters.has('subscription') ? (
              <Select value={subscriptionFilter} onChange={(event) => { setSubscriptionFilter(event.target.value as SubscriptionFilter); setPage(1); }}>
                <option value="">全部订阅</option>
                <option value="active">订阅有效</option>
                <option value="inactive">无可用订阅</option>
              </Select>
            ) : null}
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
                        <RowAction icon={Copy} label="接入" onClick={() => setUseKeyTarget(item)} />
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
              <Button
                onClick={() => {
                  const latest = apiKeys.find((item) => item.id === generatedKeyId) || null;
                  setGeneratedKey('');
                  setGeneratedKeyId('');
                  setUseKeyTarget(latest || null);
                }}
              >
                接入方式
              </Button>
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

      {useKeyTarget ? (
        <Modal
          title="接入方式"
          size="lg"
          onClose={() => setUseKeyTarget(null)}
          footer={<ModalActions><Button onClick={() => setUseKeyTarget(null)}>关闭</Button></ModalActions>}
        >
          <div className="use-key-modal">
            <div className="admin-dialog-intro">
              <strong>{useKeyTarget.name}</strong>
            </div>
            <div className="admin-dialog-summary">
              <div className="admin-dialog-summary-card">
                <span>接口入口</span>
                <strong title={apiBaseUrl}>{apiBaseUrl}</strong>
                <small>默认模型 {defaultModel}</small>
              </div>
              <div className="admin-dialog-summary-card">
                <span>Key 分组</span>
                <strong>{keyGroupName(useKeyTarget, groups)}</strong>
                <small>{keyGroupId(useKeyTarget) || '-'}</small>
              </div>
              <div className="admin-dialog-summary-card">
                <span>原始 Key</span>
                <strong>{currentUseKeySecret ? '当前浏览器已保存' : '当前浏览器未保存'}</strong>
                <small>{useKeyTarget.key_preview || '-'}</small>
              </div>
            </div>

            {!currentUseKeySecret ? (
              <div className="admin-dialog-note">当前浏览器没有这条 Key 的原始值。新建 Key 后可立即复制接入配置。</div>
            ) : (
              <>
                <div className="sub2-toolbar-row">
                  <Button tone={useKeyClient === 'codex' ? 'primary' : 'ghost'} onClick={() => setUseKeyClient('codex')}>Codex</Button>
                  <Button tone={useKeyClient === 'claude' ? 'primary' : 'ghost'} onClick={() => setUseKeyClient('claude')}>Claude Code</Button>
                  <Button tone={useKeyClient === 'gemini' ? 'primary' : 'ghost'} onClick={() => setUseKeyClient('gemini')}>Gemini CLI</Button>
                  <Button tone={useKeyClient === 'opencode' ? 'primary' : 'ghost'} onClick={() => setUseKeyClient('opencode')}>OpenCode</Button>
                </div>

                {useKeyClient !== 'opencode' ? (
                  <div className="sub2-toolbar-row">
                    <Button tone={useKeyShell === 'unix' ? 'primary' : 'ghost'} onClick={() => setUseKeyShell('unix')}>macOS / Linux</Button>
                    <Button tone={useKeyShell === 'powershell' ? 'primary' : 'ghost'} onClick={() => setUseKeyShell('powershell')}>PowerShell</Button>
                    <Button tone={useKeyShell === 'windows' ? 'primary' : 'ghost'} onClick={() => setUseKeyShell('windows')}>Windows</Button>
                  </div>
                ) : null}

                {useKeyFiles.map((file) => (
                  <div key={file.id} className="code-block">
                    <div className="code-block-head">
                      <span>{file.path}</span>
                      <button type="button" className={copiedSnippetId === file.id ? 'copied' : ''} onClick={() => void copyUseKeyContent(file)}>
                        <Copy size={14} />
                        <span>{copiedSnippetId === file.id ? '已复制' : '复制'}</span>
                      </button>
                    </div>
                    <pre><code>{file.content}</code></pre>
                    {file.hint ? <div className="admin-dialog-note">{file.hint}</div> : null}
                  </div>
                ))}
              </>
            )}
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
                disabled={createMutation.isPending || updateMutation.isPending}
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
                  {keyGroupOptions(groups).map((group) => <option key={group.id} value={group.id}>{group.name}</option>)}
                </Select>
              </Field>
              <Field label="Key 名称">
                <TextInput value={draft.name} placeholder="默认业务 Key" onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
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

function keyGroupOptions(groups: AdminGroup[]): AdminGroup[] {
  return groups.filter((group) => group.enabled !== false);
}

function defaultKeyGroupId(account: { group_id?: string; group_ids?: string[]; allowed_group_ids?: string[] } | null | undefined, groups: AdminGroup[]): string {
  const options = keyGroupOptions(groups);
  if (options.length === 1) return options[0].id;
  const userGroups = account?.group_ids || (account?.group_id ? [account.group_id] : []);
  const firstUsable = userGroups.find((groupId) => options.some((group) => group.id === groupId));
  return firstUsable || '';
}

function readRawKeyMap(): Record<string, string> {
  if (typeof window === 'undefined') return {};
  try {
    const raw = window.sessionStorage.getItem(RAW_KEY_STORAGE);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === 'object' ? parsed : {};
  } catch {
    return {};
  }
}

function storeRawKeySecret(keyId: string, rawKey: string) {
  if (typeof window === 'undefined' || !keyId || !rawKey) return;
  const next = { ...readRawKeyMap(), [keyId]: rawKey };
  window.sessionStorage.setItem(RAW_KEY_STORAGE, JSON.stringify(next));
}

function readRawKeySecret(keyId: string): string {
  return readRawKeyMap()[keyId] || '';
}

function getDefaultAccountModel(channels: AdminChannel[]): string {
  for (const channel of channels) {
    for (const pricing of channel.model_pricing || []) {
      const model = String(pricing.model || '').trim();
      if (model) return model;
    }
  }
  return 'deepseek-v4-flash';
}

function buildUseKeyFiles({
  client,
  shell,
  apiBaseUrl,
  apiKey,
  defaultModel,
}: {
  client: UseKeyClient;
  shell: UseKeyShell;
  apiBaseUrl: string;
  apiKey: string;
  defaultModel: string;
}): UseKeyFile[] {
  const codexDir = shell === 'unix' ? '~/.codex' : '%USERPROFILE%\\.codex';
  const joinPath = (base: string, name: string) => (shell === 'unix' ? `${base}/${name}` : `${base}\\${name}`);
  const openCodeConfig = JSON.stringify(
    {
      provider: {
        openai: {
          options: {
            baseURL: apiBaseUrl,
            apiKey,
          },
          models: {
            [defaultModel]: {
              name: defaultModel,
              limit: {
                context: 1000000,
                output: 128000,
              },
              options: {
                store: false,
              },
            },
          },
        },
      },
      $schema: 'https://opencode.ai/config.json',
    },
    null,
    2,
  );
  if (client === 'codex') {
    return [
      {
        id: 'codex-config',
        path: joinPath(codexDir, 'config.toml'),
        content: `model_provider = "OpenAI"
model = "${defaultModel}"
review_model = "${defaultModel}"
disable_response_storage = true
network_access = "enabled"

[model_providers.OpenAI]
name = "OpenAI"
base_url = "${apiBaseUrl}"
wire_api = "responses"
requires_openai_auth = true`,
      },
      {
        id: 'codex-auth',
        path: joinPath(codexDir, 'auth.json'),
        content: `{
  "OPENAI_API_KEY": "${apiKey}"
}`,
      },
    ];
  }
  if (client === 'claude') {
    const block =
      shell === 'unix'
        ? `export ANTHROPIC_BASE_URL="${apiBaseUrl}"
export ANTHROPIC_AUTH_TOKEN="${apiKey}"
export CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1`
        : shell === 'windows'
          ? `set ANTHROPIC_BASE_URL=${apiBaseUrl}
set ANTHROPIC_AUTH_TOKEN=${apiKey}
set CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1`
          : `$env:ANTHROPIC_BASE_URL="${apiBaseUrl}"
$env:ANTHROPIC_AUTH_TOKEN="${apiKey}"
$env:CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1`;
    return [{ id: 'claude-env', path: shell === 'unix' ? 'Terminal' : shell === 'windows' ? 'Command Prompt' : 'PowerShell', content: block }];
  }
  if (client === 'gemini') {
    const block =
      shell === 'unix'
        ? `export GOOGLE_GEMINI_BASE_URL="${apiBaseUrl}"
export GEMINI_API_KEY="${apiKey}"
export GEMINI_MODEL="${defaultModel}"`
        : shell === 'windows'
          ? `set GOOGLE_GEMINI_BASE_URL=${apiBaseUrl}
set GEMINI_API_KEY=${apiKey}
set GEMINI_MODEL=${defaultModel}`
          : `$env:GOOGLE_GEMINI_BASE_URL="${apiBaseUrl}"
$env:GEMINI_API_KEY="${apiKey}"
$env:GEMINI_MODEL="${defaultModel}"`;
    return [{ id: 'gemini-env', path: shell === 'unix' ? 'Terminal' : shell === 'windows' ? 'Command Prompt' : 'PowerShell', content: block }];
  }
  return [
    {
      id: 'opencode-config',
      path: 'opencode.json',
      content: openCodeConfig,
      hint: '把文件放到当前工作目录或 OpenCode 配置目录。',
    },
  ];
}
