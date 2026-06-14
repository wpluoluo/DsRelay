import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Ban, Copy, Edit, Eye, History, KeyRound, ListChecks, Minus, Plus, RefreshCw, ShieldCheck, Ticket, Trash2, Users, Wallet } from 'lucide-react';
import {
  adjustAdminAccountBalance,
  assignAdminAccountSubscription,
  createAdminApiKey,
  createAdminAccount,
  deleteAdminApiKey,
  deleteAdminAccount,
  fetchAdminApiKeys,
  fetchAdminGroups,
  fetchAdminSubscriptionPlans,
  fetchAdminAccountBalanceEvents,
  fetchAdminUsage,
  fetchAdminAccounts,
  fetchAdminAccountSubscriptions,
  resetAdminAccountExternalKey,
  setAdminApiKeyEnabled,
  setAdminAccountEnabled,
  updateAdminApiKey,
  updateAdminAccount,
} from '../api';
import { Badge, Button, Field, Modal, ModalActions, Select, TextArea, TextInput } from '../components';
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
import { buildPageIntro } from '../navigation';
import { queryClient } from '../state/queryClient';
import type { AdminApiKey, AdminBalanceEvent, AdminAccount } from '../types';
import { copyTextToClipboard, formatByteCount, formatNumber, formatTokenCount, formatUsdCost, getAccountId, readStorageJSON, writeStorageJSON } from '../utils';

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
  accountId: string;
  name: string;
  groupId: string;
  enabled: boolean;
};

type SubscriptionDraft = {
  accountId: string;
  planId: string;
  status: string;
};

type GroupAccessDraft = {
  accountId: string;
  group_ids: string[];
  allowed_group_ids: string[];
};

type BalanceDraft = {
  accountId: string;
  operation: 'deposit' | 'withdraw';
  amount_cents: number;
  note: string;
};

type CoverageFilter = 'all' | 'subscribed' | 'uncovered';
type StatusFilter = '' | 'enabled' | 'disabled';
type RoleFilter = '' | 'admin' | 'user';
type UserFilterKey = 'role' | 'status' | 'group' | 'subscription';
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
const DEFAULT_VISIBLE_FILTERS: UserFilterKey[] = ['role', 'status', 'group', 'subscription'];
const STORAGE_KEY = 'admin-users-view-state';

