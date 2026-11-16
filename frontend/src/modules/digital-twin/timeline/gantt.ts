/**
 * Hitungan posisi batang Gantt (DIG-178). Murni, tanpa React, supaya bisa dites.
 * Semua tanggal berbentuk ISO (YYYY-MM-DD) dan dihitung dalam UTC agar tidak bergeser
 * karena zona waktu.
 */
const DAY_MS = 86_400_000;

export const dayNumber = (iso: string) => Date.UTC(Number(iso.slice(0, 4)), Number(iso.slice(5, 7)) - 1, Number(iso.slice(8, 10))) / DAY_MS;
export const isoOf = (day: number) => new Date(day * DAY_MS).toISOString().slice(0, 10);

export type Scale = { start: string; end: string; days: number; dayWidth: number; width: number };

/** Skala dari awal bulan tanggal pertama sampai akhir bulan tanggal terakhir. */
export function makeScale(dates: readonly string[], dayWidth: number): Scale | null {
  if (dates.length === 0) return null;
  const sorted = [...dates].sort();
  const first = sorted[0];
  const last = sorted[sorted.length - 1];
  const start = `${first.slice(0, 7)}-01`;
  const end = isoOf(Date.UTC(Number(last.slice(0, 4)), Number(last.slice(5, 7)), 0) / DAY_MS);
  const days = dayNumber(end) - dayNumber(start) + 1;
  return { start, end, days, dayWidth, width: days * dayWidth };
}

/** Posisi kiri sebuah tanggal (tepi kiri kotak harinya). */
export const offsetOf = (scale: Scale, iso: string) => (dayNumber(iso) - dayNumber(scale.start)) * scale.dayWidth;

export type Bar = { left: number; width: number };

/** Batang dari `start` sampai `end`, kedua ujung ikut (task 1 hari selebar satu hari). */
export function barOf(scale: Scale, start: string, end: string): Bar {
  const from = start <= end ? start : end;
  const to = start <= end ? end : start;
  return { left: offsetOf(scale, from), width: (dayNumber(to) - dayNumber(from) + 1) * scale.dayWidth };
}

export type ActualBar = Bar & { open: boolean };

/**
 * Batang aktual. Task yang sudah mulai tetapi belum selesai digambar sampai tanggal acuan
 * dan ditandai `open`. Task yang belum mulai tidak punya batang aktual.
 */
export function actualBarOf(scale: Scale, start: string | null, finish: string | null, asOf: string): ActualBar | null {
  if (!start) return null;
  if (finish) return { ...barOf(scale, start, finish), open: false };
  return { ...barOf(scale, start, asOf > start ? asOf : start), open: true };
}

export type MonthSegment = { key: string; left: number; width: number; month: number; year: number };

/** Kolom bulan untuk kepala skala. */
export function monthSegments(scale: Scale): MonthSegment[] {
  const segments: MonthSegment[] = [];
  let year = Number(scale.start.slice(0, 4));
  let month = Number(scale.start.slice(5, 7)) - 1;
  const endDay = dayNumber(scale.end);
  for (;;) {
    const first = Date.UTC(year, month, 1) / DAY_MS;
    if (first > endDay) break;
    const days = Date.UTC(year, month + 1, 0) / DAY_MS - first + 1;
    segments.push({ key: `${year}-${month}`, left: (first - dayNumber(scale.start)) * scale.dayWidth, width: days * scale.dayWidth, month, year });
    month += 1;
    if (month === 12) { month = 0; year += 1; }
  }
  return segments;
}

/** True bila tanggal berada di dalam skala. */
export const inScale = (scale: Scale, iso: string) => iso >= scale.start && iso <= scale.end;
