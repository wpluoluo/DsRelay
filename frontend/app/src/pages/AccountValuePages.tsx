import { useQuery } from '@tanstack/react-query';
import { fetchAdminContent } from '../api';
import { Panel, PanelHead } from '../components';
import { buildPageIntro } from '../navigation';

function AccountContentPage({
  path,
  queryPath,
}: {
  path: '/redeem' | '/affiliate';
  queryPath: '/admin/redeem' | '/admin/affiliates/invites';
}) {
  const query = useQuery({ queryKey: ['account-content', queryPath], queryFn: () => fetchAdminContent(queryPath), refetchInterval: 30000 });
  const items = query.data?.items || [];
  return (
    <section className="grid-page">
      {buildPageIntro(path)}
      <Panel>
        <PanelHead title={query.data?.label || '内容列表'} />
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>标题</th>
                <th>状态</th>
                <th>摘要</th>
              </tr>
            </thead>
            <tbody>
              {items.length ? items.map((item) => (
                <tr key={item.id}>
                  <td>{item.title}</td>
                  <td>{item.status || '-'}</td>
                  <td>{item.summary || item.note || '-'}</td>
                </tr>
              )) : (
                <tr><td colSpan={3}>暂无可展示内容。</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </Panel>
    </section>
  );
}

export const AccountRedeemPage = () => <AccountContentPage path="/redeem" queryPath="/admin/redeem" />;
export const AccountAffiliatePage = () => <AccountContentPage path="/affiliate" queryPath="/admin/affiliates/invites" />;
