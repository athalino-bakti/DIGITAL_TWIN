import { PERM, type Permission } from '../../shared/auth/permissions';

// Izin baca tiap tab mengikuti izin endpoint GET-nya di backend (DIG-226).
export const dataViews: readonly { key: string; label: string; permission: Permission }[] = [
  { key: 'proyek', label: 'Proyek', permission: PERM.masterDataRead },
  { key: 'anggota', label: 'Anggota', permission: PERM.masterDataRead },
  { key: 'peran', label: 'Peran', permission: PERM.masterDataRead },
  { key: 'beban', label: 'Beban non-proyek', permission: PERM.workloadReadAll },
  { key: 'kompleksitas', label: 'Kompleksitas', permission: PERM.masterDataRead },
  { key: 'ketersediaan', label: 'Ketersediaan', permission: PERM.workloadReadAll },
  { key: 'libur', label: 'Hari libur', permission: PERM.masterDataRead },
  { key: 'impor', label: 'Impor dataset', permission: PERM.importRun },
];
