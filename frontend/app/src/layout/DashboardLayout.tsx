import React, { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Link, Outlet, useNavigate, useRouterState } from '@tanstack/react-router';
import { ChevronDown, RefreshCw } from 'lucide-react';
import { fetchDashboardState, saveConfig } from '../api';
import { Badge, Button } from '../components';
import { configFromState, normalizePool } from '../features/config/model';
import type { ConfigTab } from '../features/config/model';
import { DashboardProvider } from '../state/dashboardContext';
import { queryClient } from '../state/queryClient';
import { AccountCenterProvider } from '../state/accountCenterContext';
import type { RuntimeConfig } from '../types';
import { adminNavSections, getRouteMeta, type NavItem } from '../navigation';

export function DashboardLayout() {
  const locationHref = useRouterState({ select: (state) => state.location.href });
  const locationPathname = useRouterState({ select: (state) => state.location.pathname });
  const navigate = useNavigate();
  const [configTab, setConfigTab] = useState<ConfigTab>('routing');
  const [draft, setDraft] = useState<RuntimeConfig>({ pools: [] });
  const [dirty, setDirty] = useState(false);
  const [status, setStatus] = useState('');

  const stateQuery = useQuery({
    queryKey: ['dashboard-state'],
    queryFn: fetchDashboardState,
    refetchInterval: 2500,
  });

  useEffect(() => {
    if (stateQuery.data?.config && !dirty) {
      setDraft(configFromState(stateQuery.data.config));
    }
  }, [stateQuery.data?.config, dirty]);

  useEffect(() => {
    window.scrollTo({ top: 0, left: 0, behavior: 'auto' });
  }, [locationHref]);

  const saveMutation = useMutation({
    mutationFn: saveConfig,
    onSuccess: (data) => {
      queryClient.setQueryData(['dashboard-state'], data);
      setDraft(configFromState(data.config));
      setDirty(false);
      setStatus('配置已保存并生效。');
    },
    onError: (error) => setStatus(error instanceof Error ? error.message : '保存失败'),
  });

  const state = stateQuery.data || {};
  const isAuthPending = stateQuery.isLoading && !stateQuery.data;
  const role = state.auth?.role === 'user' ? 'user' : 'admin';
  const isAdminPath = locationPathname === '/admin' || locationPathname.startsWith('/admin/');
  const navSections = useMemo(
    () => {
      if (isAuthPending) return [];
      return role === 'user' ? adminNavSections.filter((section) => section.key === 'account') : adminNavSections;
    },
    [isAuthPending, role],
  );
  const pools = (draft.pools || []).map(normalizePool);
  const [expandedGroups, setExpandedGroups] = useState<Record<string, boolean>>({});

  const activeGroupKeys = useMemo(() => {
    const keys = new Set<string>();
    for (const section of navSections) {
      for (const item of section.items) {
        if (item.children?.some((child) => navPathMatches(locationPathname, child.path))) {
          keys.add(item.key);
        }
      }
    }
    return keys;
  }, [locationPathname, navSections]);

  useEffect(() => {
    if (isAuthPending || role !== 'user') return;
    if (locationPathname === '/' || locationPathname.startsWith('/admin')) {
      navigate({ to: '/keys', replace: true });
    }
  }, [isAuthPending, locationPathname, navigate, role]);

  function patchDraft(patch: Partial<RuntimeConfig>) {
    setDraft((current) => ({ ...current, ...patch }));
    setDirty(true);
    setStatus('配置已修改，点击保存并生效。');
  }

  const contextValue = {
    state,
    stateQuery,
    draft,
    pools,
    configTab,
    status,
    saving: saveMutation.isPending,
    setConfigTab,
    patchDraft,
    saveConfig: () => saveMutation.mutate(draft),
  };
  const holdAdminOutlet = isAdminPath && (isAuthPending || role === 'user');
  const currentMeta = getRouteMeta(locationPathname);
  const currentSectionTitle = role === 'user' ? '我的账户' : (isAdminPath ? '管理后台' : '我的账户');

  return (
    <DashboardProvider value={contextValue}>
      <div className="app-shell">
        <aside className="sidebar">
          <div className="brand">
            <div className="brand-mark">DR</div>
            <div className="brand-copy"><strong>DsRelay</strong><span>{currentSectionTitle}</span></div>
          </div>
          <nav className="sidebar-nav">
            {navSections.map((section) => (
              <div className="sidebar-section" key={section.key}>
                <div className="sidebar-section-title">
                  <span>{section.title}</span>
                </div>
                <div className="sidebar-section-links">
                  {section.items.map((item) => (
                    <SidebarItem
                      key={item.key}
                      item={item}
                      pathname={locationPathname}
                      expanded={Boolean(expandedGroups[item.key] || activeGroupKeys.has(item.key))}
                      onToggleGroup={() => setExpandedGroups((current) => ({ ...current, [item.key]: !(current[item.key] || activeGroupKeys.has(item.key)) }))}
                    />
                  ))}
                </div>
              </div>
            ))}
          </nav>
        </aside>

        <main className="main">
          <header className="topbar">
            <div className="topbar-main">
              <div className="topbar-title">
                <h1>{currentMeta?.title || '仪表盘'}</h1>
                <p>{currentSectionTitle}</p>
              </div>
            </div>
            <div className="hero-actions">
              <Badge tone={stateQuery.isError ? 'bad' : 'ok'}>{stateQuery.isError ? '连接异常' : '运行中'}</Badge>
              <Button onClick={() => stateQuery.refetch()}><RefreshCw size={15} />刷新</Button>
              <a className="btn btn-danger" href="/logout">退出登录</a>
            </div>
          </header>

          <AccountCenterProvider>
            {holdAdminOutlet ? null : <Outlet />}
          </AccountCenterProvider>
        </main>

      </div>
    </DashboardProvider>
  );
}

