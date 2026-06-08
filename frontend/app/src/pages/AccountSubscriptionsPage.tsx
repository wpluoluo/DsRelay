import { Link } from '@tanstack/react-router';
import { CreditCard, Eye, Ticket } from 'lucide-react';
import { useMemo, useState } from 'react';
import { Button, Empty, Field, Modal, ModalActions, Panel, PanelHead, Select, TextInput } from '../components';
import { useAccountCenter } from '../state/accountCenterContext';
import { formatNumber, formatUsdCost } from '../utils';

export function AccountSubscriptionsPage() {
  const { selectedAccount, selectedAccountId, subscriptions } = useAccountCenter();
  const [statusFilter, setStatusFilter] = useState('');
  const [inspectSubscription, setInspectSubscription] = useState<any | null>(null);
  const rows = useMemo(
    () => subscriptions.filter((item) => (!selectedAccountId || item.account_id === selectedAccountId) && (!statusFilter || item.status === statusFilter)),
    [selectedAccountId, statusFilter, subscriptions],
  );
  const activeRows = rows.filter((item) => item.status === 'active');
  const expiringSoon = rows.filter((item) => {
    const expiresAt = Number(item.expires_at || 0);
    if (!expiresAt) return false;
    const days = Math.ceil((expiresAt * 1000 - Date.now()) / 86400000);
    return days >= 0 && days <= 7;
  });

  return (
    <section className="grid-page">
      <div className="sub2-page-head">
        <div className="sub2-page-title">
          <strong>我的订阅</strong>
          <span>保持 SUB2 账户订阅的卡片式浏览方式，集中查看套餐、周期与额度使用。</span>
        </div>
        <div className="sub2-inline-summary">
          <div className="sub2-inline-summary-item"><span>当前账户</span><strong>{selectedAccount?.name || '未选择账户'}</strong><small>{selectedAccount?.group_name || selectedAccount?.source_type || '请选择账户'}</small></div>
          <div className="sub2-inline-summary-item"><span>订阅总数</span><strong>{formatNumber(rows.length)}</strong><small>有效 {formatNumber(activeRows.length)}</small></div>
          <div className="sub2-inline-summary-item"><span>即将到期</span><strong>{formatNumber(expiringSoon.length)}</strong><small>7 天内</small></div>
          <div className="sub2-inline-summary-item"><span>套餐金额</span><strong>{formatUsdCost(rows.reduce((sum, item) => sum + Number(item.price_cents || 0), 0) / 100, 2)}</strong><small>按订阅价格累计</small></div>
        </div>
      </div>

      <div className="toolbar-inline">
        <Select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
          <option value="">全部状态</option>
          <option value="active">有效</option>
          <option value="expired">过期</option>
          <option value="cancelled">停用</option>
          <option value="revoked">撤销</option>
        </Select>
      </div>

      <div className="channel-grid">
        {rows.length ? rows.map((item) => (
          <Panel className="dashboard-card" key={item.id}>
            <PanelHead
              title={<><Ticket size={18} />{item.plan_name || item.plan_id}</>}
              action={(
                <div className="button-row">
                  <Button onClick={() => setInspectSubscription(item)}><Eye size={14} />详情</Button>
                  <Link to="/purchase" className="btn btn-primary"><CreditCard size={14} />续费</Link>
                </div>
              )}
            />
            <div className="section-stack">
              <div className="metric-line"><span>订阅 ID</span><strong>{item.id}</strong></div>
              <div className="metric-line"><span>状态</span><strong>{item.status || '-'}</strong></div>
              <div className="metric-line"><span>分组</span><strong>{item.group_name || item.group_id || '-'}</strong></div>
              <div className="metric-line"><span>价格</span><strong>{formatUsdCost(Number(item.price_cents || 0) / 100, 2)}</strong></div>
              <div className="sub2-expiry-cell">
                <strong>到期时间</strong>
                <small>{formatDateTime(item.expires_at)}</small>
              </div>
              <UsageMeter label="日用量" used={Number(item.daily_used || 0)} limit={Number(item.daily_limit || 0)} />
              <UsageMeter label="周用量" used={Number(item.weekly_used || 0)} limit={Number(item.weekly_limit || 0)} />
              <UsageMeter label="月用量" used={Number(item.monthly_used || 0)} limit={Number(item.monthly_limit || 0)} />
            </div>
          </Panel>
        )) : <Empty>当前账户暂无订阅。</Empty>}
      </div>

      {inspectSubscription ? (
        <Modal
          title="订阅详情"
          size="lg"
          onClose={() => setInspectSubscription(null)}
          footer={<ModalActions><Button onClick={() => setInspectSubscription(null)}>关闭</Button></ModalActions>}
        >
          <div className="admin-dialog">
            <div className="admin-dialog-intro">
              <strong>{inspectSubscription.plan_name || inspectSubscription.plan_id}</strong>
              <span>查看当前订阅的状态、分组、价格和周期额度。</span>
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
                <small>{inspectSubscription.account_name || inspectSubscription.account_id || '-'}</small>
              </div>
              <div className="admin-dialog-summary-card">
                <span>价格</span>
                <strong>{formatUsdCost(Number(inspectSubscription.price_cents || 0) / 100, 2)}</strong>
                <small>{formatDateTime(inspectSubscription.expires_at)}</small>
              </div>
            </div>
            <div className="admin-dialog-grid">
              <Field label="日限额"><TextInput readOnly value={`${inspectSubscription.daily_used || 0} / ${inspectSubscription.daily_limit || 0}`} /></Field>
              <Field label="周限额"><TextInput readOnly value={`${inspectSubscription.weekly_used || 0} / ${inspectSubscription.weekly_limit || 0}`} /></Field>
              <Field label="月限额"><TextInput readOnly value={`${inspectSubscription.monthly_used || 0} / ${inspectSubscription.monthly_limit || 0}`} /></Field>
              <Field label="到期时间"><TextInput readOnly value={formatDateTime(inspectSubscription.expires_at)} /></Field>
            </div>
          </div>
        </Modal>
      ) : null}
    </section>
  );
}

function UsageMeter({ label, used, limit }: { label: string; used: number; limit: number }) {
  const safeLimit = Math.max(0, Number(limit || 0));
  const safeUsed = Math.max(0, Number(used || 0));
  const percent = safeLimit > 0 ? Math.min(100, Math.round((safeUsed / safeLimit) * 100)) : 0;
  const tone = percent >= 90 ? 'danger' : percent >= 70 ? 'warn' : 'ok';
  return (
    <div className="sub2-usage-cell">
      <div className="sub2-usage-head">
        <span>{label}</span>
        <strong>{safeLimit > 0 ? `${formatNumber(safeUsed)} / ${formatNumber(safeLimit)}` : `${formatNumber(safeUsed)} / 不限额`}</strong>
      </div>
      <div className="sub2-usage-bar">
        <span className={tone} style={{ width: `${safeLimit > 0 ? percent : 100}%` }} />
      </div>
      <small>{safeLimit > 0 ? `已使用 ${percent}%` : '当前计划未设置该周期限额'}</small>
    </div>
  );
}

function formatDateTime(value: unknown) {
  const time = Number(value || 0);
  if (!Number.isFinite(time) || time <= 0) return '-';
  return new Date(time * 1000).toLocaleString('zh-CN', { hour12: false });
}
