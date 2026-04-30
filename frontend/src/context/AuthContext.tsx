import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import type { Role, User } from '@/types/auth';
import api from '@/lib/api';

interface AuthState {
  user: User | null;
  role: Role | null;
  isLoading: boolean;
  login: (role: Role, userId: number, user: User) => void;
  logout: () => void;
}

// eslint-disable-next-line react-refresh/only-export-components
export const AuthContext = createContext<AuthState>({
  user: null,
  role: null,
  isLoading: true,
  login: () => {},
  logout: () => {},
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [role, setRole] = useState<Role | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // Hydrate from cookie on app load
  // Use raw fetch to avoid the api.ts 401→auth:unauthorized event for this expected case
  useEffect(() => {
    fetch('/api/auth/me', { credentials: 'include' })
      .then((res) => (res.ok ? (res.json() as Promise<{ success: boolean; user: User }>) : null))
      .then((data) => {
        if (data?.success && data.user) {
          setUser(data.user);
          setRole(data.user.role);
        }
      })
      .catch(() => {
        /* no cookie / expired — stay logged out */
      })
      .finally(() => setIsLoading(false));
  }, []);

  // Listen for 401 events from api.ts
  useEffect(() => {
    const handler = () => {
      setUser(null);
      setRole(null);
    };
    window.addEventListener('auth:unauthorized', handler);
    return () => window.removeEventListener('auth:unauthorized', handler);
  }, []);

  function login(newRole: Role, _userId: number, newUser: User) {
    setUser(newUser);
    setRole(newRole);
  }

  function logout() {
    api
      .post('/api/auth/logout')
      .catch(() => {})
      .finally(() => {
        setUser(null);
        setRole(null);
      });
  }

  return (
    <AuthContext.Provider value={{ user, role, isLoading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth() {
  return useContext(AuthContext);
}
