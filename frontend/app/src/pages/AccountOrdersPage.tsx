import { useEffect, useMemo, useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { Eye, RefreshCw, XCircle } from 'lucide-react';
import { cancelAccountOrder } from '../api';
import { Badge, Button, Field, Modal, ModalActions, Select, TextArea, TextInput } from '../components';
import { ColumnMenu, FilterToolbar, ListEmptyRow, Pager, RowAction, RowActions, SearchField, TablePageLayout, ToolbarButtonRow, ToolsMenu } from '../components/admin';
import { buildPageIntro } from '../navigation';
import { queryClient } from '../state/queryClient';
import { useAccountCenter } from '../state/accountCenterContext';
import { formatNumber, formatUsdCost, getAccountName, maskEmpty, readStorageJSON, writeStorageJSON } from '../utils';

type OrderFilterKey = 'status';
type OrderColumnKey = 'plan' | 'channel' | 'amount' | 'status' | 'fulfillment';

const DEFAULT_VISIBLE_COLUMNS: OrderColumnKey[] = ['plan', 'channel', 'amount', 'status', 'fulfillment'];
const DEFAULT_VISIBLE_FILTERS: OrderFilterKey[] = ['status'];
const STORAGE_KEY = 'account-orders-view-state';

export function AccountOrdersPage() {
  const { account, orders, reload } = useAccountCenter();
  const savedState = readStorageJSON(STORAGE_KEY, {
    search: '',
    status: '',
    pageSize: 20,
    visibleColumns: DEFAULT_VISIBLE_COLUMNS,
    visibleFilters: DEFAULT_VISIBLE_FILTERS,
  });
  const [search, setSearch] = useState(savedState.search || '');
  const [status, setStatus] = useState(savedState.status || '');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(savedState.pageSize || 20);
  const [visibleColumns, setVisibleColumns] = useState<Set<OrderColumnKey>>(new Set(savedState.visibleColumns || DEFAULT_VISIBLE_COLUMNS));
  const [visibleFilters, setVisibleFilters] = useState<Set<OrderFilterKey>>(new Set(savedState.visibleFilters || DEFAULT_VISIBLE_FILTERS));
  const [cancelTarget, setCancelTarget] = useState<any | null>(null);
  const [inspectOrder, setInspectOrder] = useState<any | null>(null);

  const cancelMutation = useMutation({
    mutationFn: (orderId: string) => cancelAccountOrder(orderId),
    onSuccess: async () => {
      setCancelTarget(null);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['account-payment-orders'] }),
        reload(),
      ]);
    },
  });

  const filtered = useMemo(() => {
    const keyword = search.trim().toLowerCase();
    return orders.filter((item) => {
      if (status && item.status !== status) return false;
      if (!keyword) return true;
      const haystack = [
        item.id,
        item.plan_name,
        item.plan_id,
        item.channel_name,
        item.channel_id,
        item.provider,
        item.provider_order_id,
        item.resume_token,
      ]
        .map((value) => String(value || '').toLowerCase())
        .join(' ');
      return haystack.includes(keyword);
    });
  }, [orders, search, status]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const rows = filtered.slice((page - 1) * pageSize, page * pageSize);
  const pendingCount = filtered.filter((item) => item.status === 'pending').length;
  const paidCount = filtered.filter((item) => item.status === 'paid').length;
  const failedCount = filtered.filter((item) => item.status === 'failed').length;
  const totalAmount = filtered.reduce((sum, item) => sum + Number(item.final_price_cents ?? item.amount_cents ?? 0), 0);

  useEffect(() => {
    writeStorageJSON(STORAGE_KEY, {
      search,
      status,
      pageSize,
      visibleColumns: Array.from(visibleColumns),
      visibleFilters: Array.from(visibleFilters),
    });
  }, [pageSize, search, status, visibleColumns, visibleFilters]);

  function toggleColumn(key: OrderColumnKey) {
    setVisibleColumns((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  function toggleFilter(key: OrderFilterKey) {
    setVisibleFilters((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  return (
    <section className="grid-page">
      {buildPageIntro('/orders')}

      <TablePageLayout
        filters={(
          <FilterToolbar
            right={(
              <ToolbarButtonRow>
                <Button onClick={() => void reload()}><RefreshCw size={15} />刷新</Button>
                <ToolsMenu label="筛选设置" icon={false}>
                  <button type="button" onClick={() => toggleFilter('status')}>
                    <span>状态</span>
                    <strong>{visibleFilters.has('status') ? '✓' : ''}</strong>
                  </button>
                </ToolsMenu>
                <ColumnMenu
                  label="列设置"
                  items={[
                    { key: 'plan', label: '计划', checked: visibleColumns.has('plan'), onToggle: () => toggleColumn('plan') },
                    { key: 'channel', label: '通道', checked: visibleColumns.has('channel'), onToggle: () => toggleColumn('channel') },
                    { key: 'amount', label: '金额', checked: visibleColumns.has('amount'), onToggle: () => toggleColumn('amount') },
                    { key: 'status', label: '状态', checked: visibleColumns.has('status'), onToggle: () => toggleColumn('status') },
                    { key: 'fulfillment', label: '履约', checked: visibleColumns.has('fulfillment'), onToggle: () => toggleColumn('fulfillment') },
                  ]}
                />
                <ToolsMenu>
                  <button type="button" onClick={() => { setSearch(''); setStatus(''); setPage(1); }}>
                    <span>清空筛选</span>
                  </button>
                  <button type="button" onClick={() => { setStatus('pending'); setPage(1); }}>
                    <span>仅看待支付</span>
                  </button>
                  <button type="button" onClick={() => { setPageSize(50); setPage(1); }}>
                    <span>切换 50 / 页</span>
                  </button>
                </ToolsMenu>
              </ToolbarButtonRow>
            )}
          >
            <SearchField value={search} placeholder="搜索订单 / 计划 / 通道 / 上游单号" onChange={(value) => { setSearch(value); setPage(1); }} />
            {visibleFilters.has('status') ? (
              <Select value={status} onChange={(event) => { setStatus(event.target.value); setPage(1); }}>
                <option value="">全部状态</option>
                <option value="pending">待支付</option>
                <option value="paid">已支付</option>
                <option value="failed">失败</option>
                <option value="cancelled">已取消</option>
              </Select>
            ) : null}
          </FilterToolbar>
        )}
        table={(
          <div className="table-wrap table-scroll">
            <table>
              <thead>
                <tr>
                  <th>订单</th>
                  {visibleColumns.has('plan') ? <th>计划</th> : null}
                  {visibleColumns.has('channel') ? <th>通道</th> : null}
                  {visibleColumns.has('amount') ? <th>金额</th> : null}
                  {visibleColumns.has('status') ? <th>状态</th> : null}
                  {visibleColumns.has('fulfillment') ? <th>履约</th> : null}
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {rows.length ? rows.map((item) => (
                  <tr key={item.id}>
                    <td><div className="sub2-cell-stack"><strong>{item.id}</strong><small>{getAccountName(item)}</small></div></td>
                    {visibleColumns.has('plan') ? <td><div className="sub2-cell-stack"><strong>{item.plan_name || item.plan_id}</strong><small>{item.group_name || item.group_id || '-'}</small></div></td> : null}
                    {visibleColumns.has('channel') ? <td><div className="sub2-cell-stack"><strong>{item.channel_name || item.channel_id || item.provider || '-'}</strong><small>{item.provider_order_id || item.resume_token || '-'}</small></div></td> : null}
                    {visibleColumns.has('amount') ? <td><strong className="sub2-number-cell">{formatUsdCost(Number(item.final_price_cents ?? item.amount_cents ?? 0) / 100, 2)}</strong></td> : null}
                    {visibleColumns.has('status') ? <td><Badge tone={item.status === 'paid' ? 'ok' : item.status === 'pending' ? 'warn' : 'bad'}>{item.status || '-'}</Badge></td> : null}
                    {visibleColumns.has('fulfillment') ? <td><div className="sub2-cell-stack sub2-cell-stack-tight"><strong>{item.subscription_id || '-'}</strong><small>{Array.isArray(item.fulfillment_logs) ? `${item.fulfillment_logs.length} 条日志` : '0 条日志'}</small></div></td> : null}
                    <td>
                      <RowActions>
                        <RowAction icon={Eye} label="详情" onClick={() => setInspectOrder(item)} />
                        {item.status === 'pending' ? (
                          <RowAction icon={XCircle} label="取消" tone="warn" onClick={() => setCancelTarget(item)} />
                        ) : null}
                      </RowActions>
                    </td>
                  </tr>
                )) : (
                  <ListEmptyRow colSpan={visibleColumns.size + 2} title="暂无订单" />
                )}
              </tbody>
            </table>
          </div>
        )}
        pagination={filtered.length ? (
          <Pager
            page={Math.min(page, totalPages)}
            pageSize={pageSize}
            total={filtered.length}
            onPageChange={(next) => setPage(Math.min(Math.max(1, next), totalPages))}
            onPageSizeChange={(next) => { setPageSize(next); setPage(1); }}
          />
        ) : null}
      />

      {cancelTarget ? (
        <Modal
          title="取消订单"
          size="md"
          onClose={() => setCancelTarget(null)}
          footer={(
            <ModalActions>
              <Button onClick={() => setCancelTarget(null)}>返回</Button>
              <Button tone="danger" disabled={cancelMutation.isPending} onClick={() => cancelMutation.mutate(cancelTarget.id)}>
                确认取消
              </Button>
            </ModalActions>
          )}
        >
          <div className="admin-dialog">
            <div className="admin-dialog-intro">
              <strong>{cancelTarget.id}</strong>
            </div>
            <div className="admin-dialog-summary">
              <div className="admin-dialog-summary-card">
                <span>订阅计划</span>
                <strong>{cancelTarget.plan_name || cancelTarget.plan_id || '-'}</strong>
                <small>{cancelTarget.group_name || cancelTarget.group_id || '-'}</small>
              </div>
              <div className="admin-dialog-summary-card">
                <span>订单金额</span>
                <strong>{formatUsdCost(Number(cancelTarget.final_price_cents ?? cancelTarget.amount_cents ?? 0) / 100, 2)}</strong>
                <small>{cancelTarget.currency || 'CNY'}</small>
              </div>
              <div className="admin-dialog-summary-card">
                <span>当前状态</span>
                <strong>{cancelTarget.status || '-'}</strong>
                <small>{cancelTarget.channel_name || cancelTarget.channel_id || cancelTarget.provider || '-'}</small>
              </div>
            </div>
          </div>
        </Modal>
      ) : null}

      {inspectOrder ? (
        <Modal
          title="订单详情"
          size="lg"
          onClose={() => setInspectOrder(null)}
          footer={<ModalActions><Button onClick={() => setInspectOrder(null)}>关闭</Button></ModalActions>}
        >
          <div className="admin-dialog">
            <div className="admin-dialog-intro">
              <strong>{inspectOrder.id}</strong>
            </div>
            <div className="admin-dialog-summary">
              <div className="admin-dialog-summary-card">
                <span>计划</span>
                <strong>{inspectOrder.plan_name || inspectOrder.plan_id || '-'}</strong>
                <small>{inspectOrder.group_name || inspectOrder.group_id || '-'}</small>
              </div>
              <div className="admin-dialog-summary-card">
                <span>金额</span>
                <strong>{formatUsdCost(Number(inspectOrder.final_price_cents ?? inspectOrder.amount_cents ?? 0) / 100, 2)}</strong>
                <small>{inspectOrder.currency || 'CNY'}</small>
              </div>
              <div className="admin-dialog-summary-card">
                <span>状态</span>
                <strong>{inspectOrder.status || '-'}</strong>
                <small>{inspectOrder.channel_name || inspectOrder.channel_id || inspectOrder.provider || '-'}</small>
              </div>
            </div>
            <div className="admin-dialog-grid">
              <Field label="订单号"><TextInput readOnly value={inspectOrder.id} /></Field>
              <Field label="通道"><TextInput readOnly value={inspectOrder.channel_name || inspectOrder.channel_id || inspectOrder.provider || '-'} /></Field>
              <Field label="上游订单号"><TextInput readOnly value={maskEmpty(inspectOrder.provider_order_id)} /></Field>
              <Field label="恢复标记"><TextInput readOnly value={maskEmpty(inspectOrder.resume_token)} /></Field>
            </div>
            <Field label="拉起参数" full>
              <TextArea readOnly rows={10} value={JSON.stringify(inspectOrder.provider_payload || {}, null, 2)} />
            </Field>
          </div>
        </Modal>
      ) : null}
    </section>
  );
}
