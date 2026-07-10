import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import api from '@/lib/api';

interface ConfigState {
  REGISTRATION_OPEN: boolean;
  MENTORS_STAY_TUNED: boolean;
  RANKINGS_LIVE: boolean;
  isLoading: boolean;
}

const ConfigContext = createContext<ConfigState>({
  REGISTRATION_OPEN: false,
  MENTORS_STAY_TUNED: false,
  RANKINGS_LIVE: false,
  isLoading: true,
});

export function ConfigProvider({ children }: { children: ReactNode }) {
  const [config, setConfig] = useState<ConfigState>({
    REGISTRATION_OPEN: false,
    MENTORS_STAY_TUNED: false,
    RANKINGS_LIVE: false,
    isLoading: true,
  });

  useEffect(() => {
    api
      .get<{ REGISTRATION_OPEN: boolean; MENTORS_STAY_TUNED: boolean; RANKINGS_LIVE: boolean }>(
        '/api/config',
      )
      .then((data) => {
        setConfig({
          REGISTRATION_OPEN: data.REGISTRATION_OPEN,
          MENTORS_STAY_TUNED: data.MENTORS_STAY_TUNED,
          RANKINGS_LIVE: data.RANKINGS_LIVE,
          isLoading: false,
        });
      })
      .catch(() => {
        setConfig((prev) => ({ ...prev, isLoading: false }));
      });
  }, []);

  return <ConfigContext.Provider value={config}>{children}</ConfigContext.Provider>;
}

// eslint-disable-next-line react-refresh/only-export-components
export function useConfig() {
  return useContext(ConfigContext);
}