function SidebarItem({
  item,
  pathname,
  expanded,
  onToggleGroup,
}: {
  item: NavItem;
  pathname: string;
  expanded: boolean;
  onToggleGroup: () => void;
}) {
  const Icon = item.icon;
  const isActive = navPathMatches(pathname, item.path);
  const childActive = Boolean(item.children?.some((child) => navPathMatches(pathname, child.path)));

  if (item.children?.length) {
    const buttonClass = `sidebar-link sidebar-link-button ${childActive ? 'active' : ''}`;
    if (item.expandOnly) {
      return (
        <div className="sidebar-nested">
          <button type="button" className={buttonClass} onClick={onToggleGroup}>
            <Icon size={18} />
            <span>{item.label}</span>
            <ChevronDown size={14} className={expanded ? 'sidebar-group-toggle-open nav-arrow-inline' : 'nav-arrow-inline'} />
          </button>
          {expanded ? (
            <div className="sidebar-nested-children">
              {item.children.map((child) => {
                const ChildIcon = child.icon;
                return (
                  <Link
                    key={child.key}
                    to={child.path}
                    activeOptions={{ exact: true }}
                    className={`sidebar-link sidebar-link-child ${navPathMatches(pathname, child.path, true) ? 'active' : ''}`}
                  >
                    <ChildIcon size={16} />
                    <span>{child.label}</span>
                  </Link>
                );
              })}
            </div>
          ) : null}
        </div>
      );
    }
    return (
      <div className="sidebar-nested">
        <Link to={item.path} className={buttonClass} onClick={onToggleGroup}>
          <Icon size={18} />
          <span>{item.label}</span>
          <ChevronDown size={14} className={expanded ? 'sidebar-group-toggle-open nav-arrow-inline' : 'nav-arrow-inline'} />
        </Link>
        {expanded ? (
          <div className="sidebar-nested-children">
            {item.children.map((child) => {
              const ChildIcon = child.icon;
              return (
                <Link
                  key={child.key}
                  to={child.path}
                  activeOptions={{ exact: true }}
                  className={`sidebar-link sidebar-link-child ${navPathMatches(pathname, child.path, true) ? 'active' : ''}`}
                >
                  <ChildIcon size={16} />
                  <span>{child.label}</span>
                </Link>
              );
            })}
          </div>
        ) : null}
      </div>
    );
  }

  return (
    <Link to={item.path} className={`sidebar-link ${isActive ? 'active' : ''}`}>
      <Icon size={20} />
      <span>{item.label}</span>
    </Link>
  );
}

function navPathMatches(pathname: string, targetPath: string, exact = false): boolean {
  if (pathname === targetPath) return true;
  if (exact) return false;
  if (targetPath === '/admin/orders') return false;
  return pathname.startsWith(`${targetPath}/`);
}
