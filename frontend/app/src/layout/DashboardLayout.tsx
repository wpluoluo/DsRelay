import React, { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Link, Outlet, useRouterState } from '@tanstack/react-router';
import { ChevronDown, ChevronLeft, RefreshCw } from 'lucide-react';
import { fetchDashboardState, fetchProxyKeys, saveConfig, testPool } from '../api';
import { Badge, Button } from '../components';
import { PoolModal } from '../features/config/PoolModal';
import { configFromState, normalizePool } from '../features/config/model';
import type { ConfigTab } from '../features/config/model';
import { DashboardProvider } from '../state/dashboardContext';
import { queryClient } from '../state/queryClient';
import { AccountCenterProvider } from '../state/accountCenterContext';
import type { Pool, PoolTestResult, RuntimeConfig } from '../types';
import { adminNavSections, type NavItem } from '../navigation';

export function DashboardLayout() {
  const locationHref = useRouterState({ select: (state) => state.location.href });
  const locationPathname = useRouterState({ select: (state) => state.location.pathname });
  const [configTab, setConfigTab] = useState<ConfigTab>('routing');
  const [draft, setDraft] = useState<RuntimeConfig>({ pools: [] });
  const [dirty, setDirty] = useState(false);
  const [status, setStatus] = useState('');
  const [poolIndex, setPoolIndex] = useState<number | null>(null);
  const [poolDraft, setPoolDraft] = useState<Pool | null>(null);
  const [poolTest, setPoolTest] = useState<PoolTestResult | null>(null);

  const stateQuery = useQuery({
    queryKey: ['dashboard-state'],
    queryFn: fetchDashboardState,
    refetchInterval: 2500,
  });

  const keyQuery = useQuery({
    queryKey: ['proxy-keys'],
    queryFn: fetchProxyKeys,
    refetchInterval: 8000,
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
  const pools = (draft.pools || []).map(normalizePool);
  const [menuOpen, setMenuOpen] = useState<Record<string, boolean>>({
    admin: true,
    account: true,
  });
  const [expandedGroups, setExpandedGroups] = useState<Record<string, boolean>>({});

  const activeGroupKeys = useMemo(() => {
    const keys = new Set<string>();
    for (const section of adminNavSections) {
      for (const item of section.items) {
        if (item.children?.some((child) => locationPathname === child.path)) {
          keys.add(item.key);
        }
      }
    }
    return keys;
  }, [locationPathname]);

  function patchDraft(patch: Partial<RuntimeConfig>) {
    setDraft((current) => ({ ...current, ...patch }));
    setDirty(true);
    setStatus('配置已修改，点击保存并生效。');
  }

  function updatePools(nextPools: Pool[]) {
    patchDraft({ pools: nextPools.map(normalizePool) });
  }

  function openPool(index: number | null) {
    setPoolTest(null);
    setPoolIndex(index);
    setPoolDraft(normalizePool(index == null ? undefined : pools[index]));
  }

  function savePoolDraft() {
    if (!poolDraft) return;
    const next = pools.slice();
    if (poolIndex == null) next.push(normalizePool(poolDraft));
    else next[poolIndex] = normalizePool(poolDraft);
    updatePools(next);
    setPoolDraft(null);
    setPoolIndex(null);
  }

  const contextValue = {
    state,
    stateQuery,
    keyQuery,
    draft,
    pools,
    configTab,
    status,
    saving: saveMutation.isPending,
    setConfigTab,
    patchDraft,
    saveConfig: () => saveMutation.mutate(draft),
    openPool,
    deletePool: (index: number) => updatePools(pools.filter((_, i) => i !== index)),
    movePool: (index: number, direction: number) => {
      const next = pools.slice();
      const target = index + direction;
      if (target < 0 || target >= next.length) return;
      [next[index], next[target]] = [next[target], next[index]];
      updatePools(next);
    },
  };

  return (
    <DashboardProvider value={contextValue}>
      <div className="app-shell">
        <aside className="sidebar">
          <div className="brand">
            <div className="brand-mark">DR</div>
            <div className="brand-copy"><strong>DsRelay</strong><span>管理控制台</span></div>
          </div>
          <nav className="sidebar-nav">
            {adminNavSections.map((section) => (
              <div className="sidebar-group" key={section.key}>
                <button
                  type="button"
                  className="sidebar-group-toggle"
                  onClick={() => setMenuOpen((current) => ({ ...current, [section.key]: !current[section.key] }))}
                >
                  <span>{section.title}</span>
                  <ChevronDown size={14} className={menuOpen[section.key] ? 'sidebar-group-toggle-open' : ''} />
                </button>
                {menuOpen[section.key] ? (
                  <div className="sidebar-group-links">
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
                ) : null}
              </div>
            ))}
          </nav>
        </aside>

        <main className="main">
          <header className="topbar">
            <div className="topbar-main">
              <div className="topbar-title">
                <h1>DsRelay</h1>
                <p>对齐 SUB2 的导航与入口层级</p>
              </div>
            </div>
            <div className="hero-actions">
              <Badge tone={stateQuery.isError ? 'bad' : 'ok'}>{stateQuery.isError ? '连接异常' : '运行中'}</Badge>
              <Button onClick={() => stateQuery.refetch()}><RefreshCw size={15} />刷新</Button>
              <a className="btn btn-danger" href="/logout">退出登录</a>
            </div>
          </header>

          <AccountCenterProvider>
            <Outlet />
          </AccountCenterProvider>
        </main>

        {poolDraft ? (
          <PoolModal
            pool={poolDraft}
            title={poolIndex == null ? '新增连接池' : '管理连接池'}
            testResult={poolTest}
            onChange={setPoolDraft}
            onClose={() => { setPoolDraft(null); setPoolIndex(null); }}
            onSave={savePoolDraft}
            onTest={async () => {
              if (poolIndex == null) return setPoolTest({ ok: false, message: '新连接池保存后再测试。' });
              setPoolTest(await testPool(poolIndex, poolDraft.name));
            }}
          />
        ) : null}
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
  const isActive = pathname === item.path || pathname.startsWith(`${item.path}/`);
  const childActive = Boolean(item.children?.some((child) => pathname === child.path));

  if (item.children?.length) {
    const buttonClass = `sidebar-link sidebar-link-button ${childActive && !expanded ? 'active' : ''}`;
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
                  <Link key={child.key} to={child.path} activeProps={{ className: 'active' }} className="sidebar-link sidebar-link-child">
                    <ChildIcon size={16} />
                    <span>{child.label}</span>
                    <ChevronLeft className="nav-arrow" size={14} />
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
        <Link to={item.path} activeProps={{ className: 'active' }} className={buttonClass} onClick={onToggleGroup}>
          <Icon size={18} />
          <span>{item.label}</span>
          <ChevronDown size={14} className={expanded ? 'sidebar-group-toggle-open nav-arrow-inline' : 'nav-arrow-inline'} />
        </Link>
        {expanded ? (
          <div className="sidebar-nested-children">
            {item.children.map((child) => {
              const ChildIcon = child.icon;
              return (
                <Link key={child.key} to={child.path} activeProps={{ className: 'active' }} className="sidebar-link sidebar-link-child">
                  <ChildIcon size={16} />
                  <span>{child.label}</span>
                  <ChevronLeft className="nav-arrow" size={14} />
                </Link>
              );
            })}
          </div>
        ) : null}
      </div>
    );
  }

  return (
    <Link to={item.path} activeProps={{ className: 'active' }} className={isActive ? 'active' : undefined}>
      <Icon size={18} />
      <span>{item.label}</span>
      <ChevronLeft className="nav-arrow" size={14} />
    </Link>
  );
}
