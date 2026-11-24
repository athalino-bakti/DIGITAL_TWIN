import { PERM, type Permission } from '../../shared/auth/permissions';

// Izin baca tiap tab mengikuti izin endpoint GET-nya di backend (DIG-226).
export const dataViews: readonly { key: string; label: string; permission: Permission }[] = [
  { key: 'proyek', label: 'Proyek', permission: PERM.masterDataRead },
  { key: 'anggota', label: 'Anggota', permission: PERM.masterDataRead },
  { key: 'peran', label: 'Peran', permission: PERM.masterDataRead },
  { key: 'task', label: 'Task', permission: PERM.masterDataRead },
  { key: 'beban', label: 'Beban non-proyek', permission: PERM.workloadReadAll },
  { key: 'perubahan', label: 'Riwayat perubahan', permission: PERM.workloadReadAll },
  { key: 'kompleksitas', label: 'Kompleksitas', permission: PERM.masterDataRead },
  { key: 'ketersediaan', label: 'Ketersediaan', permission: PERM.workloadReadAll },
  { key: 'libur', label: 'Hari libur', permission: PERM.masterDataRead },
  { key: 'impor', label: 'Impor dataset', permission: PERM.importRun },
  { key: 'kualitas', label: 'Kualitas data', permission: PERM.dataQualityRead },
  { key: 'trello', label: 'Pemetaan Trello', permission: PERM.importRun },
  { key: 'task-saya', label: 'Task saya', permission: PERM.workloadReadOwn },
];
