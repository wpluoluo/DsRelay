import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Copy, KeyRound, MoreHorizontal, Plus, RefreshCw, ShieldCheck, Users } from 'lucide-react';
import { createAdminApiKey, fetchAdminApiKeys, fetchAdminUsers, setAdminApiKeyEnabled } from '../api';
import { Badge, Button, Field, Modal, Select, TextInput } from '../components';
import { ActionButton, EmptyState, FilterToolbar, Pager, SearchField, TablePageLayout, ToolbarButtonRow } from '../components/admin';
import { queryClient } from '../state/queryClient';
import { cn, formatNumber, maskEmpty, readStorageJSON, writeStorageJSON } from '../utils';

const STORAGE_KEY = 'admin-api-keys-view-state';

export function AdminApiKeysPage() {
  const keysQuery = useQuery({ queryKey: ['admin-api-keys'], queryFn: fetchAdminApiKeys, refetchInterval: 10000 });
  const usersQuery = useQuery({ queryKey: ['admin-users'], queryFn: fetchAdminUsers, refetchInterval: 10000 });
  const [draft, setDraft] = useState<{ user_id: string; name: string } | null>(null);
  const [generatedKey, setGeneratedKey] = useState('');
  const [copiedKeyId, setCopiedKeyId] = useState('');
  const savedState = readStorageJSON(STORAGE_KEY, {
    search: '',
    statusFilter: '',
    pageSize: 20,
  });
  const [search, setSearch] = useState(savedState.search);
  const [statusFilter, setStatusFilter] = useState(savedState.statusFilter);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(savedState.pageSize || 20);
  const [showTools, setShowTools] = useState(false);

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
      return true;
    });
  }, [items, search, statusFilter]);

  const totalPages = Math.max(1, Math.ceil(filteredItems.length / pageSize));
  const pagedItems = useMemo(() => {
    const start = (page - 1) * pageSize;
    return filteredItems.slice(start, start + pageSize);
  }, [filteredItems, page, pageSize]);
  const enabledCount = items.filter((item) => item.enabled !== false).length;
  const disabledCount = Math.max(0, items.length - enabledCount);
  const boundUsers = new Set(items.map((item) => item.user_id).filter(Boolean)).size;
  const unboundCount = Math.max(0, items.length - boundUsers);

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
    writeStorageJSON(STORAGE_KEY, { search, statusFilter, pageSize });
  }, [search, statusFilter, pageSize]);

  return (
    <section className="grid-page">
      <div className="key-stat-grid">
        <div className="key-stat">
          <div className="key-stat-icon blue"><KeyRound size={18} /></div>
          <div><span>业务 Key 总数</span><strong>{formatNumber(items.length)}</strong><small>当前列表全量</small></div>
        </div>
        <div className="key-stat">
          <div className="key-stat-icon green"><ShieldCheck size={18} /></div>
          <div><span>启用 Key</span><strong>{formatNumber(enabledCount)}</strong><small>停用 {formatNumber(disabledCount)}</small></div>
        </div>
        <div className="key-stat">
          <div className="key-stat-icon amber"><Users size={18} /></div>
          <div><span>绑定用户</span><strong>{formatNumber(boundUsers)}</strong><small>已覆盖的业务主体</small></div>
        </div>
        <div className="key-stat">
          <div className="key-stat-icon slate"><Copy size={18} /></div>
          <div><span>本次生成</span><strong>{generatedKey ? '1' : '0'}</strong><small>{generatedKey ? '可立即复制' : '暂无新 Key'}</small></div>
        </div>
      </div>

      <div className="admin-ops-strip">
        <div className="admin-ops-item">
          <span>当前筛选</span>
          <strong>{statusFilter === 'enabled' ? '仅启用' : statusFilter === 'disabled' ? '仅停用' : '全部状态'}</strong>
          <small>{search ? `关键词：${search}` : '未设置关键词'}</small>
        </div>
        <div className="admin-ops-item">
          <span>绑定情况</span>
          <strong>{formatNumber(boundUsers)} 个用户</strong>
          <small>未覆盖 {formatNumber(unboundCount)} 个 Key</small>
        </div>
        <div className="admin-ops-item">
          <span>刷新策略</span>
          <strong>10 秒自动同步</strong>
          <small>列表和用户数据均随查询刷新</small>
        </div>
        <div className="admin-ops-item">
          <span>当前页容量</span>
          <strong>{formatNumber(pageSize)} 条</strong>
          <small>匹配结果 {formatNumber(filteredItems.length)} 条</small>
        </div>
      </div>

      <TablePageLayout
        filters={
          <FilterToolbar
            right={
              <ToolbarButtonRow>
                <ActionButton onClick={() => keysQuery.refetch()}><RefreshCw size={15} />刷新</ActionButton>
                <details className="sub2-menu" open={showTools} onToggle={(event) => setShowTools((event.target as HTMLDetailsElement).open)}>
                  <summary>
                    <MoreHorizontal size={14} />
                    <span>更多工具</span>
                  </summary>
                  <div className="sub2-menu-panel">
                    <button type="button" onClick={() => { setSearch(''); setStatusFilter(''); setPage(1); setShowTools(false); }}>
                      <span>清空筛选</span>
                    </button>
                    <button type="button" onClick={() => { setPageSize(50); setPage(1); setShowTools(false); }}>
                      <span>切换 50 / 页</span>
                    </button>
                    <button type="button" onClick={() => { void keysQuery.refetch(); void usersQuery.refetch(); setShowTools(false); }}>
                      <span>同步用户与 Key</span>
                    </button>
                  </div>
                </details>
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
          </FilterToolbar>
        }
        table={
          <div className="table-wrap table-scroll table-keys">
            <table>
              <thead>
                <tr>
                  <th className="col-key-name">名称</th>
                  <th>用户</th>
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
                      <div className="sub2-action-stack">
                        <button type="button" className={cn('sub2-icon-action', item.enabled === false ? '' : 'warn')} onClick={() => toggleMutation.mutate({ keyId: item.id, enabled: item.enabled === false })}>
                          <ShieldCheck size={14} />
                          <span>{item.enabled === false ? '启用' : '停用'}</span>
                        </button>
                      </div>
                    </td>
                  </tr>
                )) : (
                  <tr>
                    <td colSpan={7}>
                      <EmptyState title="暂无业务 API Key" description="当前还没有创建任何用户业务 Key。" action={<Button tone="primary" onClick={() => setDraft({ user_id: '', name: '' })}>生成 Key</Button>} />
                    </td>
                  </tr>
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
        <div className="generated-key-box generated-key-floating">
          <div className="generated-key-title">新生成 Key</div>
          <div className="generated-key-row">
            <div className="generated-key-value">{generatedKey}</div>
            <Button onClick={() => copyText(generatedKey)}>复制</Button>
          </div>
        </div>
      ) : null}

      {draft ? (
        <Modal
          title="生成用户 API Key"
          onClose={() => setDraft(null)}
          footer={
            <>
              <Button onClick={() => setDraft(null)}>取消</Button>
              <Button tone="primary" disabled={createMutation.isPending || !draft.user_id || !draft.name.trim()} onClick={() => createMutation.mutate(draft)}>
                生成
              </Button>
            </>
          }
        >
          <div className="form-grid modal-grid">
            <Field label="归属用户">
              <Select value={draft.user_id} onChange={(e) => setDraft({ ...draft, user_id: e.target.value })}>
                <option value="">请选择用户</option>
                {users.map((user) => <option key={user.id} value={user.id}>{user.name}</option>)}
              </Select>
            </Field>
            <Field label="Key 名称"><TextInput value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} /></Field>
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
