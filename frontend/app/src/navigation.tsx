import type { LucideIcon } from 'lucide-react';
import {
  BarChart3,
  Bell,
  CreditCard,
  FolderTree,
  Gift,
  Globe,
  KeyRound,
  LayoutDashboard,
  ListChecks,
  Receipt,
  Server,
  Settings,
  Shield,
  Signal,
  Tag,
  Ticket,
  UserRound,
  Users,
} from 'lucide-react';
import type { ReactNode } from 'react';

export type NavMeta = {
  title: string;
  description: string;
};

export type NavItem = {
  key: string;
  path: string;
  label: string;
  icon: LucideIcon;
  meta?: NavMeta;
  children?: NavItem[];
  expandOnly?: boolean;
  hidden?: boolean;
};

export type NavSection = {
  key: string;
  title: string;
  items: NavItem[];
};

function meta(title: string, description: string): NavMeta {
  return { title, description };
}

export const routeMeta = {
  '/admin/dashboard': meta('仪表盘', '按 SUB2 的管理员首页结构展示整体运营概览。'),
  '/admin/ops': meta('Ops', '查看运行态观测、异常趋势和线路运营指标。'),
  '/admin/users': meta('用户管理', '查看用户覆盖、订阅覆盖和调用 Key 覆盖，保留与 SUB2 一致的位置。'),
  '/admin/groups': meta('分组管理', '管理分组、倍率、平台归属和覆盖范围。'),
  '/admin/channels/pricing': meta('渠道管理', '按渠道口径维护连接池、支持模型、映射和协议。'),
  '/admin/channels/monitor': meta('渠道监控', '查看渠道可用性、缓存和状态趋势。'),
  '/admin/subscriptions': meta('订阅管理', '按账户分配、延期、重置或撤销订阅。'),
  '/admin/accounts': meta('账号管理', '查看上游资源账号、线路资源和协议观测，不与平台用户混用。'),
  '/admin/announcements': meta('公告', '统一维护公告位和面向用户的说明入口。'),
  '/admin/proxies': meta('代理', '集中管理代理入口、鉴权键和线路级观测。'),
  '/admin/risk-control': meta('风控', '保留 SUB2 风控层级，承接后续风控规则。'),
  '/admin/redeem': meta('兑换码', '管理兑换码和对应的发放入口。'),
  '/admin/promo-codes': meta('Promo Codes', '管理促销码和营销活动口径。'),
  '/admin/affiliates/invites': meta('邀请记录', '查看邀请返利的邀请链路记录。'),
  '/admin/affiliates/rebates': meta('返利记录', '查看返利结算和返佣流水。'),
  '/admin/affiliates/transfers': meta('提取记录', '查看返利提现或转账记录。'),
  '/admin/orders/dashboard': meta('支付概览', '按 SUB2 订单组首页展示支付统计和概览。'),
  '/admin/orders': meta('订单管理', '查看订单状态、履约结果与人工补单。'),
  '/admin/orders/plans': meta('订阅套餐', '维护订阅计划、价格、有效期和额度。'),
  '/admin/usage': meta('使用记录', '按请求、账户、分组和计划查看使用明细。'),
  '/admin/settings': meta('系统设置', '收拢代理配置与全局策略设置。'),
  '/keys': meta('API 密钥', '管理当前用户名下的 API 密钥。'),
  '/usage': meta('使用记录', '查看当前用户的请求、缓存和消费明细。'),
  '/available-channels': meta('可用渠道', '查看当前用户可使用的计划、分组和通道范围。'),
  '/monitor': meta('渠道状态', '查看当前用户可见线路和渠道状态。'),
  '/subscriptions': meta('我的订阅', '查看当前用户订阅状态、额度和到期时间。'),
  '/purchase': meta('充值/订阅', '为当前用户创建订单并购买可用订阅计划。'),
  '/orders': meta('我的订单', '查看当前用户的订单和履约结果。'),
  '/redeem': meta('兑换', '面向当前用户的兑换入口。'),
  '/affiliate': meta('邀请返利', '面向当前用户的邀请返利入口。'),
  '/profile': meta('个人资料', '面向当前用户的资料与归属信息页。'),
} satisfies Record<string, NavMeta>;

export function getRouteMeta(path: string): NavMeta | undefined {
  return (routeMeta as Record<string, NavMeta>)[path];
}

export function flattenNavItems(sections: NavSection[]): NavItem[] {
  return sections.flatMap((section) => flattenItems(section.items));
}

function flattenItems(items: NavItem[]): NavItem[] {
  return items.flatMap((item) => [item, ...(item.children ? flattenItems(item.children) : [])]);
}

