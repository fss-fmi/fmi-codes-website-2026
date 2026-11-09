import { createContext, useContext, type ReactNode } from 'react';
import { useQuery } from '@tanstack/react-query';
import api from '@/lib/api';

interface Flags {
  REGISTRATION_OPEN: boolean;
  MENTORS_STAY_TUNED: boolean;
  RANKINGS_LIVE: boolean;
  REQUIRE_EMAIL_VERIFICATION: boolean;
}

interface ConfigState extends Flags {
  isLoading: boolean;
}

const CLOSED: Flags = {
  REGISTRATION_OPEN: false,
  MENTORS_STAY_TUNED: false,
  RANKINGS_LIVE: false,
  REQUIRE_EMAIL_VERIFICATION: false,
};

const ConfigContext = createContext<ConfigState>({ ...CLOSED, isLoading: true });

export function ConfigProvider({ children }: { children: ReactNode }) {
  // The admin switches flags live from Mission Control, so open pages poll for them.
  const { data, isPending } = useQuery({
    queryKey: ['config'],
    queryFn: () => api.get<Flags>('/api/config'),
    refetchInterval: 30_000,
    refetchOnWindowFocus: 'always',
  });

  // A failed refetch keeps the last flags; a failed first load leaves everything closed.
  const flags = data ?? CLOSED;
  const value: ConfigState = {
    REGISTRATION_OPEN: flags.REGISTRATION_OPEN,
    MENTORS_STAY_TUNED: flags.MENTORS_STAY_TUNED,
    RANKINGS_LIVE: flags.RANKINGS_LIVE,
    REQUIRE_EMAIL_VERIFICATION: flags.REQUIRE_EMAIL_VERIFICATION,
    isLoading: isPending,
  };

  return <ConfigContext.Provider value={value}>{children}</ConfigContext.Provider>;
}

// eslint-disable-next-line react-refresh/only-export-components
export function useConfig() {
  return useContext(ConfigContext);
}
