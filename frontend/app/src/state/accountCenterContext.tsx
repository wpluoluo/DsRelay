import { createContext, useContext, useEffect, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  fetchAdminApiKeys,
  fetchAdminPaymentChannels,
  fetchAdminPaymentOrders,
  fetchAdminSubscriptionPlans,
  fetchAdminUsers,
  fetchAdminAccountSubscriptions,
} from '../api';
import type {
  AdminApiKey,
  AdminAccountSubscription,
  AdminPaymentChannel,
  AdminPaymentOrder,
  AdminSubscriptionPlan,
  AdminUser,
} from '../types';

export type AccountCenterContextValue = {
  users: AdminUser[];
  selectedUserId: string;
  selectedUser?: AdminUser;
  apiKeys: AdminApiKey[];
  subscriptions: AdminAccountSubscription[];
  orders: AdminPaymentOrder[];
  plans: AdminSubscriptionPlan[];
  channels: AdminPaymentChannel[];
  visiblePlans: AdminSubscriptionPlan[];
  visibleChannels: AdminPaymentChannel[];
  setSelectedUserId: (userId: string) => void;
  reload: () => Promise<void>;
  loading: boolean;
};

const AccountCenterContext = createContext<AccountCenterContextValue | null>(null);

export function AccountCenterProvider({ children }: { children: React.ReactNode }) {
  const usersQuery = useQuery({ queryKey: ['admin-users'], queryFn: fetchAdminUsers, refetchInterval: 10000 });
  const keysQuery = useQuery({ queryKey: ['admin-api-keys'], queryFn: fetchAdminApiKeys, refetchInterval: 10000 });
  const plansQuery = useQuery({ queryKey: ['admin-subscription-plans'], queryFn: fetchAdminSubscriptionPlans, refetchInterval: 10000 });
  const channelsQuery = useQuery({ queryKey: ['admin-payment-channels'], queryFn: fetchAdminPaymentChannels, refetchInterval: 10000 });
  const ordersQuery = useQuery({ queryKey: ['admin-payment-orders'], queryFn: fetchAdminPaymentOrders, refetchInterval: 10000 });
  const subscriptionsQuery = useQuery({ queryKey: ['admin-subscriptions'], queryFn: fetchAdminAccountSubscriptions, refetchInterval: 10000 });

  const users = usersQuery.data?.items || [];
  const apiKeys = keysQuery.data?.items || [];
  const plans = plansQuery.data?.items || [];
  const channels = (channelsQuery.data?.items || []).filter((item) => item.enabled !== false);
  const orders = ordersQuery.data?.items || [];
  const subscriptions = subscriptionsQuery.data?.items || [];
  const [selectedUserId, setSelectedUserId] = useState('');

  useEffect(() => {
    if (!selectedUserId && users.length) {
      setSelectedUserId(users[0].id);
    }
  }, [selectedUserId, users]);

  const selectedUser = useMemo(() => users.find((item) => item.id === selectedUserId), [selectedUserId, users]);

  const visiblePlans = useMemo(() => {
    const allowedGroups = selectedUser?.allowed_group_ids || [];
    return plans.filter((plan) => {
      if (plan.enabled === false) return false;
      if (!allowedGroups.length) return true;
      if (!plan.group_id) return true;
      return allowedGroups.includes(plan.group_id);
    });
  }, [plans, selectedUser]);

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
    users,
    selectedUserId,
    selectedUser,
    apiKeys,
    subscriptions,
    orders,
    plans,
    channels,
    visiblePlans,
    visibleChannels,
    setSelectedUserId,
    reload: async () => {
      await Promise.all([
        usersQuery.refetch(),
        keysQuery.refetch(),
        plansQuery.refetch(),
        channelsQuery.refetch(),
        ordersQuery.refetch(),
        subscriptionsQuery.refetch(),
      ]);
    },
    loading:
      usersQuery.isLoading ||
      keysQuery.isLoading ||
      plansQuery.isLoading ||
      channelsQuery.isLoading ||
      ordersQuery.isLoading ||
      subscriptionsQuery.isLoading,
  }), [
    users,
    selectedUserId,
    selectedUser,
    apiKeys,
    subscriptions,
    orders,
    plans,
    channels,
    visiblePlans,
    visibleChannels,
    usersQuery,
    keysQuery,
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
