/**
 * Utilitas tanggal untuk kalender. Tanggal disimpan sebagai string YYYY-MM-DD dan
 * dihitung dalam UTC supaya tidak bergeser satu hari karena zona waktu browser.
 * Aturan hari kerja sama dengan backend/app/modules/data/workdays.py.
 */

const DAY_MS = 86_400_000;

export const WEEKDAY_SHORT = ['Sen', 'Sel', 'Rab', 'Kam', 'Jum', 'Sab', 'Min'];

const toMs = (iso: string) => Date.UTC(Number(iso.slice(0, 4)), Number(iso.slice(5, 7)) - 1, Number(iso.slice(8, 10)));
const fromMs = (ms: number) => new Date(ms).toISOString().slice(0, 10);

export const addDays = (iso: string, days: number) => fromMs(toMs(iso) + days * DAY_MS);

/** Senin 0 sampai Minggu 6, sama seperti date.weekday() di Python. */
export const weekday = (iso: string) => (new Date(toMs(iso)).getUTCDay() + 6) % 7;
export const isWeekend = (iso: string) => weekday(iso) >= 5;

export function todayIso(): string {
  const now = new Date();
  return fromMs(Date.UTC(now.getFullYear(), now.getMonth(), now.getDate()));
}

export const isValidIso = (value: string) => /^\d{4}-\d{2}-\d{2}$/.test(value) && fromMs(toMs(value)) === value;

/** Jumlah hari kerja dari start sampai end (inklusif), tanpa akhir pekan dan hari libur. */
export function countWorkingDays(start: string, end: string, holidays: ReadonlySet<string>): number {
  let count = 0;
  for (let day = start; day <= end; day = addDays(day, 1)) if (!isWeekend(day) && !holidays.has(day)) count += 1;
  return count;
}

export const calendarDays = (start: string, end: string) => Math.round((toMs(end) - toMs(start)) / DAY_MS) + 1;

export type Month = { year: number; month: number };

export const monthOf = (iso: string): Month => ({ year: Number(iso.slice(0, 4)), month: Number(iso.slice(5, 7)) - 1 });
export const shiftMonth = ({ year, month }: Month, delta: number): Month => {
  const index = year * 12 + month + delta;
  return { year: Math.floor(index / 12), month: ((index % 12) + 12) % 12 };
};

export function monthBounds({ year, month }: Month): { first: string; last: string } {
  return { first: fromMs(Date.UTC(year, month, 1)), last: fromMs(Date.UTC(year, month + 1, 0)) };
}

/** Tanggal yang tampil di kalender: Senin sebelum tanggal 1 sampai Minggu setelah akhir bulan. */
export function monthGrid(month: Month): string[] {
  const { first, last } = monthBounds(month);
  const start = addDays(first, -weekday(first));
  const end = addDays(last, 6 - weekday(last));
  const days: string[] = [];
  for (let day = start; day <= end; day = addDays(day, 1)) days.push(day);
  return days;
}

const longDate = new Intl.DateTimeFormat('id-ID', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC' });
const shortDate = new Intl.DateTimeFormat('id-ID', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' });
const monthTitle = new Intl.DateTimeFormat('id-ID', { month: 'long', year: 'numeric', timeZone: 'UTC' });

export const formatLong = (iso: string) => longDate.format(toMs(iso));
export const formatShort = (iso: string) => shortDate.format(toMs(iso));
export const formatMonth = (month: Month) => monthTitle.format(Date.UTC(month.year, month.month, 1));

export function formatRange(start: string, end: string): string {
  return start === end ? formatShort(start) : `${formatShort(start)} s.d. ${formatShort(end)}`;
}
