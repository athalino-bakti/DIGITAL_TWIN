import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { useAuth } from '../shared/auth/AuthProvider';

/** Route guard (DIG-87): semua halaman di bawahnya wajib login. */
export function RequireAuth() {
  const { status, retry, signOut } = useAuth();
  const location = useLocation();

  if (status === 'checking') return <div className="auth-shell"><p className="auth-loading" role="status">Memeriksa sesi…</p></div>;
  if (status === 'offline') {
    // Token masih tersimpan, jadi pengguna tidak dipaksa login ulang hanya karena API mati.
    return (
      <div className="auth-shell">
        <section className="auth-card" aria-labelledby="offline-title">
          <h1 id="offline-title">API belum terhubung</h1>
          <p className="auth-subtitle" role="status">Sesi kamu masih tersimpan. Pastikan backend berjalan, lalu coba lagi.</p>
          <div className="auth-actions">
            <button type="button" className="button" onClick={retry}>Coba lagi</button>
            <button type="button" className="button button-ghost" onClick={signOut}>Masuk dengan akun lain</button>
          </div>
        </section>
      </div>
    );
  }
  if (status === 'anonymous') return <Navigate to="/login" replace state={{ from: `${location.pathname}${location.search}` }} />;
  return <Outlet />;
}
