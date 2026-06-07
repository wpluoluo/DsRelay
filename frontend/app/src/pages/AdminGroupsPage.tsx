import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Ban, Eye, Pencil, Plus, RefreshCw, ShieldCheck } from 'lucide-react';
import { fetchAdminGroups, saveAdminGroup } from '../api';
import { Button, Field, Modal, ModalActions, Select, TextArea, TextInput } from '../components';
import { ActionButton, ColumnMenu, FilterToolbar, ListEmptyRow, Pager, RowAction, RowActions, SearchField, TablePageLayout, ToolbarButtonRow, ToolsMenu } from '../components/admin';
import { queryClient } from '../state/queryClient';
import type { AdminGroup } from '../types';
import { cn, formatByteCount, formatNumber, formatTokenCount, readStorageJSON, writeStorageJSON } from '../utils';

type GroupDraft = {
  id?: string;
  name: string;
  description: string;
  platform: string;
  is_exclusive: boolean;
  rate_multiplier: number;
  enabled: boolean;
  sort_order: number;
};

type GroupColumnKey = 'platform' | 'users' | 'requests' | 'errors' | 'tokens' | 'input' | 'output' | 'status';

const EMPTY_GROUP: GroupDraft = {
  name: '',
  description: '',
  platform: '',
  is_exclusive: false,
  rate_multiplier: 1,
  enabled: true,
  sort_order: 0,
};

const DEFAULT_VISIBLE_COLUMNS: GroupColumnKey[] = ['users', 'requests', 'errors', 'tokens', 'status'];
const STORAGE_KEY = 'admin-groups-view-state';

