export const navigation = [
  { path: '/data', label: 'Data', symbol: '▤', description: 'Kelola dataset dan kualitas data proyek.' },
  { path: '/digital-twin', label: 'Digital Twin', symbol: '◈', description: 'Kondisi baseline model: timeline proyek, beban resource, dan dependency antar task.' },
  { path: '/simulasi', label: 'Simulasi', symbol: '▥', description: 'Eksplorasi skenario dan perubahan pada rencana proyek.' },
  { path: '/evaluasi', label: 'Evaluasi', symbol: '◎', description: 'Tinjau hasil simulasi dan perbandingan dengan baseline.' },
] as const;
