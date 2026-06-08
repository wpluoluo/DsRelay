import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Eye, RefreshCw, Server, ShieldCheck } from 'lucide-react';
import { fetchAdminAccounts } from '../api';
import { Badge, Button, Field, Modal, ModalActions, TextInput } from '../components';
import { ActionButton, FilterToolbar, ListEmptyRow, Pager, SearchField, TablePageLayout, ToolbarButtonRow, ToolsMenu } from '../components/admin';
import type { AdminAccount } from '../types';
import { formatByteCount, formatNumber, formatTokenCount } from '../utils';

export function AdminAccountsPage() {
  const accountsQuery = useQuery({ queryKey: ['admin-accounts'], queryFn: fetchAdminAccounts, refetchInterval: 10000 });
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [inspectAccount, setInspectAccount] = useState<AdminAccount | null>(null);

  const items = accountsQuery.data?.items || [];
  const filteredItems = useMemo(() => {
    const keyword = search.trim().toLowerCase();
    return items.filter((item) => {
      if (statusFilter) {
        const enabledValue = statusFilter === 'enabled';
        if ((item.enabled !== false) !== enabledValue) return false;
      }
      if (!keyword) return true;
      const haystack = [
        item.provider_name,
        item.pool_name,
        item.route_url,
        ...(item.models || []),
      ]
        .map((value) => String(value || '').toLowerCase())
        .join(' ');
      return haystack.includes(keyword);
    });
  }, [items, search, statusFilter]);

  const totalPages = Math.max(1, Math.ceil(filteredItems.length / pageSize));
  const pagedItems = filteredItems.slice((page - 1) * pageSize, page * pageSize);
  const enabledCount = items.filter((item) => item.enabled !== false).length;
  const requestTotal = items.reduce((sum, item) => sum + Number(item.request_count || 0), 0);
  const tokenTotal = items.reduce((sum, item) => sum + Number(item.total_tokens || 0), 0);
  const errorTotal = items.reduce((sum, item) => sum + Number(item.error_count || 0), 0);

  return (
    <section className="grid-page">
      <div className="sub2-page-head">
        <div className="sub2-page-title">
          <strong>账号管理</strong>
          <span>这里管理的是上游资源账号与线路资源，不是平台用户。用户对象保留在“用户管理”。</span>
        </div>
        <div className="sub2-inline-summary">
          <div className="sub2-inline-summary-item"><span>资源账号</span><strong>{formatNumber(items.length)}</strong><small>当前线路总数</small></div>
          <div className="sub2-inline-summary-item"><span>启用线路</span><strong>{formatNumber(enabledCount)}</strong><small>停用 {formatNumber(items.length - enabledCount)}</small></div>
          <div className="sub2-inline-summary-item"><span>累计请求</span><strong>{formatNumber(requestTotal)}</strong><small>{formatTokenCount(tokenTotal)}</small></div>
          <div className="sub2-inline-summary-item"><span>异常请求</span><strong>{formatNumber(errorTotal)}</strong><small>资源线路观测口径</small></div>
        </div>
      </div>

      <TablePageLayout
        filters={
          <FilterToolbar
            right={
              <ToolbarButtonRow>
                <ActionButton onClick={() => accountsQuery.refetch()}><RefreshCw size={15} />刷新</ActionButton>
                <ToolsMenu>
                  <button type="button" onClick={() => { setSearch(''); setStatusFilter(''); setPage(1); }}>
                    <span>清空筛选</span>
                  </button>
                </ToolsMenu>
              </ToolbarButtonRow>
            }
          >
            <SearchField value={search} placeholder="搜索资源名 / 连接池 / 线路 / 模型" onChange={(value) => { setSearch(value); setPage(1); }} />
            <select value={statusFilter} onChange={(event) => { setStatusFilter(event.target.value); setPage(1); }} className="select">
              <option value="">全部状态</option>
              <option value="enabled">启用</option>
              <option value="disabled">停用</option>
            </select>
          </FilterToolbar>
        }
        table={
          <div className="table-wrap table-scroll">
            <table>
              <thead>
                <tr>
                  <th>资源账号</th>
                  <th>连接池</th>
                  <th>协议</th>
                  <th>模型</th>
                  <th>请求</th>
                  <th>流量</th>
                  <th>状态</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {pagedItems.length ? pagedItems.map((item) => (
                  <tr key={item.id}>
                    <td>
                      <div className="sub2-cell-stack sub2-cell-stack-tight">
                        <strong>{item.provider_name || item.route_url || item.id}</strong>
                        <small>{item.route_url || '-'}</small>
                      </div>
                    </td>
                    <td>
                      <div className="sub2-cell-stack sub2-cell-stack-tight">
                        <strong>{item.pool_name || '-'}</strong>
                        <small>优先级 {formatNumber(item.priority || 0)} · 线路 {formatNumber(item.route_index || 0)}</small>
                      </div>
                    </td>
                    <td>
                      <div className="sub2-cell-stack sub2-cell-stack-tight">
                        <strong>{item.protocol || '-'}</strong>
                        <small>Key {formatNumber(item.key_count || 0)}</small>
                      </div>
                    </td>
                    <td>
                      <div className="sub2-cell-stack sub2-cell-stack-tight">
                        <strong>{item.models?.[0] || '-'}</strong>
                        <small>{item.models?.slice(1, 3).join(' / ') || '未观测到模型'}</small>
                      </div>
                    </td>
                    <td>
                      <div className="sub2-cell-stack sub2-cell-stack-tight">
                        <strong>{formatNumber(item.request_count || 0)}</strong>
                        <small>异常 {formatNumber(item.error_count || 0)}</small>
                      </div>
                    </td>
                    <td>
                      <div className="sub2-cell-stack sub2-cell-stack-tight">
                        <strong>{formatByteCount(item.input_bytes || 0)}</strong>
                        <small>{formatByteCount(item.output_bytes || 0)} / {formatTokenCount(item.total_tokens || 0)}</small>
                      </div>
                    </td>
                    <td><Badge tone={item.enabled === false ? 'warn' : 'ok'}>{item.enabled === false ? '停用' : '启用'}</Badge></td>
                    <td>
                      <Button onClick={() => setInspectAccount(item)}><Eye size={14} />详情</Button>
                    </td>
                  </tr>
                )) : (
                  <ListEmptyRow
                    colSpan={8}
                    title="暂无资源账号数据"
                    description="当前还没有可展示的上游资源线路。"
                    action={<Button onClick={() => accountsQuery.refetch()}><RefreshCw size={14} />刷新</Button>}
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

      {inspectAccount ? (
        <Modal
          title="资源账号详情"
          size="lg"
          onClose={() => setInspectAccount(null)}
          footer={<ModalActions><Button onClick={() => setInspectAccount(null)}>关闭</Button></ModalActions>}
        >
          <div className="admin-dialog">
            <div className="admin-dialog-intro">
              <strong>{inspectAccount.provider_name || inspectAccount.route_url || inspectAccount.id}</strong>
              <span>这里展示的是线路资源观测结果，不承载平台用户编辑动作。</span>
            </div>
            <div className="admin-dialog-summary">
              <div className="admin-dialog-summary-card">
                <span>连接池</span>
                <strong>{inspectAccount.pool_name || '-'}</strong>
                <small>优先级 {formatNumber(inspectAccount.priority || 0)}</small>
              </div>
              <div className="admin-dialog-summary-card">
                <span>状态</span>
                <strong>{inspectAccount.enabled === false ? '停用' : '启用'}</strong>
                <small>协议 {inspectAccount.protocol || '-'}</small>
              </div>
              <div className="admin-dialog-summary-card">
                <span>请求</span>
                <strong>{formatNumber(inspectAccount.request_count || 0)}</strong>
                <small>异常 {formatNumber(inspectAccount.error_count || 0)}</small>
              </div>
            </div>
            <div className="admin-dialog-grid">
              <Field label="线路 URL"><TextInput readOnly value={inspectAccount.route_url || '-'} /></Field>
              <Field label="Key 数量"><TextInput readOnly value={String(inspectAccount.key_count || 0)} /></Field>
              <Field label="冷却秒数"><TextInput readOnly value={String(inspectAccount.cooldown_seconds || 0)} /></Field>
              <Field label="退避次数"><TextInput readOnly value={String(inspectAccount.backoff_attempts || 0)} /></Field>
              <Field label="请求字节"><TextInput readOnly value={formatByteCount(inspectAccount.input_bytes || 0)} /></Field>
              <Field label="响应字节"><TextInput readOnly value={formatByteCount(inspectAccount.output_bytes || 0)} /></Field>
              <Field label="总 Token"><TextInput readOnly value={formatTokenCount(inspectAccount.total_tokens || 0)} /></Field>
              <Field label="最近请求"><TextInput readOnly value={inspectAccount.last_seen_at || '-'} /></Field>
            </div>
            <div className="admin-dialog-note">
              <Server size={14} /> 模型观测：{inspectAccount.models?.join(' / ') || '未观测到模型'}
            </div>
            <div className="admin-dialog-note">
              <ShieldCheck size={14} /> 用户、订阅、订单和 API Key 的业务归属请回到“用户管理 / 订阅管理 / 订单管理 / API Key”。
            </div>
          </div>
        </Modal>
      ) : null}
    </section>
  );
}
