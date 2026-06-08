import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Copy, Edit, Eye, KeyRound, Plus, RefreshCw, ShieldCheck, Trash2 } from 'lucide-react';
import {
  createAdminApiKey,
  createAdminUser,
  deleteAdminApiKey,
  deleteAdminUser,
  fetchAdminApiKeys,
  fetchAdminGroups,
  fetchAdminUsers,
  resetAdminUserExternalKey,
  setAdminApiKeyEnabled,
  setAdminUserEnabled,
  updateAdminUser,
} from '../api';
import { Badge, Button, Field, Modal, ModalActions, Select, TextInput } from '../components';
import {
  ActionButton,
  ColumnMenu,
  FilterToolbar,
  ListEmptyRow,
  Pager,
  RowAction,
  RowActions,
  SearchField,
  TablePageLayout,
  ToolbarButtonRow,
  ToolsMenu,
} from '../components/admin';
import { queryClient } from '../state/queryClient';
import type { AdminApiKey, AdminUser } from '../types';
import { copyTextToClipboard, formatNumber, formatTokenCount, formatUsdCost, getBusinessUserId, readStorageJSON, writeStorageJSON } from '../utils';

type UserDraft = {
  id?: string;
  name: string;
  email: string;
  username: string;
  password: string;
  external_key: string;
  auto_external_key: boolean;
  group_ids: string[];
  allowed_group_ids: string[];
  role: string;
  balance_cents: number;
  concurrency_limit: number;
  rpm_limit: number;
  note: string;
  enabled: boolean;
};

type KeyDraft = {
  userId: string;
  name: string;
  enabled: boolean;
};

type CoverageFilter = 'all' | 'subscribed' | 'uncovered';
type StatusFilter = '' | 'enabled' | 'disabled';
type UserColumnKey = 'identity' | 'groups' | 'limits' | 'keys' | 'subscriptions' | 'usage' | 'status';

const EMPTY_DRAFT: UserDraft = {
  name: '',
  email: '',
  username: '',
  password: '',
  external_key: '',
  auto_external_key: true,
  group_ids: [],
  allowed_group_ids: [],
  role: 'user',
  balance_cents: 0,
  concurrency_limit: 1,
  rpm_limit: 0,
  note: '',
  enabled: true,
};

const DEFAULT_VISIBLE_COLUMNS: UserColumnKey[] = ['identity', 'groups', 'limits', 'keys', 'subscriptions', 'usage', 'status'];
const STORAGE_KEY = 'admin-users-view-state';

