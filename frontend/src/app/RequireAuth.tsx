import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { useAuth } from '../shared/auth/AuthProvider';

/** Route guard (DIG-87): semua halaman di bawahnya wajib login. */
export function RequireAuth() {
  const { status } = useAuth();
  const location = useLocation();

  if (status === 'checking') return <div className="auth-shell"><p className="auth-loading" role="status">Memeriksa sesi…</p></div>;
  if (status === 'anonymous') return <Navigate to="/login" replace state={{ from: `${location.pathname}${location.search}` }} />;
  return <Outlet />;
}
