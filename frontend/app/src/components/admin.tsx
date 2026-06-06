import type { ReactNode } from 'react';
import { ChevronDown, ChevronLeft, ChevronRight, Search } from 'lucide-react';
import { Button } from '../components';
import { cn } from '../utils';

export function TablePageLayout({
  actions,
  filters,
  table,
  pagination,
}: {
  actions?: ReactNode;
  filters?: ReactNode;
  table: ReactNode;
  pagination?: ReactNode;
}) {
  return (
    <div className="sub2-page-layout">
      {actions ? <div className="layout-section-fixed">{actions}</div> : null}
      {filters ? <div className="layout-section-fixed">{filters}</div> : null}
      <div className="layout-section-scrollable">
        <div className="sub2-table-shell">{table}</div>
      </div>
      {pagination ? <div className="layout-section-fixed">{pagination}</div> : null}
    </div>
  );
}

export function FilterToolbar({ children, right }: { children: ReactNode; right?: ReactNode }) {
  return (
    <div className="sub2-filter-toolbar">
      <div className="sub2-filter-main">{children}</div>
      {right ? <div className="sub2-filter-actions">{right}</div> : null}
    </div>
  );
}

export function SearchField({
  value,
  placeholder,
  onChange,
  className,
}: {
  value: string;
  placeholder: string;
  onChange: (value: string) => void;
  className?: string;
}) {
  return (
    <label className={cn('sub2-search-field', className)}>
      <Search size={16} />
      <input value={value} placeholder={placeholder} onChange={(event) => onChange(event.target.value)} />
    </label>
  );
}

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="sub2-empty-state">
      <div className="sub2-empty-icon">□</div>
      <h3>{title}</h3>
      {description ? <p>{description}</p> : null}
      {action ? <div className="sub2-empty-action">{action}</div> : null}
    </div>
  );
}

export function Pager({
  page,
  pageSize,
  total,
  onPageChange,
  onPageSizeChange,
}: {
  page: number;
  pageSize: number;
  total: number;
  onPageChange: (page: number) => void;
  onPageSizeChange: (pageSize: number) => void;
}) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const from = total ? (page - 1) * pageSize + 1 : 0;
  const to = Math.min(total, page * pageSize);
  const pages = buildPages(page, totalPages);

  return (
    <div className="sub2-pager">
      <div className="sub2-pager-meta">
        <span>
          显示 {from} - {to} / {total}
        </span>
        <select value={pageSize} onChange={(event) => onPageSizeChange(Number(event.target.value || 20))}>
          {[10, 20, 50, 100].map((size) => (
            <option key={size} value={size}>
              {size} / 页
            </option>
          ))}
        </select>
      </div>
      <div className="sub2-pager-nav">
        <button type="button" onClick={() => onPageChange(page - 1)} disabled={page <= 1} aria-label="上一页">
          <ChevronLeft size={16} />
        </button>
        {pages.map((item, index) =>
          item === '...' ? (
            <span key={`ellipsis-${index}`} className="sub2-pager-gap">
              ...
            </span>
          ) : (
            <button
              key={item}
              type="button"
              className={item === page ? 'active' : ''}
              onClick={() => onPageChange(item)}
            >
              {item}
            </button>
          ),
        )}
        <button type="button" onClick={() => onPageChange(page + 1)} disabled={page >= totalPages} aria-label="下一页">
          <ChevronRight size={16} />
        </button>
      </div>
    </div>
  );
}

export function ColumnMenu({
  label,
  items,
}: {
  label: string;
  items: Array<{ key: string; label: string; checked: boolean; disabled?: boolean; onToggle: () => void }>;
}) {
  return (
    <details className="sub2-menu">
      <summary>
        <span>{label}</span>
        <ChevronDown size={14} />
      </summary>
      <div className="sub2-menu-panel">
        {items.map((item) => (
          <button key={item.key} type="button" disabled={item.disabled} onClick={item.onToggle}>
            <span>{item.label}</span>
            <strong>{item.checked ? '✓' : ''}</strong>
          </button>
        ))}
      </div>
    </details>
  );
}

export function ToolbarButtonRow({ children }: { children: ReactNode }) {
  return <div className="sub2-toolbar-row">{children}</div>;
}

export function ActionButton({
  children,
  tone,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { tone?: 'primary' | 'ghost' | 'danger' }) {
  return (
    <Button tone={tone || 'ghost'} className="sub2-action-btn" {...props}>
      {children}
    </Button>
  );
}

function buildPages(page: number, totalPages: number): Array<number | '...'> {
  if (totalPages <= 7) {
    return Array.from({ length: totalPages }, (_, index) => index + 1);
  }
  const items: Array<number | '...'> = [1];
  const start = Math.max(2, page - 1);
  const end = Math.min(totalPages - 1, page + 1);
  if (start > 2) items.push('...');
  for (let current = start; current <= end; current += 1) items.push(current);
  if (end < totalPages - 1) items.push('...');
  items.push(totalPages);
  return items;
}
