import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { CheckCircle2, Copy, Eye, Gift, RefreshCw, Wallet } from 'lucide-react';
import { fetchAccountAffiliate, fetchAccountRedeem, redeemAccountCode, transferAccountAffiliateQuota } from '../api';
import { Badge, Button, Modal, ModalActions, Select, TextInput } from '../components';
import { ColumnMenu, FilterToolbar, ListEmptyRow, Pager, RowAction, RowActions, SearchField, TablePageLayout, ToolbarButtonRow, ToolsMenu } from '../components/admin';
import { useAccountCenter } from '../state/accountCenterContext';
import { queryClient } from '../state/queryClient';
import type { AccountRedeemHistoryItem, AdminContentItem } from '../types';
import { copyTextToClipboard, formatNumber, formatUsdCost, maskEmpty, readStorageJSON, writeStorageJSON } from '../utils';

type RedeemTypeFilter = '' | 'affiliate_transfer' | 'balance' | 'concurrency' | 'subscription';
type RedeemColumnKey = 'type' | 'amount' | 'balance' | 'time' | 'note';
type RedeemFilterKey = 'type';
type AffiliateBucket = '' | '邀请记录' | '返利记录' | '提取记录';
type AffiliateStatusFilter = '' | 'active' | 'draft' | 'disabled';
type AffiliateColumnKey = 'bucket' | 'status' | 'amount' | 'time' | 'note';
type AffiliateFilterKey = 'bucket' | 'status';
type AffiliateActivityRow = AdminContentItem & {
  bucket: Exclude<AffiliateBucket, ''>;
  amount_cents?: number;
};

const REDEEM_STORAGE_KEY = 'account-redeem-view-state';
const AFFILIATE_STORAGE_KEY = 'account-affiliate-view-state';
const DEFAULT_REDEEM_VISIBLE_COLUMNS: RedeemColumnKey[] = ['type', 'amount', 'balance', 'time', 'note'];
const DEFAULT_REDEEM_VISIBLE_FILTERS: RedeemFilterKey[] = ['type'];
const DEFAULT_AFFILIATE_VISIBLE_COLUMNS: AffiliateColumnKey[] = ['bucket', 'status', 'amount', 'time', 'note'];
const DEFAULT_AFFILIATE_VISIBLE_FILTERS: AffiliateFilterKey[] = ['bucket', 'status'];

