import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Ban, CreditCard, Pencil, Plus, RefreshCw, ShieldCheck, Wallet, Waypoints } from 'lucide-react';
import { fetchAdminPaymentChannelTemplate, fetchAdminPaymentChannels, saveAdminPaymentChannel } from '../api';
import { Button, Field, Modal, Select, TextArea, TextInput } from '../components';
import { ActionButton, EmptyState, FilterToolbar, Pager, SearchField, TablePageLayout, ToolbarButtonRow } from '../components/admin';
import { queryClient } from '../state/queryClient';
import { cn, formatNumber, readStorageJSON, writeStorageJSON } from '../utils';

const STORAGE_KEY = 'admin-payment-channels-view-state';

export function AdminPaymentChannelsPage() {
  const channelsQuery = useQuery({ queryKey: ['admin-payment-channels'], queryFn: fetchAdminPaymentChannels, refetchInterval: 10000 });
  const [draft, setDraft] = useState<any | null>(null);
  const savedState = readStorageJSON(STORAGE_KEY, {
    search: '',
    statusFilter: '',
    pageSize: 20,
  });
  const [search, setSearch] = useState(savedState.search);
  const [statusFilter, setStatusFilter] = useState(savedState.statusFilter);
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
      return true;
    });
  }, [items, search, statusFilter]);

  const totalPages = Math.max(1, Math.ceil(filteredItems.length / pageSize));
  const pagedItems = useMemo(() => {
    const start = (page - 1) * pageSize;
    return filteredItems.slice(start, start + pageSize);
  }, [filteredItems, page, pageSize]);
  const enabledCount = items.filter((item) => item.enabled !== false).length;
  const providerCount = new Set(items.map((item) => item.provider).filter(Boolean)).size;
  const configBytes = items.reduce((sum, item) => sum + JSON.stringify(item.config || {}).length, 0);

  useEffect(() => {
    writeStorageJSON(STORAGE_KEY, {
      search,
      statusFilter,
      pageSize,
    });
  }, [pageSize, search, statusFilter]);

  async function applyProviderTemplate(provider: string) {
    const result = await fetchAdminPaymentChannelTemplate(provider);
    const config = result.config || {};
    setDraft((current: any) => current ? { ...current, provider, configText: JSON.stringify(config, null, 2) } : current);
  }

  function toggleEnabled(item: any) {
    saveMutation.mutate({
      name: item.name,
      provider: item.provider,
      enabled: item.enabled === false,
      config: item.config || {},
    });
  }

  return (
    <section className="grid-page">
      <div className="key-stat-grid">
        <div className="key-stat"><div className="key-stat-icon blue"><CreditCard size={18} /></div><div><span>通道数</span><strong>{formatNumber(items.length)}</strong><small>当前系统通道</small></div></div>
        <div className="key-stat"><div className="key-stat-icon green"><ShieldCheck size={18} /></div><div><span>启用通道</span><strong>{formatNumber(enabledCount)}</strong><small>停用 {formatNumber(items.length - enabledCount)}</small></div></div>
        <div className="key-stat"><div className="key-stat-icon amber"><Waypoints size={18} /></div><div><span>提供方</span><strong>{formatNumber(providerCount)}</strong><small>已配置 provider 数</small></div></div>
        <div className="key-stat"><div className="key-stat-icon slate"><Wallet size={18} /></div><div><span>配置体积</span><strong>{formatNumber(configBytes)}</strong><small>JSON 字符总量</small></div></div>
      </div>
      <TablePageLayout
        filters={
          <FilterToolbar
            right={
              <ToolbarButtonRow>
                <ActionButton onClick={() => channelsQuery.refetch()}><RefreshCw size={15} />刷新</ActionButton>
                <Button tone="primary" onClick={() => setDraft({ name: '', provider: 'manual', enabled: true, configText: JSON.stringify({ mode: 'manual', notify_url: '' }, null, 2) })}>
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
                        <small>{item.enabled === false ? '停用中' : '运行中'}</small>
                      </div>
                    </td>
                    <td><span className={cn('badge', item.enabled === false ? 'badge-warn' : 'badge-ok')}>{item.enabled === false ? '停用' : '启用'}</span></td>
                    <td>
                      <div className="sub2-cell-stack sub2-cell-stack-tight">
                        <strong className="request-mono">{compactConfig(item.config || {})}</strong>
                        <small>{formatNumber(Object.keys(item.config || {}).length)} 个字段</small>
                      </div>
                    </td>
                    <td>
                      <div className="sub2-action-stack">
                        <button type="button" className="sub2-icon-action" onClick={() => setDraft({ ...item, configText: JSON.stringify(item.config || {}, null, 2) })}>
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
                    <td colSpan={5}>
                      <EmptyState title="暂无支付通道" description="当前没有可展示的支付通道配置。" action={<Button tone="primary" onClick={() => setDraft({ name: '', provider: 'manual', enabled: true, configText: JSON.stringify({ mode: 'manual', notify_url: '' }, null, 2) })}>新增通道</Button>} />
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
          title="支付通道"
          onClose={() => setDraft(null)}
          footer={<><Button onClick={() => setDraft(null)}>取消</Button><Button tone="primary" disabled={saveMutation.isPending || !draft.name?.trim()} onClick={() => {
            let config = {};
            try { config = JSON.parse(draft.configText || '{}'); } catch {}
            saveMutation.mutate({ name: draft.name, provider: draft.provider, enabled: draft.enabled, config });
          }}>保存</Button></>}
        >
          <div className="form-grid modal-grid">
            <Field label="名称"><TextInput value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} /></Field>
            <Field label="提供方"><Select value={draft.provider} onChange={(e) => { void applyProviderTemplate(e.target.value); }}><option value="manual">manual</option><option value="wechat">wechat</option><option value="alipay">alipay</option></Select></Field>
            <Field label="启用状态">
              <Select value={draft.enabled === false ? '0' : '1'} onChange={(e) => setDraft({ ...draft, enabled: e.target.value === '1' })}>
                <option value="1">启用</option>
                <option value="0">停用</option>
              </Select>
            </Field>
            <Field label="配置" full note="切换提供方会自动填入模板，再按需修改。"><TextArea rows={10} value={draft.configText} onChange={(e) => setDraft({ ...draft, configText: e.target.value })} /></Field>
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
