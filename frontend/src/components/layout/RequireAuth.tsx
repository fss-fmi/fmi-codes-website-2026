import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import LoadingSpinner from '@/components/common/LoadingSpinner';
import type { Role } from '@/types/auth';

interface Props {
  children: React.ReactNode;
  roles?: Role[];
}

export default function RequireAuth({ children, roles }: Props) {
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
