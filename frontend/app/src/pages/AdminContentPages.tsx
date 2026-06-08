import { useMutation, useQuery } from '@tanstack/react-query';
import { useMemo, useState } from 'react';
import { Ban, Pencil, Plus, RefreshCw, ShieldCheck, Trash2 } from 'lucide-react';
import { deleteAdminContent, fetchAdminContent, saveAdminContent } from '../api';
import { Button, Field, Modal, ModalActions, Select, TextArea, TextInput } from '../components';
import { ActionButton, FilterToolbar, ListEmptyRow, Pager, RowAction, RowActions, SearchField, TablePageLayout, ToolbarButtonRow, ToolsMenu } from '../components/admin';
import { buildPageIntro } from '../navigation';
import { queryClient } from '../state/queryClient';
import type { AdminContentItem } from '../types';

type AdminContentPath = '/admin/announcements' | '/admin/risk-control' | '/admin/redeem' | '/admin/promo-codes' | '/admin/affiliates/invites' | '/admin/affiliates/rebates' | '/admin/affiliates/transfers';
type StatusFilter = '' | 'active' | 'draft' | 'disabled';

function ContentTable({
  path,
}: {
  path: AdminContentPath;
}) {
  const query = useQuery({ queryKey: ['admin-content', path], queryFn: () => fetchAdminContent(path), refetchInterval: 30000 });
  const [draft, setDraft] = useState<AdminContentItem | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<AdminContentItem | null>(null);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const items = query.data?.items || [];
  const activeCount = items.filter((item) => item.status === 'active').length;
  const disabledCount = items.filter((item) => item.status === 'disabled').length;
  const filteredItems = useMemo(() => {
    const keyword = search.trim().toLowerCase();
    return items.filter((item) => {
      if (statusFilter && item.status !== statusFilter) return false;
      if (!keyword) return true;
      const haystack = [item.title, item.summary, item.content, item.note, item.id]
        .map((value) => String(value || '').toLowerCase())
        .join(' ');
      return haystack.includes(keyword);
    });
  }, [items, search, statusFilter]);
  const totalPages = Math.max(1, Math.ceil(filteredItems.length / pageSize));
  const pagedItems = filteredItems.slice((page - 1) * pageSize, page * pageSize);
  const saveMutation = useMutation({
    mutationFn: (payload: Partial<AdminContentItem>) => saveAdminContent(path, payload),
    onSuccess: async () => {
      setDraft(null);
      await queryClient.invalidateQueries({ queryKey: ['admin-content', path] });
    },
  });
  const deleteMutation = useMutation({
    mutationFn: (itemId: string) => deleteAdminContent(path, itemId),
    onSuccess: async () => {
      setDeleteTarget(null);
      await queryClient.invalidateQueries({ queryKey: ['admin-content', path] });
    },
  });

  function toggleItemStatus(item: AdminContentItem) {
    saveMutation.mutate({ ...item, status: item.status === 'disabled' ? 'active' : 'disabled' });
  }

  return (
    <section className="grid-page">
      {buildPageIntro(path)}
      <TablePageLayout
        actions={(
          <div className="sub2-inline-summary">
            <div className="sub2-inline-summary-item"><span>条目数</span><strong>{items.length}</strong><small>{query.data?.label || '-'}</small></div>
            <div className="sub2-inline-summary-item"><span>启用</span><strong>{activeCount}</strong><small>停用 {disabledCount}</small></div>
            <div className="sub2-inline-summary-item"><span>筛选结果</span><strong>{filteredItems.length}</strong><small>{statusFilter || '全部状态'}</small></div>
          </div>
        )}
        filters={(
          <FilterToolbar
            right={(
              <ToolbarButtonRow>
                <ActionButton onClick={() => query.refetch()}><RefreshCw size={15} />刷新</ActionButton>
                <Button tone="primary" onClick={() => setDraft({ id: '', title: '', status: 'active', summary: '', content: '', note: '' })}>
                  <Plus size={15} />新增
                </Button>
              </ToolbarButtonRow>
            )}
          >
            <SearchField value={search} placeholder="搜索标题 / 摘要 / 内容" onChange={(value) => { setSearch(value); setPage(1); }} />
            <Select value={statusFilter} onChange={(event) => { setStatusFilter(event.target.value as StatusFilter); setPage(1); }}>
              <option value="">全部状态</option>
              <option value="active">active</option>
              <option value="draft">draft</option>
              <option value="disabled">disabled</option>
            </Select>
          </FilterToolbar>
        )}
        table={(
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>标题</th>
                  <th>状态</th>
                  <th>摘要</th>
                  <th>更新时间</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {pagedItems.length ? pagedItems.map((item) => (
                  <tr key={item.id}>
                    <td>
                      <div className="sub2-cell-stack sub2-cell-stack-tight">
                        <strong>{item.title}</strong>
                        <small>{item.id}</small>
                      </div>
                    </td>
                    <td>{item.status || '-'}</td>
                    <td>{item.summary || item.note || '-'}</td>
                    <td>{formatTime(item.updated_at)}</td>
                    <td className="row-actions-cell">
                      <RowActions>
                        <RowAction icon={Pencil} label="编辑" onClick={() => setDraft(item)} />
                        <ToolsMenu label="更多">
                          <button type="button" onClick={() => toggleItemStatus(item)}><span>{item.status === 'disabled' ? '启用' : '停用'}</span>{item.status === 'disabled' ? <ShieldCheck size={14} /> : <Ban size={14} />}</button>
                          <button type="button" className="danger" onClick={() => setDeleteTarget(item)}><span>删除</span><Trash2 size={14} /></button>
                        </ToolsMenu>
                      </RowActions>
                    </td>
                  </tr>
                )) : (
                  <ListEmptyRow colSpan={5} title="暂无内容" action={<Button tone="primary" onClick={() => setDraft({ id: '', title: '', status: 'active', summary: '', content: '', note: '' })}>新增</Button>} />
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
      {draft ? (
        <Modal
          title={draft.id ? '编辑内容' : '新增内容'}
          size="lg"
          onClose={() => setDraft(null)}
          footer={
            <ModalActions>
              <Button onClick={() => setDraft(null)}>取消</Button>
              <Button tone="primary" disabled={saveMutation.isPending || !draft.title?.trim()} onClick={() => saveMutation.mutate(draft)}>
                保存
              </Button>
            </ModalActions>
          }
        >
          <div className="admin-dialog">
            <div className="admin-dialog-intro">
              <strong>{query.data?.label || '内容维护'}</strong>
            </div>
            <div className="admin-dialog-grid modal-grid">
              <Field label="标题"><TextInput value={draft.title || ''} onChange={(event) => setDraft({ ...draft, title: event.target.value })} /></Field>
              <Field label="状态">
                <Select value={draft.status || 'active'} onChange={(event) => setDraft({ ...draft, status: event.target.value })}>
                  <option value="active">active</option>
                  <option value="disabled">disabled</option>
                  <option value="draft">draft</option>
                </Select>
              </Field>
            </div>
            <Field label="摘要" full><TextInput value={draft.summary || ''} onChange={(event) => setDraft({ ...draft, summary: event.target.value })} /></Field>
            <Field label="正文" full><TextArea rows={8} value={draft.content || ''} onChange={(event) => setDraft({ ...draft, content: event.target.value })} /></Field>
            <Field label="备注" full><TextArea rows={3} value={draft.note || ''} onChange={(event) => setDraft({ ...draft, note: event.target.value })} /></Field>
          </div>
        </Modal>
      ) : null}
      {deleteTarget ? (
        <Modal
          title="删除内容"
          size="md"
          onClose={() => setDeleteTarget(null)}
          footer={
            <ModalActions>
              <Button onClick={() => setDeleteTarget(null)}>取消</Button>
              <Button tone="danger" disabled={deleteMutation.isPending} onClick={() => deleteMutation.mutate(deleteTarget.id)}>
                删除
              </Button>
            </ModalActions>
          }
        >
          <div className="admin-dialog">
            <div className="admin-dialog-intro">
              <strong>{deleteTarget.title}</strong>
            </div>
          </div>
        </Modal>
      ) : null}
    </section>
  );
}

function formatTime(value?: number) {
  if (!value) return '-';
  const date = value > 1e12 ? new Date(value) : new Date(value * 1000);
  return Number.isNaN(date.getTime()) ? '-' : date.toLocaleString('zh-CN', { hour12: false });
}

export const AdminAnnouncementsPage = () => <ContentTable path="/admin/announcements" />;
export const AdminRiskControlPage = () => <ContentTable path="/admin/risk-control" />;
export const AdminRedeemCodesPage = () => <ContentTable path="/admin/redeem" />;
export const AdminPromoCodesPage = () => <ContentTable path="/admin/promo-codes" />;
export const AdminAffiliateInvitesPage = () => <ContentTable path="/admin/affiliates/invites" />;
export const AdminAffiliateRebatesPage = () => <ContentTable path="/admin/affiliates/rebates" />;
export const AdminAffiliateTransfersPage = () => <ContentTable path="/admin/affiliates/transfers" />;
