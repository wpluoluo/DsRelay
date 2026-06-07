import React, { useEffect, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Link, Outlet, useRouterState } from '@tanstack/react-router';
import { BarChart3, ChevronDown, ChevronLeft, Coins, CreditCard, FolderTree, KeyRound, LayoutDashboard, ListChecks, RefreshCw, Server, Settings, Ticket, Users } from 'lucide-react';
import { fetchDashboardState, fetchProxyKeys, saveConfig, testPool } from '../api';
import { Badge, Button } from '../components';
import { PoolModal } from '../features/config/PoolModal';
import { configFromState, normalizePool } from '../features/config/model';
import type { ConfigTab } from '../features/config/model';
import { DashboardProvider } from '../state/dashboardContext';
import { queryClient } from '../state/queryClient';
import { UserCenterProvider } from '../state/userCenterContext';
import type { Pool, PoolTestResult, RuntimeConfig } from '../types';

export function DashboardLayout() {
  const locationHref = useRouterState({ select: (state) => state.location.href });
  const [configTab, setConfigTab] = useState<ConfigTab>('routes');
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
  const runtime = state.runtime || {};
  const pools = (draft.pools || []).map(normalizePool);
  const [menuOpen, setMenuOpen] = useState<Record<string, boolean>>({
    console: true,
    userCenter: true,
    admin: true,
  });

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
            <div className="brand-copy"><strong>DsRelay</strong><span>本地代理控制台</span></div>
          </div>
          <nav className="sidebar-nav">
            <NavGroup
              title="控制台"
              open={menuOpen.console}
              onToggle={() => setMenuOpen((current) => ({ ...current, console: !current.console }))}
            >
              <NavLink to="/" icon={<BarChart3 size={18} />} label="总览仪表盘" />
              <NavLink to="/config" icon={<Settings size={18} />} label="线路与策略" />
              <NavLink to="/proxy-keys" icon={<KeyRound size={18} />} label="入口 API Key" />
              <NavLink to="/requests" icon={<ListChecks size={18} />} label="使用记录" />
              <NavLink to="/logs" icon={<Server size={18} />} label="运行日志" />
            </NavGroup>
            <NavGroup
              title="账户中心"
              open={menuOpen.userCenter}
              onToggle={() => setMenuOpen((current) => ({ ...current, userCenter: !current.userCenter }))}
            >
              <NavLink to="/user-dashboard" icon={<LayoutDashboard size={18} />} label="控制台" />
              <NavLink to="/purchase" icon={<CreditCard size={18} />} label="购买与订阅" />
              <NavLink to="/user-orders" icon={<CreditCard size={18} />} label="支付订单" />
              <NavLink to="/user-subscriptions" icon={<Ticket size={18} />} label="我的订阅" />
              <NavLink to="/keys" icon={<KeyRound size={18} />} label="账户 API Key" />
              <NavLink to="/usage" icon={<BarChart3 size={18} />} label="使用记录" />
            </NavGroup>
            <NavGroup
              title="管理后台"
              open={menuOpen.admin}
              onToggle={() => setMenuOpen((current) => ({ ...current, admin: !current.admin }))}
            >
              <NavLink to="/users" icon={<Users size={18} />} label="账户管理" />
              <NavLink to="/groups" icon={<FolderTree size={18} />} label="分组管理" />
              <NavLink to="/user-api-keys" icon={<KeyRound size={18} />} label="业务 API Key" />
              <NavLink to="/billing" icon={<Coins size={18} />} label="计费管理" />
              <NavLink to="/subscription-plans" icon={<Ticket size={18} />} label="订阅计划" />
              <NavLink to="/subscriptions" icon={<Ticket size={18} />} label="账户订阅" />
              <NavLink to="/payment-channels" icon={<CreditCard size={18} />} label="支付通道" />
              <NavLink to="/payment-orders" icon={<CreditCard size={18} />} label="支付订单" />
            </NavGroup>
          </nav>
        </aside>

        <main className="main">
          <header className="topbar">
            <div className="topbar-main">
              <div className="topbar-title">
                <h1>DsRelay</h1>
                <p>管理控制台</p>
              </div>
            </div>
            <div className="hero-actions">
              <Badge tone={stateQuery.isError ? 'bad' : 'ok'}>{stateQuery.isError ? '连接异常' : '运行中'}</Badge>
              <Button onClick={() => stateQuery.refetch()}><RefreshCw size={15} />刷新</Button>
              <a className="btn btn-danger" href="/logout">退出登录</a>
            </div>
          </header>

          <UserCenterProvider>
            <Outlet />
          </UserCenterProvider>
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

function NavGroup({
  title,
  open,
  onToggle,
  children,
}: {
  title: string;
  open: boolean;
  onToggle: () => void;
  children: React.ReactNode;
}) {
  return (
    <div className="sidebar-group">
      <button type="button" className="sidebar-group-toggle" onClick={onToggle}>
        <span>{title}</span>
        <ChevronDown size={14} className={open ? 'sidebar-group-toggle-open' : ''} />
      </button>
      {open ? <div className="sidebar-group-links">{children}</div> : null}
    </div>
  );
}

function NavLink({ to, icon, label }: { to: string; icon: React.ReactNode; label: string }) {
  return (
    <Link to={to} activeOptions={{ exact: to === '/' }} activeProps={{ className: 'active' }}>
      {icon}
      <span>{label}</span>
      <ChevronLeft className="nav-arrow" size={14} />
    </Link>
  );
}
