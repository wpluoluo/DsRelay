import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Activity, Ban, Edit, Eye, Plus, RefreshCw, ShieldCheck, Trash2 } from 'lucide-react';
import { deleteAdminChannel, fetchAdminChannels, fetchAdminGroups, saveAdminChannel } from '../api';
import { Badge, Button, Field, Modal, ModalActions, Panel, PanelHead, Select, TextArea, TextInput } from '../components';
import { ActionButton, FilterToolbar, ListEmptyRow, Pager, RowAction, RowActions, SearchField, TablePageLayout, ToolbarButtonRow, ToolsMenu } from '../components/admin';
import { buildPageIntro } from '../navigation';
import { useDashboard } from '../state/dashboardContext';
import { queryClient } from '../state/queryClient';
import type { AdminChannel, AdminChannelPricing } from '../types';
import { formatNumber, readStorageJSON, writeStorageJSON } from '../utils';

type ChannelDraft = {
  id?: string;
  name: string;
  description: string;
  platform: string;
  billing_model_source: string;
  group_ids: string[];
  model_pricing_text: string;
  enabled: boolean;
  sort_order: number;
};

type StatusFilter = '' | 'enabled' | 'disabled';

const EMPTY_DRAFT: ChannelDraft = {
  name: '',
  description: '',
  platform: '',
  billing_model_source: 'channel_mapped',
  group_ids: [],
  model_pricing_text: '',
  enabled: true,
  sort_order: 0,
};

const STORAGE_KEY = 'admin-channels-view-state';