export function AdminGroupsPage() {
  const groupsQuery = useQuery({ queryKey: ['admin-groups'], queryFn: fetchAdminGroups, refetchInterval: 10000 });
  const [draft, setDraft] = useState<GroupDraft | null>(null);
  const [inspectGroup, setInspectGroup] = useState<AdminGroup | null>(null);
  const [toggleTarget, setToggleTarget] = useState<AdminGroup | null>(null);
  const savedState = readStorageJSON(STORAGE_KEY, {
    search: '',
    statusFilter: '',
    platformFilter: '',
    pageSize: 20,
    visibleColumns: DEFAULT_VISIBLE_COLUMNS,
  });
  const [search, setSearch] = useState(savedState.search);
  const [statusFilter, setStatusFilter] = useState(savedState.statusFilter);
  const [platformFilter, setPlatformFilter] = useState(savedState.platformFilter || '');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(savedState.pageSize || 20);
  const [visibleColumns, setVisibleColumns] = useState<Set<GroupColumnKey>>(new Set(savedState.visibleColumns || DEFAULT_VISIBLE_COLUMNS));

  const saveMutation = useMutation({
    mutationFn: saveAdminGroup,
    onSuccess: async () => {
      setDraft(null);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['admin-groups'] }),
        queryClient.invalidateQueries({ queryKey: ['admin-accounts'] }),
        queryClient.invalidateQueries({ queryKey: ['admin-overview'] }),
      ]);
    },
  });

  const items = groupsQuery.data?.items || [];
  const filteredItems = useMemo(() => {
    const keyword = search.trim().toLowerCase();
    return items
      .filter((item) => {
      if (keyword) {
        const haystack = [item.name, item.description, item.id].map((value) => String(value || '').toLowerCase()).join(' ');
        if (!haystack.includes(keyword)) return false;
      }
      if (statusFilter) {
        const enabledValue = statusFilter === 'enabled';
        if ((item.enabled !== false) !== enabledValue) return false;
      }
      if (platformFilter && (item.platform || '') !== platformFilter) return false;
      return true;
      })
      .sort((left, right) => {
        const sortDelta = Number(left.sort_order || 0) - Number(right.sort_order || 0);
        if (sortDelta !== 0) return sortDelta;
        return String(left.name || '').localeCompare(String(right.name || ''), 'zh-CN');
      });
  }, [items, platformFilter, search, statusFilter]);

  const totalPages = Math.max(1, Math.ceil(filteredItems.length / pageSize));
  const pagedItems = useMemo(() => {
    const start = (page - 1) * pageSize;
    return filteredItems.slice(start, start + pageSize);
  }, [filteredItems, page, pageSize]);
  const enabledCount = items.filter((item) => item.enabled !== false).length;
  const requestTotal = items.reduce((sum, item) => sum + Number(item.request_count || 0), 0);
  const errorTotal = items.reduce((sum, item) => sum + Number(item.error_count || 0), 0);
  const accountTotal = items.reduce((sum, item) => sum + Number(item.account_count || 0), 0);
  const exclusiveCount = items.filter((item) => item.is_exclusive).length;
  const platformOptions = useMemo(
    () => Array.from(new Set(items.map((item) => item.platform).filter((value): value is string => Boolean(value)))).sort((left, right) => left.localeCompare(right, 'zh-CN')),
    [items],
  );

  useEffect(() => {
    writeStorageJSON(STORAGE_KEY, {
      search,
      statusFilter,
      platformFilter,
      pageSize,
      visibleColumns: Array.from(visibleColumns),
    });
  }, [pageSize, platformFilter, search, statusFilter, visibleColumns]);

  function openCreate() {
    setDraft({ ...EMPTY_GROUP });
  }

  function openEdit(item: AdminGroup) {
    setDraft({
      id: item.id,
      name: item.name || '',
      description: item.description || '',
      platform: item.platform || '',
      is_exclusive: item.is_exclusive === true,
      rate_multiplier: Number(item.rate_multiplier || 1),
      enabled: item.enabled !== false,
      sort_order: item.sort_order || 0,
    });
  }

  function toggleEnabled(item: AdminGroup) {
    setToggleTarget(item);
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
      <div className="sub2-page-head">
        <div className="sub2-page-title">
          <strong>分组管理</strong>
          <span>按分组维护平台归属、可用状态和用户覆盖，保持和 SUB2 一致的列表主视图。</span>
        </div>
        <div className="sub2-inline-summary">
          <div className="sub2-inline-summary-item"><span>分组总数</span><strong>{formatNumber(items.length)}</strong><small>当前可管理分组</small></div>
          <div className="sub2-inline-summary-item"><span>启用分组</span><strong>{formatNumber(enabledCount)}</strong><small>停用 {formatNumber(items.length - enabledCount)}</small></div>
          <div className="sub2-inline-summary-item"><span>专属分组</span><strong>{formatNumber(exclusiveCount)}</strong><small>共享 {formatNumber(Math.max(0, items.length - exclusiveCount))}</small></div>
          <div className="sub2-inline-summary-item"><span>账户覆盖</span><strong>{formatNumber(accountTotal)}</strong><small>分组下账户累计</small></div>
          <div className="sub2-inline-summary-item"><span>请求 / 错误</span><strong>{formatNumber(requestTotal)} / {formatNumber(errorTotal)}</strong><small>筛选前全量</small></div>
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
                    { key: 'users', label: '账户数', checked: visibleColumns.has('users'), onToggle: () => toggleColumn('users') },
                    { key: 'platform', label: '平台 / 倍率', checked: visibleColumns.has('platform'), onToggle: () => toggleColumn('platform') },
                    { key: 'requests', label: '请求数', checked: visibleColumns.has('requests'), onToggle: () => toggleColumn('requests') },
                    { key: 'errors', label: '错误数', checked: visibleColumns.has('errors'), onToggle: () => toggleColumn('errors') },
                    { key: 'tokens', label: '总 Token', checked: visibleColumns.has('tokens'), onToggle: () => toggleColumn('tokens') },
                    { key: 'input', label: '请求字节', checked: visibleColumns.has('input'), onToggle: () => toggleColumn('input') },
                    { key: 'output', label: '响应字节', checked: visibleColumns.has('output'), onToggle: () => toggleColumn('output') },
                    { key: 'status', label: '状态', checked: visibleColumns.has('status'), onToggle: () => toggleColumn('status') },
                  ]}
                />
                <ToolsMenu>
                  <button type="button" onClick={() => { setSearch(''); setPlatformFilter(''); setStatusFilter(''); setPage(1); }}>
                    <span>清空筛选</span>
                  </button>
                  <button type="button" onClick={() => { setStatusFilter('enabled'); setPage(1); }}>
                    <span>仅看启用分组</span>
                  </button>
                  <button type="button" onClick={() => { setPageSize(50); setPage(1); }}>
                    <span>切换 50 / 页</span>
                  </button>
                </ToolsMenu>
                <Button tone="primary" onClick={openCreate}><Plus size={15} />新增分组</Button>
              </ToolbarButtonRow>
            }
          >
            <SearchField value={search} placeholder="搜索分组 / 描述 / ID" onChange={(value) => { setSearch(value); setPage(1); }} />
            <Select value={platformFilter} onChange={(event) => { setPlatformFilter(event.target.value); setPage(1); }}>
              <option value="">全部平台</option>
              {platformOptions.map((item) => <option key={item} value={item}>{item}</option>)}
            </Select>
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
                  {visibleColumns.has('platform') ? <th>平台 / 倍率</th> : null}
                  {visibleColumns.has('users') ? <th>账户数</th> : null}
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
                    {visibleColumns.has('platform') ? (
                      <td>
                        <div className="sub2-cell-stack sub2-cell-stack-tight">
                          <strong>{item.platform || '-'}</strong>
                          <small>{item.is_exclusive ? 'exclusive' : 'shared'} · ×{Number(item.rate_multiplier || 1)}</small>
                        </div>
                      </td>
                    ) : null}
                    {visibleColumns.has('users') ? <td><strong className="sub2-number-cell">{formatNumber(item.account_count || 0)}</strong></td> : null}
                    {visibleColumns.has('requests') ? <td><strong className="sub2-number-cell">{formatNumber(item.request_count || 0)}</strong></td> : null}
                    {visibleColumns.has('errors') ? <td><strong className="sub2-number-cell sub2-number-warn">{formatNumber(item.error_count || 0)}</strong></td> : null}
                    {visibleColumns.has('tokens') ? <td><strong className="sub2-number-cell">{formatTokenCount(item.total_tokens || 0)}</strong></td> : null}
                    {visibleColumns.has('input') ? <td><strong className="sub2-number-cell">{formatByteCount(item.input_bytes || 0)}</strong></td> : null}
                    {visibleColumns.has('output') ? <td><strong className="sub2-number-cell">{formatByteCount(item.output_bytes || 0)}</strong></td> : null}
                    {visibleColumns.has('status') ? <td><span className={cn('badge', item.enabled === false ? 'badge-warn' : 'badge-ok')}>{item.enabled === false ? '停用' : '启用'}</span></td> : null}
                    <td>
                      <RowActions>
                        <RowAction icon={Eye} label="详情" onClick={() => setInspectGroup(item)} />
                        <RowAction icon={Pencil} label="编辑" onClick={() => openEdit(item)} />
                        <RowAction icon={item.enabled === false ? ShieldCheck : Ban} label={item.enabled === false ? '启用' : '停用'} tone={item.enabled === false ? 'default' : 'warn'} onClick={() => toggleEnabled(item)} />
                      </RowActions>
                    </td>
                  </tr>
                )) : (
                  <ListEmptyRow
                    colSpan={visibleColumns.size + 2}
                    title="暂无分组数据"
                    description="当前没有可展示的分组记录。"
                    action={<Button tone="primary" onClick={openCreate}>新增分组</Button>}
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

      {draft ? (
        <Modal
          title={draft.id ? '编辑分组' : '新增分组'}
          size="lg"
          onClose={() => setDraft(null)}
          footer={
            <ModalActions>
              <Button onClick={() => setDraft(null)}>取消</Button>
              <Button tone="primary" onClick={() => saveMutation.mutate(draft)} disabled={saveMutation.isPending || !draft.name.trim()}>
                保存
              </Button>
            </ModalActions>
          }
        >
          <div className="admin-dialog">
            <div className="admin-dialog-intro">
              <strong>{draft.id ? '编辑分组' : '新增分组'}</strong>
              <span>分组用于承接平台归属、账户覆盖和计费倍率，会直接影响账户、订阅和线路归因的管理视图。</span>
            </div>
            <div className="admin-dialog-summary">
              <div className="admin-dialog-summary-card">
                <span>分组总数</span>
                <strong>{formatNumber(items.length)}</strong>
                <small>当前可管理分组</small>
              </div>
              <div className="admin-dialog-summary-card">
                <span>启用分组</span>
                <strong>{formatNumber(enabledCount)}</strong>
                <small>专属 {formatNumber(exclusiveCount)}</small>
              </div>
              <div className="admin-dialog-summary-card">
                <span>当前草稿</span>
                <strong>{draft.name?.trim() || '待填写分组名'}</strong>
                <small>{draft.platform?.trim() || '待填写平台'}</small>
              </div>
            </div>
            <div className="admin-dialog-section">
              <div className="admin-dialog-section-head">
                <strong>基础信息</strong>
                <span>先定义名称、平台、排序和启用状态</span>
              </div>
              <div className="admin-dialog-grid modal-grid">
                <Field label="分组名称"><TextInput value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} /></Field>
                <Field label="平台"><TextInput value={draft.platform} onChange={(e) => setDraft({ ...draft, platform: e.target.value })} /></Field>
                <Field label="排序"><TextInput type="number" value={String(draft.sort_order)} onChange={(e) => setDraft({ ...draft, sort_order: Number(e.target.value || 0) })} /></Field>
                <Field label="倍率"><TextInput type="number" value={String(draft.rate_multiplier)} onChange={(e) => setDraft({ ...draft, rate_multiplier: Number(e.target.value || 1) })} /></Field>
                <Field label="专属">
                  <Select value={draft.is_exclusive ? '1' : '0'} onChange={(e) => setDraft({ ...draft, is_exclusive: e.target.value === '1' })}>
                    <option value="0">共享</option>
                    <option value="1">专属</option>
                  </Select>
                </Field>
                <Field label="启用状态">
                  <Select value={draft.enabled ? '1' : '0'} onChange={(e) => setDraft({ ...draft, enabled: e.target.value === '1' })}>
                    <option value="1">启用</option>
                    <option value="0">停用</option>
                  </Select>
                </Field>
              </div>
            </div>
            <Field label="描述" full><TextArea rows={4} value={draft.description} onChange={(e) => setDraft({ ...draft, description: e.target.value })} /></Field>
          </div>
        </Modal>
      ) : null}

      {inspectGroup ? (
        <Modal
          title="分组详情"
          size="lg"
          onClose={() => setInspectGroup(null)}
          footer={<ModalActions><Button onClick={() => setInspectGroup(null)}>关闭</Button></ModalActions>}
        >
          <div className="admin-dialog">
            <div className="admin-dialog-intro">
              <strong>{inspectGroup.name}</strong>
              <span>查看分组的平台归属、倍率、状态和覆盖情况，便于核对账户与订阅的下挂关系。</span>
            </div>
            <div className="admin-dialog-summary">
              <div className="admin-dialog-summary-card">
                <span>平台</span>
                <strong>{inspectGroup.platform || '-'}</strong>
                <small>{inspectGroup.id}</small>
              </div>
              <div className="admin-dialog-summary-card">
                <span>覆盖账户</span>
                <strong>{formatNumber(inspectGroup.account_count || 0)}</strong>
                <small>请求 {formatNumber(inspectGroup.request_count || 0)}</small>
              </div>
              <div className="admin-dialog-summary-card">
                <span>状态</span>
                <strong>{inspectGroup.enabled === false ? '停用' : '启用'}</strong>
                <small>{inspectGroup.is_exclusive ? '专属分组' : '共享分组'}</small>
              </div>
            </div>
            <div className="admin-dialog-section">
              <div className="admin-dialog-section-head">
                <strong>基础属性</strong>
                <span>排序、倍率与基础说明</span>
              </div>
              <div className="admin-dialog-grid">
                <Field label="排序"><TextInput readOnly value={String(inspectGroup.sort_order || 0)} /></Field>
                <Field label="倍率"><TextInput readOnly value={String(Number(inspectGroup.rate_multiplier || 1))} /></Field>
                <Field label="错误数"><TextInput readOnly value={String(inspectGroup.error_count || 0)} /></Field>
                <Field label="总 Token"><TextInput readOnly value={String(inspectGroup.total_tokens || 0)} /></Field>
              </div>
            </div>
            <Field label="描述" full><TextArea readOnly rows={4} value={inspectGroup.description || '-'} /></Field>
          </div>
        </Modal>
      ) : null}

      {toggleTarget ? (
        <Modal
          title={toggleTarget.enabled === false ? '确认启用分组' : '确认停用分组'}
          size="md"
          onClose={() => setToggleTarget(null)}
          footer={
            <ModalActions>
              <Button onClick={() => setToggleTarget(null)}>取消</Button>
              <Button
                tone={toggleTarget.enabled === false ? 'primary' : 'danger'}
                disabled={saveMutation.isPending}
                onClick={() => saveMutation.mutate({
                  id: toggleTarget.id,
                  name: toggleTarget.name || '',
                  description: toggleTarget.description || '',
                  platform: toggleTarget.platform || '',
                  is_exclusive: toggleTarget.is_exclusive === true,
                  rate_multiplier: Number(toggleTarget.rate_multiplier || 1),
                  enabled: toggleTarget.enabled === false,
                  sort_order: toggleTarget.sort_order || 0,
                }, { onSuccess: async () => {
                  setToggleTarget(null);
                  setInspectGroup(null);
                  await Promise.resolve();
                } })}
              >
                确认
              </Button>
            </ModalActions>
          }
        >
          <div className="admin-dialog">
            <div className="admin-dialog-intro">
              <strong>{toggleTarget.name}</strong>
              <span>{toggleTarget.enabled === false ? '启用后该分组会重新参与账户、订阅和线路配置的可见范围。' : '停用后不会删除历史数据，但会让该分组退出当前业务配置。'}</span>
            </div>
            <div className="admin-dialog-summary">
              <div className="admin-dialog-summary-card">
                <span>操作类型</span>
                <strong>{toggleTarget.enabled === false ? '启用分组' : '停用分组'}</strong>
                <small>{toggleTarget.enabled === false ? '重新进入可用范围' : '退出新业务配置'}</small>
              </div>
              <div className="admin-dialog-summary-card">
                <span>平台 / 倍率</span>
                <strong>{toggleTarget.platform || '-'}</strong>
                <small>×{Number(toggleTarget.rate_multiplier || 1)}</small>
              </div>
              <div className="admin-dialog-summary-card">
                <span>影响范围</span>
                <strong>{toggleTarget.is_exclusive ? '专属分组' : '共享分组'}</strong>
                <small>历史数据保留不删</small>
              </div>
            </div>
          </div>
        </Modal>
      ) : null}
    </section>
  );
}
