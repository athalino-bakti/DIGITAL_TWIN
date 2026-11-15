/**
 * Izin aplikasi di sisi frontend (DIG-92, FR-12).
 *
 * Kodenya sama dengan `Perm` di backend/app/modules/auth/permissions.py dan dikirim backend
 * lewat `permissions` pada /auth/me. Frontend hanya menyembunyikan menu dan tombol; penolakan
 * yang sebenarnya tetap dilakukan backend (403).
 */
export const PERM = {
  masterDataRead: 'master_data:read',
  masterDataWrite: 'master_data:write',
  importRun: 'import:run',
  dataQualityRead: 'data_quality:read',
  changeEventWrite: 'change_event:write',
  changeEventWriteOwn: 'change_event:write_own',
  availabilityWrite: 'availability:write',
  baselineRead: 'baseline:read',
  workloadReadAll: 'workload:read_all',
  workloadReadOwn: 'workload:read_own',
  eventLogExport: 'event_log:export',
  userManage: 'user:manage',
} as const;

export type Permission = (typeof PERM)[keyof typeof PERM];

type WithPermissions = { permissions?: readonly string[] } | null | undefined;

/** True bila pengguna memegang izin itu. Pengguna tanpa daftar izin dianggap tidak berizin. */
export function can(user: WithPermissions, permission: Permission): boolean {
  return user?.permissions?.includes(permission) ?? false;
}

/** Item yang izinnya dipegang pengguna, urutan tetap. */
export function allowed<T extends { permission: Permission }>(items: readonly T[], user: WithPermissions): T[] {
  return items.filter((item) => can(user, item.permission));
}
