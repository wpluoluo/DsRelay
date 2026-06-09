import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Activity, Ban, Edit, Eye, Plus, RefreshCw, ShieldCheck, Trash2 } from 'lucide-react';
import { deleteAdminChannel, fetchAdminChannels, fetchAdminGroups, saveAdminChannel, saveConfig } from '../api';
import { Badge, Button, Field, Modal, ModalActions, Panel, PanelHead, Select, TextArea, TextInput } from '../components';
import { ActionButton, FilterToolbar, ListEmptyRow, Pager, RowAction, RowActions, SearchField, TablePageLayout, ToolbarButtonRow, ToolsMenu } from '../components/admin';
import { buildPageIntro } from '../navigation';
import { useDashboard } from '../state/dashboardContext';
import { queryClient } from '../state/queryClient';
import type { AdminChannel, AdminChannelPricing, Pool, RuntimeConfig } from '../types';
import { formatNumber, readStorageJSON, writeStorageJSON } from '../utils';
import { normalizePool } from '../features/config/model';
import { ProviderAccountModal } from './AdminAccountsPage';

type ChannelDraft = {
  id?: string;
  name: string;
  description: string;
  billing_model_source: string;
  platform_configs: ChannelPlatformConfig[];
  model_pricing_text: string;
  enabled: boolean;
  sort_order: number;
};

type ChannelPlatformConfig = {
  platform: string;
  enabled: boolean;
  group_ids: string[];
};

type StatusFilter = '' | 'enabled' | 'disabled';

