import { createContext, useContext, useEffect, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  fetchAdminPaymentChannels,
  fetchAdminPaymentOrders,
  fetchAdminAccounts,
  fetchAdminAccountSubscriptions,
  fetchAdminSubscriptionPlans,
} from '../api';
import type {
  AdminAccount,
  AdminAccountSubscription,
  AdminPaymentChannel,
  AdminPaymentOrder,
  AdminSubscriptionPlan,
} from '../types';

export type AccountCenterContextValue = {
  accounts: AdminAccount[];
  selectedAccountId: string;
  selectedAccount?: AdminAccount;
  subscriptions: AdminAccountSubscription[];
  orders: AdminPaymentOrder[];
  plans: AdminSubscriptionPlan[];
  channels: AdminPaymentChannel[];
  visiblePlans: AdminSubscriptionPlan[];
  visibleChannels: AdminPaymentChannel[];
  setSelectedAccountId: (accountId: string) => void;
  reload: () => Promise<void>;
  loading: boolean;
};

const AccountCenterContext = createContext<AccountCenterContextValue | null>(null);

export function AccountCenterProvider({ children }: { children: React.ReactNode }) {
  const accountsQuery = useQuery({ queryKey: ['admin-accounts'], queryFn: fetchAdminAccounts, refetchInterval: 10000 });
  const plansQuery = useQuery({ queryKey: ['admin-subscription-plans'], queryFn: fetchAdminSubscriptionPlans, refetchInterval: 10000 });
  const channelsQuery = useQuery({ queryKey: ['admin-payment-channels'], queryFn: fetchAdminPaymentChannels, refetchInterval: 10000 });
  const ordersQuery = useQuery({ queryKey: ['admin-payment-orders'], queryFn: fetchAdminPaymentOrders, refetchInterval: 10000 });
  const subscriptionsQuery = useQuery({ queryKey: ['admin-subscriptions'], queryFn: fetchAdminAccountSubscriptions, refetchInterval: 10000 });

  const accounts = accountsQuery.data?.items || [];
  const plans = plansQuery.data?.items || [];
  const channels = (channelsQuery.data?.items || []).filter((item) => item.enabled !== false);
  const orders = ordersQuery.data?.items || [];
  const subscriptions = subscriptionsQuery.data?.items || [];
  const [selectedAccountId, setSelectedAccountId] = useState('');

  useEffect(() => {
    if (!selectedAccountId && accounts.length) {
      setSelectedAccountId(accounts[0].id);
    }
  }, [accounts, selectedAccountId]);

  const selectedAccount = useMemo(() => accounts.find((item) => item.id === selectedAccountId), [selectedAccountId, accounts]);

  const visiblePlans = useMemo(() => {
    if (!selectedAccount) return plans.filter((item) => item.enabled !== false);
    const allowedGroups = selectedAccount.allowed_group_ids || [];
    return plans.filter((plan) => {
      if (plan.enabled === false) return false;
      if (!allowedGroups.length) return true;
      if (!plan.group_id) return true;
      return allowedGroups.includes(plan.group_id);
    });
  }, [plans, selectedAccount]);

  const visibleChannels = useMemo(() => {
    const groupIds = new Set(visiblePlans.map((item) => item.group_id).filter(Boolean));
    return channels.filter((channel) => {
      const allowedGroups = channel.allowed_group_ids || [];
      if (!allowedGroups.length) return true;
      for (const groupId of groupIds) {
        if (allowedGroups.includes(String(groupId))) return true;
      }
      return groupIds.size === 0;
    });
  }, [channels, visiblePlans]);

  const value = useMemo<AccountCenterContextValue>(() => ({
    accounts,
    selectedAccountId,
    selectedAccount,
    subscriptions,
    orders,
    plans,
    channels,
    visiblePlans,
    visibleChannels,
    setSelectedAccountId,
    reload: async () => {
      await Promise.all([
        accountsQuery.refetch(),
        plansQuery.refetch(),
        channelsQuery.refetch(),
        ordersQuery.refetch(),
        subscriptionsQuery.refetch(),
      ]);
    },
    loading: accountsQuery.isLoading || plansQuery.isLoading || channelsQuery.isLoading || ordersQuery.isLoading || subscriptionsQuery.isLoading,
  }), [
    accounts,
    selectedAccountId,
    selectedAccount,
    subscriptions,
    orders,
    plans,
    channels,
    visiblePlans,
    visibleChannels,
    accountsQuery,
    plansQuery,
    channelsQuery,
    ordersQuery,
    subscriptionsQuery,
  ]);

  return <AccountCenterContext.Provider value={value}>{children}</AccountCenterContext.Provider>;
}

export function useAccountCenter() {
  const value = useContext(AccountCenterContext);
  if (!value) throw new Error('Account center context is not available');
  return value;
}
