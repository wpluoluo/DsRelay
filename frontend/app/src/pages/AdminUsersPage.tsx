import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Edit, Eye, KeyRound, Plus, RefreshCw, ShieldCheck, Trash2 } from 'lucide-react';
import {
  createAdminUser,
  deleteAdminUser,
  fetchAdminApiKeys,
  fetchAdminGroups,
  fetchAdminUsers,
  resetAdminUserExternalKey,
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
import { formatNumber, readStorageJSON, writeStorageJSON } from '../utils';

type UserDraft = {
  id?: string;
  name: string;
  external_key: string;
  group_ids: string[];
  note: string;
  enabled: boolean;
};

type CoverageFilter = 'all' | 'subscribed' | 'uncovered';
type StatusFilter = '' | 'enabled' | 'disabled';
type UserColumnKey = 'identifier' | 'group' | 'keys' | 'subscriptions' | 'requests' | 'status';

const EMPTY_DRAFT: UserDraft = {
  name: '',
  external_key: '',
  group_ids: [],
  note: '',
  enabled: true,
};

const DEFAULT_VISIBLE_COLUMNS: UserColumnKey[] = ['identifier', 'group', 'keys', 'subscriptions', 'requests', 'status'];
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
  const [toggleTarget, setToggleTarget] = useState<AdminUser | null>(null);
  const [resetTarget, setResetTarget] = useState<AdminUser | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<AdminUser | null>(null);

  const createMutation = useMutation({
    mutationFn: createAdminUser,
    onSuccess: async () => {
      setDraft(null);
      await queryClient.invalidateQueries({ queryKey: ['admin-users'] });
    },
  });
  const updateMutation = useMutation({
    mutationFn: ({ userId, payload }: { userId: string; payload: Record<string, unknown> }) => updateAdminUser(userId, payload),
    onSuccess: async () => {
      setDraft(null);
      await queryClient.invalidateQueries({ queryKey: ['admin-users'] });
    },
  });
  const toggleMutation = useMutation({
    mutationFn: ({ userId, enabled }: { userId: string; enabled: boolean }) => setAdminUserEnabled(userId, enabled),
    onSuccess: async () => {
      setToggleTarget(null);
      await queryClient.invalidateQueries({ queryKey: ['admin-users'] });
    },
  });
  const resetMutation = useMutation({
    mutationFn: (userId: string) => resetAdminUserExternalKey(userId),
    onSuccess: async () => {
      setResetTarget(null);
      await queryClient.invalidateQueries({ queryKey: ['admin-users'] });
    },
  });
  const deleteMutation = useMutation({
    mutationFn: (userId: string) => deleteAdminUser(userId),
    onSuccess: async () => {
      setDeleteTarget(null);
      await queryClient.invalidateQueries({ queryKey: ['admin-users'] });
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
        if (!ids.includes(groupFilter)) return false;
      }
      if (!keyword) return true;
      const haystack = [item.name, item.id, item.group_name, item.group_id, item.preview, item.external_key, item.note]
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
  const uncoveredUsers = rows.length - coveredUsers;
  const keyCoveredUsers = rows.filter((item) => item.active_key_count > 0).length;

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

  function openCreate() {
    setDraft({ ...EMPTY_DRAFT });
  }

  function openEdit(user: AdminUser) {
    setDraft({
      id: user.id,
      name: user.name || '',
      external_key: user.external_key || '',
      group_ids: user.group_ids || (user.group_id ? [user.group_id] : []),
      note: user.note || '',
      enabled: user.enabled !== false,
    });
  }

  function submitDraft() {
    if (!draft) return;
    const payload = {
      name: draft.name,
      external_key: draft.external_key,
      group_ids: draft.group_ids,
      note: draft.note,
      enabled: draft.enabled,
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

  const relatedKeys = useMemo(
    () => keyItems.filter((item) => viewKeysUser && item.account_id === viewKeysUser.id),
    [keyItems, viewKeysUser],
  );

  return (
    <section className="grid-page">
      <div className="sub2-page-head">
        <div className="sub2-page-title">
          <strong>用户管理</strong>
        </div>
        <div className="sub2-inline-summary">
          <div className="sub2-inline-summary-item"><span>用户总数</span><strong>{formatNumber(rows.length)}</strong><small>业务用户</small></div>
          <div className="sub2-inline-summary-item"><span>启用用户</span><strong>{formatNumber(activeUsers)}</strong><small>停用 {formatNumber(rows.length - activeUsers)}</small></div>
          <div className="sub2-inline-summary-item"><span>订阅覆盖</span><strong>{formatNumber(coveredUsers)}</strong><small>未覆盖 {formatNumber(uncoveredUsers)}</small></div>
          <div className="sub2-inline-summary-item"><span>Key 覆盖</span><strong>{formatNumber(keyCoveredUsers)}</strong><small>可调用用户</small></div>
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
                    { key: 'identifier', label: '业务标识', checked: visibleColumns.has('identifier'), onToggle: () => toggleColumn('identifier') },
                    { key: 'group', label: '当前分组', checked: visibleColumns.has('group'), onToggle: () => toggleColumn('group') },
                    { key: 'keys', label: 'Key 覆盖', checked: visibleColumns.has('keys'), onToggle: () => toggleColumn('keys') },
                    { key: 'subscriptions', label: '订阅覆盖', checked: visibleColumns.has('subscriptions'), onToggle: () => toggleColumn('subscriptions') },
                    { key: 'requests', label: '最近归因', checked: visibleColumns.has('requests'), onToggle: () => toggleColumn('requests') },
                    { key: 'status', label: '状态', checked: visibleColumns.has('status'), onToggle: () => toggleColumn('status') },
                  ]}
                />
                <ToolsMenu>
                  <button type="button" onClick={() => { setSearch(''); setCoverageFilter('all'); setStatusFilter(''); setGroupFilter(''); setPage(1); }}>
                    <span>清空筛选</span>
                  </button>
                  <button type="button" onClick={() => { setCoverageFilter('uncovered'); setPage(1); }}>
                    <span>仅看未覆盖</span>
                  </button>
                  <button type="button" onClick={() => { setStatusFilter('disabled'); setPage(1); }}>
                    <span>仅看停用用户</span>
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
            <SearchField value={search} placeholder="搜索用户 / 分组 / 标识" onChange={(value) => { setSearch(value); setPage(1); }} />
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
                { value: 'uncovered', label: '未覆盖' },
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
          <div className="table-wrap table-scroll">
            <table>
              <thead>
                <tr>
                  <th>用户</th>
                  {visibleColumns.has('identifier') ? <th>业务标识</th> : null}
                  {visibleColumns.has('group') ? <th>当前分组</th> : null}
                  {visibleColumns.has('keys') ? <th>Key 覆盖</th> : null}
                  {visibleColumns.has('subscriptions') ? <th>订阅覆盖</th> : null}
                  {visibleColumns.has('requests') ? <th>最近归因</th> : null}
                  {visibleColumns.has('status') ? <th>状态</th> : null}
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {pagedRows.length ? pagedRows.map((item) => (
                  <tr key={item.id}>
                    <td>
                      <div className="sub2-cell-stack sub2-cell-stack-tight">
                        <strong>{item.name}</strong>
                        <small>{item.id}</small>
                      </div>
                    </td>
                    {visibleColumns.has('identifier') ? (
                      <td>
                        <div className="sub2-cell-stack sub2-cell-stack-tight">
                          <strong>{item.external_key || '-'}</strong>
                          <small>{item.preview || '-'}</small>
                        </div>
                      </td>
                    ) : null}
                    {visibleColumns.has('group') ? (
                      <td>
                        <div className="sub2-cell-stack sub2-cell-stack-tight">
                          <strong>{item.group_name || '未分组'}</strong>
                          <small>{item.group_id || '-'}</small>
                        </div>
                      </td>
                    ) : null}
                    {visibleColumns.has('keys') ? (
                      <td>
                        <div className="sub2-cell-stack sub2-cell-stack-tight">
                          <strong>{formatNumber(item.active_key_count)} / {formatNumber(item.key_count)}</strong>
                          <small>{item.active_key_count > 0 ? '存在可用 Key' : '未配置可用 Key'}</small>
                        </div>
                      </td>
                    ) : null}
                    {visibleColumns.has('subscriptions') ? (
                      <td>
                        <div className="sub2-cell-stack sub2-cell-stack-tight">
                          <strong>{formatNumber(item.active_subscription_count)} / {formatNumber(item.subscription_count)}</strong>
                          <small>{item.active_subscription_count > 0 ? (item.active_plan_name || '订阅已覆盖') : '无有效订阅'}</small>
                        </div>
                      </td>
                    ) : null}
                    {visibleColumns.has('requests') ? (
                      <td>
                        <div className="sub2-cell-stack sub2-cell-stack-tight">
                          <strong>{item.last_seen_at || '-'}</strong>
                          <small>{formatNumber(item.request_count || 0)} 次请求</small>
                        </div>
                      </td>
                    ) : null}
                    {visibleColumns.has('status') ? (
                      <td>
                        <div className="sub2-cell-stack sub2-cell-stack-tight">
                          <Badge tone={item.enabled === false ? 'warn' : 'ok'}>{item.enabled === false ? '停用' : '启用'}</Badge>
                          <small>{item.active_subscription_count > 0 ? '订阅已覆盖' : '等待订阅'}</small>
                        </div>
                      </td>
                    ) : null}
                    <td>
                      <RowActions>
                        <RowAction icon={Eye} label="详情" onClick={() => setInspectUser(item)} />
                        <RowAction icon={KeyRound} label="查看 Key" onClick={() => setViewKeysUser(item)} />
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
                    description="当前没有可展示的业务用户。"
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
          size="md"
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
              <Field label="用户名称">
                <TextInput value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} />
              </Field>
              <Field label="业务标识">
                <TextInput value={draft.external_key} onChange={(event) => setDraft({ ...draft, external_key: event.target.value })} />
              </Field>
              <Field label="当前分组">
                <Select value={draft.group_ids[0] || ''} onChange={(event) => setDraft({ ...draft, group_ids: event.target.value ? [event.target.value] : [] })}>
                  <option value="">未分组</option>
                  {groups.map((group) => <option key={group.id} value={group.id}>{group.name}</option>)}
                </Select>
              </Field>
              <Field label="状态">
                <Select value={draft.enabled ? 'enabled' : 'disabled'} onChange={(event) => setDraft({ ...draft, enabled: event.target.value === 'enabled' })}>
                  <option value="enabled">启用</option>
                  <option value="disabled">停用</option>
                </Select>
              </Field>
              <Field label="备注" full>
                <TextInput value={draft.note} onChange={(event) => setDraft({ ...draft, note: event.target.value })} />
              </Field>
            </div>
          </div>
        </Modal>
      ) : null}

      {inspectUser ? (
        <Modal
          title="用户详情"
          size="md"
          onClose={() => setInspectUser(null)}
          footer={<ModalActions><Button onClick={() => setInspectUser(null)}>关闭</Button></ModalActions>}
        >
          <div className="admin-dialog">
            <div className="admin-dialog-intro">
              <strong>{inspectUser.name}</strong>
            </div>
            <div className="admin-dialog-summary">
              <div className="admin-dialog-summary-card">
                <span>业务标识</span>
                <strong>{inspectUser.external_key || '-'}</strong>
                <small>{inspectUser.preview || '-'}</small>
              </div>
              <div className="admin-dialog-summary-card">
                <span>当前分组</span>
                <strong>{inspectUser.group_name || '未分组'}</strong>
                <small>{inspectUser.group_id || '-'}</small>
              </div>
              <div className="admin-dialog-summary-card">
                <span>当前状态</span>
                <strong>{inspectUser.enabled === false ? '停用' : '启用'}</strong>
                <small>{formatNumber(inspectUser.request_count || 0)} 次请求</small>
              </div>
            </div>
            <div className="admin-dialog-grid">
              <Field label="Key 覆盖"><TextInput readOnly value={`${formatNumber(inspectUser.active_key_count || 0)} / ${formatNumber(inspectUser.key_count || 0)}`} /></Field>
              <Field label="订阅覆盖"><TextInput readOnly value={`${formatNumber(inspectUser.active_subscription_count || 0)} / ${formatNumber(inspectUser.subscription_count || 0)}`} /></Field>
              <Field label="最近归因"><TextInput readOnly value={inspectUser.last_seen_at || '-'} /></Field>
              <Field label="备注"><TextInput readOnly value={inspectUser.note || '-'} /></Field>
            </div>
          </div>
        </Modal>
      ) : null}

      {viewKeysUser ? (
        <Modal
          title="关联 API Key"
          size="lg"
          onClose={() => setViewKeysUser(null)}
          footer={<ModalActions><Button onClick={() => setViewKeysUser(null)}>关闭</Button></ModalActions>}
        >
          <div className="admin-dialog">
            <div className="admin-dialog-intro">
              <strong>{viewKeysUser.name}</strong>
            </div>
            <div className="table-wrap table-scroll table-keys">
              <table>
                <thead>
                  <tr>
                    <th>Key 名称</th>
                    <th>预览</th>
                    <th>订阅</th>
                    <th>状态</th>
                    <th>最近使用</th>
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
                      <td><code>{item.key_preview}</code></td>
                      <td>
                        <div className="sub2-cell-stack sub2-cell-stack-tight">
                          <strong>{item.subscription_active ? (item.active_plan_name || '订阅有效') : '无可用订阅'}</strong>
                          <small>{item.active_group_name || item.active_group_id || '-'}</small>
                        </div>
                      </td>
                      <td><Badge tone={item.enabled === false ? 'warn' : 'ok'}>{item.enabled === false ? '停用' : '启用'}</Badge></td>
                      <td>{formatUnixTimestamp(item.last_used_at)}</td>
                    </tr>
                  )) : (
                    <ListEmptyRow colSpan={5} title="暂无关联 Key" description="当前用户还没有生成任何调用 Key。" />
                  )}
                </tbody>
              </table>
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
          <div className="admin-dialog">
            <div className="admin-dialog-intro">
              <strong>{toggleTarget.name}</strong>
            </div>
          </div>
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
          <div className="admin-dialog">
            <div className="admin-dialog-intro">
              <strong>{resetTarget.name}</strong>
            </div>
          </div>
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

function formatUnixTimestamp(value: number | null | undefined) {
  if (!value) return '-';
  const date = new Date(value * 1000);
  if (Number.isNaN(date.getTime())) return '-';
  return date.toLocaleString('zh-CN', { hour12: false });
}
