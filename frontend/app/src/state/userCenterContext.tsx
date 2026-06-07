import { createContext, useContext, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  fetchAdminPaymentChannels,
  fetchAdminPaymentOrders,
  fetchAdminSubscriptionPlans,
  fetchAdminSubscriptions,
  fetchAdminUsers,
} from '../api';
import type {
  AdminPaymentChannel,
  AdminPaymentOrder,
  AdminSubscriptionPlan,
  AdminUser,
  AdminUserSubscription,
} from '../types';

export type UserCenterContextValue = {
  users: AdminUser[];
  selectedUserId: string;
  selectedUser?: AdminUser;
  subscriptions: AdminUserSubscription[];
  orders: AdminPaymentOrder[];
  plans: AdminSubscriptionPlan[];
  channels: AdminPaymentChannel[];
  visiblePlans: AdminSubscriptionPlan[];
  visibleChannels: AdminPaymentChannel[];
  setSelectedUserId: (userId: string) => void;
  reload: () => Promise<void>;
  loading: boolean;
};

const UserCenterContext = createContext<UserCenterContextValue | null>(null);

export function UserCenterProvider({ children }: { children: React.ReactNode }) {
  const usersQuery = useQuery({ queryKey: ['admin-users'], queryFn: fetchAdminUsers, refetchInterval: 10000 });
  const plansQuery = useQuery({ queryKey: ['admin-subscription-plans'], queryFn: fetchAdminSubscriptionPlans, refetchInterval: 10000 });
  const channelsQuery = useQuery({ queryKey: ['admin-payment-channels'], queryFn: fetchAdminPaymentChannels, refetchInterval: 10000 });
  const ordersQuery = useQuery({ queryKey: ['admin-payment-orders'], queryFn: fetchAdminPaymentOrders, refetchInterval: 10000 });
  const subscriptionsQuery = useQuery({ queryKey: ['admin-subscriptions'], queryFn: fetchAdminSubscriptions, refetchInterval: 10000 });

  const users = usersQuery.data?.items || [];
  const plans = plansQuery.data?.items || [];
  const channels = (channelsQuery.data?.items || []).filter((item) => item.enabled !== false);
  const orders = ordersQuery.data?.items || [];
  const subscriptions = subscriptionsQuery.data?.items || [];
  const [selectedUserId, setSelectedUserId] = useState('');

  const selectedUser = useMemo(() => users.find((item) => item.id === selectedUserId), [selectedUserId, users]);

  const visiblePlans = useMemo(() => {
    if (!selectedUser) return plans.filter((item) => item.enabled !== false);
    const allowedGroups = selectedUser.allowed_group_ids || [];
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

  const value = useMemo<UserCenterContextValue>(() => ({
    users,
    selectedUserId,
    selectedUser,
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
        plansQuery.refetch(),
        channelsQuery.refetch(),
        ordersQuery.refetch(),
        subscriptionsQuery.refetch(),
      ]);
    },
    loading: usersQuery.isLoading || plansQuery.isLoading || channelsQuery.isLoading || ordersQuery.isLoading || subscriptionsQuery.isLoading,
  }), [
    users,
    selectedUserId,
    selectedUser,
    subscriptions,
    orders,
    plans,
    channels,
    visiblePlans,
    visibleChannels,
    usersQuery,
    plansQuery,
    channelsQuery,
    ordersQuery,
    subscriptionsQuery,
  ]);

  return <UserCenterContext.Provider value={value}>{children}</UserCenterContext.Provider>;
}

export function useUserCenter() {
  const value = useContext(UserCenterContext);
  if (!value) throw new Error('User center context is not available');
  return value;
}