export const adminNavSections: NavSection[] = [
  {
    key: 'admin',
    title: '管理后台',
    items: [
      { key: 'admin-dashboard', path: '/admin/dashboard', label: '仪表盘', icon: LayoutDashboard, meta: routeMeta['/admin/dashboard'] },
      { key: 'admin-ops', path: '/admin/ops', label: 'Ops', icon: BarChart3, meta: routeMeta['/admin/ops'] },
      { key: 'admin-users', path: '/admin/users', label: '用户管理', icon: Users, meta: routeMeta['/admin/users'] },
      { key: 'admin-groups', path: '/admin/groups', label: '分组管理', icon: FolderTree, meta: routeMeta['/admin/groups'] },
      {
        key: 'admin-channels',
        path: '/admin/channels',
        label: '渠道管理',
        icon: Signal,
        expandOnly: true,
        meta: routeMeta['/admin/channels/pricing'],
        children: [
          { key: 'admin-channels-pricing', path: '/admin/channels/pricing', label: '渠道定价', icon: Tag, meta: routeMeta['/admin/channels/pricing'] },
          { key: 'admin-channels-monitor', path: '/admin/channels/monitor', label: '渠道监控', icon: Signal, meta: routeMeta['/admin/channels/monitor'] },
        ],
      },
      { key: 'admin-subscriptions', path: '/admin/subscriptions', label: '订阅管理', icon: Ticket, meta: routeMeta['/admin/subscriptions'] },
      { key: 'admin-accounts', path: '/admin/accounts', label: '账号管理', icon: Globe, meta: routeMeta['/admin/accounts'] },
      { key: 'admin-announcements', path: '/admin/announcements', label: '公告', icon: Bell, meta: routeMeta['/admin/announcements'] },
      { key: 'admin-proxies', path: '/admin/proxies', label: '代理', icon: Server, meta: routeMeta['/admin/proxies'] },
      { key: 'admin-risk', path: '/admin/risk-control', label: '风控', icon: Shield, meta: routeMeta['/admin/risk-control'] },
      { key: 'admin-redeem', path: '/admin/redeem', label: '兑换码', icon: Ticket, meta: routeMeta['/admin/redeem'] },
      { key: 'admin-promo', path: '/admin/promo-codes', label: 'Promo Codes', icon: Gift, meta: routeMeta['/admin/promo-codes'] },
      {
        key: 'admin-affiliates',
        path: '/admin/affiliates',
        label: '邀请返利',
        icon: Users,
        expandOnly: true,
        meta: routeMeta['/admin/affiliates/invites'],
        children: [
          { key: 'admin-affiliates-invites', path: '/admin/affiliates/invites', label: '邀请记录', icon: Users, meta: routeMeta['/admin/affiliates/invites'] },
          { key: 'admin-affiliates-rebates', path: '/admin/affiliates/rebates', label: '返利记录', icon: Receipt, meta: routeMeta['/admin/affiliates/rebates'] },
          { key: 'admin-affiliates-transfers', path: '/admin/affiliates/transfers', label: '提取记录', icon: CreditCard, meta: routeMeta['/admin/affiliates/transfers'] },
        ],
      },
      {
        key: 'admin-orders',
        path: '/admin/orders',
        label: '订单管理',
        icon: Receipt,
        meta: routeMeta['/admin/orders'],
        children: [
          { key: 'admin-orders-dashboard', path: '/admin/orders/dashboard', label: '支付概览', icon: BarChart3, meta: routeMeta['/admin/orders/dashboard'] },
          { key: 'admin-orders-main', path: '/admin/orders', label: '订单管理', icon: Receipt, meta: routeMeta['/admin/orders'] },
          { key: 'admin-orders-plans', path: '/admin/orders/plans', label: '订阅套餐', icon: CreditCard, meta: routeMeta['/admin/orders/plans'] },
        ],
      },
      { key: 'admin-usage', path: '/admin/usage', label: '使用记录', icon: ListChecks, meta: routeMeta['/admin/usage'] },
      { key: 'admin-settings', path: '/admin/settings', label: '系统设置', icon: Settings, meta: routeMeta['/admin/settings'] },
    ],
  },
  {
    key: 'account',
    title: '我的账户',
    items: [
      { key: 'account-keys', path: '/keys', label: 'API 密钥', icon: KeyRound, meta: routeMeta['/keys'] },
      { key: 'account-usage', path: '/usage', label: '使用记录', icon: ListChecks, meta: routeMeta['/usage'] },
      { key: 'account-available-channels', path: '/available-channels', label: '可用渠道', icon: Signal, meta: routeMeta['/available-channels'] },
      { key: 'account-monitor', path: '/monitor', label: '渠道状态', icon: Signal, meta: routeMeta['/monitor'] },
      { key: 'account-subscriptions', path: '/subscriptions', label: '我的订阅', icon: Ticket, meta: routeMeta['/subscriptions'] },
      { key: 'account-purchase', path: '/purchase', label: '充值/订阅', icon: CreditCard, meta: routeMeta['/purchase'] },
      { key: 'account-orders', path: '/orders', label: '我的订单', icon: Receipt, meta: routeMeta['/orders'] },
      { key: 'account-redeem', path: '/redeem', label: '兑换', icon: Gift, meta: routeMeta['/redeem'] },
      { key: 'account-affiliate', path: '/affiliate', label: '邀请返利', icon: Users, meta: routeMeta['/affiliate'] },
      { key: 'account-profile', path: '/profile', label: '个人资料', icon: UserRound, meta: routeMeta['/profile'] },
    ],
  },
];

export function buildPageIntro(path: string): ReactNode {
  const current = getRouteMeta(path);
  if (!current) return null;
  return (
    <div className="sub2-page-head">
      <div className="sub2-page-title">
        <strong>{current.title}</strong>
      </div>
    </div>
  );
}