export function AccountRedeemPage() {
  const { account, reload } = useAccountCenter();
  const savedState = readStorageJSON(REDEEM_STORAGE_KEY, {
    search: '',
    typeFilter: '' as RedeemTypeFilter,
    pageSize: 20,
    visibleColumns: DEFAULT_REDEEM_VISIBLE_COLUMNS,
    visibleFilters: DEFAULT_REDEEM_VISIBLE_FILTERS,
  });

  const [code, setCode] = useState('');
  const [result, setResult] = useState<any | null>(null);
  const [inspectHistory, setInspectHistory] = useState<AccountRedeemHistoryItem | null>(null);
  const [search, setSearch] = useState(savedState.search || '');
  const [typeFilter, setTypeFilter] = useState<RedeemTypeFilter>(savedState.typeFilter || '');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(savedState.pageSize || 20);
  const [visibleColumns, setVisibleColumns] = useState<Set<RedeemColumnKey>>(new Set(savedState.visibleColumns || DEFAULT_REDEEM_VISIBLE_COLUMNS));
  const [visibleFilters, setVisibleFilters] = useState<Set<RedeemFilterKey>>(new Set(savedState.visibleFilters || DEFAULT_REDEEM_VISIBLE_FILTERS));

  const redeemQuery = useQuery({
    queryKey: ['account-redeem'],
    queryFn: () => fetchAccountRedeem(),
    refetchInterval: 30000,
    retry: false,
  });
  const redeemMutation = useMutation({
    mutationFn: (value: string) => redeemAccountCode(value),
    onSuccess: async (payload) => {
      setResult(payload);
      setCode('');
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['account-redeem'] }),
        queryClient.invalidateQueries({ queryKey: ['account-me'] }),
        reload(),
      ]);
    },
  });

  const history = redeemQuery.data?.history || [];
  const balanceCents = redeemQuery.data?.balance_cents ?? account?.balance_cents ?? 0;
  const concurrency = redeemQuery.data?.concurrency_limit ?? account?.concurrency_limit ?? 0;
  const filteredRows = useMemo(() => {
    const keyword = search.trim().toLowerCase();
    return history.filter((item) => {
      if (typeFilter && item.type !== typeFilter) return false;
      if (!keyword) return true;
      return [
        item.id,
        item.type,
        item.note,
        formatRedeemHistoryLabel(item),
      ]
        .map((value) => String(value || '').toLowerCase())
        .join(' ')
        .includes(keyword);
    });
  }, [history, search, typeFilter]);

  const totalPages = Math.max(1, Math.ceil(filteredRows.length / pageSize));
  const pagedRows = useMemo(() => {
    const start = (page - 1) * pageSize;
    return filteredRows.slice(start, start + pageSize);
  }, [filteredRows, page, pageSize]);
  const positiveCount = filteredRows.filter((item) => Number(item.amount_cents || 0) > 0).length;
  const totalRedeemedCents = filteredRows.reduce((sum, item) => sum + Number(item.amount_cents || 0), 0);

  useEffect(() => {
    writeStorageJSON(REDEEM_STORAGE_KEY, {
      search,
      typeFilter,
      pageSize,
      visibleColumns: Array.from(visibleColumns),
      visibleFilters: Array.from(visibleFilters),
    });
  }, [pageSize, search, typeFilter, visibleColumns, visibleFilters]);

  function toggleColumn(key: RedeemColumnKey) {
    setVisibleColumns((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  function toggleFilter(key: RedeemFilterKey) {
    setVisibleFilters((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  function submitRedeem() {
    const value = code.trim();
    if (!value) return;
    redeemMutation.mutate(value);
  }

  return (
    <section className="grid-page">
      <div className="sub2-page-head">
        <div className="sub2-page-title">
          <strong>兑换</strong>
        </div>
        <div className="sub2-inline-summary">
          <div className="sub2-inline-summary-item"><span>账户</span><strong>{account?.name || '-'}</strong><small>{account?.id || '-'}</small></div>
          <div className="sub2-inline-summary-item"><span>余额</span><strong>{formatUsdCost(Number(balanceCents) / 100, 2)}</strong><small>当前余额</small></div>
          <div className="sub2-inline-summary-item"><span>并发</span><strong>{formatNumber(concurrency)}</strong><small>请求并发</small></div>
          <div className="sub2-inline-summary-item"><span>兑换记录</span><strong>{formatNumber(filteredRows.length)}</strong><small>入账 {formatNumber(positiveCount)} · 累计 {formatUsdCost(totalRedeemedCents / 100, 2)}</small></div>
        </div>
      </div>

      <TablePageLayout
        filters={(
          <FilterToolbar
            right={(
              <ToolbarButtonRow>
                <Button onClick={() => void redeemQuery.refetch()}><RefreshCw size={15} />刷新</Button>
                <ToolsMenu label="筛选设置" icon={false}>
                  <button type="button" onClick={() => toggleFilter('type')}>
                    <span>类型</span>
                    <strong>{visibleFilters.has('type') ? '✓' : ''}</strong>
                  </button>
                </ToolsMenu>
                <ColumnMenu
                  label="列设置"
                  items={[
                    { key: 'type', label: '类型', checked: visibleColumns.has('type'), onToggle: () => toggleColumn('type') },
                    { key: 'amount', label: '金额', checked: visibleColumns.has('amount'), onToggle: () => toggleColumn('amount') },
                    { key: 'balance', label: '余额变化', checked: visibleColumns.has('balance'), onToggle: () => toggleColumn('balance') },
                    { key: 'time', label: '时间', checked: visibleColumns.has('time'), onToggle: () => toggleColumn('time') },
                    { key: 'note', label: '说明', checked: visibleColumns.has('note'), onToggle: () => toggleColumn('note') },
                  ]}
                />
                <ToolsMenu>
                  <button type="button" onClick={() => { setSearch(''); setTypeFilter(''); setPage(1); }}>
                    <span>清空筛选</span>
                  </button>
                  <button type="button" onClick={() => { setPageSize(50); setPage(1); }}>
                    <span>切换 50 / 页</span>
                  </button>
                </ToolsMenu>
                <Button tone="primary" disabled={!code.trim() || redeemMutation.isPending} onClick={submitRedeem}>
                  <CheckCircle2 size={15} />兑换
                </Button>
              </ToolbarButtonRow>
            )}
          >
            <SearchField value={search} placeholder="搜索兑换记录 / 备注 / 类型" onChange={(value) => { setSearch(value); setPage(1); }} />
            {visibleFilters.has('type') ? (
              <Select value={typeFilter} onChange={(event) => { setTypeFilter(event.target.value as RedeemTypeFilter); setPage(1); }}>
                <option value="">全部类型</option>
                <option value="affiliate_transfer">邀请返利</option>
                <option value="balance">余额</option>
                <option value="concurrency">并发</option>
                <option value="subscription">订阅</option>
              </Select>
            ) : null}
            <TextInput value={code} placeholder="输入兑换码" onChange={(event) => setCode(event.target.value)} disabled={redeemMutation.isPending} />
          </FilterToolbar>
        )}
        table={(
          <div className="table-wrap table-scroll">
            <table>
              <thead>
                <tr>
                  <th>记录</th>
                  {visibleColumns.has('type') ? <th>类型</th> : null}
                  {visibleColumns.has('amount') ? <th>金额</th> : null}
                  {visibleColumns.has('balance') ? <th>余额变化</th> : null}
                  {visibleColumns.has('time') ? <th>时间</th> : null}
                  {visibleColumns.has('note') ? <th>说明</th> : null}
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {pagedRows.length ? pagedRows.map((item) => (
                  <tr key={item.id}>
                    <td>
                      <div className="sub2-cell-stack sub2-cell-stack-tight">
                        <strong>{formatRedeemHistoryLabel(item)}</strong>
                        <small>{item.id}</small>
                      </div>
                    </td>
                    {visibleColumns.has('type') ? <td>{formatRedeemType(item.type)}</td> : null}
                    {visibleColumns.has('amount') ? (
                      <td><strong className={Number(item.amount_cents || 0) >= 0 ? 'money-positive' : 'money-negative'}>{formatUsdCost(Number(item.amount_cents || 0) / 100, 2)}</strong></td>
                    ) : null}
                    {visibleColumns.has('balance') ? (
                      <td>
                        <div className="sub2-cell-stack sub2-cell-stack-tight">
                          <strong>{formatUsdCost(Number(item.after_balance_cents || 0) / 100, 2)}</strong>
                          <small>前值 {formatUsdCost(Number(item.before_balance_cents || 0) / 100, 2)}</small>
                        </div>
                      </td>
                    ) : null}
                    {visibleColumns.has('time') ? <td>{formatTime(item.created_at)}</td> : null}
                    {visibleColumns.has('note') ? <td>{maskEmpty(item.note)}</td> : null}
                    <td>
                      <RowActions>
                        <RowAction icon={Eye} label="详情" onClick={() => setInspectHistory(item)} />
                      </RowActions>
                    </td>
                  </tr>
                )) : (
                  <ListEmptyRow colSpan={visibleColumns.size + 2} title="暂无兑换记录" />
                )}
              </tbody>
            </table>
          </div>
        )}
        pagination={filteredRows.length ? (
          <Pager
            page={Math.min(page, totalPages)}
            pageSize={pageSize}
            total={filteredRows.length}
            onPageChange={(next) => setPage(Math.min(Math.max(1, next), totalPages))}
            onPageSizeChange={(next) => { setPageSize(next); setPage(1); }}
          />
        ) : null}
      />

      {redeemMutation.error ? (
        <Modal
          title="兑换失败"
          size="md"
          onClose={() => redeemMutation.reset()}
          footer={<ModalActions><Button onClick={() => redeemMutation.reset()}>关闭</Button></ModalActions>}
        >
          <div className="admin-dialog">
            <div className="admin-dialog-intro">
              <strong>{redeemMutation.error instanceof Error ? redeemMutation.error.message : '兑换失败'}</strong>
            </div>
          </div>
        </Modal>
      ) : null}

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

      {inspectHistory ? (
        <Modal
          title="兑换记录详情"
          size="md"
          onClose={() => setInspectHistory(null)}
          footer={<ModalActions><Button onClick={() => setInspectHistory(null)}>关闭</Button></ModalActions>}
        >
          <div className="admin-dialog">
            <div className="admin-dialog-summary">
              <div className="admin-dialog-summary-card"><span>类型</span><strong>{formatRedeemType(inspectHistory.type)}</strong><small>{inspectHistory.id}</small></div>
              <div className="admin-dialog-summary-card"><span>金额</span><strong>{formatUsdCost(Number(inspectHistory.amount_cents || 0) / 100, 2)}</strong><small>{formatTime(inspectHistory.created_at)}</small></div>
              <div className="admin-dialog-summary-card"><span>余额</span><strong>{formatUsdCost(Number(inspectHistory.after_balance_cents || 0) / 100, 2)}</strong><small>前值 {formatUsdCost(Number(inspectHistory.before_balance_cents || 0) / 100, 2)}</small></div>
            </div>
            <div className="sub2-cell-stack">
              <strong>备注</strong>
              <small>{maskEmpty(inspectHistory.note)}</small>
            </div>
          </div>
        </Modal>
      ) : null}
    </section>
  );
}

export function AccountAffiliatePage() {
  const { account, reload } = useAccountCenter();
  const savedState = readStorageJSON(AFFILIATE_STORAGE_KEY, {
    search: '',
    bucketFilter: '' as AffiliateBucket,
    statusFilter: '' as AffiliateStatusFilter,
    pageSize: 20,
    visibleColumns: DEFAULT_AFFILIATE_VISIBLE_COLUMNS,
    visibleFilters: DEFAULT_AFFILIATE_VISIBLE_FILTERS,
  });

  const [copied, setCopied] = useState('');
  const [inspectRow, setInspectRow] = useState<AffiliateActivityRow | null>(null);
  const [search, setSearch] = useState(savedState.search || '');
  const [bucketFilter, setBucketFilter] = useState<AffiliateBucket>(savedState.bucketFilter || '');
  const [statusFilter, setStatusFilter] = useState<AffiliateStatusFilter>(savedState.statusFilter || '');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(savedState.pageSize || 20);
  const [visibleColumns, setVisibleColumns] = useState<Set<AffiliateColumnKey>>(new Set(savedState.visibleColumns || DEFAULT_AFFILIATE_VISIBLE_COLUMNS));
  const [visibleFilters, setVisibleFilters] = useState<Set<AffiliateFilterKey>>(new Set(savedState.visibleFilters || DEFAULT_AFFILIATE_VISIBLE_FILTERS));

  const affiliateQuery = useQuery({
    queryKey: ['account-affiliate'],
    queryFn: () => fetchAccountAffiliate(),
    refetchInterval: 30000,
    retry: false,
  });
  const transferMutation = useMutation({
    mutationFn: () => transferAccountAffiliateQuota(),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['account-affiliate'] }),
        queryClient.invalidateQueries({ queryKey: ['account-redeem'] }),
        queryClient.invalidateQueries({ queryKey: ['account-me'] }),
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
  const activityRows = useMemo<AffiliateActivityRow[]>(() => [
    ...invitees.map((item) => ({ ...item, bucket: '邀请记录' as const })),
    ...rebates.map((item) => ({ ...item, bucket: '返利记录' as const, amount_cents: Number((item as any).amount_cents || 0) })),
    ...transfers.map((item) => ({ ...item, bucket: '提取记录' as const, amount_cents: Number((item as any).amount_cents || 0) })),
  ], [invitees, rebates, transfers]);
  const filteredRows = useMemo(() => {
    const keyword = search.trim().toLowerCase();
    return activityRows.filter((item) => {
      if (bucketFilter && item.bucket !== bucketFilter) return false;
      if (statusFilter && (item.status || '') !== statusFilter) return false;
      if (!keyword) return true;
      return [item.title, item.summary, item.content, item.note, item.id, item.bucket]
        .map((value) => String(value || '').toLowerCase())
        .join(' ')
        .includes(keyword);
    });
  }, [activityRows, bucketFilter, search, statusFilter]);

  const totalPages = Math.max(1, Math.ceil(filteredRows.length / pageSize));
  const pagedRows = useMemo(() => {
    const start = (page - 1) * pageSize;
    return filteredRows.slice(start, start + pageSize);
  }, [filteredRows, page, pageSize]);

  useEffect(() => {
    writeStorageJSON(AFFILIATE_STORAGE_KEY, {
      search,
      bucketFilter,
      statusFilter,
      pageSize,
      visibleColumns: Array.from(visibleColumns),
      visibleFilters: Array.from(visibleFilters),
    });
  }, [bucketFilter, pageSize, search, statusFilter, visibleColumns, visibleFilters]);

  async function copyValue(value: string, key: string) {
    const ok = await copyTextToClipboard(value);
    if (!ok) return;
    setCopied(key);
    window.setTimeout(() => setCopied(''), 1200);
  }

  function toggleColumn(key: AffiliateColumnKey) {
    setVisibleColumns((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  function toggleFilter(key: AffiliateFilterKey) {
    setVisibleFilters((current) => {
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
          <strong>邀请返利</strong>
        </div>
        <div className="sub2-inline-summary">
          <div className="sub2-inline-summary-item"><span>账户</span><strong>{account?.name || '-'}</strong><small>{account?.id || '-'}</small></div>
          <div className="sub2-inline-summary-item"><span>返利比例</span><strong>{formatNumber(detail?.effective_rebate_rate_percent || 0)}%</strong><small>当前策略</small></div>
          <div className="sub2-inline-summary-item"><span>邀请用户</span><strong>{formatNumber(detail?.aff_count || invitees.length)}</strong><small>当前记录 {formatNumber(filteredRows.length)}</small></div>
          <div className="sub2-inline-summary-item"><span>可转余额</span><strong>{formatUsdCost(Number(detail?.aff_quota_cents || 0) / 100, 2)}</strong><small>累计 {formatUsdCost(Number(detail?.aff_history_quota_cents || 0) / 100, 2)}</small></div>
        </div>
      </div>

      <TablePageLayout
        actions={(
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
        )}
        filters={(
          <FilterToolbar
            right={(
              <ToolbarButtonRow>
                <Button onClick={() => void affiliateQuery.refetch()}><RefreshCw size={15} />刷新</Button>
                <ToolsMenu label="筛选设置" icon={false}>
                  <button type="button" onClick={() => toggleFilter('bucket')}>
                    <span>类型</span>
                    <strong>{visibleFilters.has('bucket') ? '✓' : ''}</strong>
                  </button>
                  <button type="button" onClick={() => toggleFilter('status')}>
                    <span>状态</span>
                    <strong>{visibleFilters.has('status') ? '✓' : ''}</strong>
                  </button>
                </ToolsMenu>
                <ColumnMenu
                  label="列设置"
                  items={[
                    { key: 'bucket', label: '类型', checked: visibleColumns.has('bucket'), onToggle: () => toggleColumn('bucket') },
                    { key: 'status', label: '状态', checked: visibleColumns.has('status'), onToggle: () => toggleColumn('status') },
                    { key: 'amount', label: '金额', checked: visibleColumns.has('amount'), onToggle: () => toggleColumn('amount') },
                    { key: 'time', label: '时间', checked: visibleColumns.has('time'), onToggle: () => toggleColumn('time') },
                    { key: 'note', label: '说明', checked: visibleColumns.has('note'), onToggle: () => toggleColumn('note') },
                  ]}
                />
                <ToolsMenu>
                  <button type="button" onClick={() => { setSearch(''); setBucketFilter(''); setStatusFilter(''); setPage(1); }}>
                    <span>清空筛选</span>
                  </button>
                  <button type="button" onClick={() => { setBucketFilter('提取记录'); setPage(1); }}>
                    <span>仅看提取记录</span>
                  </button>
                  <button type="button" onClick={() => { setPageSize(50); setPage(1); }}>
                    <span>切换 50 / 页</span>
                  </button>
                </ToolsMenu>
                <Button tone="primary" disabled={Number(detail?.aff_quota_cents || 0) <= 0 || transferMutation.isPending} onClick={() => transferMutation.mutate()}>
                  <Wallet size={15} />转入余额
                </Button>
              </ToolbarButtonRow>
            )}
          >
            <SearchField value={search} placeholder="搜索邀请 / 返利 / 提取记录" onChange={(value) => { setSearch(value); setPage(1); }} />
            {visibleFilters.has('bucket') ? (
              <Select value={bucketFilter} onChange={(event) => { setBucketFilter(event.target.value as AffiliateBucket); setPage(1); }}>
                <option value="">全部类型</option>
                <option value="邀请记录">邀请记录</option>
                <option value="返利记录">返利记录</option>
                <option value="提取记录">提取记录</option>
              </Select>
            ) : null}
            {visibleFilters.has('status') ? (
              <Select value={statusFilter} onChange={(event) => { setStatusFilter(event.target.value as AffiliateStatusFilter); setPage(1); }}>
                <option value="">全部状态</option>
                <option value="active">active</option>
                <option value="draft">draft</option>
                <option value="disabled">disabled</option>
              </Select>
            ) : null}
          </FilterToolbar>
        )}
        table={(
          <div className="table-wrap table-scroll">
            <table>
              <thead>
                <tr>
                  <th>记录</th>
                  {visibleColumns.has('bucket') ? <th>类型</th> : null}
                  {visibleColumns.has('status') ? <th>状态</th> : null}
                  {visibleColumns.has('amount') ? <th>金额</th> : null}
                  {visibleColumns.has('time') ? <th>时间</th> : null}
                  {visibleColumns.has('note') ? <th>说明</th> : null}
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {pagedRows.length ? pagedRows.map((item) => (
                  <tr key={`${item.bucket}-${item.id}`}>
                    <td>
                      <div className="sub2-cell-stack">
                        <strong>{item.title || item.id}</strong>
                        <small>{item.summary || item.note || item.id}</small>
                      </div>
                    </td>
                    {visibleColumns.has('bucket') ? <td>{item.bucket}</td> : null}
                    {visibleColumns.has('status') ? <td><Badge tone={item.status === 'disabled' ? 'warn' : 'ok'}>{item.status || '-'}</Badge></td> : null}
                    {visibleColumns.has('amount') ? (
                      <td>{item.amount_cents === undefined ? '-' : <strong className={Number(item.amount_cents || 0) >= 0 ? 'money-positive' : 'money-negative'}>{formatUsdCost(Number(item.amount_cents || 0) / 100, 2)}</strong>}</td>
                    ) : null}
                    {visibleColumns.has('time') ? <td>{formatTime(item.updated_at || item.created_at)}</td> : null}
                    {visibleColumns.has('note') ? <td>{maskEmpty(item.note || item.content || item.summary)}</td> : null}
                    <td>
                      <RowActions>
                        <RowAction icon={Eye} label="详情" onClick={() => setInspectRow(item)} />
                      </RowActions>
                    </td>
                  </tr>
                )) : (
                  <ListEmptyRow colSpan={visibleColumns.size + 2} title="暂无返利记录" />
                )}
              </tbody>
            </table>
          </div>
        )}
        pagination={filteredRows.length ? (
          <Pager
            page={Math.min(page, totalPages)}
            pageSize={pageSize}
            total={filteredRows.length}
            onPageChange={(next) => setPage(Math.min(Math.max(1, next), totalPages))}
            onPageSizeChange={(next) => { setPageSize(next); setPage(1); }}
          />
        ) : null}
      />

      {transferMutation.error ? (
        <Modal
          title="转入失败"
          size="md"
          onClose={() => transferMutation.reset()}
          footer={<ModalActions><Button onClick={() => transferMutation.reset()}>关闭</Button></ModalActions>}
        >
          <div className="admin-dialog">
            <div className="admin-dialog-intro">
              <strong>{transferMutation.error instanceof Error ? transferMutation.error.message : '转入失败'}</strong>
            </div>
          </div>
        </Modal>
      ) : null}

      {inspectRow ? (
        <Modal
          title="返利记录详情"
          size="md"
          onClose={() => setInspectRow(null)}
          footer={<ModalActions><Button onClick={() => setInspectRow(null)}>关闭</Button></ModalActions>}
        >
          <div className="admin-dialog">
            <div className="admin-dialog-summary">
              <div className="admin-dialog-summary-card"><span>类型</span><strong>{inspectRow.bucket}</strong><small>{inspectRow.id}</small></div>
              <div className="admin-dialog-summary-card"><span>状态</span><strong>{inspectRow.status || '-'}</strong><small>{formatTime(inspectRow.updated_at || inspectRow.created_at)}</small></div>
              <div className="admin-dialog-summary-card"><span>金额</span><strong>{inspectRow.amount_cents === undefined ? '-' : formatUsdCost(Number(inspectRow.amount_cents || 0) / 100, 2)}</strong><small>{inspectRow.title || '-'}</small></div>
            </div>
            <div className="sub2-cell-stack">
              <strong>摘要</strong>
              <small>{maskEmpty(inspectRow.summary)}</small>
            </div>
            <div className="sub2-cell-stack">
              <strong>说明</strong>
              <small>{maskEmpty(inspectRow.note || inspectRow.content)}</small>
            </div>
          </div>
        </Modal>
      ) : null}
    </section>
  );
}

function formatRedeemHistoryLabel(item: AccountRedeemHistoryItem) {
  if (item.type === 'affiliate_transfer') return '邀请返利入账';
  if (item.type === 'balance') return '余额兑换';
  if (item.type === 'concurrency') return '并发兑换';
  if (item.type === 'subscription') return '订阅兑换';
  return item.type || '兑换记录';
}

function formatRedeemType(value?: string) {
  if (value === 'affiliate_transfer') return '邀请返利';
  if (value === 'balance') return '余额';
  if (value === 'concurrency') return '并发';
  if (value === 'subscription') return '订阅';
  return value || '-';
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
