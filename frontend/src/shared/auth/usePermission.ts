import { useAuth } from './AuthProvider';
import { can, type Permission } from './permissions';

/** True bila pengguna yang sedang login memegang izin itu. */
export function useCan(permission: Permission): boolean {
  return can(useAuth().user, permission);
}
