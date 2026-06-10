import { Link } from '@tanstack/react-router';
import { CreditCard, Eye, RefreshCw } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { Badge, Button, Field, Modal, ModalActions, Select, TextInput } from '../components';
import {
  ColumnMenu,
  FilterToolbar,
  ListEmptyRow,
  Pager,
  RowAction,
  RowActions,
  SearchField,
  TablePageLayout,
  ToolbarButtonRow,
  ToolsMenu,
} from '../components/admin';
import { buildPageIntro } from '../navigation';
import { useAccountCenter } from '../state/accountCenterContext';
import type { AdminAccountSubscription } from '../types';
import { formatNumber, formatUsdCost, readStorageJSON, writeStorageJSON } from '../utils';

type SubscriptionColumnKey = 'status' | 'daily' | 'weekly' | 'monthly' | 'expires';
type SubscriptionFilterKey = 'status' | 'group';

const DEFAULT_VISIBLE_COLUMNS: SubscriptionColumnKey[] = ['status', 'daily', 'weekly', 'monthly', 'expires'];
const DEFAULT_VISIBLE_FILTERS: SubscriptionFilterKey[] = ['status', 'group'];
const STORAGE_KEY = 'account-subscriptions-view-state';

export function AccountSubscriptionsPage() {
  const { groups, subscriptions, reload } = useAccountCenter();
  const savedState = readStorageJSON(STORAGE_KEY, {
    search: '',
    statusFilter: '',
    groupFilter: '',
    pageSize: 20,
    visibleColumns: DEFAULT_VISIBLE_COLUMNS,
    visibleFilters: DEFAULT_VISIBLE_FILTERS,
  });

  const [search, setSearch] = useState(savedState.search || '');
  const [statusFilter, setStatusFilter] = useState(savedState.statusFilter || '');
  const [groupFilter, setGroupFilter] = useState(savedState.groupFilter || '');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(savedState.pageSize || 20);
  const [visibleColumns, setVisibleColumns] = useState<Set<SubscriptionColumnKey>>(new Set(savedState.visibleColumns || DEFAULT_VISIBLE_COLUMNS));
  const [visibleFilters, setVisibleFilters] = useState<Set<SubscriptionFilterKey>>(new Set(savedState.visibleFilters || DEFAULT_VISIBLE_FILTERS));
  const [inspectSubscription, setInspectSubscription] = useState<AdminAccountSubscription | null>(null);

  const groupOptions = useMemo(() => {
    const fromGroups = groups.map((group) => ({ id: group.id, name: group.name || group.id }));
    const existing = new Set(fromGroups.map((group) => group.id));
    const fromSubscriptions = subscriptions
      .filter((item) => item.group_id && !existing.has(String(item.group_id)))
      .map((item) => ({ id: String(item.group_id), name: String(item.group_name || item.group_id) }));
    return [...fromGroups, ...fromSubscriptions].sort((left, right) => left.name.localeCompare(right.name, 'zh-CN'));
  }, [groups, subscriptions]);

  const filteredItems = useMemo(() => {
    const keyword = search.trim().toLowerCase();
    return subscriptions.filter((item) => {
      if (statusFilter && item.status !== statusFilter) return false;
      if (groupFilter && String(item.group_id || '') !== groupFilter) return false;
      if (!keyword) return true;
      const haystack = [
        item.id,
        item.plan_name,
        item.plan_id,
        item.group_name,
        item.group_id,
        item.status,
      ]
        .map((value) => String(value || '').toLowerCase())
        .join(' ');
      return haystack.includes(keyword);
    });
  }, [groupFilter, search, statusFilter, subscriptions]);

  const totalPages = Math.max(1, Math.ceil(filteredItems.length / pageSize));
  const pagedItems = useMemo(() => {
    const start = (page - 1) * pageSize;
    return filteredItems.slice(start, start + pageSize);
  }, [filteredItems, page, pageSize]);
  useEffect(() => {
    writeStorageJSON(STORAGE_KEY, {
      search,
      statusFilter,
      groupFilter,
      pageSize,
      visibleColumns: Array.from(visibleColumns),
      visibleFilters: Array.from(visibleFilters),
    });
  }, [groupFilter, pageSize, search, statusFilter, visibleColumns, visibleFilters]);

  function toggleColumn(key: SubscriptionColumnKey) {
    setVisibleColumns((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  function toggleFilter(key: SubscriptionFilterKey) {
    setVisibleFilters((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  return (
    <section className="grid-page">
      {buildPageIntro('/subscriptions')}

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
                  <button type="button" onClick={() => toggleFilter('group')}>
                    <span>分组</span>
                    <strong>{visibleFilters.has('group') ? '✓' : ''}</strong>
                  </button>
                </ToolsMenu>
                <ColumnMenu
                  label="列设置"
                  items={[
                    { key: 'status', label: '状态', checked: visibleColumns.has('status'), onToggle: () => toggleColumn('status') },
                    { key: 'daily', label: '日用量', checked: visibleColumns.has('daily'), onToggle: () => toggleColumn('daily') },
                    { key: 'weekly', label: '周用量', checked: visibleColumns.has('weekly'), onToggle: () => toggleColumn('weekly') },
                    { key: 'monthly', label: '月用量', checked: visibleColumns.has('monthly'), onToggle: () => toggleColumn('monthly') },
                    { key: 'expires', label: '到期时间', checked: visibleColumns.has('expires'), onToggle: () => toggleColumn('expires') },
                  ]}
                />
                <ToolsMenu>
                  <button type="button" onClick={() => { setSearch(''); setStatusFilter(''); setGroupFilter(''); setPage(1); }}>
                    <span>清空筛选</span>
                  </button>
                  <button type="button" onClick={() => { setStatusFilter('active'); setPage(1); }}>
                    <span>仅看有效订阅</span>
                  </button>
                  <button type="button" onClick={() => { setPageSize(50); setPage(1); }}>
                    <span>切换 50 / 页</span>
                  </button>
                </ToolsMenu>
                <Link to="/purchase" className="btn btn-primary">
                  <CreditCard size={15} />
                  <span>充值/订阅</span>
                </Link>
              </ToolbarButtonRow>
            )}
          >
            <SearchField value={search} placeholder="搜索订阅 / 计划 / 分组" onChange={(value) => { setSearch(value); setPage(1); }} />
            {visibleFilters.has('status') ? (
              <Select value={statusFilter} onChange={(event) => { setStatusFilter(event.target.value); setPage(1); }}>
                <option value="">全部状态</option>
                <option value="active">active</option>
                <option value="expired">expired</option>
                <option value="cancelled">cancelled</option>
                <option value="revoked">revoked</option>
              </Select>
            ) : null}
            {visibleFilters.has('group') ? (
              <Select value={groupFilter} onChange={(event) => { setGroupFilter(event.target.value); setPage(1); }}>
                <option value="">全部分组</option>
                {groupOptions.map((group) => (
                  <option key={group.id} value={group.id}>{group.name}</option>
                ))}
              </Select>
            ) : null}
          </FilterToolbar>
        )}
        table={(
          <div className="table-wrap table-scroll">
            <table>
              <thead>
                <tr>
                  <th>订阅</th>
                  <th>计划</th>
                  <th>分组 / 价格</th>
                  {visibleColumns.has('status') ? <th>状态</th> : null}
                  {visibleColumns.has('daily') ? <th>日用量</th> : null}
                  {visibleColumns.has('weekly') ? <th>周用量</th> : null}
                  {visibleColumns.has('monthly') ? <th>月用量</th> : null}
                  {visibleColumns.has('expires') ? <th>到期时间</th> : null}
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {pagedItems.length ? pagedItems.map((item) => (
                  <tr key={item.id}>
                    <td>
                      <div className="sub2-cell-stack sub2-cell-stack-tight">
                        <strong>{item.id}</strong>
                        <small>{formatDateTime(item.started_at)}</small>
                      </div>
                    </td>
                    <td>
                      <div className="sub2-cell-stack sub2-cell-stack-tight">
                        <strong>{item.plan_name || item.plan_id || '-'}</strong>
                        <small>{item.plan_id || '-'}</small>
                      </div>
                    </td>
                    <td>
                      <div className="sub2-cell-stack sub2-cell-stack-tight">
                        <strong>{item.group_name || item.group_id || '-'}</strong>
                        <small>{formatUsdCost(Number(item.price_cents || 0) / 100, 2)} · 倍率 ×{formatNumber(item.rate_multiplier || 1)}</small>
                      </div>
                    </td>
                    {visibleColumns.has('status') ? (
                      <td>
                        <Badge tone={item.status === 'active' ? 'ok' : item.status === 'expired' ? 'warn' : 'bad'}>
                          {item.status || '-'}
                        </Badge>
                      </td>
                    ) : null}
                    {visibleColumns.has('daily') ? <td><UsageProgress used={Number(item.daily_used || 0)} limit={Number(item.daily_limit || 0)} label="日" /></td> : null}
                    {visibleColumns.has('weekly') ? <td><UsageProgress used={Number(item.weekly_used || 0)} limit={Number(item.weekly_limit || 0)} label="周" /></td> : null}
                    {visibleColumns.has('monthly') ? <td><UsageProgress used={Number(item.monthly_used || 0)} limit={Number(item.monthly_limit || 0)} label="月" /></td> : null}
                    {visibleColumns.has('expires') ? <td><ExpiryCell value={item.expires_at} /></td> : null}
                    <td className="row-actions-cell">
                      <RowActions>
                        <RowAction icon={Eye} label="详情" onClick={() => setInspectSubscription(item)} />
                        <Link to="/purchase" className="sub2-icon-action">
                          <CreditCard size={14} />
                          <span>续费</span>
                        </Link>
                      </RowActions>
                    </td>
                  </tr>
                )) : (
                  <ListEmptyRow
                    colSpan={visibleColumns.size + 4}
                    title="暂无订阅"
                    action={(
                      <Link to="/purchase" className="btn btn-primary">
                        充值/订阅
                      </Link>
                    )}
                  />
                )}
              </tbody>
            </table>
          </div>
        )}
        pagination={filteredItems.length ? (
          <Pager
            page={Math.min(page, totalPages)}
            pageSize={pageSize}
            total={filteredItems.length}
            onPageChange={(next) => setPage(Math.min(Math.max(1, next), totalPages))}
            onPageSizeChange={(next) => { setPageSize(next); setPage(1); }}
          />
        ) : null}
      />

      {inspectSubscription ? (
        <Modal
          title="订阅详情"
          size="lg"
          onClose={() => setInspectSubscription(null)}
          footer={(
            <ModalActions>
              <Link to="/purchase" className="btn btn-primary">
                充值/订阅
              </Link>
              <Button onClick={() => setInspectSubscription(null)}>关闭</Button>
            </ModalActions>
          )}
        >
          <div className="admin-dialog">
            <div className="admin-dialog-intro">
              <strong>{inspectSubscription.plan_name || inspectSubscription.plan_id || '-'}</strong>
            </div>
            <div className="admin-dialog-summary">
              <div className="admin-dialog-summary-card">
                <span>状态</span>
                <strong>{inspectSubscription.status || '-'}</strong>
                <small>{inspectSubscription.id}</small>
              </div>
              <div className="admin-dialog-summary-card">
                <span>分组</span>
                <strong>{inspectSubscription.group_name || inspectSubscription.group_id || '-'}</strong>
                <small>{formatDateTime(inspectSubscription.started_at)}</small>
              </div>
              <div className="admin-dialog-summary-card">
                <span>价格</span>
                <strong>{formatUsdCost(Number(inspectSubscription.price_cents || 0) / 100, 2)}</strong>
                <small>{formatDateTime(inspectSubscription.expires_at)}</small>
              </div>
            </div>
            <div className="admin-dialog-grid">
              <Field label="订阅 ID"><TextInput readOnly value={inspectSubscription.id} /></Field>
              <Field label="计划"><TextInput readOnly value={inspectSubscription.plan_name || inspectSubscription.plan_id || '-'} /></Field>
              <Field label="日额度"><TextInput readOnly value={`${formatNumber(inspectSubscription.daily_used || 0)} / ${formatNumber(inspectSubscription.daily_limit || 0)}`} /></Field>
              <Field label="周额度"><TextInput readOnly value={`${formatNumber(inspectSubscription.weekly_used || 0)} / ${formatNumber(inspectSubscription.weekly_limit || 0)}`} /></Field>
              <Field label="月额度"><TextInput readOnly value={`${formatNumber(inspectSubscription.monthly_used || 0)} / ${formatNumber(inspectSubscription.monthly_limit || 0)}`} /></Field>
              <Field label="到期时间"><TextInput readOnly value={formatDateTime(inspectSubscription.expires_at)} /></Field>
            </div>
          </div>
        </Modal>
      ) : null}
    </section>
  );
}

function UsageProgress({ used, limit, label }: { used: number; limit: number; label: string }) {
  const safeUsed = Math.max(0, Number(used || 0));
  const safeLimit = Math.max(0, Number(limit || 0));
  if (!safeLimit) {
    return (
      <div className="sub2-cell-stack sub2-cell-stack-tight">
        <strong>{formatNumber(safeUsed)}</strong>
        <small>{label}不限额</small>
      </div>
    );
  }
  const percent = Math.min(100, Math.round((safeUsed / safeLimit) * 100));
  const tone = percent >= 90 ? 'danger' : percent >= 70 ? 'warn' : 'ok';
  return (
    <div className="sub2-usage-cell">
      <div className="sub2-usage-head">
        <span>{label}</span>
        <strong>{formatNumber(safeUsed)} / {formatNumber(safeLimit)}</strong>
      </div>
      <div className="sub2-usage-bar">
        <span className={tone} style={{ width: `${percent}%` }} />
      </div>
      <small>已使用 {percent}%</small>
    </div>
  );
}

function ExpiryCell({ value }: { value: number | string | null | undefined }) {
  const timestamp = normalizeTimestamp(value);
  if (!timestamp) {
    return (
      <div className="sub2-cell-stack sub2-cell-stack-tight">
        <strong>-</strong>
        <small>未设置</small>
      </div>
    );
  }
  const remaining = timestamp - Date.now();
  const days = Math.ceil(remaining / 86400000);
  const tone = remaining < 0 ? 'sub2-number-bad' : days <= 7 ? 'sub2-number-warn' : '';
  return (
    <div className="sub2-cell-stack sub2-cell-stack-tight">
      <strong className={tone}>{formatDateTime(value)}</strong>
      <small>{remaining < 0 ? '已过期' : `${formatNumber(days)} 天内`}</small>
    </div>
  );
}

function normalizeTimestamp(value: unknown): number {
  if (value === null || value === undefined || value === '') return 0;
  if (typeof value === 'number') {
    return value > 1e12 ? value : value * 1000;
  }
  const text = String(value).trim();
  if (!text) return 0;
  const asNumber = Number(text);
  if (Number.isFinite(asNumber) && asNumber > 0) {
    return asNumber > 1e12 ? asNumber : asNumber * 1000;
  }
  const asDate = new Date(text).getTime();
  return Number.isFinite(asDate) ? asDate : 0;
}

function formatDateTime(value: unknown) {
  const timestamp = normalizeTimestamp(value);
  if (!timestamp) return '-';
  return new Date(timestamp).toLocaleString('zh-CN', { hour12: false });
}

function isExpiringSoon(value: unknown) {
  const timestamp = normalizeTimestamp(value);
  if (!timestamp) return false;
  const days = Math.ceil((timestamp - Date.now()) / 86400000);
  return days >= 0 && days <= 7;
}
