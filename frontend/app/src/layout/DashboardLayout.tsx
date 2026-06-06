import React, { useEffect, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Link, Outlet } from '@tanstack/react-router';
import { Activity, KeyRound, ListChecks, RefreshCw, Server, Settings } from 'lucide-react';
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
            <div><strong>DsRelay</strong><span>本地代理控制台</span></div>
          </div>
          <nav>
            <NavLink to="/" icon={<Activity size={16} />} label="总览" />
            <NavLink to="/requests" icon={<ListChecks size={16} />} label="请求观测" />
            <NavLink to="/logs" icon={<Server size={16} />} label="运行日志" />
            <NavLink to="/keys" icon={<KeyRound size={16} />} label="入口 Key" />
            <NavLink to="/config" icon={<Settings size={16} />} label="路由与策略" />
          </nav>
          <div className="sidebar-foot">
            <span>运行中 · {formatUptime(runtime.uptime_seconds)}</span>
            <small>PID {runtime.pid || '-'} · 端口 {runtime.port || '18765'}</small>
          </div>
        </aside>

        <main className="main">
          <header className="hero">
            <div>
              <p>本地代理</p>
              <h1>运行控制台</h1>
              <span className="endpoint">http://127.0.0.1:{runtime.port || '18765'}/v1</span>
            </div>
            <div className="hero-actions">
              <Badge tone={stateQuery.isError ? 'bad' : 'ok'}>{stateQuery.isError ? '连接异常' : '运行中'}</Badge>
              <Button onClick={() => stateQuery.refetch()}><RefreshCw size={15} />刷新</Button>
              <a className="btn btn-danger" href="/logout">退出登录</a>
            </div>
          </header>

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

function NavLink({ to, icon, label }: { to: string; icon: React.ReactNode; label: string }) {
  return <Link to={to} activeOptions={{ exact: to === '/' }} activeProps={{ className: 'active' }}>{icon}<span>{label}</span></Link>;
}