export function AdminChannelsPricingPage() {
  const savedState = readStorageJSON(STORAGE_KEY, {
    search: '',
    statusFilter: '' as StatusFilter,
    platformFilter: '',
    pageSize: 20,
  });
  const channelsQuery = useQuery({ queryKey: ['admin-channels'], queryFn: fetchAdminChannels, refetchInterval: 10000 });
  const groupsQuery = useQuery({ queryKey: ['admin-groups'], queryFn: fetchAdminGroups, refetchInterval: 10000 });
  const [search, setSearch] = useState(savedState.search || '');
  const [statusFilter, setStatusFilter] = useState<StatusFilter>(savedState.statusFilter || '');
  const [platformFilter, setPlatformFilter] = useState(savedState.platformFilter || '');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(savedState.pageSize || 20);
  const [draft, setDraft] = useState<ChannelDraft | null>(null);
  const [inspectChannel, setInspectChannel] = useState<AdminChannel | null>(null);
  const [toggleTarget, setToggleTarget] = useState<AdminChannel | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<AdminChannel | null>(null);

  const saveMutation = useMutation({
    mutationFn: saveAdminChannel,
    onSuccess: async () => {
      setDraft(null);
      setToggleTarget(null);
      await queryClient.invalidateQueries({ queryKey: ['admin-channels'] });
    },
  });
  const deleteMutation = useMutation({
    mutationFn: (channelId: string) => deleteAdminChannel(channelId),
    onSuccess: async () => {
      setDeleteTarget(null);
      setInspectChannel(null);
      await queryClient.invalidateQueries({ queryKey: ['admin-channels'] });
    },
  });

  const channels = channelsQuery.data?.items || [];
  const groups = groupsQuery.data?.items || [];
  const platformOptions = useMemo(
    () => Array.from(new Set(channels.map((item) => item.platform).filter((value): value is string => Boolean(value)))).sort((left, right) => left.localeCompare(right, 'zh-CN')),
    [channels],
  );
  const filteredItems = useMemo(() => {
    const keyword = search.trim().toLowerCase();
    return channels
      .filter((item) => {
        if (statusFilter) {
          const enabledValue = statusFilter === 'enabled';
          if ((item.enabled !== false) !== enabledValue) return false;
        }
        if (platformFilter && (item.platform || '') !== platformFilter) return false;
        if (!keyword) return true;
        const haystack = [
          item.name,
          item.description,
          item.platform,
          item.billing_model_source,
          item.id,
          ...(item.group_names || []),
        ].map((value) => String(value || '').toLowerCase()).join(' ');
        return haystack.includes(keyword);
      })
      .sort((left, right) => {
        const sortDelta = Number(left.sort_order || 0) - Number(right.sort_order || 0);
        if (sortDelta !== 0) return sortDelta;
        return String(left.name || '').localeCompare(String(right.name || ''), 'zh-CN');
      });
  }, [channels, platformFilter, search, statusFilter]);

  const totalPages = Math.max(1, Math.ceil(filteredItems.length / pageSize));
  const pagedItems = filteredItems.slice((page - 1) * pageSize, page * pageSize);

  useEffect(() => {
    writeStorageJSON(STORAGE_KEY, { search, statusFilter, platformFilter, pageSize });
  }, [pageSize, platformFilter, search, statusFilter]);

  function openCreate() {
    setDraft({ ...EMPTY_DRAFT });
  }

  function openEdit(item: AdminChannel) {
    setDraft({
      id: item.id,
      name: item.name || '',
      description: item.description || '',
      platform: item.platform || '',
      billing_model_source: item.billing_model_source || 'channel_mapped',
      group_ids: item.group_ids || [],
      model_pricing_text: pricingText(item.model_pricing || []),
      enabled: item.enabled !== false,
      sort_order: Number(item.sort_order || 0),
    });
  }

  function toggleGroup(groupId: string) {
    if (!draft) return;
    const values = new Set(draft.group_ids);
    if (values.has(groupId)) values.delete(groupId);
    else values.add(groupId);
    setDraft({ ...draft, group_ids: Array.from(values) });
  }

  function submitDraft() {
    if (!draft) return;
    saveMutation.mutate({
      id: draft.id,
      name: draft.name,
      description: draft.description,
      platform: draft.platform,
      billing_model_source: draft.billing_model_source,
      group_ids: draft.group_ids,
      model_pricing: parsePricingText(draft.model_pricing_text),
      enabled: draft.enabled,
      sort_order: draft.sort_order,
    });
  }

  function toggleChannel() {
    if (!toggleTarget) return;
    saveMutation.mutate({
      ...toggleTarget,
      enabled: toggleTarget.enabled === false,
    });
  }

  return (
    <section className="grid-page">
      {buildPageIntro('/admin/channels/pricing')}
      <TablePageLayout
        filters={
          <FilterToolbar
            right={
              <ToolbarButtonRow>
                <ActionButton onClick={() => channelsQuery.refetch()}><RefreshCw size={15} />刷新</ActionButton>
                <ToolsMenu>
                  <button type="button" onClick={() => { setSearch(''); setStatusFilter(''); setPlatformFilter(''); setPage(1); }}>
                    <span>清空筛选</span>
                  </button>
                  <button type="button" onClick={() => { setStatusFilter('enabled'); setPage(1); }}>
                    <span>仅看启用渠道</span>
                  </button>
                  <button type="button" onClick={() => { setPageSize(50); setPage(1); }}>
                    <span>切换 50 / 页</span>
                  </button>
                </ToolsMenu>
                <Button tone="primary" onClick={openCreate}><Plus size={15} />添加渠道</Button>
              </ToolbarButtonRow>
            }
          >
            <SearchField value={search} placeholder="搜索渠道 / 平台 / 分组" onChange={(value) => { setSearch(value); setPage(1); }} />
            <Select value={platformFilter} onChange={(event) => { setPlatformFilter(event.target.value); setPage(1); }}>
              <option value="">全部平台</option>
              {platformOptions.map((item) => <option key={item} value={item}>{item}</option>)}
            </Select>
            <Select value={statusFilter} onChange={(event) => { setStatusFilter(event.target.value as StatusFilter); setPage(1); }}>
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
                  <th>渠道</th>
                  <th>平台</th>
                  <th>计费模型</th>
                  <th>分组</th>
                  <th>价格</th>
                  <th>套餐</th>
                  <th>状态</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {pagedItems.length ? pagedItems.map((item) => (
                  <tr key={item.id}>
                    <td>
                      <div className="sub2-cell-stack sub2-cell-stack-tight">
                        <strong>{item.name}</strong>
                        <small>{item.description || item.id}</small>
                      </div>
                    </td>
                    <td>{item.platform || '-'}</td>
                    <td>{item.billing_model_source || 'channel_mapped'}</td>
                    <td>
                      <div className="sub2-cell-stack sub2-cell-stack-tight">
                        <strong>{formatNumber(item.group_count || item.group_ids?.length || 0)}</strong>
                        <small>{item.group_names?.slice(0, 3).join(' / ') || '-'}</small>
                      </div>
                    </td>
                    <td><strong className="sub2-number-cell">{formatNumber(item.pricing_count || item.model_pricing?.length || 0)}</strong></td>
                    <td><strong className="sub2-number-cell">{formatNumber(item.plan_count || 0)}</strong></td>
                    <td><Badge tone={item.enabled === false ? 'warn' : 'ok'}>{item.enabled === false ? '停用' : '启用'}</Badge></td>
                    <td>
                      <RowActions>
                        <RowAction icon={Eye} label="详情" onClick={() => setInspectChannel(item)} />
                        <RowAction icon={Edit} label="编辑" onClick={() => openEdit(item)} />
                        <RowAction icon={item.enabled === false ? ShieldCheck : Ban} label={item.enabled === false ? '启用' : '停用'} tone={item.enabled === false ? 'default' : 'warn'} onClick={() => setToggleTarget(item)} />
                        <RowAction icon={Trash2} label="删除" tone="danger" onClick={() => setDeleteTarget(item)} />
                      </RowActions>
                    </td>
                  </tr>
                )) : (
                  <ListEmptyRow colSpan={8} title="暂无渠道数据" action={<Button tone="primary" onClick={openCreate}>添加渠道</Button>} />
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
          title={draft.id ? '编辑渠道' : '添加渠道'}
          size="lg"
          onClose={() => setDraft(null)}
          footer={
            <ModalActions>
              <Button onClick={() => setDraft(null)}>取消</Button>
              <Button tone="primary" disabled={saveMutation.isPending || !draft.name.trim()} onClick={submitDraft}>保存</Button>
            </ModalActions>
          }
        >
          <div className="admin-dialog">
            <div className="admin-dialog-section">
              <div className="admin-dialog-section-head"><strong>基础信息</strong></div>
              <div className="admin-dialog-grid">
                <Field label="渠道名称"><TextInput value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} /></Field>
                <Field label="平台"><TextInput value={draft.platform} onChange={(event) => setDraft({ ...draft, platform: event.target.value })} /></Field>
                <Field label="排序"><TextInput type="number" value={String(draft.sort_order)} onChange={(event) => setDraft({ ...draft, sort_order: Number(event.target.value || 0) })} /></Field>
                <Field label="状态">
                  <Select value={draft.enabled ? '1' : '0'} onChange={(event) => setDraft({ ...draft, enabled: event.target.value === '1' })}>
                    <option value="1">启用</option>
                    <option value="0">停用</option>
                  </Select>
                </Field>
                <Field label="计费模型">
                  <Select value={draft.billing_model_source} onChange={(event) => setDraft({ ...draft, billing_model_source: event.target.value })}>
                    <option value="channel_mapped">渠道映射模型</option>
                    <option value="request_model">请求模型</option>
                  </Select>
                </Field>
              </div>
              <Field label="描述" full><TextArea rows={3} value={draft.description} onChange={(event) => setDraft({ ...draft, description: event.target.value })} /></Field>
            </div>
            <div className="admin-dialog-section">
              <div className="admin-dialog-section-head"><strong>分组</strong></div>
              <div className="cap-grid">
                {groups.map((group) => (
                  <label key={group.id} className="toggle">
                    <input type="checkbox" checked={draft.group_ids.includes(group.id)} onChange={() => toggleGroup(group.id)} />
                    <span>{group.name}</span>
                  </label>
                ))}
              </div>
            </div>
            <Field label="模型价格" full>
              <TextArea
                rows={5}
                value={draft.model_pricing_text}
                onChange={(event) => setDraft({ ...draft, model_pricing_text: event.target.value })}
                placeholder="model,input_price,output_price"
              />
            </Field>
          </div>
        </Modal>
      ) : null}

      {inspectChannel ? (
        <Modal
          title="渠道详情"
          size="lg"
          onClose={() => setInspectChannel(null)}
          footer={<ModalActions><Button onClick={() => setInspectChannel(null)}>关闭</Button></ModalActions>}
        >
          <div className="admin-dialog">
            <div className="admin-dialog-intro"><strong>{inspectChannel.name}</strong></div>
            <div className="admin-dialog-summary">
              <div className="admin-dialog-summary-card"><span>平台</span><strong>{inspectChannel.platform || '-'}</strong><small>{inspectChannel.billing_model_source || '-'}</small></div>
              <div className="admin-dialog-summary-card"><span>分组</span><strong>{formatNumber(inspectChannel.group_count || 0)}</strong><small>{inspectChannel.group_names?.join(' / ') || '-'}</small></div>
              <div className="admin-dialog-summary-card"><span>价格</span><strong>{formatNumber(inspectChannel.pricing_count || 0)}</strong><small>套餐 {formatNumber(inspectChannel.plan_count || 0)}</small></div>
            </div>
            <Field label="描述" full><TextArea readOnly rows={3} value={inspectChannel.description || '-'} /></Field>
            <Field label="模型价格" full><TextArea readOnly rows={5} value={pricingText(inspectChannel.model_pricing || []) || '-'} /></Field>
          </div>
        </Modal>
      ) : null}

      {toggleTarget ? (
        <Modal
          title={toggleTarget.enabled === false ? '确认启用渠道' : '确认停用渠道'}
          size="md"
          onClose={() => setToggleTarget(null)}
          footer={
            <ModalActions>
              <Button onClick={() => setToggleTarget(null)}>取消</Button>
              <Button tone={toggleTarget.enabled === false ? 'primary' : 'danger'} disabled={saveMutation.isPending} onClick={toggleChannel}>确认</Button>
            </ModalActions>
          }
        >
          <div className="admin-dialog">
            <div className="admin-dialog-intro"><strong>{toggleTarget.name}</strong></div>
          </div>
        </Modal>
      ) : null}

      {deleteTarget ? (
        <Modal
          title="删除渠道"
          size="md"
          onClose={() => setDeleteTarget(null)}
          footer={
            <ModalActions>
              <Button onClick={() => setDeleteTarget(null)}>取消</Button>
              <Button tone="danger" disabled={deleteMutation.isPending} onClick={() => deleteMutation.mutate(deleteTarget.id)}>删除</Button>
            </ModalActions>
          }
        >
          <div className="admin-dialog">
            <div className="admin-dialog-intro"><strong>{deleteTarget.name}</strong></div>
          </div>
        </Modal>
      ) : null}
    </section>
  );
}