export function AdminUsersPage() {
  const usersQuery = useQuery({ queryKey: ['admin-users'], queryFn: fetchAdminUsers, refetchInterval: 10000 });
  const groupsQuery = useQuery({ queryKey: ['admin-groups'], queryFn: fetchAdminGroups, refetchInterval: 10000 });
  const keysQuery = useQuery({ queryKey: ['admin-api-keys'], queryFn: fetchAdminApiKeys, refetchInterval: 10000 });

  const savedState = readStorageJSON(STORAGE_KEY, {
    search: '',
    coverageFilter: 'all' as CoverageFilter,
    statusFilter: '' as StatusFilter,
    groupFilter: '',
    pageSize: 20,
    visibleColumns: DEFAULT_VISIBLE_COLUMNS,
  });

  const [search, setSearch] = useState(savedState.search);
  const [coverageFilter, setCoverageFilter] = useState<CoverageFilter>(savedState.coverageFilter || 'all');
  const [statusFilter, setStatusFilter] = useState<StatusFilter>(savedState.statusFilter || '');
  const [groupFilter, setGroupFilter] = useState(savedState.groupFilter || '');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(savedState.pageSize || 20);
  const [visibleColumns, setVisibleColumns] = useState<Set<UserColumnKey>>(new Set(savedState.visibleColumns || DEFAULT_VISIBLE_COLUMNS));
  const [draft, setDraft] = useState<UserDraft | null>(null);
  const [inspectUser, setInspectUser] = useState<AdminUser | null>(null);
  const [viewKeysUser, setViewKeysUser] = useState<AdminUser | null>(null);
  const [keyDraft, setKeyDraft] = useState<KeyDraft | null>(null);
  const [generatedKey, setGeneratedKey] = useState('');
  const [copiedKeyId, setCopiedKeyId] = useState('');
  const [toggleTarget, setToggleTarget] = useState<AdminUser | null>(null);
  const [resetTarget, setResetTarget] = useState<AdminUser | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<AdminUser | null>(null);
  const [deleteKeyTarget, setDeleteKeyTarget] = useState<AdminApiKey | null>(null);

  const createMutation = useMutation({
    mutationFn: createAdminUser,
    onSuccess: async () => {
      setDraft(null);
      await refreshAll();
    },
  });
  const updateMutation = useMutation({
    mutationFn: ({ userId, payload }: { userId: string; payload: Record<string, unknown> }) => updateAdminUser(userId, payload),
    onSuccess: async () => {
      setDraft(null);
      await refreshAll();
    },
  });
  const toggleMutation = useMutation({
    mutationFn: ({ userId, enabled }: { userId: string; enabled: boolean }) => setAdminUserEnabled(userId, enabled),
    onSuccess: async () => {
      setToggleTarget(null);
      await refreshAll();
    },
  });
  const resetMutation = useMutation({
    mutationFn: (userId: string) => resetAdminUserExternalKey(userId),
    onSuccess: async () => {
      setResetTarget(null);
      await refreshAll();
    },
  });
  const deleteMutation = useMutation({
    mutationFn: (userId: string) => deleteAdminUser(userId),
    onSuccess: async () => {
      setDeleteTarget(null);
      await refreshAll();
    },
  });
  const createKeyMutation = useMutation({
    mutationFn: createAdminApiKey,
    onSuccess: async (result) => {
      setGeneratedKey(result.generated_key || '');
      setKeyDraft(null);
      await refreshAll();
    },
  });
  const toggleKeyMutation = useMutation({
    mutationFn: ({ keyId, enabled }: { keyId: string; enabled: boolean }) => setAdminApiKeyEnabled(keyId, enabled),
    onSuccess: async () => {
      await refreshAll();
    },
  });
  const deleteKeyMutation = useMutation({
    mutationFn: (keyId: string) => deleteAdminApiKey(keyId),
    onSuccess: async () => {
      setDeleteKeyTarget(null);
      await refreshAll();
    },
  });

  const groups = groupsQuery.data?.items || [];
  const keyItems = keysQuery.data?.items || [];
  const rows = useMemo(
    () =>
      (usersQuery.data?.items || []).map((item) => ({
        ...item,
        key_count: item.key_count || 0,
        active_key_count: item.active_key_count || 0,
        subscription_count: item.subscription_count || 0,
        active_subscription_count: item.active_subscription_count || 0,
        request_count: item.request_count || 0,
        total_tokens: item.total_tokens || 0,
        coverage_state: (item.active_subscription_count || 0) > 0 ? 'subscribed' : 'uncovered',
      })),
    [usersQuery.data?.items],
  );

  const filteredRows = useMemo(() => {
    const keyword = search.trim().toLowerCase();
    return rows.filter((item) => {
      if (coverageFilter !== 'all' && item.coverage_state !== coverageFilter) return false;
      if (statusFilter) {
        const enabledValue = statusFilter === 'enabled';
        if ((item.enabled !== false) !== enabledValue) return false;
      }
      if (groupFilter) {
        const ids = item.group_ids || (item.group_id ? [item.group_id] : []);
        const allowedIds = item.allowed_group_ids || [];
        if (!ids.includes(groupFilter) && !allowedIds.includes(groupFilter)) return false;
      }
      if (!keyword) return true;
      const haystack = [
        item.name,
        item.email,
        item.username,
        item.id,
        item.group_name,
        item.group_id,
        item.preview,
        item.external_key,
        item.note,
      ]
        .map((value) => String(value || '').toLowerCase())
        .join(' ');
      return haystack.includes(keyword);
    });
  }, [coverageFilter, groupFilter, rows, search, statusFilter]);

  const totalPages = Math.max(1, Math.ceil(filteredRows.length / pageSize));
  const pagedRows = useMemo(() => {
    const start = (page - 1) * pageSize;
    return filteredRows.slice(start, start + pageSize);
  }, [filteredRows, page, pageSize]);

  const activeUsers = rows.filter((item) => item.enabled !== false).length;
  const coveredUsers = rows.filter((item) => item.active_subscription_count > 0).length;
  const keyCoveredUsers = rows.filter((item) => item.active_key_count > 0).length;
  const totalTokens = rows.reduce((sum, item) => sum + Number(item.total_tokens || 0), 0);

  const relatedKeys = useMemo(
    () => keyItems.filter((item) => viewKeysUser && getBusinessUserId(item) === viewKeysUser.id),
    [keyItems, viewKeysUser],
  );

  useEffect(() => {
    writeStorageJSON(STORAGE_KEY, {
      search,
      coverageFilter,
      statusFilter,
      groupFilter,
      pageSize,
      visibleColumns: Array.from(visibleColumns),
    });
  }, [coverageFilter, groupFilter, pageSize, search, statusFilter, visibleColumns]);

  async function refreshAll() {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['admin-users'] }),
      queryClient.invalidateQueries({ queryKey: ['admin-api-keys'] }),
      queryClient.invalidateQueries({ queryKey: ['admin-user-subscriptions'] }),
    ]);
  }

  function openCreate() {
    setDraft({ ...EMPTY_DRAFT, password: randomPassword() });
  }

  function openEdit(user: AdminUser) {
    setDraft({
      id: user.id,
      name: user.name || '',
      email: user.email || user.user_email || '',
      username: user.username || user.user_username || '',
      password: '',
      external_key: user.external_key || user.user_key || '',
      auto_external_key: false,
      group_ids: user.group_ids || (user.group_id ? [user.group_id] : []),
      allowed_group_ids: user.allowed_group_ids || user.user_allowed_group_ids || [],
      role: user.role || user.user_role || 'user',
      balance_cents: Number(user.balance_cents ?? user.user_balance_cents ?? 0),
      concurrency_limit: Number(user.concurrency_limit ?? user.user_concurrency_limit ?? 1),
      rpm_limit: Number(user.rpm_limit ?? user.user_rpm_limit ?? 0),
      note: user.note || '',
      enabled: user.enabled !== false,
    });
  }

  function submitDraft() {
    if (!draft) return;
    const payload = {
      name: draft.name,
      email: draft.email,
      username: draft.username,
      password: draft.password,
      external_key: draft.auto_external_key ? '' : draft.external_key,
      group_ids: draft.group_ids,
      allowed_group_ids: draft.allowed_group_ids,
      role: draft.role,
      balance_cents: draft.balance_cents,
      concurrency_limit: draft.concurrency_limit,
      rpm_limit: draft.rpm_limit,
      note: draft.note,
      enabled: draft.enabled,
      status: draft.enabled ? 'active' : 'disabled',
    };
    if (draft.id) {
      updateMutation.mutate({ userId: draft.id, payload });
      return;
    }
    createMutation.mutate(payload);
  }

  function toggleColumn(key: UserColumnKey) {
    setVisibleColumns((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  function toggleGroup(field: 'group_ids' | 'allowed_group_ids', groupId: string) {
    if (!draft) return;
    const values = new Set(draft[field]);
    if (values.has(groupId)) values.delete(groupId);
    else values.add(groupId);
    setDraft({ ...draft, [field]: Array.from(values) });
  }

  async function copyText(value: string, keyId?: string) {
    const ok = await copyTextToClipboard(value);
    if (!ok) return;
    if (keyId) {
      setCopiedKeyId(keyId);
      window.setTimeout(() => setCopiedKeyId(''), 1200);
    }
  }

  return (
    <section className="grid-page">
      <div className="sub2-page-head">
        <div className="sub2-page-title">
          <strong>用户管理</strong>
        </div>
        <div className="sub2-inline-summary">
          <div className="sub2-inline-summary-item"><span>用户总数</span><strong>{formatNumber(rows.length)}</strong><small>启用 {formatNumber(activeUsers)}</small></div>
          <div className="sub2-inline-summary-item"><span>订阅覆盖</span><strong>{formatNumber(coveredUsers)}</strong><small>未覆盖 {formatNumber(rows.length - coveredUsers)}</small></div>
          <div className="sub2-inline-summary-item"><span>Key 覆盖</span><strong>{formatNumber(keyCoveredUsers)}</strong><small>可调用用户</small></div>
          <div className="sub2-inline-summary-item"><span>总 Token</span><strong>{formatTokenCount(totalTokens)}</strong><small>当前用户列表</small></div>
        </div>
      </div>
      <TablePageLayout
        filters={
          <FilterToolbar
            right={
              <ToolbarButtonRow>
                <ActionButton onClick={() => { void usersQuery.refetch(); void groupsQuery.refetch(); void keysQuery.refetch(); }}>
                  <RefreshCw size={15} />
                  刷新
                </ActionButton>
                <ColumnMenu
                  label="列设置"
                  items={[
                    { key: 'identity', label: '身份信息', checked: visibleColumns.has('identity'), onToggle: () => toggleColumn('identity') },
                    { key: 'groups', label: '分组', checked: visibleColumns.has('groups'), onToggle: () => toggleColumn('groups') },
                    { key: 'limits', label: '余额 / 限制', checked: visibleColumns.has('limits'), onToggle: () => toggleColumn('limits') },
                    { key: 'keys', label: 'Key', checked: visibleColumns.has('keys'), onToggle: () => toggleColumn('keys') },
                    { key: 'subscriptions', label: '订阅', checked: visibleColumns.has('subscriptions'), onToggle: () => toggleColumn('subscriptions') },
                    { key: 'usage', label: '使用记录', checked: visibleColumns.has('usage'), onToggle: () => toggleColumn('usage') },
                    { key: 'status', label: '状态', checked: visibleColumns.has('status'), onToggle: () => toggleColumn('status') },
                  ]}
                />
                <ToolsMenu>
                  <button type="button" onClick={() => { setSearch(''); setCoverageFilter('all'); setStatusFilter(''); setGroupFilter(''); setPage(1); }}>
                    <span>清空筛选</span>
                  </button>
                  <button type="button" onClick={() => { setCoverageFilter('uncovered'); setPage(1); }}>
                    <span>仅看未订阅</span>
                  </button>
                  <button type="button" onClick={() => { setStatusFilter('disabled'); setPage(1); }}>
                    <span>仅看停用</span>
                  </button>
                  <button type="button" onClick={() => { setPageSize(50); setPage(1); }}>
                    <span>切换 50 / 页</span>
                  </button>
                </ToolsMenu>
                <Button tone="primary" onClick={openCreate}>
                  <Plus size={15} />
                  新增用户
                </Button>
              </ToolbarButtonRow>
            }
          >
            <SearchField value={search} placeholder="搜索邮箱 / 用户名 / 名称 / 标识" onChange={(value) => { setSearch(value); setPage(1); }} />
            <Select value={statusFilter} onChange={(event) => { setStatusFilter(event.target.value as StatusFilter); setPage(1); }}>
              <option value="">全部状态</option>
              <option value="enabled">启用</option>
              <option value="disabled">停用</option>
            </Select>
            <Select value={groupFilter} onChange={(event) => { setGroupFilter(event.target.value); setPage(1); }}>
              <option value="">全部分组</option>
              {groups.map((group) => <option key={group.id} value={group.id}>{group.name}</option>)}
            </Select>
            <div className="tabs">
              {[
                { value: 'all', label: '全部用户' },
                { value: 'subscribed', label: '已订阅' },
                { value: 'uncovered', label: '未订阅' },
              ].map((item) => (
                <button
                  key={item.value}
                  type="button"
                  className={coverageFilter === item.value ? 'active' : ''}
                  onClick={() => { setCoverageFilter(item.value as CoverageFilter); setPage(1); }}
                >
                  {item.label}
                </button>
              ))}
            </div>
          </FilterToolbar>
        }
        table={
          <div className="table-wrap table-scroll table-users">
            <table>
              <thead>
                <tr>
                  <th>用户</th>
                  {visibleColumns.has('identity') ? <th>身份信息</th> : null}
                  {visibleColumns.has('groups') ? <th>分组</th> : null}
                  {visibleColumns.has('limits') ? <th>余额 / 限制</th> : null}
                  {visibleColumns.has('keys') ? <th>API Key</th> : null}
                  {visibleColumns.has('subscriptions') ? <th>订阅</th> : null}
                  {visibleColumns.has('usage') ? <th>使用记录</th> : null}
                  {visibleColumns.has('status') ? <th>状态</th> : null}
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {pagedRows.length ? pagedRows.map((item) => (
                  <tr key={item.id}>
                    <td>
                      <div className="sub2-cell-stack sub2-cell-stack-tight">
                        <strong>{item.email || item.user_email || item.name}</strong>
                        <small>{item.username || item.user_username || item.name}</small>
                      </div>
                    </td>
                    {visibleColumns.has('identity') ? (
                      <td>
                        <div className="sub2-cell-stack sub2-cell-stack-tight">
                          <strong>{item.external_key || item.user_key || '-'}</strong>
                          <small>{item.role || item.user_role || 'user'} · {item.id}</small>
                        </div>
                      </td>
                    ) : null}
                    {visibleColumns.has('groups') ? (
                      <td>
                        <div className="sub2-cell-stack sub2-cell-stack-tight">
                          <strong>{groupNames(item.group_ids || (item.group_id ? [item.group_id] : []), groups) || '未分组'}</strong>
                          <small>{groupNames(item.allowed_group_ids || [], groups) || '全部可用分组'}</small>
                        </div>
                      </td>
                    ) : null}
                    {visibleColumns.has('limits') ? (
                      <td>
                        <div className="sub2-cell-stack sub2-cell-stack-tight">
                          <strong>{formatMoneyCents(item.balance_cents || item.user_balance_cents || 0)}</strong>
                          <small>并发 {formatNumber(item.concurrency_limit || item.user_concurrency_limit || 0)} · RPM {formatNumber(item.rpm_limit || item.user_rpm_limit || 0)}</small>
                        </div>
                      </td>
                    ) : null}
                    {visibleColumns.has('keys') ? (
                      <td>
                        <div className="sub2-cell-stack sub2-cell-stack-tight">
                          <strong>{formatNumber(item.active_key_count)} / {formatNumber(item.key_count)}</strong>
                          <small>{item.active_key_count > 0 ? '可调用' : '未配置 Key'}</small>
                        </div>
                      </td>
                    ) : null}
                    {visibleColumns.has('subscriptions') ? (
                      <td>
                        <div className="sub2-cell-stack sub2-cell-stack-tight">
                          <strong>{formatNumber(item.active_subscription_count)} / {formatNumber(item.subscription_count)}</strong>
                          <small>{item.active_subscription_count > 0 ? (item.active_plan_name || '订阅有效') : '无有效订阅'}</small>
                        </div>
                      </td>
                    ) : null}
                    {visibleColumns.has('usage') ? (
                      <td>
                        <div className="sub2-cell-stack sub2-cell-stack-tight">
                          <strong>{formatNumber(item.request_count || 0)} 次</strong>
                          <small>{formatTokenCount(item.total_tokens || 0)} · 错误 {formatNumber(item.error_count || 0)}</small>
                        </div>
                      </td>
                    ) : null}
                    {visibleColumns.has('status') ? (
                      <td>
                        <div className="sub2-cell-stack sub2-cell-stack-tight">
                          <Badge tone={item.enabled === false ? 'warn' : 'ok'}>{item.enabled === false ? '停用' : '启用'}</Badge>
                          <small>{item.password_set || item.user_password_set ? '已设置密码' : '未设置密码'}</small>
                        </div>
                      </td>
                    ) : null}
                    <td>
                      <RowActions>
                        <RowAction icon={Eye} label="详情" onClick={() => setInspectUser(item)} />
                        <RowAction icon={KeyRound} label="Key" onClick={() => setViewKeysUser(item)} />
                        <RowAction icon={Edit} label="编辑" onClick={() => openEdit(item)} />
                        <RowAction icon={ShieldCheck} label={item.enabled === false ? '启用' : '停用'} tone={item.enabled === false ? 'default' : 'warn'} onClick={() => setToggleTarget(item)} />
                        <RowAction icon={KeyRound} label="重置标识" onClick={() => setResetTarget(item)} />
                        <RowAction icon={Trash2} label="删除" tone="danger" onClick={() => setDeleteTarget(item)} />
                      </RowActions>
                    </td>
                  </tr>
                )) : (
                  <ListEmptyRow
                    colSpan={visibleColumns.size + 2}
                    title="暂无用户"
                    action={<Button tone="primary" onClick={openCreate}>新增用户</Button>}
                  />
                )}
              </tbody>
            </table>
          </div>
        }
        pagination={
          filteredRows.length ? (
            <Pager
              page={Math.min(page, totalPages)}
              pageSize={pageSize}
              total={filteredRows.length}
              onPageChange={(next) => setPage(Math.min(Math.max(1, next), totalPages))}
              onPageSizeChange={(next) => { setPageSize(next); setPage(1); }}
            />
          ) : null
        }
      />

      {draft ? (
        <Modal
          title={draft.id ? '编辑用户' : '新增用户'}
          size="lg"
          onClose={() => setDraft(null)}
          footer={
            <ModalActions>
              <Button onClick={() => setDraft(null)}>取消</Button>
              <Button tone="primary" disabled={!draft.name.trim() || createMutation.isPending || updateMutation.isPending} onClick={submitDraft}>
                保存
              </Button>
            </ModalActions>
          }
        >
          <div className="admin-dialog">
            <div className="admin-dialog-grid modal-grid">
              <Field label="邮箱">
                <TextInput value={draft.email} type="email" onChange={(event) => setDraft({ ...draft, email: event.target.value, name: draft.name || event.target.value })} />
              </Field>
              <Field label="用户名">
                <TextInput value={draft.username} onChange={(event) => setDraft({ ...draft, username: event.target.value, name: draft.name || event.target.value })} />
              </Field>
              <Field label="显示名称">
                <TextInput value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} />
              </Field>
              <Field label="密码">
                <div className="inline-form">
                  <TextInput value={draft.password} type="text" onChange={(event) => setDraft({ ...draft, password: event.target.value })} />
                  <Button onClick={() => setDraft({ ...draft, password: randomPassword() })}>生成</Button>
                </div>
              </Field>
              <Field label="角色">
                <Select value={draft.role} onChange={(event) => setDraft({ ...draft, role: event.target.value })}>
                  <option value="user">user</option>
                  <option value="admin">admin</option>
                </Select>
              </Field>
              <Field label="状态">
                <Select value={draft.enabled ? 'enabled' : 'disabled'} onChange={(event) => setDraft({ ...draft, enabled: event.target.value === 'enabled' })}>
                  <option value="enabled">启用</option>
                  <option value="disabled">停用</option>
                </Select>
              </Field>
              <Field label="业务标识">
                <Select value={draft.auto_external_key ? 'auto' : 'manual'} onChange={(event) => setDraft({ ...draft, auto_external_key: event.target.value === 'auto' })}>
                  <option value="auto">系统生成</option>
                  <option value="manual">手工填写</option>
                </Select>
              </Field>
              {!draft.auto_external_key ? (
                <Field label="标识内容">
                  <TextInput value={draft.external_key} onChange={(event) => setDraft({ ...draft, external_key: event.target.value })} />
                </Field>
              ) : null}
              <Field label="余额(分)">
                <TextInput type="number" value={String(draft.balance_cents)} onChange={(event) => setDraft({ ...draft, balance_cents: Number(event.target.value || 0) })} />
              </Field>
              <Field label="并发限制">
                <TextInput type="number" value={String(draft.concurrency_limit)} onChange={(event) => setDraft({ ...draft, concurrency_limit: Number(event.target.value || 0) })} />
              </Field>
              <Field label="RPM 限制">
                <TextInput type="number" value={String(draft.rpm_limit)} onChange={(event) => setDraft({ ...draft, rpm_limit: Number(event.target.value || 0) })} />
              </Field>
              <Field label="备注" full>
                <TextInput value={draft.note} onChange={(event) => setDraft({ ...draft, note: event.target.value })} />
              </Field>
            </div>
            <div className="admin-dialog-section">
              <div className="admin-dialog-section-head">
                <strong>所属分组</strong>
              </div>
              <div className="sub2-check-grid">
                {groups.map((group) => (
                  <label key={group.id} className="sub2-check-item">
                    <input type="checkbox" checked={draft.group_ids.includes(group.id)} onChange={() => toggleGroup('group_ids', group.id)} />
                    <span>{group.name}</span>
                  </label>
                ))}
              </div>
            </div>
            <div className="admin-dialog-section">
              <div className="admin-dialog-section-head">
                <strong>允许分组</strong>
              </div>
              <div className="sub2-check-grid">
                {groups.map((group) => (
                  <label key={group.id} className="sub2-check-item">
                    <input type="checkbox" checked={draft.allowed_group_ids.includes(group.id)} onChange={() => toggleGroup('allowed_group_ids', group.id)} />
                    <span>{group.name}</span>
                  </label>
                ))}
              </div>
            </div>
          </div>
        </Modal>
      ) : null}

      {inspectUser ? (
        <Modal
          title="用户详情"
          size="lg"
          onClose={() => setInspectUser(null)}
          footer={<ModalActions><Button onClick={() => setInspectUser(null)}>关闭</Button></ModalActions>}
        >
          <UserInspect user={inspectUser} groups={groups} />
        </Modal>
      ) : null}

      {viewKeysUser ? (
        <Modal
          title="用户 API Key"
          size="lg"
          onClose={() => setViewKeysUser(null)}
          footer={
            <ModalActions>
              <Button onClick={() => setKeyDraft({ userId: viewKeysUser.id, name: '默认业务 Key', enabled: true })}>新增 Key</Button>
              <Button onClick={() => setViewKeysUser(null)}>关闭</Button>
            </ModalActions>
          }
        >
          <div className="admin-dialog">
            <div className="admin-dialog-intro">
              <strong>{viewKeysUser.email || viewKeysUser.username || viewKeysUser.name}</strong>
            </div>
            <div className="table-wrap table-scroll table-keys">
              <table>
                <thead>
                  <tr>
                    <th>Key 名称</th>
                    <th>预览</th>
                    <th>订阅</th>
                    <th>用量</th>
                    <th>状态</th>
                    <th>操作</th>
                  </tr>
                </thead>
                <tbody>
                  {relatedKeys.length ? relatedKeys.map((item) => (
                    <tr key={item.id}>
                      <td>
                        <div className="sub2-cell-stack sub2-cell-stack-tight">
                          <strong>{item.name}</strong>
                          <small>{item.id}</small>
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
                      <td>
                        <div className="sub2-cell-stack sub2-cell-stack-tight">
                          <strong>{item.subscription_active ? (item.active_plan_name || '订阅有效') : '无可用订阅'}</strong>
                          <small>{item.active_group_name || item.active_group_id || '-'}</small>
                        </div>
                      </td>
                      <td>
                        <div className="sub2-cell-stack sub2-cell-stack-tight">
                          <strong>{formatNumber(item.request_count || 0)} 次</strong>
                          <small>{formatTokenCount(item.total_tokens || 0)} · {formatUsdCost(item.actual_cost || item.total_cost || 0)}</small>
                        </div>
                      </td>
                      <td><Badge tone={item.enabled === false ? 'warn' : 'ok'}>{item.enabled === false ? '停用' : '启用'}</Badge></td>
                      <td>
                        <RowActions>
                          <RowAction icon={ShieldCheck} label={item.enabled === false ? '启用' : '停用'} tone={item.enabled === false ? 'default' : 'warn'} onClick={() => toggleKeyMutation.mutate({ keyId: item.id, enabled: item.enabled === false })} />
                          <RowAction icon={Trash2} label="删除" tone="danger" onClick={() => setDeleteKeyTarget(item)} />
                        </RowActions>
                      </td>
                    </tr>
                  )) : (
                    <ListEmptyRow colSpan={6} title="暂无 API Key" action={<Button tone="primary" onClick={() => setKeyDraft({ userId: viewKeysUser.id, name: '默认业务 Key', enabled: true })}>新增 Key</Button>} />
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </Modal>
      ) : null}

      {keyDraft ? (
        <Modal
          title="新增 API Key"
          size="md"
          onClose={() => setKeyDraft(null)}
          footer={
            <ModalActions>
              <Button onClick={() => setKeyDraft(null)}>取消</Button>
              <Button tone="primary" disabled={!keyDraft.name.trim() || createKeyMutation.isPending} onClick={() => createKeyMutation.mutate({ user_id: keyDraft.userId, name: keyDraft.name, enabled: keyDraft.enabled })}>生成</Button>
            </ModalActions>
          }
        >
          <div className="admin-dialog">
            <div className="admin-dialog-grid">
              <Field label="Key 名称">
                <TextInput value={keyDraft.name} onChange={(event) => setKeyDraft({ ...keyDraft, name: event.target.value })} />
              </Field>
              <Field label="状态">
                <Select value={keyDraft.enabled ? 'enabled' : 'disabled'} onChange={(event) => setKeyDraft({ ...keyDraft, enabled: event.target.value === 'enabled' })}>
                  <option value="enabled">启用</option>
                  <option value="disabled">停用</option>
                </Select>
              </Field>
            </div>
          </div>
        </Modal>
      ) : null}

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
          <div className="generated-key-box generated-key-floating">
            <div className="generated-key-title">原始 Key</div>
            <div className="generated-key-row">
              <div className="generated-key-value">{generatedKey}</div>
              <Button onClick={() => copyText(generatedKey)}>复制</Button>
            </div>
          </div>
        </Modal>
      ) : null}

      {toggleTarget ? (
        <Modal
          title={toggleTarget.enabled === false ? '启用用户' : '停用用户'}
          size="md"
          onClose={() => setToggleTarget(null)}
          footer={
            <ModalActions>
              <Button onClick={() => setToggleTarget(null)}>取消</Button>
              <Button tone="primary" disabled={toggleMutation.isPending} onClick={() => toggleMutation.mutate({ userId: toggleTarget.id, enabled: toggleTarget.enabled === false })}>
                确认
              </Button>
            </ModalActions>
          }
        >
          <div className="admin-dialog"><div className="admin-dialog-intro"><strong>{toggleTarget.name}</strong></div></div>
        </Modal>
      ) : null}

      {resetTarget ? (
        <Modal
          title="重置业务标识"
          size="md"
          onClose={() => setResetTarget(null)}
          footer={
            <ModalActions>
              <Button onClick={() => setResetTarget(null)}>取消</Button>
              <Button tone="primary" disabled={resetMutation.isPending} onClick={() => resetMutation.mutate(resetTarget.id)}>
                确认
              </Button>
            </ModalActions>
          }
        >
          <div className="admin-dialog"><div className="admin-dialog-intro"><strong>{resetTarget.name}</strong></div></div>
        </Modal>
      ) : null}

      {deleteTarget ? (
        <Modal
          title="删除用户"
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
          <div className="admin-dialog"><div className="admin-dialog-intro"><strong>{deleteTarget.name}</strong></div></div>
        </Modal>
      ) : null}

      {deleteKeyTarget ? (
        <Modal
          title="删除 API Key"
          size="md"
          onClose={() => setDeleteKeyTarget(null)}
          footer={
            <ModalActions>
              <Button onClick={() => setDeleteKeyTarget(null)}>取消</Button>
              <Button tone="danger" disabled={deleteKeyMutation.isPending} onClick={() => deleteKeyMutation.mutate(deleteKeyTarget.id)}>
                删除
              </Button>
            </ModalActions>
          }
        >
          <div className="admin-dialog"><div className="admin-dialog-intro"><strong>{deleteKeyTarget.name}</strong></div></div>
        </Modal>
      ) : null}
    </section>
  );
}

function UserInspect({ user, groups }: { user: AdminUser; groups: Array<{ id: string; name: string }> }) {
  return (
    <div className="admin-dialog">
      <div className="admin-dialog-intro">
        <strong>{user.email || user.user_email || user.username || user.user_username || user.name}</strong>
      </div>
      <div className="admin-dialog-summary">
        <div className="admin-dialog-summary-card">
          <span>余额</span>
          <strong>{formatMoneyCents(user.balance_cents || user.user_balance_cents || 0)}</strong>
          <small>并发 {formatNumber(user.concurrency_limit || user.user_concurrency_limit || 0)}</small>
        </div>
        <div className="admin-dialog-summary-card">
          <span>订阅</span>
          <strong>{formatNumber(user.active_subscription_count || 0)} / {formatNumber(user.subscription_count || 0)}</strong>
          <small>{user.active_plan_name || '无有效订阅'}</small>
        </div>
        <div className="admin-dialog-summary-card">
          <span>API Key</span>
          <strong>{formatNumber(user.active_key_count || 0)} / {formatNumber(user.key_count || 0)}</strong>
          <small>{user.enabled === false ? '停用' : '启用'}</small>
        </div>
      </div>
      <div className="admin-dialog-grid">
        <Field label="用户 ID"><TextInput readOnly value={user.id || '-'} /></Field>
        <Field label="业务标识"><TextInput readOnly value={user.external_key || user.user_key || '-'} /></Field>
        <Field label="邮箱"><TextInput readOnly value={user.email || user.user_email || '-'} /></Field>
        <Field label="用户名"><TextInput readOnly value={user.username || user.user_username || '-'} /></Field>
        <Field label="角色"><TextInput readOnly value={user.role || user.user_role || 'user'} /></Field>
        <Field label="RPM"><TextInput readOnly value={formatNumber(user.rpm_limit || user.user_rpm_limit || 0)} /></Field>
        <Field label="所属分组"><TextInput readOnly value={groupNames(user.group_ids || (user.group_id ? [user.group_id] : []), groups) || '未分组'} /></Field>
        <Field label="允许分组"><TextInput readOnly value={groupNames(user.allowed_group_ids || user.user_allowed_group_ids || [], groups) || '全部可用分组'} /></Field>
        <Field label="请求次数"><TextInput readOnly value={formatNumber(user.request_count || 0)} /></Field>
        <Field label="总 Token"><TextInput readOnly value={formatTokenCount(user.total_tokens || 0)} /></Field>
        <Field label="错误次数"><TextInput readOnly value={formatNumber(user.error_count || 0)} /></Field>
        <Field label="最近使用"><TextInput readOnly value={user.last_seen_at || '-'} /></Field>
      </div>
    </div>
  );
}

function groupNames(ids: string[], groups: Array<{ id: string; name: string }>) {
  const names = ids
    .map((id) => groups.find((group) => group.id === id)?.name || id)
    .filter(Boolean);
  return names.join('、');
}

function formatMoneyCents(value: unknown) {
  const cents = Number(value || 0);
  if (!Number.isFinite(cents)) return '￥0.00';
  return `￥${(cents / 100).toFixed(2)}`;
}

function randomPassword() {
  const chars = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz23456789!@#$%^&*';
  let value = '';
  for (let index = 0; index < 16; index += 1) value += chars.charAt(Math.floor(Math.random() * chars.length));
  return value;
}
