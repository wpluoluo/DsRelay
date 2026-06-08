import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link } from '@tanstack/react-router';
import { ArrowRight, RefreshCw } from 'lucide-react';
import { fetchAdminUsers } from '../api';
import { Badge, Panel, PanelHead } from '../components';
import { ActionButton, FilterToolbar, SearchField, TablePageLayout, ToolbarButtonRow } from '../components/admin';
import { buildPageIntro } from '../navigation';
import { formatNumber } from '../utils';

export function AdminUsersPage() {
  const usersQuery = useQuery({ queryKey: ['admin-users'], queryFn: fetchAdminUsers, refetchInterval: 10000 });
  const [search, setSearch] = useState('');
  const [coverageFilter, setCoverageFilter] = useState<'all' | 'subscribed' | 'uncovered'>('all');

  const rows = useMemo(
    () =>
      (usersQuery.data?.items || []).map((item) => ({
        ...item,
        key_count: item.key_count || 0,
        active_key_count: item.active_key_count || 0,
        subscription_count: item.subscription_count || 0,
        active_subscription_count: item.active_subscription_count || 0,
        request_count: item.request_count || 0,
        coverage_state: (item.active_subscription_count || 0) > 0 ? 'subscribed' : 'uncovered',
      })),
    [usersQuery.data?.items],
  );

  const filteredRows = useMemo(() => {
    const keyword = search.trim().toLowerCase();
    return rows.filter((item) => {
      if (coverageFilter !== 'all' && item.coverage_state !== coverageFilter) return false;
      if (!keyword) return true;
      const haystack = [item.name, item.id, item.group_name, item.group_id, item.preview]
        .map((value) => String(value || '').toLowerCase())
        .join(' ');
      return haystack.includes(keyword);
    });
  }, [coverageFilter, rows, search]);

  const activeUsers = rows.filter((item) => item.enabled !== false).length;
  const coveredUsers = rows.filter((item) => item.active_subscription_count > 0).length;
  const uncoveredUsers = rows.length - coveredUsers;
  const keyCoveredUsers = rows.filter((item) => item.active_key_count > 0).length;

  return (
    <section className="grid-page">
      {buildPageIntro('/admin/users')}
      <div className="sub2-inline-summary">
        <div className="sub2-inline-summary-item"><span>用户总数</span><strong>{formatNumber(rows.length)}</strong><small>业务对象总览</small></div>
        <div className="sub2-inline-summary-item"><span>启用用户</span><strong>{formatNumber(activeUsers)}</strong><small>停用 {formatNumber(rows.length - activeUsers)}</small></div>
        <div className="sub2-inline-summary-item"><span>订阅覆盖</span><strong>{formatNumber(coveredUsers)}</strong><small>未覆盖 {formatNumber(uncoveredUsers)}</small></div>
        <div className="sub2-inline-summary-item"><span>Key 覆盖</span><strong>{formatNumber(keyCoveredUsers)}</strong><small>可直接调用用户</small></div>
      </div>
      <TablePageLayout
        filters={
          <FilterToolbar
            right={
              <ToolbarButtonRow>
                <ActionButton onClick={() => { usersQuery.refetch(); }}>
                  <RefreshCw size={15} />
                  刷新
                </ActionButton>
              </ToolbarButtonRow>
            }
          >
            <SearchField value={search} placeholder="搜索用户 / 分组 / 归属" onChange={setSearch} />
            <div className="tabs">
              {[
                { value: 'all', label: '全部用户' },
                { value: 'subscribed', label: '已订阅' },
                { value: 'uncovered', label: '未覆盖' },
              ].map((item) => (
                <button
                  key={item.value}
                  type="button"
                  className={coverageFilter === item.value ? 'active' : ''}
                  onClick={() => setCoverageFilter(item.value as typeof coverageFilter)}
                >
                  {item.label}
                </button>
              ))}
            </div>
          </FilterToolbar>
        }
        table={
          <Panel>
            <PanelHead
              title="用户覆盖列表"
              action={<Link to="/admin/accounts" className="panel-link">进入账号管理 <ArrowRight size={14} /></Link>}
            />
            <div className="table-wrap table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>用户</th>
                    <th>当前分组</th>
                    <th>Key 覆盖</th>
                    <th>订阅覆盖</th>
                    <th>最近归因</th>
                    <th>状态</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredRows.length ? filteredRows.map((item) => (
                    <tr key={item.id}>
                      <td>
                        <div className="sub2-cell-stack sub2-cell-stack-tight">
                          <strong>{item.name}</strong>
                          <small>{item.preview || item.id}</small>
                        </div>
                      </td>
                      <td>
                        <div className="sub2-cell-stack sub2-cell-stack-tight">
                          <strong>{item.group_name || '未分组'}</strong>
                          <small>{item.group_id || '-'}</small>
                        </div>
                      </td>
                      <td>
                        <div className="sub2-cell-stack sub2-cell-stack-tight">
                          <strong>{formatNumber(item.active_key_count)} / {formatNumber(item.key_count)}</strong>
                          <small>{item.active_key_count > 0 ? '存在可用 Key' : '未配置可用 Key'}</small>
                        </div>
                      </td>
                      <td>
                        <div className="sub2-cell-stack sub2-cell-stack-tight">
                          <strong>{formatNumber(item.active_subscription_count)} / {formatNumber(item.subscription_count)}</strong>
                          <small>{item.active_subscription_count > 0 ? (item.active_plan_name || '订阅已覆盖') : '无有效订阅'}</small>
                        </div>
                      </td>
                      <td>
                        <div className="sub2-cell-stack sub2-cell-stack-tight">
                          <strong>{item.last_seen_at || '-'}</strong>
                          <small>{formatNumber(item.request_count || 0)} 次请求</small>
                        </div>
                      </td>
                      <td>
                        <div className="sub2-cell-stack sub2-cell-stack-tight">
                          <Badge tone={item.enabled === false ? 'warn' : 'ok'}>{item.enabled === false ? '停用' : '启用'}</Badge>
                          <small>{item.active_subscription_count > 0 ? '订阅已覆盖' : '等待订阅'}</small>
                        </div>
                      </td>
                    </tr>
                  )) : (
                    <tr><td colSpan={6}>暂无符合条件的用户数据。</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </Panel>
        }
      />
    </section>
  );
}