export function AdminChannelsMonitorPage() {
  const dashboard = useDashboard();

  return (
    <section className="grid-page">
      {buildPageIntro('/admin/channels/monitor')}
      <Panel>
        <PanelHead title={<><Activity size={18} />渠道监控</>} />
        <div className="table-wrap table-scroll">
          <table>
            <thead>
              <tr>
                <th>渠道</th>
                <th>优先级</th>
                <th>线路数</th>
                <th>Key</th>
                <th>状态</th>
              </tr>
            </thead>
            <tbody>
              {dashboard.pools.length ? dashboard.pools.map((pool, index) => (
                <tr key={`${pool.name || 'pool'}-${index}`}>
                  <td>
                    <div className="sub2-cell-stack sub2-cell-stack-tight">
                      <strong>{pool.name || `渠道 ${index + 1}`}</strong>
                      <small>{pool.urls?.[0] || '-'}</small>
                    </div>
                  </td>
                  <td>{formatNumber(pool.priority || 0)}</td>
                  <td>{formatNumber(pool.urls?.length || 0)}</td>
                  <td>{formatNumber(pool.keys?.length || 0)}</td>
                  <td>{pool.enabled === false ? '停用' : '启用'}</td>
                </tr>
              )) : (
                <tr><td colSpan={5}>暂无渠道监控数据。</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </Panel>
    </section>
  );
}

function pricingText(rows: AdminChannelPricing[]) {
  return rows
    .map((item) => [item.model, item.input_price ?? 0, item.output_price ?? 0].join(','))
    .join('\n');
}

function parsePricingText(value: string): AdminChannelPricing[] {
  return String(value || '')
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const [model, inputPrice, outputPrice] = line.split(',').map((part) => part.trim());
      return {
        model,
        input_price: Number(inputPrice || 0),
        output_price: Number(outputPrice || 0),
        unit: '1M tokens',
      };
    })
    .filter((item) => item.model);
}
