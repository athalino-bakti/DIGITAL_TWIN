import type { IconName } from '../shared/components/Icon';

type NavItem = { path: string; label: string; icon: IconName; description: string };

export const navigation: readonly NavItem[] = [
  { path: '/data', label: 'Data', icon: 'list-checks', description: 'Kelola dataset dan kualitas data proyek.' },
  { path: '/digital-twin', label: 'Digital Twin', icon: 'layout-dashboard', description: 'Kondisi baseline model: timeline proyek, beban resource, dan dependency antar task.' },
  { path: '/simulasi', label: 'Simulasi', icon: 'sliders-horizontal', description: 'Eksplorasi skenario dan perubahan pada rencana proyek.' },
  { path: '/evaluasi', label: 'Evaluasi', icon: 'chart-column', description: 'Tinjau hasil simulasi dan perbandingan dengan baseline.' },
];
