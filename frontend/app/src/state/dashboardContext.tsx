import { createContext, useContext } from 'react';
import type { UseQueryResult } from '@tanstack/react-query';
import type { ConfigTab } from '../features/config/model';
import type { DashboardState, Pool, RuntimeConfig } from '../types';

export type DashboardContextValue = {
  state: DashboardState;
  stateQuery: UseQueryResult<DashboardState, Error>;
  draft: RuntimeConfig;
  pools: Pool[];
  configTab: ConfigTab;
  status: string;
  saving: boolean;
  setConfigTab: (tab: ConfigTab) => void;
  patchDraft: (patch: Partial<RuntimeConfig>) => void;
  saveConfig: () => void;
};

const DashboardContext = createContext<DashboardContextValue | null>(null);

export const DashboardProvider = DashboardContext.Provider;

export function useDashboard() {
  const value = useContext(DashboardContext);
  if (!value) throw new Error('Dashboard context is not available');
  return value;
}
