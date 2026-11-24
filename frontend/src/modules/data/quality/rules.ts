/** Aturan murni tab Kualitas data (DIG-147): label, format angka, dan susunan query. */

export const SOURCES = [
  { key: 'project_plan', label: 'Project Plan' },
  { key: 'trello', label: 'Trello' },
  { key: 'teamgit', label: 'TeamGit' },
] as const;

export const CHARACTERISTICS = [
  { key: 'completeness', label: 'Kelengkapan' },
  { key: 'consistency', label: 'Konsistensi' },
  { key: 'currentness', label: 'Kemutakhiran' },
  { key: 'traceability', label: 'Keterlacakan' },
] as const;

export const LEVELS = [
  { key: 'tolak', label: 'Ditolak' },
  { key: 'peringatan', label: 'Peringatan' },
] as const;

export const PAGE_SIZE = 50;

export type RejectedFilters = {
  level: string;
  characteristic: string;
  ruleId: string;
};

export const NO_FILTER: RejectedFilters = { level: '', characteristic: '', ruleId: '' };

const labelOf = (list: readonly { key: string; label: string }[], key: string) =>
  list.find((item) => item.key === key)?.label ?? key;

export const sourceLabel = (key: string) => labelOf(SOURCES, key);
export const characteristicLabel = (key: string) => labelOf(CHARACTERISTICS, key);
export const levelLabel = (key: string) => labelOf(LEVELS, key);

/** Tingkat lolos 0..1 sebagai persen berkoma Indonesia (0,9825 menjadi "98,3%"). null berarti belum ada yang diperiksa. */
export function formatRate(rate: number | null): string {
  if (rate === null) return '-';
  return `${String(Number((rate * 100).toFixed(1))).replace('.', ',')}%`;
}

export const pageCount = (total: number, pageSize: number) => Math.max(1, Math.ceil(total / pageSize));

/** "1-50 dari 120"; kosong bila tidak ada hasil. */
export function rangeText(page: number, pageSize: number, total: number): string {
  if (total === 0) return '0 baris';
  const start = (page - 1) * pageSize + 1;
  return `${start}-${Math.min(page * pageSize, total)} dari ${total}`;
}

export const hasFilter = (filters: RejectedFilters) => Boolean(filters.level || filters.characteristic || filters.ruleId);

/** Penanda baris di sumber: nomor baris bila ada (berkas), kalau tidak kunci barisnya (mis. id kartu). */
export function rowLabel(item: { row_number: number | null; row_key: string | null }): string {
  if (item.row_number !== null) return `Baris ${item.row_number}`;
  return item.row_key ?? '-';
}

export const summaryPath = (source: string) => `/data/quality/summary?source=${encodeURIComponent(source)}`;

/** Path daftar baris ditolak; filter kosong tidak dikirim. */
export function rejectedRowsPath(jobId: number, filters: RejectedFilters, page: number, pageSize: number): string {
  const params = new URLSearchParams({ job_id: String(jobId), page: String(page), page_size: String(pageSize) });
  if (filters.level) params.set('level', filters.level);
  if (filters.characteristic) params.set('characteristic', filters.characteristic);
  if (filters.ruleId) params.set('rule_id', filters.ruleId);
  return `/data/quality/rejected-rows?${params.toString()}`;
}
