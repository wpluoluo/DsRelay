import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Activity, Ban, FolderKanban, Pencil, Plus, RefreshCw, ShieldCheck, Users } from 'lucide-react';
import { fetchAdminGroups, saveAdminGroup } from '../api';
import { Button, Field, Modal, Select, TextArea, TextInput } from '../components';
import { ActionButton, ColumnMenu, EmptyState, FilterToolbar, Pager, SearchField, TablePageLayout, ToolbarButtonRow } from '../components/admin';
import { queryClient } from '../state/queryClient';
import type { AdminGroup } from '../types';
import { cn, formatByteCount, formatNumber, formatTokenCount, readStorageJSON, writeStorageJSON } from '../utils';

type GroupDraft = {
  id?: string;
  name: string;
  description: string;
  enabled: boolean;
  sort_order: number;
};

type GroupColumnKey = 'users' | 'requests' | 'errors' | 'tokens' | 'input' | 'output' | 'status';

const EMPTY_GROUP: GroupDraft = {
  name: '',
  description: '',
  enabled: true,
  sort_order: 0,
};

const DEFAULT_VISIBLE_COLUMNS: GroupColumnKey[] = ['users', 'requests', 'errors', 'tokens', 'status'];
const STORAGE_KEY = 'admin-groups-view-state';