const EMPTY_DRAFT: ChannelDraft = {
  name: '',
  description: '',
  billing_model_source: 'channel_mapped',
  platform_configs: [
    { platform: 'openai', enabled: true, group_ids: [] },
    { platform: 'anthropic', enabled: false, group_ids: [] },
    { platform: 'gemini', enabled: false, group_ids: [] },
    { platform: 'deepseek', enabled: false, group_ids: [] },
    { platform: 'openai-compatible', enabled: false, group_ids: [] },
  ],
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
      billing_model_source: item.billing_model_source || 'channel_mapped',
      platform_configs: platformConfigsFromChannel(item),
      model_pricing_text: pricingText(item.model_pricing || []),
      enabled: item.enabled !== false,
      sort_order: Number(item.sort_order || 0),
    });
  }

  function togglePlatform(platform: string) {
    if (!draft) return;
    setDraft({
      ...draft,
      platform_configs: draft.platform_configs.map((item) => (item.platform === platform ? { ...item, enabled: !item.enabled } : item)),
    });
  }

  function toggleGroup(platform: string, groupId: string) {
    if (!draft) return;
    const platformConfig = draft.platform_configs.find((item) => item.platform === platform);
    const values = new Set(platformConfig?.group_ids || []);
    if (values.has(groupId)) values.delete(groupId);
    else values.add(groupId);
    setDraft({
      ...draft,
      platform_configs: draft.platform_configs.map((item) => (item.platform === platform ? { ...item, group_ids: Array.from(values) } : item)),
    });
  }

  function submitDraft() {
    if (!draft) return;
    const enabledPlatforms = draft.platform_configs.filter((item) => item.enabled);
    const primaryPlatform = enabledPlatforms[0]?.platform || draft.platform_configs[0]?.platform || '';
    const groupIds = Array.from(new Set(enabledPlatforms.flatMap((item) => item.group_ids)));
    saveMutation.mutate({
      id: draft.id,
      name: draft.name,
      description: draft.description,
      platform: primaryPlatform,
      billing_model_source: draft.billing_model_source,
      group_ids: groupIds,
      model_pricing: parsePricingText(draft.model_pricing_text),
      features_config: {
        platform_configs: draft.platform_configs,
      },
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
                <Button tone="primary" data-tour="channels-create-btn" onClick={openCreate}><Plus size={15} />添加渠道</Button>
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
                        <ToolsMenu label="更多">
                          <button type="button" onClick={() => setToggleTarget(item)}><span>{item.enabled === false ? '启用' : '停用'}</span>{item.enabled === false ? <ShieldCheck size={14} /> : <Ban size={14} />}</button>
                          <button type="button" className="danger" onClick={() => setDeleteTarget(item)}><span>删除</span><Trash2 size={14} /></button>
                        </ToolsMenu>
                      </RowActions>
                    </td>
                  </tr>
                )) : (
                  <ListEmptyRow colSpan={8} title="暂无渠道数据" action={<Button tone="primary" data-tour="channels-create-btn" onClick={openCreate}>添加渠道</Button>} />
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
              <div className="admin-dialog-section-head"><strong>平台配置</strong></div>
              <div className="channel-platform-grid">
                {draft.platform_configs.map((platformConfig) => (
                  <div className="channel-platform-card" key={platformConfig.platform}>
                    <div className="channel-platform-card-head">
                      <label className="toggle">
                        <input type="checkbox" checked={platformConfig.enabled} onChange={() => togglePlatform(platformConfig.platform)} />
                        <span>{platformConfig.platform}</span>
                      </label>
                      <small>{formatNumber(platformConfig.group_ids.length)} 个分组</small>
                    </div>
                    {platformConfig.enabled ? (
                      <div className="sub2-check-grid">
                        {groups.filter((group) => !group.platform || group.platform === platformConfig.platform).map((group) => (
                          <label key={group.id} className="sub2-check-item">
                            <input type="checkbox" checked={platformConfig.group_ids.includes(group.id)} onChange={() => toggleGroup(platformConfig.platform, group.id)} />
                            <span>{group.name}</span>
                          </label>
                        ))}
                      </div>
                    ) : null}
                  </div>
                ))}
              </div>
            </div>
            <Field label="模型价格" full>
              <TextArea
                rows={5}
                value={draft.model_pricing_text}
                onChange={(event) => setDraft({ ...draft, model_pricing_text: event.target.value })}
                placeholder="model,input_price,output_price,cache_write_price,cache_read_price"
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
  const channelsQuery = useQuery({ queryKey: ['admin-channels'], queryFn: fetchAdminChannels, refetchInterval: 10000 });
  const [accountDraft, setAccountDraft] = useState<Pool | null>(null);
  const [accountStatus, setAccountStatus] = useState('');
  const channels = channelsQuery.data?.items || [];
  const savePoolsMutation = useMutation({
    mutationFn: (config: RuntimeConfig) => saveConfig(config),
    onSuccess: async (state) => {
      queryClient.setQueryData(['dashboard-state'], state);
      setAccountDraft(null);
      setAccountStatus('');
      await queryClient.invalidateQueries({ queryKey: ['admin-provider-accounts'] });
    },
    onError: (error) => {
      setAccountStatus(error instanceof Error ? error.message : '上游账号保存失败');
    },
  });
  const poolsByProtocol = useMemo(() => {
    const map = new Map<string, { enabled: number; total: number; requests: number; errors: number; keys: number }>();
    for (const pool of dashboard.pools || []) {
      const policy = pool.route_policy || {};
      const protocol = String(policy.text_upstream_protocol || 'auto');
      const entry = map.get(protocol) || { enabled: 0, total: 0, requests: 0, errors: 0, keys: 0 };
      entry.total += 1;
      if (pool.enabled !== false) entry.enabled += 1;
      entry.keys += Array.isArray(pool.keys) ? pool.keys.filter((key) => String(key?.key || '').trim()).length : 0;
      map.set(protocol, entry);
    }
    return map;
  }, [dashboard.pools]);

  function openCreateAccount() {
    setAccountStatus('');
    setAccountDraft(normalizePool());
  }

  function saveAccountDraft() {
    if (!accountDraft) return;
    const nextConfig = { ...dashboard.draft, pools: [...dashboard.pools, normalizePool(accountDraft)] };
    savePoolsMutation.mutate(nextConfig);
  }

  return (
    <section className="grid-page">
      {buildPageIntro('/admin/channels/monitor')}
      <Panel>
        <PanelHead
          title={<><Activity size={18} />渠道监控</>}
          action={
            <div className="button-row">
              <Button onClick={() => channelsQuery.refetch()}><RefreshCw size={14} />刷新</Button>
              <Button tone="primary" onClick={openCreateAccount}><Plus size={14} />添加上游账号</Button>
            </div>
          }
        />
        <div className="table-wrap table-scroll">
          <table>
            <thead>
              <tr>
                <th>渠道</th>
                <th>平台</th>
                <th>分组 / 套餐</th>
                <th>价格规则</th>
                <th>上游能力</th>
                <th>状态</th>
              </tr>
            </thead>
            <tbody>
              {channels.length ? channels.map((channel) => {
                const platformConfigs = platformConfigsFromChannel(channel).filter((item) => item.enabled);
                const upstreamStats = platformConfigs.reduce(
                  (sum, item) => {
                    const protocolStats = poolsByProtocol.get(item.platform) || poolsByProtocol.get('auto');
                    if (!protocolStats) return sum;
                    return {
                      enabled: sum.enabled + protocolStats.enabled,
                      total: sum.total + protocolStats.total,
                      keys: sum.keys + protocolStats.keys,
                    };
                  },
                  { enabled: 0, total: 0, keys: 0 },
                );
                return (
                <tr key={channel.id}>
                  <td>
                    <div className="sub2-cell-stack sub2-cell-stack-tight">
                      <strong>{channel.name}</strong>
                      <small>{channel.description || channel.id}</small>
                    </div>
                  </td>
                  <td>{platformConfigs.map((item) => item.platform).join(' / ') || channel.platform || '-'}</td>
                  <td>
                    <div className="sub2-cell-stack sub2-cell-stack-tight">
                      <strong>{formatNumber(channel.group_count || channel.group_ids?.length || 0)}</strong>
                      <small>套餐 {formatNumber(channel.plan_count || 0)}</small>
                    </div>
                  </td>
                  <td>{formatNumber(channel.pricing_count || channel.model_pricing?.length || 0)}</td>
                  <td>
                    <div className="sub2-cell-stack sub2-cell-stack-tight">
                      <strong>{formatNumber(upstreamStats.enabled)} / {formatNumber(upstreamStats.total)}</strong>
                      <small>Key {formatNumber(upstreamStats.keys)}</small>
                    </div>
                  </td>
                  <td><Badge tone={channel.enabled === false ? 'warn' : 'ok'}>{channel.enabled === false ? '停用' : '启用'}</Badge></td>
                </tr>
              );}) : (
                <tr><td colSpan={6}>暂无渠道监控数据。</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </Panel>
      {accountDraft ? (
        <ProviderAccountModal
          pool={accountDraft}
          title="添加上游账号"
          saving={savePoolsMutation.isPending}
          testing={false}
          status={accountStatus}
          testResult={null}
          canTest={false}
          onChange={setAccountDraft}
          onClose={() => { setAccountDraft(null); setAccountStatus(''); }}
          onSave={saveAccountDraft}
          onTest={() => setAccountStatus('')}
        />
      ) : null}
    </section>
  );
}

function pricingText(rows: AdminChannelPricing[]) {
  return rows
    .map((item) => [item.model, item.input_price ?? 0, item.output_price ?? 0, item.cache_write_price ?? 0, item.cache_read_price ?? 0].join(','))
    .join('\n');
}

function platformConfigsFromChannel(item: AdminChannel): ChannelPlatformConfig[] {
  const features = item.features_config || {};
  const rawConfigs = Array.isArray(features.platform_configs) ? features.platform_configs : [];
  const configs = rawConfigs
    .map((row) => {
      if (!row || typeof row !== 'object') return null;
      const record = row as Record<string, unknown>;
      const platform = String(record.platform || '').trim();
      if (!platform) return null;
      const rawGroupIds = Array.isArray(record.group_ids) ? record.group_ids : [];
      return {
        platform,
        enabled: record.enabled !== false,
        group_ids: rawGroupIds.map((groupId) => String(groupId || '').trim()).filter(Boolean),
      };
    })
    .filter((row): row is ChannelPlatformConfig => Boolean(row));
  const defaults = EMPTY_DRAFT.platform_configs.map((defaultItem) => {
    const existing = configs.find((row) => row.platform === defaultItem.platform);
    return existing || { ...defaultItem, enabled: defaultItem.platform === item.platform, group_ids: item.platform === defaultItem.platform ? item.group_ids || [] : [] };
  });
  for (const config of configs) {
    if (!defaults.some((item) => item.platform === config.platform)) defaults.push(config);
  }
  return defaults;
}

function parsePricingText(value: string): AdminChannelPricing[] {
  return String(value || '')
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const [model, inputPrice, outputPrice, cacheWritePrice, cacheReadPrice] = line.split(',').map((part) => part.trim());
      return {
        model,
        input_price: Number(inputPrice || 0),
        output_price: Number(outputPrice || 0),
        cache_write_price: Number(cacheWritePrice || 0),
        cache_read_price: Number(cacheReadPrice || 0),
        unit: '1M tokens',
      };
    })
    .filter((item) => item.model);
}
