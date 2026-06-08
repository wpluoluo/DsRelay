import { useMemo, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { CheckCircle2, Copy, Gift, RefreshCw, Wallet } from 'lucide-react';
import { fetchAccountAffiliate, fetchAccountRedeem, redeemAccountCode, transferAccountAffiliateQuota } from '../api';
import { Badge, Button, Field, Modal, ModalActions, Panel, PanelHead, TextInput } from '../components';
import { EmptyState, FilterToolbar, Pager, RowAction, RowActions, SearchField, TablePageLayout, ToolbarButtonRow } from '../components/admin';
import { buildPageIntro } from '../navigation';
import { useAccountCenter } from '../state/accountCenterContext';
import { queryClient } from '../state/queryClient';
import type { AccountRedeemHistoryItem, AdminContentItem } from '../types';
import { copyTextToClipboard, formatNumber, formatUsdCost, maskEmpty } from '../utils';

export function AccountRedeemPage() {
  const { selectedUser, selectedUserId, reload } = useAccountCenter();
  const [code, setCode] = useState('');
  const [result, setResult] = useState<any | null>(null);
  const redeemQuery = useQuery({
    queryKey: ['account-redeem', selectedUserId],
    queryFn: () => fetchAccountRedeem(selectedUserId),
    enabled: Boolean(selectedUserId),
    refetchInterval: 30000,
  });
  const redeemMutation = useMutation({
    mutationFn: (value: string) => redeemAccountCode(selectedUserId, value),
    onSuccess: async (payload) => {
      setResult(payload);
      setCode('');
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['account-redeem', selectedUserId] }),
        queryClient.invalidateQueries({ queryKey: ['admin-users'] }),
        reload(),
      ]);
    },
  });
  const history = redeemQuery.data?.history || [];
  const latestHistory = history.slice(0, 20);
  const balanceCents = redeemQuery.data?.balance_cents ?? selectedUser?.balance_cents ?? 0;
  const concurrency = redeemQuery.data?.concurrency_limit ?? selectedUser?.concurrency_limit ?? 0;

  function submitRedeem(event: React.FormEvent) {
    event.preventDefault();
    const value = code.trim();
    if (!value || !selectedUserId) return;
    redeemMutation.mutate(value);
  }

  return (
    <section className="grid-page">
      {buildPageIntro('/redeem')}
      <div className="sub2-inline-summary">
        <div className="sub2-inline-summary-item"><span>当前用户</span><strong>{selectedUser?.name || '未选择用户'}</strong><small>{selectedUserId || '-'}</small></div>
        <div className="sub2-inline-summary-item"><span>余额</span><strong>{formatUsdCost(Number(balanceCents) / 100, 2)}</strong><small>账户余额</small></div>
        <div className="sub2-inline-summary-item"><span>并发</span><strong>{formatNumber(concurrency)}</strong><small>请求数</small></div>
        <div className="sub2-inline-summary-item"><span>兑换记录</span><strong>{formatNumber(history.length)}</strong><small>最近记录</small></div>
      </div>
      <div className="account-value-grid">
        <Panel>
          <PanelHead title={<><Gift size={18} />兑换码</>} />
          <form className="account-value-form" onSubmit={submitRedeem}>
            <Field label="兑换码" full>
              <TextInput value={code} onChange={(event) => setCode(event.target.value)} disabled={!selectedUserId || redeemMutation.isPending} />
            </Field>
            {redeemMutation.error ? <div className="status-msg err">{redeemMutation.error instanceof Error ? redeemMutation.error.message : '兑换失败'}</div> : null}
            <div className="modal-actions">
              <Button type="button" onClick={() => void redeemQuery.refetch()}><RefreshCw size={15} />刷新</Button>
              <Button type="submit" tone="primary" disabled={!selectedUserId || !code.trim() || redeemMutation.isPending}>
                <CheckCircle2 size={15} />兑换
              </Button>
            </div>
          </form>
        </Panel>
        <Panel>
          <PanelHead title={<><Wallet size={18} />最近活动</>} />
          <div className="admin-entry-list">
            {latestHistory.length ? latestHistory.map((item) => (
              <RedeemHistoryRow key={item.id} item={item} />
            )) : <EmptyState title="暂无兑换记录" />}
          </div>
        </Panel>
      </div>
      {result ? (
        <Modal
          title="兑换结果"
          size="md"
          onClose={() => setResult(null)}
          footer={<ModalActions><Button onClick={() => setResult(null)}>关闭</Button></ModalActions>}
        >
          <div className="admin-dialog">
            <div className="admin-dialog-summary">
              <div className="admin-dialog-summary-card"><span>类型</span><strong>{result.type || '-'}</strong><small>{result.code || '-'}</small></div>
              <div className="admin-dialog-summary-card"><span>值</span><strong>{formatRedeemValue(result)}</strong><small>{result.plan_name || result.plan_id || '-'}</small></div>
              <div className="admin-dialog-summary-card"><span>余额</span><strong>{result.balance_cents === undefined ? '-' : formatUsdCost(Number(result.balance_cents) / 100, 2)}</strong><small>{result.message || '-'}</small></div>
            </div>
          </div>
        </Modal>
      ) : null}
    </section>
  );
}

