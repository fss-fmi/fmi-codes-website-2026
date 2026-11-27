import { createContext, useCallback, useContext, useEffect, type ReactNode } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import type { Role, User } from '@/types/auth';
import api from '@/lib/api';
import { ME_KEY, startNewSession, useMe, type MeData } from '@/hooks/useMe';

interface AuthState {
  user: User | null;
  role: Role | null;
  isLoading: boolean;
  login: (role: Role, user: User) => void;
  logout: () => void;
  refreshUser: () => Promise<void>;
}

// eslint-disable-next-line react-refresh/only-export-components
export const AuthContext = createContext<AuthState>({
  user: null,
  role: null,
  isLoading: true,
  login: () => {},
  logout: () => {},
  refreshUser: () => Promise.resolve(),
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const { data, isPending } = useMe();
  const user = data?.success && data.user ? data.user : null;

  const setMe = useCallback(
    (me: MeData) => {
      startNewSession();
      queryClient.setQueryData<MeData>(ME_KEY, me);
    },
    [queryClient],
  );

  // api.ts broadcasts this on any 401: the session is gone.
  useEffect(() => {
    const handler = () => setMe(null);
    window.addEventListener('auth:unauthorized', handler);
    return () => window.removeEventListener('auth:unauthorized', handler);
  }, [setMe]);

  const login = useCallback(
    (newRole: Role, newUser: User) => setMe({ success: true, user: { ...newUser, role: newRole } }),
    [setMe],
  );

  const refreshUser = useCallback(async () => {
    await queryClient.refetchQueries({ queryKey: ME_KEY });
  }, [queryClient]);

  const logout = useCallback(() => {
    api
      .post('/api/auth/logout')
      .catch(() => {})
      .finally(() => setMe(null));
  }, [setMe]);

  return (
    <AuthContext.Provider
      value={{ user, role: user?.role ?? null, isLoading: isPending, login, logout, refreshUser }}
    >
      {children}
    </AuthContext.Provider>
  );
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth() {
  return useContext(AuthContext);
}
