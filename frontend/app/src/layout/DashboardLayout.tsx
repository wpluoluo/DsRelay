import React, { useEffect, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Link, Outlet } from '@tanstack/react-router';
import { Activity, BarChart3, ChevronLeft, Coins, CreditCard, Database, FolderTree, KeyRound, ListChecks, RefreshCw, Server, Settings, Ticket, Users, Wifi } from 'lucide-react';
import { fetchDashboardState, fetchProxyKeys, saveConfig, testPool } from '../api';
import { Badge, Button } from '../components';
import { PoolModal } from '../features/config/PoolModal';
import { configFromState, normalizePool } from '../features/config/model';
import type { ConfigTab } from '../features/config/model';
import { DashboardProvider } from '../state/dashboardContext';
import { queryClient } from '../state/queryClient';
import type { Pool, PoolTestResult, RuntimeConfig } from '../types';
import { formatUptime } from '../utils';

export function DashboardLayout() {
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
  const recentRequests = Array.isArray(state.recent_requests) ? state.recent_requests : [];
  const activeRequests = Array.isArray(state.active_requests) ? state.active_requests : [];
  const pools = (draft.pools || []).map(normalizePool);

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
            <div className="sidebar-section-title">总览</div>
            <NavLink to="/" icon={<BarChart3 size={18} />} label="总览仪表盘" />
            <NavLink to="/requests" icon={<ListChecks size={18} />} label="使用记录" />
            <NavLink to="/logs" icon={<Server size={18} />} label="运行日志" />
            <div className="sidebar-section-title">API 管理</div>
            <NavLink to="/keys" icon={<KeyRound size={18} />} label="API Key 管理" />
            <NavLink to="/user-api-keys" icon={<KeyRound size={18} />} label="用户 API Key" />
            <div className="sidebar-section-title">用户与分组</div>
            <NavLink to="/users" icon={<Users size={18} />} label="用户管理" />
            <NavLink to="/groups" icon={<FolderTree size={18} />} label="分组管理" />
            <div className="sidebar-section-title">订阅与计费</div>
            <NavLink to="/billing" icon={<Coins size={18} />} label="计费管理" />
            <NavLink to="/subscription-plans" icon={<Ticket size={18} />} label="订阅计划" />
            <NavLink to="/subscriptions" icon={<Ticket size={18} />} label="用户订阅" />
            <NavLink to="/payment-channels" icon={<CreditCard size={18} />} label="支付通道" />
            <NavLink to="/payment-orders" icon={<CreditCard size={18} />} label="支付订单" />
            <div className="sidebar-section-title">系统</div>
            <NavLink to="/config" icon={<Settings size={18} />} label="渠道与策略" />
          </nav>
          <div className="sidebar-foot">
            <div className="sidebar-status-dot"><span />运行中 · {formatUptime(runtime.uptime_seconds)}</div>
            <small>PID {runtime.pid || '-'} · 端口 {runtime.port || '18765'}</small>
          </div>
        </aside>

        <main className="main">
          <header className="topbar">
            <div className="topbar-main">
              <div className="topbar-title">
                <h1>运行控制台</h1>
                <p><Database size={13} />入口地址 <span className="endpoint">http://127.0.0.1:{runtime.port || '18765'}/v1</span></p>
              </div>
              <div className="topbar-runtime-strip">
                <TopbarMeta label="运行时长" value={formatUptime(runtime.uptime_seconds)} />
                <TopbarMeta label="活跃请求" value={String(activeRequests.length)} />
                <TopbarMeta label="最近记录" value={String(recentRequests.length)} />
                <TopbarMeta label="已启用线路" value={`${state.pools_enabled_count ?? state.config?.pools_enabled_count ?? 0}`} />
              </div>
            </div>
            <div className="hero-actions">
              <Badge tone={stateQuery.isError ? 'bad' : 'ok'}>{stateQuery.isError ? '连接异常' : '运行中'}</Badge>
              <Button onClick={() => stateQuery.refetch()}><RefreshCw size={15} />刷新</Button>
              <a className="btn btn-danger" href="/logout">退出登录</a>
            </div>
          </header>

          <div className="topbar-meta-row">
            <div className="topbar-meta-chip"><Activity size={14} /><span>采样窗口 {recentRequests.length} 条</span></div>
            <div className="topbar-meta-chip"><Wifi size={14} /><span>运行端口 {runtime.port || '18765'}</span></div>
            <div className="topbar-meta-chip"><Server size={14} /><span>PID {runtime.pid || '-'}</span></div>
            <div className="topbar-meta-chip"><Database size={14} /><span>{runtime.config_source || state.config?.config_source || '未标记配置来源'}</span></div>
          </div>

          <Outlet />
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

function TopbarMeta({ label, value }: { label: string; value: string }) {
  return (
    <div className="topbar-runtime-item">
      <span>{label}</span>
      <strong>{value}</strong>
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