export function AccountAffiliatePage() {
  const { selectedUser, selectedUserId, reload } = useAccountCenter();
  const [copied, setCopied] = useState('');
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const affiliateQuery = useQuery({
    queryKey: ['account-affiliate', selectedUserId],
    queryFn: () => fetchAccountAffiliate(selectedUserId),
    enabled: Boolean(selectedUserId),
    refetchInterval: 30000,
  });
  const transferMutation = useMutation({
    mutationFn: () => transferAccountAffiliateQuota(selectedUserId),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['account-affiliate', selectedUserId] }),
        queryClient.invalidateQueries({ queryKey: ['account-redeem', selectedUserId] }),
        queryClient.invalidateQueries({ queryKey: ['admin-users'] }),
        reload(),
      ]);
    },
  });
  const detail = affiliateQuery.data;
  const affCode = detail?.aff_code || '';
  const inviteLink = affCode ? `${window.location.origin}/register?aff=${encodeURIComponent(affCode)}` : '';
  const invitees = detail?.invitees || [];
  const rebates = detail?.rebates || [];
  const transfers = detail?.transfers || [];
  const activityRows = useMemo(() => {
    const keyword = search.trim().toLowerCase();
    return [...rebates.map((item) => ({ ...item, bucket: '返利记录' })), ...transfers.map((item) => ({ ...item, bucket: '提取记录' }))]
      .filter((item) => {
        if (!keyword) return true;
        return [item.title, item.summary, item.content, item.note, item.bucket]
          .map((value) => String(value || '').toLowerCase())
          .join(' ')
          .includes(keyword);
      });
  }, [rebates, search, transfers]);
  const totalPages = Math.max(1, Math.ceil(activityRows.length / pageSize));
  const pagedRows = activityRows.slice((page - 1) * pageSize, page * pageSize);

  async function copyValue(value: string, key: string) {
    const ok = await copyTextToClipboard(value);
    if (!ok) return;
    setCopied(key);
    window.setTimeout(() => setCopied(''), 1200);
  }

  return (
    <section className="grid-page">
      {buildPageIntro('/affiliate')}
      <div className="sub2-inline-summary">
        <div className="sub2-inline-summary-item"><span>当前用户</span><strong>{selectedUser?.name || '未选择用户'}</strong><small>{selectedUserId || '-'}</small></div>
        <div className="sub2-inline-summary-item"><span>返利比例</span><strong>{formatNumber(detail?.effective_rebate_rate_percent || 0)}%</strong><small>当前策略</small></div>
        <div className="sub2-inline-summary-item"><span>邀请用户</span><strong>{formatNumber(detail?.aff_count || invitees.length)}</strong><small>邀请记录</small></div>
        <div className="sub2-inline-summary-item"><span>可转余额</span><strong>{formatUsdCost(Number(detail?.aff_quota_cents || 0) / 100, 2)}</strong><small>累计 {formatUsdCost(Number(detail?.aff_history_quota_cents || 0) / 100, 2)}</small></div>
      </div>
      <Panel>
        <PanelHead
          title="邀请信息"
          action={(
            <div className="button-row">
              <Button onClick={() => void affiliateQuery.refetch()}><RefreshCw size={15} />刷新</Button>
              <Button tone="primary" disabled={!selectedUserId || Number(detail?.aff_quota_cents || 0) <= 0 || transferMutation.isPending} onClick={() => transferMutation.mutate()}>
                转入余额
              </Button>
            </div>
          )}
        />
        <div className="account-invite-grid">
          <div className="generated-key-box">
            <div className="generated-key-title">邀请码</div>
            <div className="generated-key-row">
              <div className="generated-key-value">{affCode || '-'}</div>
              <Button onClick={() => copyValue(affCode, 'code')} disabled={!affCode}><Copy size={14} />{copied === 'code' ? '已复制' : '复制'}</Button>
            </div>
          </div>
          <div className="generated-key-box">
            <div className="generated-key-title">邀请链接</div>
            <div className="generated-key-row">
              <div className="generated-key-value">{inviteLink || '-'}</div>
              <Button onClick={() => copyValue(inviteLink, 'link')} disabled={!inviteLink}><Copy size={14} />{copied === 'link' ? '已复制' : '复制'}</Button>
            </div>
          </div>
        </div>
        {transferMutation.error ? <div className="status-msg err">{transferMutation.error instanceof Error ? transferMutation.error.message : '转入失败'}</div> : null}
      </Panel>
      <TablePageLayout
        filters={(
          <FilterToolbar>
            <SearchField value={search} placeholder="搜索返利 / 提取记录" onChange={(value) => { setSearch(value); setPage(1); }} />
          </FilterToolbar>
        )}
        table={(
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>记录</th>
                  <th>类型</th>
                  <th>金额</th>
                  <th>状态</th>
                  <th>时间</th>
                </tr>
              </thead>
              <tbody>
                {pagedRows.length ? pagedRows.map((item) => (
                  <tr key={`${item.bucket}-${item.id}`}>
                    <td><div className="sub2-cell-stack"><strong>{item.title}</strong><small>{item.summary || item.note || item.id}</small></div></td>
                    <td>{item.bucket}</td>
                    <td><strong className="sub2-number-cell">{formatUsdCost(Number((item as any).amount_cents || 0) / 100, 2)}</strong></td>
                    <td><Badge tone={item.status === 'disabled' ? 'warn' : 'ok'}>{item.status || '-'}</Badge></td>
                    <td>{formatTime(item.updated_at || item.created_at)}</td>
                  </tr>
                )) : (
                  <tr><td colSpan={5}><EmptyState title="暂无返利记录" /></td></tr>
                )}
              </tbody>
            </table>
          </div>
        )}
        pagination={activityRows.length ? (
          <Pager
            page={Math.min(page, totalPages)}
            pageSize={pageSize}
            total={activityRows.length}
            onPageChange={(next) => setPage(Math.min(Math.max(1, next), totalPages))}
            onPageSizeChange={(next) => { setPageSize(next); setPage(1); }}
          />
        ) : null}
      />
    </section>
  );
}

function RedeemHistoryRow({ item }: { item: AccountRedeemHistoryItem }) {
  const amount = Number(item.amount_cents || 0);
  return (
    <div className="admin-sort-item">
      <div>
        <strong>{item.type === 'affiliate_transfer' ? '邀请返利' : '兑换入账'}</strong>
        <small>{maskEmpty(item.note)} · {formatTime(item.created_at)}</small>
      </div>
      <strong className={amount >= 0 ? 'money-positive' : 'money-negative'}>{formatUsdCost(amount / 100, 2)}</strong>
    </div>
  );
}

function formatRedeemValue(result: any) {
  if (result.type === 'balance') return formatUsdCost(Number(result.value || 0) / 100, 2);
  if (result.type === 'concurrency') return `${formatNumber(result.value || 0)} 并发`;
  if (result.type === 'subscription') return result.plan_name || result.plan_id || '-';
  return maskEmpty(result.value);
}

function formatTime(value?: number) {
  if (!value) return '-';
  const date = value > 1e12 ? new Date(value) : new Date(value * 1000);
  return Number.isNaN(date.getTime()) ? '-' : date.toLocaleString('zh-CN', { hour12: false });
}
