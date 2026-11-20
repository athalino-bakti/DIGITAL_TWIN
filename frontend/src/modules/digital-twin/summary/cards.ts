import type { BaselineSummary } from './api';

export type CardKey = 'active' | 'late' | 'overload' | 'multi';

export type Card = { key: CardKey; label: string; value: number | null; note: string; clickable: boolean };

/** Isi empat kartu ringkasan baseline dari respons API (DIG-176). */
export function buildCards(summary: BaselineSummary | null): Card[] {
  if (!summary) {
    return (['active', 'late', 'overload', 'multi'] as const).map((key, index) => ({
      key,
      label: LABELS[index],
      value: null,
      note: 'Memuat…',
      clickable: false,
    }));
  }
  const active = summary.active_projects.count;
  const late = summary.late_projects.count;
  const worst = summary.late_projects.items[0];
  const multi = summary.multi_role_resources.items;
  const busy = multi.filter((item) => item.other_active_roles.length > 0).length;
  return [
    { key: 'active', label: LABELS[0], value: active, note: active ? 'Planning, development, dan testing' : 'Belum ada proyek aktif', clickable: active > 0 },
    { key: 'late', label: LABELS[1], value: late, note: worst ? `Paling telat ${worst.project_name}, ${worst.days_late} hari` : 'Semua proyek aktif sesuai target', clickable: late > 0 },
    { key: 'overload', label: LABELS[2], value: null, note: 'Menunggu perhitungan RLI', clickable: false },
    { key: 'multi', label: LABELS[3], value: multi.length, note: multi.length ? `${busy} sedang menjalankan peran lain` : 'Belum ada anggota multi-role', clickable: multi.length > 0 },
  ];
}

const LABELS = ['Proyek aktif', 'Proyek lewat target', 'Resource overload', 'Resource multi-role'] as const;
