import type { ReactNode } from 'react';
import { cloneElement, isValidElement, useEffect, useId, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import type { LucideIcon } from 'lucide-react';
import { ChevronDown, ChevronLeft, ChevronRight, MoreHorizontal, Search } from 'lucide-react';
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
      <div className="sub2-table-shell">{table}</div>
      {pagination ? <div className="layout-section-fixed">{pagination}</div> : null}
    </div>
  );
}

export function FilterToolbar({ children, right }: { children?: ReactNode; right?: ReactNode }) {
  return (
    <div className="sub2-filter-toolbar">
      {children ? <div className="sub2-filter-main">{children}</div> : null}
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

export function ListEmptyRow({
  colSpan,
  title,
  description,
  action,
}: {
  colSpan: number;
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <tr>
      <td colSpan={colSpan}>
        <EmptyState title={title} description={description} action={action} />
      </td>
    </tr>
  );
}

export function RowActions({ children }: { children: ReactNode }) {
  return <div className="sub2-action-stack sub2-row-actions">{children}</div>;
}

export function RowAction({
  icon: Icon,
  label,
  tone,
  onClick,
}: {
  icon: LucideIcon;
  label: string;
  tone?: 'default' | 'warn' | 'danger';
  onClick?: () => void;
}) {
  return (
    <button type="button" className={cn('sub2-icon-action', tone === 'warn' && 'warn', tone === 'danger' && 'danger')} onClick={onClick}>
      <Icon size={14} />
      <span>{label}</span>
    </button>
  );
}

export function ToolsMenu({
  label = '更多工具',
  icon = true,
  children,
}: {
  label?: string;
  icon?: boolean;
  children: ReactNode;
}) {
  return (
    <PortalMenu
      trigger={(
        <>
          {icon ? <MoreHorizontal size={14} /> : null}
          <span>{label}</span>
        </>
      )}
    >
      {children}
    </PortalMenu>
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
    <PortalMenu
      trigger={(
        <>
          <span>{label}</span>
          <ChevronDown size={14} />
        </>
      )}
    >
        {items.map((item) => (
          <button key={item.key} type="button" disabled={item.disabled} onClick={item.onToggle}>
            <span>{item.label}</span>
            <strong>{item.checked ? '✓' : ''}</strong>
          </button>
        ))}
    </PortalMenu>
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

function PortalMenu({ trigger, children }: { trigger: ReactNode; children: ReactNode }) {
  const id = useId();
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const panelRef = useRef<HTMLDivElement | null>(null);
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState({ top: 0, left: 0, minWidth: 180 });

  useLayoutEffect(() => {
    if (!open) return;
    const updatePosition = () => {
      const rect = triggerRef.current?.getBoundingClientRect();
      const panel = panelRef.current;
      if (!rect) return;
      const panelWidth = Math.max(180, panel?.offsetWidth || rect.width);
      const gap = 6;
      const left = Math.min(Math.max(8, rect.right - panelWidth), window.innerWidth - panelWidth - 8);
      const belowTop = rect.bottom + gap;
      const panelHeight = panel?.offsetHeight || 0;
      const top = belowTop + panelHeight > window.innerHeight - 8 ? Math.max(8, rect.top - panelHeight - gap) : belowTop;
      setPosition({ top, left, minWidth: Math.max(180, rect.width) });
    };
    updatePosition();
    window.addEventListener('scroll', updatePosition, true);
    window.addEventListener('resize', updatePosition);
    return () => {
      window.removeEventListener('scroll', updatePosition, true);
      window.removeEventListener('resize', updatePosition);
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const handlePointerDown = (event: MouseEvent) => {
      const target = event.target as Node;
      if (triggerRef.current?.contains(target) || panelRef.current?.contains(target)) return;
      setOpen(false);
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', handlePointerDown);
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('mousedown', handlePointerDown);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [open]);

  const panelChildren = mapMenuChildren(children, () => setOpen(false));

  return (
    <div className={cn('sub2-menu', open && 'open')}>
      <button
        ref={triggerRef}
        type="button"
        className="sub2-menu-trigger"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? id : undefined}
        onClick={() => setOpen((current) => !current)}
      >
        {trigger}
      </button>
      {open && typeof document !== 'undefined' ? createPortal(
        <div
          id={id}
          ref={panelRef}
          className="sub2-menu-panel sub2-menu-panel-fixed"
          role="menu"
          style={{ top: `${position.top}px`, left: `${position.left}px`, minWidth: `${position.minWidth}px` }}
        >
          {panelChildren}
        </div>,
        document.body,
      ) : null}
    </div>
  );
}

function mapMenuChildren(children: ReactNode, close: () => void): ReactNode {
  return Array.isArray(children)
    ? children.map((child, index) => mapMenuChild(child, close, index))
    : mapMenuChild(children, close);
}

function mapMenuChild(child: ReactNode, close: () => void, key?: number): ReactNode {
  if (!isValidElement(child)) return child;
  const props = child.props as { onClick?: (event: React.MouseEvent) => void; children?: ReactNode };
  return cloneElement(child, {
    key: child.key ?? key,
    onClick: (event: React.MouseEvent) => {
      props.onClick?.(event);
      if (!event.defaultPrevented) close();
    },
    children: props.children ? mapMenuChildren(props.children, close) : props.children,
  } as Record<string, unknown>);
}
