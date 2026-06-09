import { createContext, useContext, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  fetchAccountApiKeys,
  fetchAccountChannels,
  fetchAccountGroups,
  fetchAccountMe,
  fetchAccountOrders,
  fetchAccountPaymentChannels,
  fetchAccountSubscriptionPlans,
  fetchAccountSubscriptions,
} from '../api';
import type {
  AdminApiKey,
  AdminChannel,
  AdminGroup,
  AdminPaymentChannel,
  AdminPaymentOrder,
  AdminSubscriptionPlan,
  AdminAccount,
  AdminAccountSubscription,
} from '../types';

export type AccountCenterContextValue = {
  account?: AdminAccount;
  groups: AdminGroup[];
  apiKeys: AdminApiKey[];
  subscriptions: AdminAccountSubscription[];
  orders: AdminPaymentOrder[];
  plans: AdminSubscriptionPlan[];
  channels: AdminPaymentChannel[];
  availableChannels: AdminChannel[];
  visiblePlans: AdminSubscriptionPlan[];
  visibleChannels: AdminPaymentChannel[];
  visibleAvailableChannels: AdminChannel[];
  reload: () => Promise<void>;
  loading: boolean;
};

const AccountCenterContext = createContext<AccountCenterContextValue | null>(null);

export function AccountCenterProvider({ children }: { children: React.ReactNode }) {
  const accountQuery = useQuery({ queryKey: ['account-me'], queryFn: fetchAccountMe, refetchInterval: 10000, retry: false });
  const groupsQuery = useQuery({ queryKey: ['account-groups'], queryFn: fetchAccountGroups, refetchInterval: 30000, retry: false });
  const availableChannelsQuery = useQuery({ queryKey: ['account-channels'], queryFn: fetchAccountChannels, refetchInterval: 30000, retry: false });
  const keysQuery = useQuery({ queryKey: ['account-api-keys'], queryFn: fetchAccountApiKeys, refetchInterval: 10000, retry: false });
  const plansQuery = useQuery({ queryKey: ['account-subscription-plans'], queryFn: fetchAccountSubscriptionPlans, refetchInterval: 30000, retry: false });
  const channelsQuery = useQuery({ queryKey: ['account-payment-channels'], queryFn: fetchAccountPaymentChannels, refetchInterval: 30000, retry: false });
  const ordersQuery = useQuery({ queryKey: ['account-payment-orders'], queryFn: fetchAccountOrders, refetchInterval: 10000, retry: false });
  const subscriptionsQuery = useQuery({ queryKey: ['account-subscriptions'], queryFn: fetchAccountSubscriptions, refetchInterval: 10000, retry: false });

  const account = accountQuery.data?.item;
  const groups = groupsQuery.data?.items || [];
  const availableChannels = availableChannelsQuery.data?.items || [];
  const apiKeys = keysQuery.data?.items || [];
  const plans = plansQuery.data?.items || [];
  const channels = (channelsQuery.data?.items || []).filter((item) => item.enabled !== false);
  const orders = ordersQuery.data?.items || [];
  const subscriptions = subscriptionsQuery.data?.items || [];

  const visiblePlans = useMemo(() => plans.filter((plan) => plan.enabled !== false), [plans]);
  const visibleChannels = useMemo(() => channels.filter((channel) => channel.enabled !== false), [channels]);
  const visibleAvailableChannels = useMemo(() => availableChannels.filter((channel) => channel.enabled !== false), [availableChannels]);

  const value = useMemo<AccountCenterContextValue>(() => ({
    account,
    groups,
    apiKeys,
    subscriptions,
    orders,
    plans,
    channels,
    availableChannels,
    visiblePlans,
    visibleChannels,
    visibleAvailableChannels,
    reload: async () => {
      await Promise.all([
        accountQuery.refetch(),
        groupsQuery.refetch(),
        availableChannelsQuery.refetch(),
        keysQuery.refetch(),
        plansQuery.refetch(),
        channelsQuery.refetch(),
        ordersQuery.refetch(),
        subscriptionsQuery.refetch(),
      ]);
    },
    loading:
      accountQuery.isLoading ||
      groupsQuery.isLoading ||
      availableChannelsQuery.isLoading ||
      keysQuery.isLoading ||
      plansQuery.isLoading ||
      channelsQuery.isLoading ||
      ordersQuery.isLoading ||
      subscriptionsQuery.isLoading,
  }), [
    account,
    groups,
    availableChannels,
    apiKeys,
    subscriptions,
    orders,
    plans,
    channels,
    visiblePlans,
    visibleChannels,
    visibleAvailableChannels,
    accountQuery,
    groupsQuery,
    availableChannelsQuery,
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
