import { describe, expect, it } from 'vitest';
import type { HeatmapCategory, HeatmapCell, HeatmapRow, HeatmapWeek } from './api';
import { cellAt, cellDetails, describeCell, formatRli, hasOverload, holidayNote, isOverload, rangeLabel, shortDate, summaryText, visibleRows, weekLabel } from './rules';

const CATEGORIES: HeatmapCategory[] = [
  { code: 'rendah', label: 'Rendah', min: null, max: 0.5, overload: false },
  { code: 'sedang', label: 'Sedang', min: 0.5, max: 0.8, overload: false },
  { code: 'penuh', label: 'Penuh', min: 0.8, max: 1.0, overload: false },
  { code: 'overload', label: 'Overload', min: 1.0, max: 1.2, overload: true },
  { code: 'overload_berat', label: 'Overload berat', min: 1.2, max: null, overload: true },
  { code: 'tidak_tersedia', label: 'Tidak tersedia', min: null, max: null, overload: false },
];

const cell = (overrides: Partial<HeatmapCell> = {}): HeatmapCell => ({
  week_start: '2026-11-23',
  rli: 0.75,
  category: 'sedang',
  project_load: 3,
  non_project_load: 0.5,
  capacity: 4.67,
  available_days: 5,
  onboarding_factor: 1,
  tasks: 2,
  workload_items: 1,
  ...overrides,
});

const row = (name: string, cells: HeatmapCell[]): HeatmapRow => ({
  resource_id: `RES-${name}`,
  resource_name: name,
  primary_role_id: 'ROLE-FE',
  capacity_reference: 5,
  is_onboarding: false,
  cells,
});

describe('formatRli', () => {
  it('memakai koma desimal dengan dua angka', () => {
    expect(formatRli(1.2)).toBe('1,20');
    expect(formatRli(0.5)).toBe('0,50');
    expect(formatRli(0.7549)).toBe('0,75');
  });

  it('null menjadi strip', () => {
    expect(formatRli(null)).toBe('–');
  });
});

describe('tanggal minggu', () => {
  it('shortDate memakai nama bulan Indonesia', () => {
    expect(shortDate('2026-11-23')).toBe('23 Nov');
    expect(shortDate('2026-08-03')).toBe('3 Agu');
    expect(shortDate('2026-05-04')).toBe('4 Mei');
  });

  it('weekLabel memakai awal minggu', () => {
    const week: HeatmapWeek = { week_start: '2026-12-21', week_end: '2026-12-27', working_days: 4, holidays: ['2026-12-25'] };
    expect(weekLabel(week)).toBe('21 Des');
  });

  it('holidayNote hanya muncul bila ada libur', () => {
    const base = { week_start: '2026-12-21', week_end: '2026-12-27' };
    expect(holidayNote({ ...base, working_days: 5, holidays: [] })).toBeNull();
    expect(holidayNote({ ...base, working_days: 4, holidays: ['2026-12-25'] })).toBe('1 hari libur, 4 hari kerja');
  });
});

describe('rangeLabel', () => {
  it('menulis batas tiap kategori untuk legenda', () => {
    const labels = CATEGORIES.map(rangeLabel);
    expect(labels).toEqual(['< 0,50', '0,50 – 0,80', '0,80 – 1,00', '1,00 – 1,20', '> 1,20', 'Tanpa kapasitas']);
  });
});

describe('overload', () => {
  it('isOverload mengikuti flag kategori dari backend', () => {
    expect(isOverload(cell({ category: 'overload' }), CATEGORIES)).toBe(true);
    expect(isOverload(cell({ category: 'overload_berat' }), CATEGORIES)).toBe(true);
    expect(isOverload(cell({ category: 'penuh' }), CATEGORIES)).toBe(false);
    expect(isOverload(cell({ category: 'tidak_tersedia', rli: null }), CATEGORIES)).toBe(false);
  });

  it('kode kategori yang tidak dikenal tidak dianggap overload', () => {
    expect(isOverload(cell({ category: 'baru' }), CATEGORIES)).toBe(false);
  });

  it('hasOverload dan visibleRows menyaring baris', () => {
    const aman = row('Sari', [cell(), cell({ week_start: '2026-11-30', category: 'penuh', rli: 0.95 })]);
    const berat = row('Budi', [cell(), cell({ week_start: '2026-11-30', category: 'overload', rli: 1.1 })]);
    expect(hasOverload(aman, CATEGORIES)).toBe(false);
    expect(hasOverload(berat, CATEGORIES)).toBe(true);
    expect(visibleRows([aman, berat], CATEGORIES, true)).toEqual([berat]);
    expect(visibleRows([aman, berat], CATEGORIES, false)).toEqual([aman, berat]);
  });
});

describe('cellAt', () => {
  it('mengambil sel menurut awal minggu', () => {
    const r = row('Sari', [cell({ week_start: '2026-11-23' }), cell({ week_start: '2026-11-30', rli: 1.3, category: 'overload_berat' })]);
    expect(cellAt(r, '2026-11-30')?.rli).toBe(1.3);
    expect(cellAt(r, '2027-01-04')).toBeUndefined();
  });
});

describe('summaryText', () => {
  it('menyebut jumlah anggota overload dan minggunya', () => {
    expect(summaryText(2, 5, '2026-11-23')).toBe('2 dari 5 anggota overload pada minggu 23 Nov');
  });

  it('tanpa anggota menampilkan pesan kosong', () => {
    expect(summaryText(0, 0, '2026-11-23')).toBe('Belum ada anggota yang ditampilkan');
  });
});

describe('deskripsi sel', () => {
  const r = row('Sari', []);

  it('menyebut RLI dan kategori', () => {
    const c = cell({ rli: 1.2, category: 'overload' });
    expect(describeCell(r, c, CATEGORIES[3])).toBe('Sari, minggu 23 Nov: RLI 1,20, Overload.');
  });

  it('sel tanpa kapasitas tidak menampilkan RLI', () => {
    const c = cell({ rli: null, category: 'tidak_tersedia', capacity: 0 });
    expect(describeCell(r, c, CATEGORIES[5])).toBe('Sari, minggu 23 Nov: Tidak tersedia. Kapasitas 0.');
  });

  it('kategori tak dikenal memakai kodenya', () => {
    expect(describeCell(r, cell({ category: 'baru' }), undefined)).toContain('baru');
  });

  it('cellDetails memuat tujuh komponen beban', () => {
    const details = cellDetails(cell());
    expect(details).toHaveLength(7);
    expect(details[0]).toEqual({ label: 'Beban proyek', value: '3,00' });
    expect(details[2]).toEqual({ label: 'Kapasitas', value: '4,67' });
    expect(details[3]).toEqual({ label: 'Hari tersedia', value: '5' });
  });
});
