import { useMutation, useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { Pencil, Plus, RefreshCw } from 'lucide-react';
import { fetchAdminContent, saveAdminContent } from '../api';
import { Button, Field, Modal, ModalActions, Select, TextArea, TextInput } from '../components';
import { ActionButton, EmptyState, FilterToolbar, RowAction, RowActions, TablePageLayout, ToolbarButtonRow } from '../components/admin';
import { buildPageIntro } from '../navigation';
import { queryClient } from '../state/queryClient';
import type { AdminContentItem } from '../types';

function ContentTable({
  path,
}: {
  path: '/admin/announcements' | '/admin/risk-control' | '/admin/redeem' | '/admin/promo-codes' | '/admin/affiliates/invites' | '/admin/affiliates/rebates' | '/admin/affiliates/transfers';
}) {
  const query = useQuery({ queryKey: ['admin-content', path], queryFn: () => fetchAdminContent(path), refetchInterval: 30000 });
  const [draft, setDraft] = useState<AdminContentItem | null>(null);
  const items = query.data?.items || [];
  const saveMutation = useMutation({
    mutationFn: (payload: Partial<AdminContentItem>) => saveAdminContent(path, payload),
    onSuccess: async () => {
      setDraft(null);
      await queryClient.invalidateQueries({ queryKey: ['admin-content', path] });
    },
  });

  return (
    <section className="grid-page">
      {buildPageIntro(path)}
      <TablePageLayout
        actions={(
          <div className="sub2-inline-summary">
            <div className="sub2-inline-summary-item"><span>条目数</span><strong>{items.length}</strong><small>{query.data?.label || '-'}</small></div>
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
            <div />
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
                {items.length ? items.map((item) => (
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
                    <td>
                      <RowActions>
                        <RowAction icon={Pencil} label="编辑" onClick={() => setDraft(item)} />
                      </RowActions>
                    </td>
                  </tr>
                )) : (
                  <tr>
                    <td colSpan={5}>
                      <EmptyState title="暂无内容" description="当前模块还没有内容数据。" />
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
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
              <span>这里直接维护当前模块的标题、状态和正文内容。</span>
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
