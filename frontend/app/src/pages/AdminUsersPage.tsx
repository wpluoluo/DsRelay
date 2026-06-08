import { useMemo, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Edit, KeyRound, Plus, RefreshCw, ShieldCheck, Trash2 } from 'lucide-react';
import { createAdminUser, deleteAdminUser, fetchAdminGroups, fetchAdminUsers, resetAdminUserExternalKey, setAdminUserEnabled, updateAdminUser } from '../api';
import { Badge, Button, Field, Modal, ModalActions, Select, TextInput } from '../components';
import { ActionButton, FilterToolbar, ListEmptyRow, SearchField, TablePageLayout, ToolbarButtonRow } from '../components/admin';
import { buildPageIntro } from '../navigation';
import { queryClient } from '../state/queryClient';
import type { AdminUser } from '../types';
import { formatNumber } from '../utils';

type UserDraft = {
  id?: string;
  name: string;
  external_key: string;
  group_ids: string[];
  note: string;
  enabled: boolean;
};

const EMPTY_DRAFT: UserDraft = {
  name: '',
  external_key: '',
  group_ids: [],
  note: '',
  enabled: true,
};

export function AdminUsersPage() {
  const usersQuery = useQuery({ queryKey: ['admin-users'], queryFn: fetchAdminUsers, refetchInterval: 10000 });
  const groupsQuery = useQuery({ queryKey: ['admin-groups'], queryFn: fetchAdminGroups, refetchInterval: 10000 });
  const [search, setSearch] = useState('');
  const [coverageFilter, setCoverageFilter] = useState<'all' | 'subscribed' | 'uncovered'>('all');
  const [draft, setDraft] = useState<UserDraft | null>(null);
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
      if (!keyword) return true;
      const haystack = [item.name, item.id, item.group_name, item.group_id, item.preview, item.external_key]
        .map((value) => String(value || '').toLowerCase())
        .join(' ');
      return haystack.includes(keyword);
    });
  }, [coverageFilter, rows, search]);

  const groups = groupsQuery.data?.items || [];
  const activeUsers = rows.filter((item) => item.enabled !== false).length;
  const coveredUsers = rows.filter((item) => item.active_subscription_count > 0).length;
  const uncoveredUsers = rows.length - coveredUsers;
  const keyCoveredUsers = rows.filter((item) => item.active_key_count > 0).length;

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

  return (
    <section className="grid-page">
      {buildPageIntro('/admin/users')}
      <div className="sub2-inline-summary">
        <div className="sub2-inline-summary-item"><span>用户总数</span><strong>{formatNumber(rows.length)}</strong><small>业务用户</small></div>
        <div className="sub2-inline-summary-item"><span>启用用户</span><strong>{formatNumber(activeUsers)}</strong><small>停用 {formatNumber(rows.length - activeUsers)}</small></div>
        <div className="sub2-inline-summary-item"><span>订阅覆盖</span><strong>{formatNumber(coveredUsers)}</strong><small>未覆盖 {formatNumber(uncoveredUsers)}</small></div>
        <div className="sub2-inline-summary-item"><span>Key 覆盖</span><strong>{formatNumber(keyCoveredUsers)}</strong><small>可调用用户</small></div>
      </div>
      <TablePageLayout
        filters={
          <FilterToolbar
            right={
              <ToolbarButtonRow>
                <ActionButton onClick={() => { usersQuery.refetch(); groupsQuery.refetch(); }}>
                  <RefreshCw size={15} />
                  刷新
                </ActionButton>
                <Button tone="primary" onClick={openCreate}>
                  <Plus size={15} />
                  新增用户
                </Button>
              </ToolbarButtonRow>
            }
          >
            <SearchField value={search} placeholder="搜索用户 / 分组 / 标识" onChange={setSearch} />
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
                  onClick={() => setCoverageFilter(item.value as typeof coverageFilter)}
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
                  <th>业务标识</th>
                  <th>当前分组</th>
                  <th>Key 覆盖</th>
                  <th>订阅覆盖</th>
                  <th>最近归因</th>
                  <th>状态</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {filteredRows.length ? filteredRows.map((item) => (
                  <tr key={item.id}>
                    <td>
                      <div className="sub2-cell-stack sub2-cell-stack-tight">
                        <strong>{item.name}</strong>
                        <small>{item.id}</small>
                      </div>
                    </td>
                    <td>
                      <div className="sub2-cell-stack sub2-cell-stack-tight">
                        <strong>{item.external_key || '-'}</strong>
                        <small>{item.preview || '-'}</small>
                      </div>
                    </td>
                    <td>
                      <div className="sub2-cell-stack sub2-cell-stack-tight">
                        <strong>{item.group_name || '未分组'}</strong>
                        <small>{item.group_id || '-'}</small>
                      </div>
                    </td>
                    <td>
                      <div className="sub2-cell-stack sub2-cell-stack-tight">
                        <strong>{formatNumber(item.active_key_count)} / {formatNumber(item.key_count)}</strong>
                        <small>{item.active_key_count > 0 ? '存在可用 Key' : '未配置可用 Key'}</small>
                      </div>
                    </td>
                    <td>
                      <div className="sub2-cell-stack sub2-cell-stack-tight">
                        <strong>{formatNumber(item.active_subscription_count)} / {formatNumber(item.subscription_count)}</strong>
                        <small>{item.active_subscription_count > 0 ? (item.active_plan_name || '订阅已覆盖') : '无有效订阅'}</small>
                      </div>
                    </td>
                    <td>
                      <div className="sub2-cell-stack sub2-cell-stack-tight">
                        <strong>{item.last_seen_at || '-'}</strong>
                        <small>{formatNumber(item.request_count || 0)} 次请求</small>
                      </div>
                    </td>
                    <td>
                      <div className="sub2-cell-stack sub2-cell-stack-tight">
                        <Badge tone={item.enabled === false ? 'warn' : 'ok'}>{item.enabled === false ? '停用' : '启用'}</Badge>
                        <small>{item.active_subscription_count > 0 ? '订阅已覆盖' : '等待订阅'}</small>
                      </div>
                    </td>
                    <td>
                      <div className="button-row">
                        <Button onClick={() => openEdit(item)}><Edit size={14} />编辑</Button>
                        <Button onClick={() => setToggleTarget(item)}><ShieldCheck size={14} />{item.enabled === false ? '启用' : '停用'}</Button>
                        <Button onClick={() => setResetTarget(item)}><KeyRound size={14} />重置标识</Button>
                        <Button tone="danger" onClick={() => setDeleteTarget(item)}><Trash2 size={14} />删除</Button>
                      </div>
                    </td>
                  </tr>
                )) : (
                  <ListEmptyRow
                    colSpan={8}
                    title="暂无用户"
                    description="当前没有可展示的业务用户。"
                    action={<Button tone="primary" onClick={openCreate}>新增用户</Button>}
                  />
                )}
              </tbody>
            </table>
          </div>
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