export function AdminUsersPage() {
  const usersQuery = useQuery({ queryKey: ['admin-users'], queryFn: fetchAdminAccounts, refetchInterval: 10000 });
  const groupsQuery = useQuery({ queryKey: ['admin-groups'], queryFn: fetchAdminGroups, refetchInterval: 10000 });
  const plansQuery = useQuery({ queryKey: ['admin-subscription-plans'], queryFn: fetchAdminSubscriptionPlans, refetchInterval: 10000 });

  const savedState = readStorageJSON(STORAGE_KEY, {
    search: '',
    coverageFilter: 'all' as CoverageFilter,
    statusFilter: '' as StatusFilter,
    roleFilter: '' as RoleFilter,
    groupFilter: '',
    pageSize: 20,
    visibleColumns: DEFAULT_VISIBLE_COLUMNS,
    visibleFilters: DEFAULT_VISIBLE_FILTERS,
  });

  const [search, setSearch] = useState(savedState.search);
  const [coverageFilter, setCoverageFilter] = useState<CoverageFilter>(savedState.coverageFilter || 'all');
  const [statusFilter, setStatusFilter] = useState<StatusFilter>(savedState.statusFilter || '');
  const [roleFilter, setRoleFilter] = useState<RoleFilter>(savedState.roleFilter || '');
  const [groupFilter, setGroupFilter] = useState(savedState.groupFilter || '');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(savedState.pageSize || 20);
  const [visibleColumns, setVisibleColumns] = useState<Set<UserColumnKey>>(new Set(savedState.visibleColumns || DEFAULT_VISIBLE_COLUMNS));
  const [visibleFilters, setVisibleFilters] = useState<Set<UserFilterKey>>(new Set(savedState.visibleFilters || DEFAULT_VISIBLE_FILTERS));
  const [draft, setDraft] = useState<UserDraft | null>(null);
  const [inspectUser, setInspectUser] = useState<AdminAccount | null>(null);
  const [viewKeysUser, setViewKeysUser] = useState<AdminAccount | null>(null);
  const [viewSubscriptionsUser, setViewSubscriptionsUser] = useState<AdminAccount | null>(null);
  const [viewUsageUser, setViewUsageUser] = useState<AdminAccount | null>(null);
  const [groupAccessDraft, setGroupAccessDraft] = useState<GroupAccessDraft | null>(null);
  const [balanceDraft, setBalanceDraft] = useState<BalanceDraft | null>(null);
  const [balanceHistoryUser, setBalanceHistoryUser] = useState<AdminAccount | null>(null);
  const [keyDraft, setKeyDraft] = useState<KeyDraft | null>(null);
  const [subscriptionDraft, setSubscriptionDraft] = useState<SubscriptionDraft | null>(null);
  const [generatedKey, setGeneratedKey] = useState('');
  const [copiedKeyId, setCopiedKeyId] = useState('');
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [bulkBusy, setBulkBusy] = useState('');
  const [toggleTarget, setToggleTarget] = useState<AdminAccount | null>(null);
  const [resetTarget, setResetTarget] = useState<AdminAccount | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<AdminAccount | null>(null);
  const [deleteKeyTarget, setDeleteKeyTarget] = useState<AdminApiKey | null>(null);

  const createMutation = useMutation({
    mutationFn: createAdminAccount,
    onSuccess: async () => {
      setDraft(null);
      await refreshAll();
    },
  });
  const updateMutation = useMutation({
    mutationFn: ({ accountId, payload }: { accountId: string; payload: Record<string, unknown> }) => updateAdminAccount(accountId, payload),
    onSuccess: async () => {
      setDraft(null);
      await refreshAll();
    },
  });
  const toggleMutation = useMutation({
    mutationFn: ({ accountId, enabled }: { accountId: string; enabled: boolean }) => setAdminAccountEnabled(accountId, enabled),
    onSuccess: async () => {
      setToggleTarget(null);
      await refreshAll();
    },
  });
  const resetMutation = useMutation({
    mutationFn: (accountId: string) => resetAdminAccountExternalKey(accountId),
    onSuccess: async () => {
      setResetTarget(null);
      await refreshAll();
    },
  });
  const deleteMutation = useMutation({
    mutationFn: (accountId: string) => deleteAdminAccount(accountId),
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
  const updateKeyMutation = useMutation({
    mutationFn: ({ keyId, payload }: { keyId: string; payload: Record<string, unknown> }) => updateAdminApiKey(keyId, payload),
    onSuccess: async () => {
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
  const assignSubscriptionMutation = useMutation({
    mutationFn: assignAdminAccountSubscription,
    onSuccess: async () => {
      setSubscriptionDraft(null);
      await refreshAll();
    },
  });
  const groupAccessMutation = useMutation({
    mutationFn: ({ accountId, payload }: { accountId: string; payload: Record<string, unknown> }) => updateAdminAccount(accountId, payload),
    onSuccess: async () => {
      setGroupAccessDraft(null);
      await refreshAll();
    },
  });
  const balanceMutation = useMutation({
    mutationFn: ({ accountId, payload }: { accountId: string; payload: Record<string, unknown> }) => adjustAdminAccountBalance(accountId, payload),
    onSuccess: async () => {
      const targetAccountId = balanceDraft?.accountId || '';
      setBalanceDraft(null);
      await refreshAll();
      if (targetAccountId) {
        await queryClient.invalidateQueries({ queryKey: ['admin-account-balance-events', targetAccountId] });
      }
    },
  });

  const groups = groupsQuery.data?.items || [];
  const planItems = plansQuery.data?.items || [];
  const keysQuery = useQuery({
    queryKey: ['admin-api-keys', viewKeysUser?.id || ''],
    queryFn: () => fetchAdminApiKeys({ account_id: viewKeysUser?.id || '' }),
    enabled: Boolean(viewKeysUser?.id),
    refetchInterval: 10000,
  });
  const subscriptionsQuery = useQuery({
    queryKey: ['admin-account-subscriptions', viewSubscriptionsUser?.id || ''],
    queryFn: () => fetchAdminAccountSubscriptions({ account_id: viewSubscriptionsUser?.id || '' }),
    enabled: Boolean(viewSubscriptionsUser?.id),
    refetchInterval: 10000,
  });
  const usageQuery = useQuery({
    queryKey: ['admin-usage', viewUsageUser?.id || ''],
    queryFn: () => fetchAdminUsage({ account_id: viewUsageUser?.id || '', limit: 50 }),
    enabled: Boolean(viewUsageUser?.id),
    refetchInterval: 10000,
  });
  const balanceEventsQuery = useQuery({
    queryKey: ['admin-account-balance-events', balanceHistoryUser?.id || ''],
    queryFn: () => fetchAdminAccountBalanceEvents(balanceHistoryUser?.id || ''),
    enabled: Boolean(balanceHistoryUser?.id),
    refetchInterval: 10000,
  });
  const balanceEvents = balanceEventsQuery.data?.items || [];
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
      if (roleFilter && (item.role || 'user') !== roleFilter) return false;
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
  }, [coverageFilter, groupFilter, roleFilter, rows, search, statusFilter]);

  const totalPages = Math.max(1, Math.ceil(filteredRows.length / pageSize));
  const pagedRows = useMemo(() => {
    const start = (page - 1) * pageSize;
    return filteredRows.slice(start, start + pageSize);
  }, [filteredRows, page, pageSize]);
  const selectedUsers = useMemo(() => rows.filter((item) => selectedIds.has(item.id)), [rows, selectedIds]);
  const selectedMutableUsers = useMemo(() => selectedUsers.filter((item) => (item.role || 'user') !== 'admin'), [selectedUsers]);
  const allPageSelected = pagedRows.length > 0 && pagedRows.every((item) => selectedIds.has(item.id));

  const relatedKeys = keysQuery.data?.items || [];
  const relatedSubscriptions = subscriptionsQuery.data?.items || [];
  const relatedUsage = usageQuery.data?.items || [];
  const keyOwner = keyDraft ? rows.find((item) => item.id === keyDraft.accountId) : null;
  const keyGroupOptions = useMemo(() => {
    if (!keyOwner) return groups;
    const allowedIds = keyOwner.allowed_group_ids || [];
    if (!allowedIds.length) return groups;
    return groups.filter((group) => allowedIds.includes(group.id));
  }, [groups, keyOwner]);

  useEffect(() => {
    writeStorageJSON(STORAGE_KEY, {
      search,
      coverageFilter,
      statusFilter,
      roleFilter,
      groupFilter,
      pageSize,
      visibleColumns: Array.from(visibleColumns),
      visibleFilters: Array.from(visibleFilters),
    });
  }, [coverageFilter, groupFilter, pageSize, roleFilter, search, statusFilter, visibleColumns, visibleFilters]);

  useEffect(() => {
    const validIds = new Set(rows.map((item) => item.id));
    setSelectedIds((current) => {
      const next = new Set(Array.from(current).filter((id) => validIds.has(id)));
      return next.size === current.size ? current : next;
    });
  }, [rows]);

  async function refreshAll() {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['admin-users'] }),
      queryClient.invalidateQueries({ queryKey: ['admin-api-keys'] }),
      queryClient.invalidateQueries({ queryKey: ['admin-account-subscriptions'] }),
      queryClient.invalidateQueries({ queryKey: ['admin-subscription-plans'] }),
      queryClient.invalidateQueries({ queryKey: ['admin-usage'] }),
    ]);
  }

  function openCreate() {
    setDraft({ ...EMPTY_DRAFT, password: randomPassword() });
  }

  function openEdit(user: AdminAccount) {
    setDraft({
      id: user.id,
      name: user.name || '',
      email: user.email || '',
      username: user.username || '',
      password: '',
      external_key: user.external_key || '',
      auto_external_key: false,
      group_ids: user.group_ids || (user.group_id ? [user.group_id] : []),
      allowed_group_ids: user.allowed_group_ids || [],
      role: user.role || 'user',
      balance_cents: Number(user.balance_cents ?? 0),
      concurrency_limit: Number(user.concurrency_limit ?? 1),
      rpm_limit: Number(user.rpm_limit ?? 0),
      note: user.note || '',
      enabled: user.enabled !== false,
    });
  }

  function openGroupAccess(user: AdminAccount) {
    setGroupAccessDraft({
      accountId: user.id,
      group_ids: user.group_ids || (user.group_id ? [user.group_id] : []),
      allowed_group_ids: user.allowed_group_ids || [],
    });
  }

  function openBalance(user: AdminAccount, operation: 'deposit' | 'withdraw') {
    setBalanceDraft({ accountId: user.id, operation, amount_cents: 0, note: '' });
  }

  function openBalanceFromHistory(user: AdminAccount, operation: 'deposit' | 'withdraw') {
    setBalanceHistoryUser(null);
    setBalanceDraft({ accountId: user.id, operation, amount_cents: 0, note: '' });
  }

  function submitGroupAccess() {
    if (!groupAccessDraft) return;
    groupAccessMutation.mutate({
      accountId: groupAccessDraft.accountId,
      payload: {
        group_ids: groupAccessDraft.group_ids,
        allowed_group_ids: groupAccessDraft.allowed_group_ids,
      },
    });
  }

  function submitBalance() {
    if (!balanceDraft || balanceDraft.amount_cents <= 0) return;
    balanceMutation.mutate({
      accountId: balanceDraft.accountId,
      payload: {
        operation: balanceDraft.operation,
        amount_cents: balanceDraft.amount_cents,
        note: balanceDraft.note,
      },
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
      updateMutation.mutate({ accountId: draft.id, payload });
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

  function toggleFilter(key: UserFilterKey) {
    setVisibleFilters((current) => {
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

  function toggleGroupAccess(field: 'group_ids' | 'allowed_group_ids', groupId: string) {
    if (!groupAccessDraft) return;
    const values = new Set(groupAccessDraft[field]);
    if (values.has(groupId)) values.delete(groupId);
    else values.add(groupId);
    setGroupAccessDraft({ ...groupAccessDraft, [field]: Array.from(values) });
  }

  async function copyText(value: string, keyId?: string) {
    const ok = await copyTextToClipboard(value);
    if (!ok) return;
    if (keyId) {
      setCopiedKeyId(keyId);
      window.setTimeout(() => setCopiedKeyId(''), 1200);
    }
  }

  function toggleSelected(accountId: string) {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (next.has(accountId)) next.delete(accountId);
      else next.add(accountId);
      return next;
    });
  }

  function togglePageSelected() {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (allPageSelected) {
        for (const item of pagedRows) next.delete(item.id);
      } else {
        for (const item of pagedRows) next.add(item.id);
      }
      return next;
    });
  }

  async function runBulkAction(action: 'enable' | 'disable' | 'delete') {
    const targets = action === 'delete' ? selectedMutableUsers : selectedMutableUsers;
    if (!targets.length) return;
    setBulkBusy(action);
    try {
      if (action === 'delete') {
        await Promise.all(targets.map((item) => deleteAdminAccount(item.id)));
      } else {
        const enabled = action === 'enable';
        await Promise.all(targets.map((item) => setAdminAccountEnabled(item.id, enabled)));
      }
      setSelectedIds(new Set());
      await refreshAll();
    } finally {
      setBulkBusy('');
    }
  }

  return (
    <section className="grid-page">
      {buildPageIntro('/admin/users')}
      <TablePageLayout
        filters={
          <FilterToolbar
            right={
              <ToolbarButtonRow>
                <ActionButton onClick={() => { void usersQuery.refetch(); void groupsQuery.refetch(); void keysQuery.refetch(); }}>
                  <RefreshCw size={15} />
                  刷新
                </ActionButton>
                <ToolsMenu label="筛选设置" icon={false}>
                  <button type="button" onClick={() => toggleFilter('role')}>
                    <span>角色</span>
                    <strong>{visibleFilters.has('role') ? '✓' : ''}</strong>
                  </button>
                  <button type="button" onClick={() => toggleFilter('status')}>
                    <span>状态</span>
                    <strong>{visibleFilters.has('status') ? '✓' : ''}</strong>
                  </button>
                  <button type="button" onClick={() => toggleFilter('group')}>
                    <span>分组</span>
                    <strong>{visibleFilters.has('group') ? '✓' : ''}</strong>
                  </button>
                  <button type="button" onClick={() => toggleFilter('subscription')}>
                    <span>订阅状态</span>
                    <strong>{visibleFilters.has('subscription') ? '✓' : ''}</strong>
                  </button>
                </ToolsMenu>
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
                  <button type="button" onClick={() => { setSearch(''); setCoverageFilter('all'); setStatusFilter(''); setRoleFilter(''); setGroupFilter(''); setPage(1); }}>
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
                <Button tone="primary" data-tour="users-create-btn" onClick={openCreate}>
                  <Plus size={15} />
                  添加用户
                </Button>
              </ToolbarButtonRow>
            }
          >
            <SearchField value={search} placeholder="搜索邮箱 / 用户名 / 名称 / 调用标识" onChange={(value) => { setSearch(value); setPage(1); }} />
            {visibleFilters.has('role') ? (
              <Select value={roleFilter} onChange={(event) => { setRoleFilter(event.target.value as RoleFilter); setPage(1); }}>
                <option value="">全部角色</option>
                <option value="admin">管理员</option>
                <option value="user">用户</option>
              </Select>
            ) : null}
            {visibleFilters.has('status') ? (
              <Select value={statusFilter} onChange={(event) => { setStatusFilter(event.target.value as StatusFilter); setPage(1); }}>
                <option value="">全部状态</option>
                <option value="enabled">启用</option>
                <option value="disabled">停用</option>
              </Select>
            ) : null}
            {visibleFilters.has('group') ? (
              <Select value={groupFilter} onChange={(event) => { setGroupFilter(event.target.value); setPage(1); }}>
                <option value="">全部分组</option>
                {groups.map((group) => <option key={group.id} value={group.id}>{group.name}</option>)}
              </Select>
            ) : null}
            {visibleFilters.has('subscription') ? (
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
            ) : null}
          </FilterToolbar>
        }
        table={
          <div className="table-wrap table-scroll table-users">
            {selectedIds.size ? (
              <div className="sub2-bulk-bar">
                <strong>已选择 {formatNumber(selectedIds.size)} 个用户</strong>
                <div className="button-row">
                  <Button onClick={() => void runBulkAction('enable')} disabled={!selectedMutableUsers.length || bulkBusy === 'enable'}>
                    <ShieldCheck size={14} />
                    启用
                  </Button>
                  <Button tone="danger" onClick={() => void runBulkAction('disable')} disabled={!selectedMutableUsers.length || bulkBusy === 'disable'}>
                    <Ban size={14} />
                    停用
                  </Button>
                  <Button tone="danger" onClick={() => void runBulkAction('delete')} disabled={!selectedMutableUsers.length || bulkBusy === 'delete'}>
                    <Trash2 size={14} />
                    删除
                  </Button>
                  <Button onClick={() => setSelectedIds(new Set())}>取消选择</Button>
                </div>
              </div>
            ) : null}
            <table>
              <thead>
                <tr>
                  <th><input type="checkbox" checked={allPageSelected} onChange={togglePageSelected} aria-label="选择当前页用户" /></th>
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
                    <td><input type="checkbox" checked={selectedIds.has(item.id)} onChange={() => toggleSelected(item.id)} aria-label={`选择 ${item.email || item.username || item.name}`} /></td>
                    <td>
                      <div className="sub2-cell-stack sub2-cell-stack-tight">
                        <strong>{item.email || item.name}</strong>
                        <small>{item.username || item.name}</small>
                      </div>
                    </td>
                    {visibleColumns.has('identity') ? (
                      <td>
                        <div className="sub2-cell-stack sub2-cell-stack-tight">
                          <strong>{item.external_key || '-'}</strong>
                          <small>{item.role || 'user'} · {item.id}</small>
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
                          <strong>{formatMoneyCents(item.balance_cents || 0)}</strong>
                          <small>并发 {formatNumber(item.concurrency_limit || 0)} · RPM {formatNumber(item.rpm_limit || 0)}</small>
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
                          <small>{item.password_set ? '已设置密码' : '未设置密码'}</small>
                        </div>
                      </td>
                    ) : null}
                    <td className="row-actions-cell">
                      <RowActions>
                        <RowAction icon={Edit} label="编辑" onClick={() => openEdit(item)} />
                        {(item.role || 'user') !== 'admin' ? (
                          <RowAction
                            icon={item.enabled === false ? ShieldCheck : Ban}
                            label={item.enabled === false ? '启用' : '停用'}
                            tone={item.enabled === false ? 'default' : 'warn'}
                            onClick={() => setToggleTarget(item)}
                          />
                        ) : null}
                        <ToolsMenu label="更多">
                          <button type="button" onClick={() => setInspectUser(item)}><span>详情</span><Eye size={14} /></button>
                          <button type="button" onClick={() => setViewKeysUser(item)}><span>API Key</span><KeyRound size={14} /></button>
                          <button type="button" onClick={() => openGroupAccess(item)}><span>允许分组</span><Users size={14} /></button>
                          <button type="button" onClick={() => openBalance(item, 'deposit')}><span>充值</span><Wallet size={14} /></button>
                          <button type="button" onClick={() => openBalance(item, 'withdraw')}><span>扣款</span><Minus size={14} /></button>
                          <button type="button" onClick={() => setBalanceHistoryUser(item)}><span>余额历史</span><History size={14} /></button>
                          <button type="button" onClick={() => setViewSubscriptionsUser(item)}><span>订阅</span><Ticket size={14} /></button>
                          <button type="button" onClick={() => setViewUsageUser(item)}><span>使用记录</span><ListChecks size={14} /></button>
                          <button type="button" onClick={() => setResetTarget(item)}><span>重置调用标识</span><KeyRound size={14} /></button>
                          {(item.role || 'user') !== 'admin' ? (
                            <button type="button" className="danger" onClick={() => setDeleteTarget(item)}><span>删除</span><Trash2 size={14} /></button>
                          ) : null}
                        </ToolsMenu>
                      </RowActions>
                    </td>
                  </tr>
                )) : (
                  <ListEmptyRow
                    colSpan={visibleColumns.size + 3}
                    title="暂无用户"
                    action={<Button tone="primary" data-tour="users-create-btn" onClick={openCreate}>添加用户</Button>}
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
          title={draft.id ? '编辑用户' : '添加用户'}
          size="lg"
          onClose={() => setDraft(null)}
          footer={
            <ModalActions>
              <Button onClick={() => setDraft(null)}>取消</Button>
              <Button tone="primary" disabled={!(draft.name.trim() || draft.email.trim() || draft.username.trim()) || createMutation.isPending || updateMutation.isPending} onClick={submitDraft}>
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
              <Field label="调用标识">
                <Select value={draft.auto_external_key ? 'auto' : 'manual'} onChange={(event) => setDraft({ ...draft, auto_external_key: event.target.value === 'auto' })}>
                  <option value="auto">系统生成</option>
                  <option value="manual">手工填写</option>
                </Select>
              </Field>
              {!draft.auto_external_key ? (
                <Field label="密钥内容">
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
              <Button onClick={() => setKeyDraft({ accountId: viewKeysUser.id, name: '默认业务 Key', groupId: '', enabled: true })}>添加 Key</Button>
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
                    <th>分组</th>
                    <th>订阅</th>
                    <th>用量</th>
                    <th>状态</th>
                    <th>操作</th>
                  </tr>
                </thead>
                <tbody>
                  {keysQuery.isLoading ? (
                    <ListEmptyRow colSpan={7} title="加载中" />
                  ) : relatedKeys.length ? relatedKeys.map((item) => (
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
                        <Select
                          value={item.group_id || ''}
                          disabled={updateKeyMutation.isPending}
                          onChange={(event) => updateKeyMutation.mutate({ keyId: item.id, payload: { group_id: event.target.value } })}
                        >
                          <option value="">未绑定</option>
                          {keyGroupOptions.map((group) => <option key={group.id} value={group.id}>{group.name}</option>)}
                        </Select>
                      </td>
                      <td>
                        <div className="sub2-cell-stack sub2-cell-stack-tight">
                          <strong>{item.subscription_active ? (item.active_plan_name || '订阅有效') : '无可用订阅'}</strong>
                          <small>{item.group_name || item.group_id || item.active_group_name || item.active_group_id || '-'}</small>
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
                    <ListEmptyRow colSpan={7} title="暂无 API Key" action={<Button tone="primary" onClick={() => setKeyDraft({ accountId: viewKeysUser.id, name: '默认业务 Key', groupId: '', enabled: true })}>添加 Key</Button>} />
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </Modal>
      ) : null}

      {keyDraft ? (
        <Modal
          title="添加 API Key"
          size="md"
          onClose={() => setKeyDraft(null)}
          footer={
            <ModalActions>
              <Button onClick={() => setKeyDraft(null)}>取消</Button>
              <Button
                tone="primary"
                disabled={createKeyMutation.isPending}
                onClick={() => createKeyMutation.mutate({
                  account_id: keyDraft.accountId,
                  ...(keyDraft.name.trim() ? { name: keyDraft.name.trim() } : {}),
                  group_id: keyDraft.groupId,
                  enabled: keyDraft.enabled,
                })}
              >
                生成
              </Button>
            </ModalActions>
          }
        >
          <div className="admin-dialog">
            <div className="admin-dialog-grid">
              <Field label="Key 名称">
                <TextInput value={keyDraft.name} placeholder="默认业务 Key" onChange={(event) => setKeyDraft({ ...keyDraft, name: event.target.value })} />
              </Field>
              <Field label="分组">
                <Select value={keyDraft.groupId} onChange={(event) => setKeyDraft({ ...keyDraft, groupId: event.target.value })}>
                  <option value="">未绑定</option>
                  {keyGroupOptions.map((group) => <option key={group.id} value={group.id}>{group.name}</option>)}
                </Select>
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

      {groupAccessDraft ? (
        <Modal
          title="允许分组"
          size="lg"
          onClose={() => setGroupAccessDraft(null)}
          footer={
            <ModalActions>
              <Button onClick={() => setGroupAccessDraft(null)}>取消</Button>
              <Button tone="primary" disabled={groupAccessMutation.isPending} onClick={submitGroupAccess}>保存</Button>
            </ModalActions>
          }
        >
          <div className="admin-dialog">
            <div className="admin-dialog-grid modal-grid">
              <div className="admin-dialog-section">
                <div className="admin-dialog-section-head"><strong>所属分组</strong></div>
                <div className="sub2-check-grid">
                  {groups.map((group) => (
                    <label key={group.id} className="sub2-check-item">
                      <input type="checkbox" checked={groupAccessDraft.group_ids.includes(group.id)} onChange={() => toggleGroupAccess('group_ids', group.id)} />
                      <span>{group.name}</span>
                    </label>
                  ))}
                </div>
              </div>
              <div className="admin-dialog-section">
                <div className="admin-dialog-section-head"><strong>允许分组</strong></div>
                <div className="sub2-check-grid">
                  {groups.map((group) => (
                    <label key={group.id} className="sub2-check-item">
                      <input type="checkbox" checked={groupAccessDraft.allowed_group_ids.includes(group.id)} onChange={() => toggleGroupAccess('allowed_group_ids', group.id)} />
                      <span>{group.name}</span>
                    </label>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </Modal>
      ) : null}

      {balanceDraft ? (
        <Modal
          title={balanceDraft.operation === 'deposit' ? '充值' : '扣款'}
          size="md"
          onClose={() => setBalanceDraft(null)}
          footer={
            <ModalActions>
              <Button onClick={() => setBalanceDraft(null)}>取消</Button>
              <Button tone={balanceDraft.operation === 'deposit' ? 'primary' : 'danger'} disabled={balanceDraft.amount_cents <= 0 || balanceMutation.isPending} onClick={submitBalance}>
                确认
              </Button>
            </ModalActions>
          }
        >
          <div className="admin-dialog">
            <div className="admin-dialog-grid">
              <Field label="金额(分)">
                <TextInput type="number" min="1" value={String(balanceDraft.amount_cents)} onChange={(event) => setBalanceDraft({ ...balanceDraft, amount_cents: Number(event.target.value || 0) })} />
              </Field>
              <Field label="类型">
                <Select value={balanceDraft.operation} onChange={(event) => setBalanceDraft({ ...balanceDraft, operation: event.target.value as 'deposit' | 'withdraw' })}>
                  <option value="deposit">充值</option>
                  <option value="withdraw">扣款</option>
                </Select>
              </Field>
              <Field label="备注" full>
                <TextArea rows={3} value={balanceDraft.note} onChange={(event) => setBalanceDraft({ ...balanceDraft, note: event.target.value })} />
              </Field>
            </div>
          </div>
        </Modal>
      ) : null}

      {balanceHistoryUser ? (
        <Modal
          title="余额历史"
          size="lg"
          onClose={() => setBalanceHistoryUser(null)}
          footer={
            <ModalActions>
              <Button onClick={() => openBalanceFromHistory(balanceHistoryUser, 'deposit')}>充值</Button>
              <Button onClick={() => openBalanceFromHistory(balanceHistoryUser, 'withdraw')}>扣款</Button>
              <Button onClick={() => setBalanceHistoryUser(null)}>关闭</Button>
            </ModalActions>
          }
        >
          <BalanceHistoryPanel
            user={balanceHistoryUser}
            events={balanceEvents}
            loading={balanceEventsQuery.isLoading}
            onDeposit={() => openBalanceFromHistory(balanceHistoryUser, 'deposit')}
            onWithdraw={() => openBalanceFromHistory(balanceHistoryUser, 'withdraw')}
          />
        </Modal>
      ) : null}

      {viewSubscriptionsUser ? (
        <Modal
          title="用户订阅"
          size="lg"
          onClose={() => setViewSubscriptionsUser(null)}
          footer={
            <ModalActions>
              <Button onClick={() => setSubscriptionDraft({ accountId: viewSubscriptionsUser.id, planId: '', status: 'active' })}>分配订阅</Button>
              <Button onClick={() => setViewSubscriptionsUser(null)}>关闭</Button>
            </ModalActions>
          }
        >
          <div className="admin-dialog">
            <div className="admin-dialog-intro">
              <strong>{viewSubscriptionsUser.email || viewSubscriptionsUser.username || viewSubscriptionsUser.name}</strong>
            </div>
            <div className="table-wrap table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>订阅</th>
                    <th>计划</th>
                    <th>分组</th>
                    <th>日额度</th>
                    <th>状态</th>
                  </tr>
                </thead>
                <tbody>
                  {subscriptionsQuery.isLoading ? (
                    <ListEmptyRow colSpan={5} title="加载中" />
                  ) : relatedSubscriptions.length ? relatedSubscriptions.map((item) => (
                    <tr key={item.id}>
                      <td><div className="sub2-cell-stack sub2-cell-stack-tight"><strong>{item.id}</strong><small>{formatTime(item.expires_at)}</small></div></td>
                      <td><div className="sub2-cell-stack sub2-cell-stack-tight"><strong>{item.plan_name || item.plan_id}</strong><small>{formatMoneyCents(item.price_cents || 0)}</small></div></td>
                      <td>{item.group_name || item.group_id || '-'}</td>
                      <td><div className="sub2-cell-stack sub2-cell-stack-tight"><strong>{formatNumber(item.daily_used || 0)} / {formatNumber(item.daily_limit || 0)}</strong><small>周 {formatNumber(item.weekly_used || 0)} / 月 {formatNumber(item.monthly_used || 0)}</small></div></td>
                      <td><Badge tone={item.status === 'active' ? 'ok' : item.status === 'expired' ? 'warn' : 'bad'}>{item.status || '-'}</Badge></td>
                    </tr>
                  )) : (
                    <ListEmptyRow colSpan={5} title="暂无订阅" action={<Button tone="primary" onClick={() => setSubscriptionDraft({ accountId: viewSubscriptionsUser.id, planId: '', status: 'active' })}>分配订阅</Button>} />
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </Modal>
      ) : null}

      {viewUsageUser ? (
        <Modal
          title="用户使用记录"
          size="lg"
          onClose={() => setViewUsageUser(null)}
          footer={<ModalActions><Button onClick={() => setViewUsageUser(null)}>关闭</Button></ModalActions>}
        >
          <div className="admin-dialog">
            <div className="admin-dialog-intro">
              <strong>{viewUsageUser.email || viewUsageUser.username || viewUsageUser.name}</strong>
            </div>
            <div className="table-wrap table-scroll table-requests">
              <table>
                <thead>
                  <tr>
                    <th>时间</th>
                    <th>模型</th>
                    <th>线路</th>
                    <th>Token</th>
                    <th>状态</th>
                  </tr>
                </thead>
                <tbody>
                  {usageQuery.isLoading ? (
                    <ListEmptyRow colSpan={5} title="加载中" />
                  ) : relatedUsage.length ? relatedUsage.map((item) => (
                    <tr key={item.request_id}>
                      <td><div className="sub2-cell-stack sub2-cell-stack-tight"><strong>{item.started_at || '-'}</strong><small>{item.request_id}</small></div></td>
                      <td><div className="sub2-cell-stack sub2-cell-stack-tight"><strong>{item.model || '-'}</strong><small>{item.resolved_model || '-'}</small></div></td>
                      <td><div className="sub2-cell-stack sub2-cell-stack-tight"><strong>{item.pool_name || '-'}</strong><small>{item.route_url || '-'}</small></div></td>
                      <td><div className="sub2-cell-stack sub2-cell-stack-tight"><strong>{formatTokenCount(item.total_tokens || 0)}</strong><small>请求 {formatByteCount(item.input_bytes || 0)} · 响应 {formatByteCount(item.output_bytes || 0)}</small></div></td>
                      <td><Badge tone={item.error || Number(item.status_code || 0) >= 400 ? 'bad' : 'ok'}>{item.error || item.status_code || '-'}</Badge></td>
                    </tr>
                  )) : (
                    <ListEmptyRow colSpan={5} title="暂无使用记录" />
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </Modal>
      ) : null}

      {subscriptionDraft ? (
        <Modal
          title="分配订阅"
          size="md"
          onClose={() => setSubscriptionDraft(null)}
          footer={
            <ModalActions>
              <Button onClick={() => setSubscriptionDraft(null)}>取消</Button>
              <Button
                tone="primary"
                disabled={!subscriptionDraft.planId || assignSubscriptionMutation.isPending}
                onClick={() => assignSubscriptionMutation.mutate({ account_id: subscriptionDraft.accountId, plan_id: subscriptionDraft.planId, status: subscriptionDraft.status })}
              >
                分配
              </Button>
            </ModalActions>
          }
        >
          <div className="admin-dialog">
            <div className="admin-dialog-grid">
              <Field label="计划">
                <Select value={subscriptionDraft.planId} onChange={(event) => setSubscriptionDraft({ ...subscriptionDraft, planId: event.target.value })}>
                  <option value="">请选择计划</option>
                  {planItems.map((plan) => <option key={plan.id} value={plan.id}>{plan.name}</option>)}
                </Select>
              </Field>
              <Field label="状态">
                <Select value={subscriptionDraft.status} onChange={(event) => setSubscriptionDraft({ ...subscriptionDraft, status: event.target.value })}>
                  <option value="active">active</option>
                  <option value="expired">expired</option>
                  <option value="revoked">revoked</option>
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
              <Button tone="primary" disabled={toggleMutation.isPending} onClick={() => toggleMutation.mutate({ accountId: toggleTarget.id, enabled: toggleTarget.enabled === false })}>
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
          title="重置调用标识"
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

function UserInspect({ user, groups }: { user: AdminAccount; groups: Array<{ id: string; name: string }> }) {
  return (
    <div className="admin-dialog">
      <div className="admin-dialog-intro">
        <strong>{user.email || user.username || user.name}</strong>
      </div>
      <div className="admin-dialog-summary">
        <div className="admin-dialog-summary-card">
          <span>余额</span>
          <strong>{formatMoneyCents(user.balance_cents || 0)}</strong>
          <small>并发 {formatNumber(user.concurrency_limit || 0)}</small>
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
        <Field label="调用标识"><TextInput readOnly value={user.external_key || '-'} /></Field>
        <Field label="邮箱"><TextInput readOnly value={user.email || '-'} /></Field>
        <Field label="用户名"><TextInput readOnly value={user.username || '-'} /></Field>
        <Field label="角色"><TextInput readOnly value={user.role || 'user'} /></Field>
        <Field label="RPM"><TextInput readOnly value={formatNumber(user.rpm_limit || 0)} /></Field>
        <Field label="所属分组"><TextInput readOnly value={groupNames(user.group_ids || (user.group_id ? [user.group_id] : []), groups) || '未分组'} /></Field>
        <Field label="允许分组"><TextInput readOnly value={groupNames(user.allowed_group_ids || [], groups) || '全部可用分组'} /></Field>
        <Field label="请求次数"><TextInput readOnly value={formatNumber(user.request_count || 0)} /></Field>
        <Field label="总 Token"><TextInput readOnly value={formatTokenCount(user.total_tokens || 0)} /></Field>
        <Field label="错误次数"><TextInput readOnly value={formatNumber(user.error_count || 0)} /></Field>
        <Field label="最近使用"><TextInput readOnly value={user.last_seen_at || '-'} /></Field>
      </div>
    </div>
  );
}

function BalanceHistoryPanel({
  user,
  events,
  loading,
  onDeposit,
  onWithdraw,
}: {
  user: AdminAccount;
  events: AdminBalanceEvent[];
  loading?: boolean;
  onDeposit: () => void;
  onWithdraw: () => void;
}) {
  const totalDeposit = events.filter((item) => Number(item.amount_cents || 0) > 0).reduce((sum, item) => sum + Number(item.amount_cents || 0), 0);
  return (
    <div className="admin-dialog">
      <div className="admin-dialog-intro balance-history-head">
        <div>
          <strong>{user.email || user.username || user.name}</strong>
          <span>{user.id}</span>
        </div>
        <div>
          <small>当前余额</small>
          <strong>{formatMoneyCents(user.balance_cents || 0)}</strong>
        </div>
      </div>
      <div className="admin-dialog-summary">
        <div className="admin-dialog-summary-card"><span>累计充值</span><strong>{formatMoneyCents(totalDeposit)}</strong></div>
        <div className="admin-dialog-summary-card"><span>流水数</span><strong>{formatNumber(events.length)}</strong></div>
        <div className="admin-dialog-summary-card"><span>最近流水</span><strong>{events[0] ? formatTime(events[0].created_at) : '-'}</strong></div>
      </div>
      <div className="sub2-toolbar-row">
        <Button onClick={onDeposit}><Plus size={14} />充值</Button>
        <Button onClick={onWithdraw}><Minus size={14} />扣款</Button>
      </div>
      <div className="table-wrap table-scroll">
        <table>
          <thead>
            <tr>
              <th>时间</th>
              <th>类型</th>
              <th>金额</th>
              <th>变更前</th>
              <th>变更后</th>
              <th>备注</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <ListEmptyRow colSpan={6} title="加载中" />
            ) : events.length ? events.map((item) => (
              <tr key={item.id}>
                <td><div className="sub2-cell-stack sub2-cell-stack-tight"><strong>{formatTime(item.created_at)}</strong><small>{item.id}</small></div></td>
                <td><Badge tone={Number(item.amount_cents || 0) >= 0 ? 'ok' : 'warn'}>{item.event_type === 'withdraw' ? '扣款' : '充值'}</Badge></td>
                <td><strong className={Number(item.amount_cents || 0) >= 0 ? 'money-positive' : 'money-negative'}>{formatSignedMoneyCents(item.amount_cents || 0)}</strong></td>
                <td>{formatMoneyCents(item.before_balance_cents || 0)}</td>
                <td>{formatMoneyCents(item.after_balance_cents || 0)}</td>
                <td>{item.note || '-'}</td>
              </tr>
            )) : (
              <ListEmptyRow colSpan={6} title="暂无余额流水" />
            )}
          </tbody>
        </table>
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

function formatSignedMoneyCents(value: unknown) {
  const cents = Number(value || 0);
  const prefix = cents >= 0 ? '+' : '-';
  return `${prefix}${formatMoneyCents(Math.abs(cents))}`;
}

function formatTime(value: unknown) {
  const raw = Number(value || 0);
  if (!Number.isFinite(raw) || raw <= 0) return '-';
  const date = new Date(raw * 1000);
  if (Number.isNaN(date.getTime())) return '-';
  return date.toLocaleString('zh-CN', { hour12: false });
}

function randomPassword() {
  const chars = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz23456789!@#$%^&*';
  let value = '';
  for (let index = 0; index < 16; index += 1) value += chars.charAt(Math.floor(Math.random() * chars.length));
  return value;
}
