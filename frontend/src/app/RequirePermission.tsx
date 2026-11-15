import { Navigate, Outlet } from 'react-router-dom';
import { useAuth } from '../shared/auth/AuthProvider';
import { allowed, can, type Permission } from '../shared/auth/permissions';
import { navigation } from './navigation';

/** Pesan untuk halaman yang tidak boleh dibuka pengguna ini. */
export function NoAccess() {
  const { user } = useAuth();
  const noRole = (user?.roles?.length ?? 0) === 0;
  return (
    <section className="empty-state" aria-labelledby="no-access-title">
      <h2 id="no-access-title">{noRole ? 'Akun belum punya peran' : 'Tidak punya akses'}</h2>
      <p>
        {noRole
          ? 'Akun kamu belum diberi peran aplikasi, jadi belum ada halaman yang bisa dibuka. Hubungi Admin IT untuk mengatur peran.'
          : 'Peran kamu tidak mencakup halaman ini. Pilih halaman lain dari menu, atau hubungi Admin IT bila butuh akses.'}
      </p>
    </section>
  );
}

/** Guard per bagian (DIG-92): halaman di bawahnya hanya untuk pemegang izin itu. */
export function RequirePermission({ permission }: { permission: Permission }) {
  const { user } = useAuth();
  return can(user, permission) ? <Outlet /> : <NoAccess />;
}

/** Halaman awal: menu pertama yang boleh dibuka pengguna ini. */
export function HomeRedirect() {
  const { user } = useAuth();
  const first = allowed(navigation, user)[0];
  return first ? <Navigate to={first.path} replace /> : <NoAccess />;
}
