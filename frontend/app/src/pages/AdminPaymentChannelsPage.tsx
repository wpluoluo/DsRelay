import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Ban, Eye, Pencil, Plus, RefreshCw, ShieldCheck } from 'lucide-react';
import { fetchAdminGroups, fetchAdminPaymentChannelTemplate, fetchAdminPaymentChannels, saveAdminPaymentChannel } from '../api';
import { Button, Field, Modal, ModalActions, Select, TextArea, TextInput } from '../components';
import { ActionButton, FilterToolbar, ListEmptyRow, Pager, RowAction, RowActions, SearchField, TablePageLayout, ToolbarButtonRow, ToolsMenu } from '../components/admin';
import { queryClient } from '../state/queryClient';
import { cn, formatNumber, readStorageJSON, writeStorageJSON } from '../utils';

const STORAGE_KEY = 'admin-payment-channels-view-state';

export function AdminPaymentChannelsPage() {
  const channelsQuery = useQuery({ queryKey: ['admin-payment-channels'], queryFn: fetchAdminPaymentChannels, refetchInterval: 10000 });
  const groupsQuery = useQuery({ queryKey: ['admin-groups'], queryFn: fetchAdminGroups, refetchInterval: 10000 });
  const [draft, setDraft] = useState<any | null>(null);
  const [inspectChannel, setInspectChannel] = useState<any | null>(null);
  const [toggleTarget, setToggleTarget] = useState<any | null>(null);
  const savedState = readStorageJSON(STORAGE_KEY, {
    search: '',
    statusFilter: '',
    providerFilter: '',
    pageSize: 20,
  });
  const [search, setSearch] = useState(savedState.search);
  const [statusFilter, setStatusFilter] = useState(savedState.statusFilter);
  const [providerFilter, setProviderFilter] = useState(savedState.providerFilter || '');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(savedState.pageSize || 20);

  const saveMutation = useMutation({
    mutationFn: saveAdminPaymentChannel,
    onSuccess: async () => {
      setDraft(null);
      await queryClient.invalidateQueries({ queryKey: ['admin-payment-channels'] });
    },
  });

  const items = channelsQuery.data?.items || [];
  const groups = groupsQuery.data?.items || [];
  const groupMap = useMemo(() => new Map(groups.map((group) => [group.id, group.name])), [groups]);
  const filteredItems = useMemo(() => {
    const keyword = search.trim().toLowerCase();
    return items.filter((item) => {
      if (keyword) {
        const haystack = [item.name, item.provider, JSON.stringify(item.config || {})].join(' ').toLowerCase();
        if (!haystack.includes(keyword)) return false;
      }
      if (statusFilter) {
        const enabledValue = statusFilter === 'enabled';
        if ((item.enabled !== false) !== enabledValue) return false;
      }
      if (providerFilter && item.provider !== providerFilter) return false;
      return true;
    });
  }, [items, providerFilter, search, statusFilter]);

  const totalPages = Math.max(1, Math.ceil(filteredItems.length / pageSize));
  const pagedItems = useMemo(() => {
    const start = (page - 1) * pageSize;
    return filteredItems.slice(start, start + pageSize);
  }, [filteredItems, page, pageSize]);
  const enabledCount = items.filter((item) => item.enabled !== false).length;
  const providerCount = new Set(items.map((item) => item.provider).filter(Boolean)).size;
  const scopedGroupCount = items.filter((item) => Array.isArray(item.allowed_group_ids) && item.allowed_group_ids.length > 0).length;
  const providerOptions = useMemo(
    () => Array.from(new Set(items.map((item) => item.provider).filter((value): value is string => Boolean(value)))).sort((left, right) => left.localeCompare(right, 'zh-CN')),
    [items],
  );

  useEffect(() => {
    writeStorageJSON(STORAGE_KEY, {
      search,
      statusFilter,
      providerFilter,
      pageSize,
    });
  }, [pageSize, providerFilter, search, statusFilter]);

  async function applyProviderTemplate(provider: string) {
    const result = await fetchAdminPaymentChannelTemplate(provider);
    const config = result.config || {};
    setDraft((current: any) => current ? {
      ...current,
      provider,
      configText: JSON.stringify(config, null, 2),
      allowed_group_ids: current.allowed_group_ids || [],
      allowed_protocols: current.allowed_protocols || [],
      allowed_platforms: current.allowed_platforms || [],
    } : current);
  }

  function toggleEnabled(item: any) {
    setToggleTarget(item);
  }

  return (
    <section className="grid-page">
      <div className="sub2-page-head">
        <div className="sub2-page-title">
          <strong>支付通道</strong>
          <span>集中管理支付提供方、通道状态和适用范围，保持和 SUB2 一致的列表主视图。</span>
        </div>
        <div className="sub2-inline-summary">
          <div className="sub2-inline-summary-item"><span>通道数</span><strong>{formatNumber(items.length)}</strong><small>当前可管理通道</small></div>
          <div className="sub2-inline-summary-item"><span>启用通道</span><strong>{formatNumber(enabledCount)}</strong><small>停用 {formatNumber(items.length - enabledCount)}</small></div>
          <div className="sub2-inline-summary-item"><span>提供方</span><strong>{formatNumber(providerCount)}</strong><small>已配置 provider 数</small></div>
          <div className="sub2-inline-summary-item"><span>分组限制</span><strong>{formatNumber(scopedGroupCount)}</strong><small>未限制 {formatNumber(Math.max(0, items.length - scopedGroupCount))}</small></div>
        </div>
      </div>
      <TablePageLayout
        filters={
          <FilterToolbar
            right={
              <ToolbarButtonRow>
                <ActionButton onClick={() => channelsQuery.refetch()}><RefreshCw size={15} />刷新</ActionButton>
                <ToolsMenu>
                  <button type="button" onClick={() => { setSearch(''); setStatusFilter(''); setProviderFilter(''); setPage(1); }}>
                    <span>清空筛选</span>
                  </button>
                  <button type="button" onClick={() => { setStatusFilter('enabled'); setPage(1); }}>
                    <span>仅看启用通道</span>
                  </button>
                  <button type="button" onClick={() => { setPageSize(50); setPage(1); }}>
                    <span>切换 50 / 页</span>
                  </button>
                </ToolsMenu>
                <Button tone="primary" onClick={() => setDraft({ name: '', provider: 'manual', enabled: true, configText: JSON.stringify({ mode: 'manual', notify_url: '' }, null, 2), allowed_group_ids: [], allowed_protocols: [], allowed_platforms: [] })}>
                  <Plus size={15} />新增通道
                </Button>
              </ToolbarButtonRow>
            }
          >
            <SearchField value={search} placeholder="搜索通道 / 提供方 / 配置" onChange={(value) => { setSearch(value); setPage(1); }} />
            <Select value={statusFilter} onChange={(event) => { setStatusFilter(event.target.value); setPage(1); }}>
              <option value="">全部状态</option>
              <option value="enabled">启用</option>
              <option value="disabled">停用</option>
            </Select>
            <Select value={providerFilter} onChange={(event) => { setProviderFilter(event.target.value); setPage(1); }}>
              <option value="">全部提供方</option>
              {providerOptions.map((provider) => <option key={provider} value={provider}>{provider}</option>)}
            </Select>
          </FilterToolbar>
        }
        table={
          <div className="table-wrap table-scroll">
            <table>
              <thead>
                <tr>
                  <th>名称</th>
                  <th>提供方</th>
                  <th>状态</th>
                  <th>约束</th>
                  <th>配置</th>
                  <th>操作</th>
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
                      <div className="sub2-cell-stack sub2-cell-stack-tight">
                        <strong>{item.provider}</strong>
                          <small>{item.enabled === false ? '停用中' : '已启用'}</small>
                      </div>
                    </td>
                    <td><span className={cn('badge', item.enabled === false ? 'badge-warn' : 'badge-ok')}>{item.enabled === false ? '停用' : '启用'}</span></td>
                    <td>
                      <div className="sub2-cell-stack sub2-cell-stack-tight">
                        <strong>{(item.allowed_group_ids || []).length ? `${item.allowed_group_ids?.length} 个分组` : '全部分组'}</strong>
                        <small>{(item.allowed_platforms || []).join(', ') || '全部平台'} · {(item.allowed_protocols || []).length ? `${(item.allowed_protocols || []).length} 个接入类型` : '全部接入类型'}</small>
                      </div>
                    </td>
                    <td>
                      <div className="sub2-cell-stack sub2-cell-stack-tight">
                        <strong className="request-mono">{compactConfig(item.config || {})}</strong>
                        <small>{formatNumber(Object.keys(item.config || {}).length)} 个字段</small>
                      </div>
                    </td>
                    <td>
                      <RowActions>
                        <RowAction icon={Eye} label="详情" onClick={() => setInspectChannel(item)} />
                        <RowAction icon={Pencil} label="编辑" onClick={() => setDraft({ ...item, configText: JSON.stringify(item.config || {}, null, 2), allowed_group_ids: item.allowed_group_ids || [], allowed_protocols: item.allowed_protocols || [], allowed_platforms: item.allowed_platforms || [] })} />
                        <RowAction icon={item.enabled === false ? ShieldCheck : Ban} label={item.enabled === false ? '启用' : '停用'} tone={item.enabled === false ? 'default' : 'warn'} onClick={() => toggleEnabled(item)} />
                      </RowActions>
                    </td>
                  </tr>
                )) : (
                  <ListEmptyRow
                    colSpan={6}
                    title="暂无支付通道"
                    description="当前没有可展示的支付通道配置。"
                    action={<Button tone="primary" onClick={() => setDraft({ name: '', provider: 'manual', enabled: true, configText: JSON.stringify({ mode: 'manual', notify_url: '' }, null, 2), allowed_group_ids: [], allowed_protocols: [], allowed_platforms: [] })}>新增通道</Button>}
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
          title="支付通道"
          size="lg"
          onClose={() => setDraft(null)}
          footer={<ModalActions><Button onClick={() => setDraft(null)}>取消</Button><Button tone="primary" disabled={saveMutation.isPending || !draft.name?.trim()} onClick={() => {
            let config = {};
            try { config = JSON.parse(draft.configText || '{}'); } catch {}
            saveMutation.mutate({
              name: draft.name,
              provider: draft.provider,
              enabled: draft.enabled,
              config,
              allowed_group_ids: draft.allowed_group_ids || [],
              allowed_protocols: draft.allowed_protocols || [],
              allowed_platforms: draft.allowed_platforms || [],
            });
          }}>保存</Button></ModalActions>}
        >
          <div className="admin-dialog">
            <div className="admin-dialog-intro">
              <strong>{draft.id ? '编辑支付通道' : '新增支付通道'}</strong>
              <span>通道会直接影响订单拉起和支付履约，先确定提供方和限制范围，再维护配置内容。</span>
            </div>
            <div className="admin-dialog-summary">
              <div className="admin-dialog-summary-card">
                <span>通道总数</span>
                <strong>{formatNumber(items.length)}</strong>
                <small>当前可管理通道</small>
              </div>
              <div className="admin-dialog-summary-card">
                <span>启用通道</span>
                <strong>{formatNumber(enabledCount)}</strong>
                <small>停用 {formatNumber(items.length - enabledCount)}</small>
              </div>
              <div className="admin-dialog-summary-card">
                <span>当前草稿</span>
                <strong>{draft.provider || 'manual'}</strong>
                <small>{draft.name?.trim() || '待填写名称'}</small>
              </div>
            </div>
            <div className="admin-dialog-section">
              <div className="admin-dialog-section-head">
                <strong>基础信息</strong>
                <span>先定义提供方、状态和作用范围</span>
              </div>
              <div className="admin-dialog-grid modal-grid">
                <Field label="名称"><TextInput value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} /></Field>
                <Field label="提供方"><Select value={draft.provider} onChange={(e) => { void applyProviderTemplate(e.target.value); }}><option value="manual">manual</option><option value="wechat">wechat</option><option value="alipay">alipay</option></Select></Field>
                <Field label="启用状态">
                  <Select value={draft.enabled === false ? '0' : '1'} onChange={(e) => setDraft({ ...draft, enabled: e.target.value === '1' })}>
                    <option value="1">启用</option>
                    <option value="0">停用</option>
                  </Select>
                </Field>
                <Field label="允许分组">
                  <Select value={draft.allowed_group_ids?.[0] || ''} onChange={(e) => setDraft({ ...draft, allowed_group_ids: e.target.value ? [e.target.value] : [] })}>
                    <option value="">全部分组</option>
                    {groups.map((group) => <option key={group.id} value={group.id}>{group.name}</option>)}
                  </Select>
                </Field>
                <Field label="允许接入类型">
                  <Select value={draft.allowed_protocols?.[0] || ''} onChange={(e) => setDraft({ ...draft, allowed_protocols: e.target.value ? [e.target.value] : [] })}>
                    <option value="">全部接入类型</option>
                    <option value="openai">openai</option>
                    <option value="responses">responses</option>
                    <option value="anthropic">anthropic</option>
                    <option value="gemini">gemini</option>
                  </Select>
                </Field>
                <Field label="允许平台">
                  <TextInput value={draft.allowed_platforms?.[0] || ''} onChange={(e) => setDraft({ ...draft, allowed_platforms: e.target.value.trim() ? [e.target.value.trim()] : [] })} />
                </Field>
              </div>
            </div>
            <div className="admin-dialog-section">
              <div className="admin-dialog-section-head">
                <strong>配置内容</strong>
                <span>切换提供方会自动填入模板，再按需修改</span>
              </div>
              <Field label="配置" full>
                <TextArea rows={10} value={draft.configText} onChange={(e) => setDraft({ ...draft, configText: e.target.value })} />
              </Field>
            </div>
          </div>
        </Modal>
      ) : null}

      {inspectChannel ? (
        <Modal
          title="通道详情"
          size="lg"
          onClose={() => setInspectChannel(null)}
          footer={<ModalActions><Button onClick={() => setInspectChannel(null)}>关闭</Button></ModalActions>}
        >
          <div className="admin-dialog">
            <div className="admin-dialog-intro">
              <strong>{inspectChannel.name}</strong>
              <span>查看提供方、状态、生效范围和配置摘要，适合在调整支付入口前先核对一次。</span>
            </div>
            <div className="admin-dialog-summary">
              <div className="admin-dialog-summary-card">
                <span>提供方</span>
                <strong>{inspectChannel.provider || 'manual'}</strong>
                <small>{inspectChannel.id}</small>
              </div>
              <div className="admin-dialog-summary-card">
                <span>状态</span>
                <strong>{inspectChannel.enabled === false ? '停用' : '启用'}</strong>
                <small>{(inspectChannel.allowed_protocols || []).length ? `${inspectChannel.allowed_protocols.length} 个接入类型` : '全部接入类型'}</small>
              </div>
              <div className="admin-dialog-summary-card">
                <span>限制范围</span>
                <strong>{(inspectChannel.allowed_group_ids || []).length ? `${inspectChannel.allowed_group_ids.length} 个分组` : '全部分组'}</strong>
                <small>{(inspectChannel.allowed_platforms || []).join(', ') || '全部平台'}</small>
              </div>
            </div>
            <div className="admin-dialog-section">
              <div className="admin-dialog-section-head">
                <strong>适用范围</strong>
                <span>这里决定通道会在哪些业务入口下可见</span>
              </div>
              <div className="admin-dialog-grid">
                <Field label="允许分组">
                  <TextInput
                    readOnly
                    value={(inspectChannel.allowed_group_ids || []).length
                      ? inspectChannel.allowed_group_ids.map((id: string) => groupMap.get(id) || id).join('，')
                      : '全部分组'}
                  />
                </Field>
                <Field label="允许接入类型">
                  <TextInput readOnly value={(inspectChannel.allowed_protocols || []).join('，') || '全部接入类型'} />
                </Field>
                <Field label="允许平台">
                  <TextInput readOnly value={(inspectChannel.allowed_platforms || []).join('，') || '全部平台'} />
                </Field>
                <Field label="配置字段数">
                  <TextInput readOnly value={String(Object.keys(inspectChannel.config || {}).length)} />
                </Field>
              </div>
            </div>
            <div className="admin-dialog-section">
              <div className="admin-dialog-section-head">
                <strong>配置摘要</strong>
                <span>原始配置保留完整 JSON，便于和上游支付提供方参数逐项核对</span>
              </div>
              <Field label="配置 JSON" full>
                <TextArea readOnly rows={10} value={JSON.stringify(inspectChannel.config || {}, null, 2)} />
              </Field>
            </div>
          </div>
        </Modal>
      ) : null}

      {toggleTarget ? (
        <Modal
          title={toggleTarget.enabled === false ? '确认启用通道' : '确认停用通道'}
          size="md"
          onClose={() => setToggleTarget(null)}
          footer={
            <ModalActions>
              <Button onClick={() => setToggleTarget(null)}>取消</Button>
              <Button
                tone={toggleTarget.enabled === false ? 'primary' : 'danger'}
                disabled={saveMutation.isPending}
                onClick={() => saveMutation.mutate({
                  name: toggleTarget.name,
                  provider: toggleTarget.provider,
                  enabled: toggleTarget.enabled === false,
                  config: toggleTarget.config || {},
                  allowed_group_ids: toggleTarget.allowed_group_ids || [],
                  allowed_protocols: toggleTarget.allowed_protocols || [],
                  allowed_platforms: toggleTarget.allowed_platforms || [],
                })}
              >
                确认
              </Button>
            </ModalActions>
          }
        >
          <div className="admin-dialog">
            <div className="admin-dialog-intro">
              <strong>{toggleTarget.name}</strong>
              <span>{toggleTarget.enabled === false ? '启用后该通道会重新参与订单拉起和支付履约。' : '停用后不会删除配置，但会阻止新订单继续使用该通道。'}</span>
            </div>
            <div className="admin-dialog-summary">
              <div className="admin-dialog-summary-card">
                <span>操作类型</span>
                <strong>{toggleTarget.enabled === false ? '启用通道' : '停用通道'}</strong>
                <small>{toggleTarget.enabled === false ? '重新参与拉起与履约' : '阻止新订单继续使用'}</small>
              </div>
              <div className="admin-dialog-summary-card">
                <span>提供方</span>
                <strong>{toggleTarget.provider || 'manual'}</strong>
                <small>{toggleTarget.id || '当前通道'}</small>
              </div>
              <div className="admin-dialog-summary-card">
                <span>限制范围</span>
                <strong>{(toggleTarget.allowed_group_ids || []).length ? `${toggleTarget.allowed_group_ids.length} 个分组` : '全部分组'}</strong>
                <small>{(toggleTarget.allowed_protocols || []).length ? `${toggleTarget.allowed_protocols.length} 个接入类型` : '全部接入类型'}</small>
              </div>
            </div>
          </div>
        </Modal>
      ) : null}
    </section>
  );
}

function compactConfig(config: Record<string, unknown>) {
  const text = JSON.stringify(config);
  return text.length > 120 ? `${text.slice(0, 116)}...` : text;
}
