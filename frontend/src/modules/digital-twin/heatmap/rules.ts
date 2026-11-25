import type { HeatmapCategory, HeatmapCell, HeatmapRow, HeatmapWeek } from './api';

/** Pilihan jumlah minggu. Backend menerima 1 s.d. 26, bawaannya 12. */
export const WEEK_OPTIONS = [8, 12, 26] as const;
export const DEFAULT_WEEKS = 12;

/** Kategori sel tanpa kapasitas (libur penuh, cuti, atau belum bergabung). */
export const UNAVAILABLE = 'tidak_tersedia';

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'Mei', 'Jun', 'Jul', 'Agu', 'Sep', 'Okt', 'Nov', 'Des'];

/** Angka dengan koma desimal: 1.2 menjadi "1,20". Null menjadi tanda strip. */
export function formatRli(rli: number | null): string {
  return rli === null ? '–' : rli.toFixed(2).replace('.', ',');
}

function number2(value: number): string {
  return value.toFixed(2).replace('.', ',');
}

/** "2026-11-16" menjadi "16 Nov". Tanpa Intl supaya sama di semua lingkungan. */
export function shortDate(iso: string): string {
  const [, month, day] = iso.split('-').map(Number);
  return `${day} ${MONTHS[month - 1]}`;
}

export function weekLabel(week: HeatmapWeek): string {
  return shortDate(week.week_start);
}

/** Batas kategori untuk legenda. Batas 1,20 masih Overload; Overload berat mulai di atasnya. */
export function rangeLabel(category: HeatmapCategory): string {
  const { min, max } = category;
  if (min === null && max === null) return 'Tanpa kapasitas';
  if (min === null) return `< ${number2(max as number)}`;
  if (max === null) return `> ${number2(min)}`;
  return `${number2(min)} – ${number2(max)}`;
}

export function categoryOf(categories: HeatmapCategory[], code: string): HeatmapCategory | undefined {
  return categories.find((category) => category.code === code);
}

export function isOverload(cell: HeatmapCell, categories: HeatmapCategory[]): boolean {
  return categoryOf(categories, cell.category)?.overload ?? false;
}

/** Baris yang punya sedikitnya satu minggu overload. */
export function hasOverload(row: HeatmapRow, categories: HeatmapCategory[]): boolean {
  return row.cells.some((cell) => isOverload(cell, categories));
}

export function visibleRows(rows: HeatmapRow[], categories: HeatmapCategory[], overloadOnly: boolean): HeatmapRow[] {
  return overloadOnly ? rows.filter((row) => hasOverload(row, categories)) : rows;
}

/** Sel pada minggu tertentu, atau undefined bila baris tidak memuatnya. */
export function cellAt(row: HeatmapRow, weekStart: string): HeatmapCell | undefined {
  return row.cells.find((cell) => cell.week_start === weekStart);
}

/** Ringkasan kartu: anggota overload pada minggu berjalan. */
export function summaryText(overloaded: number, resources: number, weekStart: string): string {
  if (resources === 0) return 'Belum ada anggota yang ditampilkan';
  return `${overloaded} dari ${resources} anggota overload pada minggu ${shortDate(weekStart)}`;
}

/** Deskripsi satu sel untuk pembaca layar dan tooltip. */
export function describeCell(row: HeatmapRow, cell: HeatmapCell, category: HeatmapCategory | undefined): string {
  const label = category?.label ?? cell.category;
  if (cell.rli === null) return `${row.resource_name}, minggu ${shortDate(cell.week_start)}: ${label}. Kapasitas 0.`;
  return `${row.resource_name}, minggu ${shortDate(cell.week_start)}: RLI ${formatRli(cell.rli)}, ${label}.`;
}

/** Rincian beban satu sel, satu baris per komponen. */
export function cellDetails(cell: HeatmapCell): { label: string; value: string }[] {
  return [
    { label: 'Beban proyek', value: number2(cell.project_load) },
    { label: 'Beban non-proyek', value: number2(cell.non_project_load) },
    { label: 'Kapasitas', value: number2(cell.capacity) },
    { label: 'Hari tersedia', value: String(cell.available_days) },
    { label: 'Faktor onboarding', value: number2(cell.onboarding_factor) },
    { label: 'Task aktif', value: String(cell.tasks) },
    { label: 'Item non-proyek', value: String(cell.workload_items) },
  ];
}

/** Minggu yang memuat hari libur nasional, untuk penanda di kepala kolom. */
export function holidayNote(week: HeatmapWeek): string | null {
  if (week.holidays.length === 0) return null;
  return `${week.holidays.length} hari libur, ${week.working_days} hari kerja`;
}
