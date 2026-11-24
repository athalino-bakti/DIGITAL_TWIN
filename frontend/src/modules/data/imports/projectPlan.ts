import { ApiError, apiPostForm } from '../../../shared/api/client';

/** Atribut staging_project_plan, urutannya sama dengan PROJECT_PLAN_FIELDS di backend. */
export const PLAN_ATTRIBUTES = [
  'task_code',
  'feature_name',
  'task_name',
  'role_label',
  'pic',
  'complexity_label',
  'priority',
  'estimated_days',
  'planned_start',
  'planned_finish',
  'actual_start',
  'actual_finish',
  'status_label',
  'depends_on',
  'notes',
] as const;
export type PlanAttribute = (typeof PLAN_ATTRIBUTES)[number];

export const REQUIRED_ATTRIBUTES: readonly PlanAttribute[] = ['task_code', 'task_name'];

export const ATTRIBUTE_LABEL: Record<PlanAttribute, string> = {
  task_code: 'Kode task',
  feature_name: 'Fitur',
  task_name: 'Nama task',
  role_label: 'Peran',
  pic: 'PIC',
  complexity_label: 'Kompleksitas',
  priority: 'Prioritas',
  estimated_days: 'Estimasi (hari)',
  planned_start: 'Mulai rencana',
  planned_finish: 'Selesai rencana',
  actual_start: 'Mulai aktual',
  actual_finish: 'Selesai aktual',
  status_label: 'Status',
  depends_on: 'Bergantung pada',
  notes: 'Catatan',
};

export type PreviewRow = { row: number; values: Partial<Record<PlanAttribute, string | null>> };
export type PlanRowError = { row: number; item_id: string | null; field: string | null; message: string };

/** Respons POST /data/imports/project-plan (ProjectPlanImportResult di backend). */
export type ProjectPlanResult = {
  dry_run: boolean;
  applied: boolean;
  project_id: string;
  project_id_source: 'parameter' | 'file_name';
  file_name: string;
  file_type: 'csv' | 'xlsx';
  file_sha256: string;
  sheet_name: string | null;
  sheets: string[];
  delimiter: string | null;
  mapping: Record<string, PlanAttribute>;
  unmapped_headers: string[];
  missing_required: PlanAttribute[];
  missing_optional: PlanAttribute[];
  total_rows: number;
  skipped_blank_rows: number[];
  typed_cells: Record<string, number>;
  preview_rows: PreviewRow[];
  errors: PlanRowError[];
  same_file_job_id: number | null;
  job_id: number | null;
  job_status: string | null;
  rows_read: number | null;
  rows_written: number | null;
};

/** Pilihan pemetaan per judul kolom: atribut, atau null = sengaja tidak dipetakan (hanya di raw). */
export type ColumnOverrides = Record<string, PlanAttribute | null>;

export type UploadOptions = {
  file: File;
  projectId: string;
  sheet: string | null;
  overrides: ColumnOverrides;
  dryRun: boolean;
};

export const MAX_BYTES = 5 * 1024 * 1024;
export const EXTENSIONS = ['.csv', '.xlsx'] as const;

/** Pesan pemeriksaan berkas sebelum diunggah, atau null bila boleh dikirim. */
export function checkFile(file: { name: string; size: number }): string | null {
  const name = file.name.toLowerCase();
  if (!EXTENSIONS.some((extension) => name.endsWith(extension))) return 'Berkas harus .csv atau .xlsx.';
  if (file.size === 0) return 'Berkas kosong.';
  if (file.size > MAX_BYTES) return 'Berkas lebih dari 5 MB. Pecah menjadi beberapa berkas.';
  return null;
}

/** Proyek dari nama berkas, aturan yang sama dengan backend (`PRJ-` + minimal 3 angka). */
export function projectFromFileName(name: string): string | null {
  const stem = name.replace(/\.[^.]+$/, '');
  return stem.match(/PRJ-[0-9]{3,}/)?.[0] ?? null;
}

/** Judul kolom berkas: yang terpetakan lebih dulu, lalu yang hanya disimpan di raw. */
export function fileHeaders(result: Pick<ProjectPlanResult, 'mapping' | 'unmapped_headers'>): string[] {
  return [...Object.keys(result.mapping), ...result.unmapped_headers.filter((name) => !(name in result.mapping))];
}

/** Atribut yang dipakai kolom pratinjau, urut seperti templat Project Plan. */
export function previewAttributes(mapping: Record<string, PlanAttribute>): PlanAttribute[] {
  const used = new Set(Object.values(mapping));
  return PLAN_ATTRIBUTES.filter((attribute) => used.has(attribute));
}

/** Judul kolom lain yang sudah memakai atribut ini, untuk mencegah satu atribut dari dua kolom. */
export function takenBy(mapping: Record<string, PlanAttribute>, attribute: PlanAttribute, header: string): string | null {
  return Object.entries(mapping).find(([name, value]) => value === attribute && name !== header)?.[0] ?? null;
}

/**
 * Pilihan baru pengguna digabung ke pilihan sebelumnya. Atribut yang dipindah ke kolom lain
 * dilepas dari kolom lamanya (null), supaya backend tidak menolak karena atribut ganda.
 */
export function chooseColumn(
  overrides: ColumnOverrides,
  mapping: Record<string, PlanAttribute>,
  header: string,
  attribute: PlanAttribute | null,
): ColumnOverrides {
  const next: ColumnOverrides = { ...overrides, [header]: attribute };
  if (attribute !== null) {
    for (const [name, value] of Object.entries({ ...mapping, ...overrides })) {
      if (name !== header && value === attribute) next[name] = null;
    }
  }
  return next;
}

/** Boleh disimpan ke staging: hasil pratinjau tanpa masalah struktur dan berisi baris. */
export function readyToImport(result: ProjectPlanResult | null): boolean {
  return result !== null && result.errors.length === 0 && result.total_rows > 0;
}

export function buildForm({ file, projectId, sheet, overrides, dryRun }: UploadOptions): FormData {
  const form = new FormData();
  form.append('file', file, file.name);
  form.append('dry_run', String(dryRun));
  if (projectId) form.append('project_id', projectId);
  if (sheet) form.append('sheet', sheet);
  if (Object.keys(overrides).length) form.append('column_map', JSON.stringify(overrides));
  return form;
}

export const uploadProjectPlan = (options: UploadOptions, signal?: AbortSignal) =>
  apiPostForm<ProjectPlanResult>('/data/imports/project-plan', buildForm(options), signal);

/** Pesan untuk pengguna dari error unggah (validasi, 409 job bentrok, 413, atau API mati). */
export function uploadErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 413) return 'Berkas lebih dari 5 MB. Pecah menjadi beberapa berkas.';
    if (error.status === 403) return 'Akun Anda tidak punya izin menjalankan impor.';
    if (error.status === 409) return 'Impor Project Plan lain sedang berjalan. Tunggu sebentar lalu coba lagi.';
    const message = error.issues.map((issue) => issue.message).join(' ') || error.message;
    // 422 setelah dry_run=false: job tercatat gagal di import_job (lihat tab pemantauan impor).
    return error.status === 422 && !error.issues.some((issue) => issue.field)
      ? `${message}. Kegagalan tercatat di riwayat job impor; periksa berkas lalu ulangi pratinjau.`
      : message;
  }
  return 'API belum terhubung. Periksa koneksi lalu coba lagi.';
}