export function AdminGroupsPage() {
  const groupsQuery = useQuery({ queryKey: ['admin-groups'], queryFn: fetchAdminGroups, refetchInterval: 10000 });
  const [draft, setDraft] = useState<GroupDraft | null>(null);
  const savedState = readStorageJSON(STORAGE_KEY, {
    search: '',
    statusFilter: '',
    pageSize: 20,
    visibleColumns: DEFAULT_VISIBLE_COLUMNS,
  });
  const [search, setSearch] = useState(savedState.search);
  const [statusFilter, setStatusFilter] = useState(savedState.statusFilter);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(savedState.pageSize || 20);
  const [visibleColumns, setVisibleColumns] = useState<Set<GroupColumnKey>>(new Set(savedState.visibleColumns || DEFAULT_VISIBLE_COLUMNS));

  const saveMutation = useMutation({
    mutationFn: saveAdminGroup,
    onSuccess: async () => {
      setDraft(null);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['admin-groups'] }),
        queryClient.invalidateQueries({ queryKey: ['admin-users'] }),
        queryClient.invalidateQueries({ queryKey: ['admin-overview'] }),
      ]);
    },
  });

  const items = groupsQuery.data?.items || [];
  const filteredItems = useMemo(() => {
    const keyword = search.trim().toLowerCase();
    return items.filter((item) => {
      if (keyword) {
        const haystack = [item.name, item.description, item.id].map((value) => String(value || '').toLowerCase()).join(' ');
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
  const requestTotal = items.reduce((sum, item) => sum + Number(item.request_count || 0), 0);
  const errorTotal = items.reduce((sum, item) => sum + Number(item.error_count || 0), 0);
  const userTotal = items.reduce((sum, item) => sum + Number(item.user_count || 0), 0);

  useEffect(() => {
    writeStorageJSON(STORAGE_KEY, {
      search,
      statusFilter,
      pageSize,
      visibleColumns: Array.from(visibleColumns),
    });
  }, [pageSize, search, statusFilter, visibleColumns]);

  function openCreate() {
    setDraft({ ...EMPTY_GROUP });
  }

  function openEdit(item: AdminGroup) {
    setDraft({
      id: item.id,
      name: item.name || '',
      description: item.description || '',
      enabled: item.enabled !== false,
      sort_order: item.sort_order || 0,
    });
  }

  function toggleEnabled(item: AdminGroup) {
    saveMutation.mutate({
      id: item.id,
      name: item.name || '',
      description: item.description || '',
      enabled: item.enabled === false,
      sort_order: item.sort_order || 0,
    });
  }

  function toggleColumn(key: GroupColumnKey) {
    setVisibleColumns((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  return (
    <section className="grid-page">
      <div className="key-stat-grid">
        <div className="key-stat">
          <div className="key-stat-icon blue"><FolderKanban size={18} /></div>
          <div><span>分组总数</span><strong>{formatNumber(items.length)}</strong><small>当前系统分组</small></div>
        </div>
        <div className="key-stat">
          <div className="key-stat-icon green"><ShieldCheck size={18} /></div>
          <div><span>启用分组</span><strong>{formatNumber(enabledCount)}</strong><small>停用 {formatNumber(items.length - enabledCount)}</small></div>
        </div>
        <div className="key-stat">
          <div className="key-stat-icon amber"><Users size={18} /></div>
          <div><span>覆盖用户</span><strong>{formatNumber(userTotal)}</strong><small>分组下用户累计</small></div>
        </div>
        <div className="key-stat">
          <div className="key-stat-icon slate"><Activity size={18} /></div>
          <div><span>请求 / 错误</span><strong>{formatNumber(requestTotal)}</strong><small>错误 {formatNumber(errorTotal)}</small></div>
        </div>
      </div>
      <div className="admin-ops-strip">
        <div className="admin-ops-item">
          <span>当前筛选</span>
          <strong>{statusFilter === 'enabled' ? '仅启用' : statusFilter === 'disabled' ? '仅停用' : '全部分组'}</strong>
          <small>{search ? `关键词：${search}` : '未设置关键词'}</small>
        </div>
        <div className="admin-ops-item">
          <span>列视图</span>
          <strong>{formatNumber(visibleColumns.size)} 列</strong>
          <small>可按运营视角切换展示字段</small>
        </div>
        <div className="admin-ops-item">
          <span>用户覆盖</span>
          <strong>{formatNumber(userTotal)} 人次</strong>
          <small>分组维度下累计归属</small>
        </div>
        <div className="admin-ops-item">
          <span>列表容量</span>
          <strong>{formatNumber(pageSize)} 条 / 页</strong>
          <small>匹配结果 {formatNumber(filteredItems.length)} 条</small>
        </div>
      </div>
      <TablePageLayout
        filters={
          <FilterToolbar
            right={
              <ToolbarButtonRow>
                <ActionButton onClick={() => groupsQuery.refetch()}><RefreshCw size={15} />刷新</ActionButton>
                <ColumnMenu
                  label="列设置"
                  items={[
                    { key: 'users', label: '用户数', checked: visibleColumns.has('users'), onToggle: () => toggleColumn('users') },
                    { key: 'requests', label: '请求数', checked: visibleColumns.has('requests'), onToggle: () => toggleColumn('requests') },
                    { key: 'errors', label: '错误数', checked: visibleColumns.has('errors'), onToggle: () => toggleColumn('errors') },
                    { key: 'tokens', label: '总 Token', checked: visibleColumns.has('tokens'), onToggle: () => toggleColumn('tokens') },
                    { key: 'input', label: '请求字节', checked: visibleColumns.has('input'), onToggle: () => toggleColumn('input') },
                    { key: 'output', label: '响应字节', checked: visibleColumns.has('output'), onToggle: () => toggleColumn('output') },
                    { key: 'status', label: '状态', checked: visibleColumns.has('status'), onToggle: () => toggleColumn('status') },
                  ]}
                />
                <Button tone="primary" onClick={openCreate}><Plus size={15} />新增分组</Button>
              </ToolbarButtonRow>
            }
          >
            <SearchField value={search} placeholder="搜索分组 / 描述 / ID" onChange={(value) => { setSearch(value); setPage(1); }} />
            <Select value={statusFilter} onChange={(event) => { setStatusFilter(event.target.value); setPage(1); }}>
              <option value="">全部状态</option>
              <option value="enabled">启用</option>
              <option value="disabled">停用</option>
            </Select>
          </FilterToolbar>
        }
        table={
          <div className="table-wrap table-scroll">
            <table>
              <thead>
                <tr>
                  <th>分组</th>
                  {visibleColumns.has('users') ? <th>用户数</th> : null}
                  {visibleColumns.has('requests') ? <th>请求数</th> : null}
                  {visibleColumns.has('errors') ? <th>错误数</th> : null}
                  {visibleColumns.has('tokens') ? <th>总 Token</th> : null}
                  {visibleColumns.has('input') ? <th>请求字节</th> : null}
                  {visibleColumns.has('output') ? <th>响应字节</th> : null}
                  {visibleColumns.has('status') ? <th>状态</th> : null}
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {pagedItems.length ? pagedItems.map((item) => (
                  <tr key={item.id}>
                    <td>
                      <div className="sub2-cell-stack">
                        <strong>{item.name}</strong>
                        <small>{item.description || item.id}</small>
                      </div>
                    </td>
                    {visibleColumns.has('users') ? <td><strong className="sub2-number-cell">{formatNumber(item.user_count || 0)}</strong></td> : null}
                    {visibleColumns.has('requests') ? <td><strong className="sub2-number-cell">{formatNumber(item.request_count || 0)}</strong></td> : null}
                    {visibleColumns.has('errors') ? <td><strong className="sub2-number-cell sub2-number-warn">{formatNumber(item.error_count || 0)}</strong></td> : null}
                    {visibleColumns.has('tokens') ? <td><strong className="sub2-number-cell">{formatTokenCount(item.total_tokens || 0)}</strong></td> : null}
                    {visibleColumns.has('input') ? <td><strong className="sub2-number-cell">{formatByteCount(item.input_bytes || 0)}</strong></td> : null}
                    {visibleColumns.has('output') ? <td><strong className="sub2-number-cell">{formatByteCount(item.output_bytes || 0)}</strong></td> : null}
                    {visibleColumns.has('status') ? <td><span className={cn('badge', item.enabled === false ? 'badge-warn' : 'badge-ok')}>{item.enabled === false ? '停用' : '启用'}</span></td> : null}
                    <td>
                      <div className="sub2-action-stack">
                        <button type="button" className="sub2-icon-action" onClick={() => openEdit(item)}>
                          <Pencil size={14} />
                          <span>编辑</span>
                        </button>
                        <button type="button" className={cn('sub2-icon-action', item.enabled === false ? '' : 'warn')} onClick={() => toggleEnabled(item)}>
                          {item.enabled === false ? <ShieldCheck size={14} /> : <Ban size={14} />}
                          <span>{item.enabled === false ? '启用' : '停用'}</span>
                        </button>
                      </div>
                    </td>
                  </tr>
                )) : (
                  <tr>
                    <td colSpan={visibleColumns.size + 2}>
                      <EmptyState title="暂无分组数据" description="当前没有可展示的分组记录。" action={<Button tone="primary" onClick={openCreate}>新增分组</Button>} />
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

      {draft ? (
        <Modal
          title={draft.id ? '编辑分组' : '新增分组'}
          onClose={() => setDraft(null)}
          footer={
            <>
              <Button onClick={() => setDraft(null)}>取消</Button>
              <Button tone="primary" onClick={() => saveMutation.mutate(draft)} disabled={saveMutation.isPending || !draft.name.trim()}>
                保存
              </Button>
            </>
          }
        >
          <div className="form-grid modal-grid">
            <Field label="分组名称"><TextInput value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} /></Field>
            <Field label="排序"><TextInput type="number" value={String(draft.sort_order)} onChange={(e) => setDraft({ ...draft, sort_order: Number(e.target.value || 0) })} /></Field>
            <Field label="启用状态">
              <Select value={draft.enabled ? '1' : '0'} onChange={(e) => setDraft({ ...draft, enabled: e.target.value === '1' })}>
                <option value="1">启用</option>
                <option value="0">停用</option>
              </Select>
            </Field>
            <Field label="描述" full><TextArea rows={4} value={draft.description} onChange={(e) => setDraft({ ...draft, description: e.target.value })} /></Field>
          </div>
        </Modal>
      ) : null}
    </section>
  );
}
