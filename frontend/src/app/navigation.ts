import type { IconName } from '../shared/components/Icon';
import { PERM, type Permission } from '../shared/auth/permissions';

export type NavItem = { path: string; label: string; icon: IconName; description: string; permission: Permission };

// Menu disaring per izin (FR-12). Simulasi dan Evaluasi membaca baseline, jadi memakai izin
// yang sama dengan halaman Digital Twin sampai ada izin khusus untuk keduanya.
export const navigation: readonly NavItem[] = [
  { path: '/data', label: 'Data', icon: 'list-checks', description: 'Kelola dataset dan kualitas data proyek.', permission: PERM.masterDataRead },
  { path: '/digital-twin', label: 'Digital Twin', icon: 'layout-dashboard', description: 'Kondisi baseline model: timeline proyek, beban resource, dan dependency antar task.', permission: PERM.baselineRead },
  { path: '/simulasi', label: 'Simulasi', icon: 'sliders-horizontal', description: 'Eksplorasi skenario dan perubahan pada rencana proyek.', permission: PERM.baselineRead },
  { path: '/evaluasi', label: 'Evaluasi', icon: 'chart-column', description: 'Tinjau hasil simulasi dan perbandingan dengan baseline.', permission: PERM.baselineRead },
];
