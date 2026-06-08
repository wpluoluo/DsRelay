import { useMemo, useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { Eye, RefreshCw, ReceiptText, Wallet, XCircle } from 'lucide-react';
import { updateAdminPaymentOrderStatus } from '../api';
import { Badge, Button, Field, Modal, ModalActions, Select, TextArea, TextInput } from '../components';
import { EmptyState, FilterToolbar, Pager, RowAction, RowActions, SearchField, TablePageLayout, ToolbarButtonRow } from '../components/admin';
import { queryClient } from '../state/queryClient';
import { useAccountCenter } from '../state/accountCenterContext';
import { formatNumber, formatUsdCost, maskEmpty } from '../utils';

export function AccountOrdersPage() {
  const { selectedUser, selectedUserId, orders, reload } = useAccountCenter();
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [cancelTarget, setCancelTarget] = useState<any | null>(null);
  const [inspectOrder, setInspectOrder] = useState<any | null>(null);

  const cancelMutation = useMutation({
    mutationFn: (orderId: string) => updateAdminPaymentOrderStatus(orderId, { status: 'cancelled' }),
    onSuccess: async () => {
      setCancelTarget(null);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['admin-payment-orders'] }),
        reload(),
      ]);
    },
  });

  const filtered = useMemo(() => {
    const keyword = search.trim().toLowerCase();
    return orders.filter((item) => {
      if (selectedUserId && item.account_id !== selectedUserId) return false;
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
  }, [orders, search, selectedUserId, status]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const rows = filtered.slice((page - 1) * pageSize, page * pageSize);
  const pendingCount = filtered.filter((item) => item.status === 'pending').length;
  const paidCount = filtered.filter((item) => item.status === 'paid').length;
  const failedCount = filtered.filter((item) => item.status === 'failed').length;
  const totalAmount = filtered.reduce((sum, item) => sum + Number(item.final_price_cents ?? item.amount_cents ?? 0), 0);

  return (
    <section className="grid-page">
      <div className="sub2-page-head">
        <div className="sub2-page-title">
          <strong>我的订单</strong>
          <span>按 SUB2 个人订单的结构展示筛选、状态与详情，保持用户中心视角。</span>
        </div>
        <div className="sub2-inline-summary">
          <div className="sub2-inline-summary-item"><span>当前用户</span><strong>{selectedUser?.name || '未选择用户'}</strong><small>{selectedUser?.group_name || selectedUser?.source_type || '-'}</small></div>
          <div className="sub2-inline-summary-item"><span>订单总数</span><strong>{formatNumber(filtered.length)}</strong><small>当前筛选范围</small></div>
          <div className="sub2-inline-summary-item"><span>待支付</span><strong>{formatNumber(pendingCount)}</strong><small>已支付 {formatNumber(paidCount)}</small></div>
          <div className="sub2-inline-summary-item"><span>失败订单</span><strong>{formatNumber(failedCount)}</strong><small>累计金额 {formatUsdCost(totalAmount / 100, 2)}</small></div>
        </div>
      </div>

      <TablePageLayout
        filters={(
          <FilterToolbar
            right={(
              <ToolbarButtonRow>
                <Button onClick={() => void reload()}><RefreshCw size={15} />刷新</Button>
              </ToolbarButtonRow>
            )}
          >
            <SearchField value={search} placeholder="搜索订单 / 计划 / 通道 / 上游单号" onChange={(value) => { setSearch(value); setPage(1); }} />
            <Select value={status} onChange={(event) => { setStatus(event.target.value); setPage(1); }}>
              <option value="">全部状态</option>
              <option value="pending">待支付</option>
              <option value="paid">已支付</option>
              <option value="failed">失败</option>
              <option value="cancelled">已取消</option>
            </Select>
          </FilterToolbar>
        )}
        table={(
          <div className="table-wrap table-scroll">
            <table>
              <thead>
                <tr>
                  <th>订单</th>
                  <th>计划</th>
                  <th>通道</th>
                  <th>金额</th>
                  <th>状态</th>
                  <th>履约</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {rows.length ? rows.map((item) => (
                  <tr key={item.id}>
                    <td><div className="sub2-cell-stack"><strong>{item.id}</strong><small>{item.account_name || item.account_id}</small></div></td>
                    <td><div className="sub2-cell-stack"><strong>{item.plan_name || item.plan_id}</strong><small>{item.group_name || item.group_id || '-'}</small></div></td>
                    <td><div className="sub2-cell-stack"><strong>{item.channel_name || item.channel_id || item.provider || '-'}</strong><small>{item.provider_order_id || item.resume_token || '-'}</small></div></td>
                    <td><strong className="sub2-number-cell">{formatUsdCost(Number(item.final_price_cents ?? item.amount_cents ?? 0) / 100, 2)}</strong></td>
                    <td><Badge tone={item.status === 'paid' ? 'ok' : item.status === 'pending' ? 'warn' : 'bad'}>{item.status || '-'}</Badge></td>
                    <td><div className="sub2-cell-stack sub2-cell-stack-tight"><strong>{item.subscription_id || '-'}</strong><small>{Array.isArray(item.fulfillment_logs) ? `${item.fulfillment_logs.length} 条日志` : '0 条日志'}</small></div></td>
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
                  <tr>
                    <td colSpan={7}>
                      <EmptyState title="暂无订单" description="当前用户在筛选条件下没有订单记录。" />
                    </td>
                  </tr>
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
              <span>这会把当前待处理订单状态改为 `cancelled`，不会删除历史记录。</span>
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
                <small>取消后仅保留历史记录</small>
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
              <span>这里可以核对订单状态、金额、通道和拉起参数。</span>
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
