import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { useMe } from '@/hooks/useMe';
import LoadingSpinner from '@/components/common/LoadingSpinner';
import type { Role } from '@/types/auth';

interface Props {
  children: React.ReactNode;
  roles?: Role[];
}

export default function RequireAuth({ children, roles }: Props) {
  // Mounting a protected page refetches a stale user, so a team change someone else
  // made shows up on navigation. useAuth() alone adds no observer.
  useMe();
  const { user, role, isLoading } = useAuth();
  const location = useLocation();

  if (isLoading) return <LoadingSpinner fullPage />;
  if (!user)
    return (
      <Navigate
        to="/login"
        state={{ from: location }}
        replace
      />
    );
  if (roles && role && !roles.includes(role))
    return (
      <Navigate
        to="/"
        replace
      />
    );

  return <>{children}</>;
}
