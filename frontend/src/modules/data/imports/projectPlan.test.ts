// @vitest-environment jsdom
import { describe, expect, it } from 'vitest';
import { ApiError } from '../../../shared/api/client';
import {
  buildForm,
  checkFile,
  chooseColumn,
  fileHeaders,
  previewAttributes,
  projectFromFileName,
  readyToImport,
  takenBy,
  uploadErrorMessage,
  type ProjectPlanResult,
} from './projectPlan';

const result = (overrides: Partial<ProjectPlanResult> = {}): ProjectPlanResult => ({
  dry_run: true,
  applied: false,
  project_id: 'PRJ-002',
  project_id_source: 'file_name',
  file_name: 'project_plan_PRJ-002.csv',
  file_type: 'csv',
  file_sha256: 'x',
  sheet_name: null,
  sheets: [],
  delimiter: ',',
  mapping: { 'Kode Task': 'task_code', Task: 'task_name', PIC: 'pic' },
  unmapped_headers: ['Kolom Bebas'],
  missing_required: [],
  missing_optional: [],
  total_rows: 3,
  skipped_blank_rows: [],
  typed_cells: {},
  preview_rows: [],
  errors: [],
  same_file_job_id: null,
  job_id: null,
  job_status: null,
  rows_read: null,
  rows_written: null,
  ...overrides,
});

describe('pemeriksaan berkas', () => {
  it('menerima .csv dan .xlsx sampai 5 MB', () => {
    expect(checkFile({ name: 'plan.CSV', size: 10 })).toBeNull();
    expect(checkFile({ name: 'plan.xlsx', size: 5 * 1024 * 1024 })).toBeNull();
  });

  it('menolak ekstensi lain, berkas kosong, dan berkas terlalu besar', () => {
    expect(checkFile({ name: 'plan.xls', size: 10 })).toMatch(/\.csv atau \.xlsx/);
    expect(checkFile({ name: 'plan.csv', size: 0 })).toMatch(/kosong/);
    expect(checkFile({ name: 'plan.csv', size: 5 * 1024 * 1024 + 1 })).toMatch(/5 MB/);
  });

  it('mengambil PRJ-xxx dari nama berkas seperti backend', () => {
    expect(projectFromFileName('project_plan_PRJ-002.xlsx')).toBe('PRJ-002');
    expect(projectFromFileName('PRJ-12.csv')).toBeNull();
    expect(projectFromFileName('rencana.csv')).toBeNull();
  });
});

describe('pemetaan kolom', () => {
  it('judul kolom terpetakan tampil lebih dulu, lalu kolom raw', () => {
    expect(fileHeaders(result())).toEqual(['Kode Task', 'Task', 'PIC', 'Kolom Bebas']);
  });

  it('kolom pratinjau mengikuti urutan templat, bukan urutan berkas', () => {
    expect(previewAttributes({ PIC: 'pic', Task: 'task_name', Kode: 'task_code' })).toEqual(['task_code', 'task_name', 'pic']);
  });

  it('mengenali kolom lain yang sudah memakai atribut', () => {
    const mapping = result().mapping;
    expect(takenBy(mapping, 'pic', 'Kolom Bebas')).toBe('PIC');
    expect(takenBy(mapping, 'pic', 'PIC')).toBeNull();
  });

  it('memindah atribut melepasnya dari kolom lama supaya tidak ganda', () => {
    const next = chooseColumn({}, result().mapping, 'Kolom Bebas', 'pic');
    expect(next).toEqual({ 'Kolom Bebas': 'pic', PIC: null });
  });

  it('memilih "tidak dipetakan" hanya mengubah kolom itu', () => {
    expect(chooseColumn({ 'Kolom Bebas': 'notes' }, result().mapping, 'PIC', null)).toEqual({ 'Kolom Bebas': 'notes', PIC: null });
  });

  it('pilihan sebelumnya ikut diperiksa saat memindah atribut', () => {
    const next = chooseColumn({ 'Kolom Bebas': 'notes' }, result().mapping, 'PIC', 'notes');
    expect(next).toEqual({ 'Kolom Bebas': null, PIC: 'notes' });
  });
});

describe('siap impor', () => {
  it('butuh pratinjau tanpa error dan minimal satu baris', () => {
    expect(readyToImport(null)).toBe(false);
    expect(readyToImport(result())).toBe(true);
    expect(readyToImport(result({ total_rows: 0 }))).toBe(false);
    expect(readyToImport(result({ errors: [{ row: 1, item_id: null, field: null, message: 'Kolom wajib tidak ditemukan: task_code' }] }))).toBe(false);
  });
});

describe('form unggah', () => {
  const file = new File(['task_code,task_name\nT-1,Login\n'], 'project_plan_PRJ-002.csv', { type: 'text/csv' });

  it('mengirim berkas, dry_run, proyek, sheet, dan pemetaan', () => {
    const form = buildForm({ file, projectId: 'PRJ-002', sheet: 'Plan', overrides: { PIC: null }, dryRun: false });
    expect((form.get('file') as File).name).toBe('project_plan_PRJ-002.csv');
    expect(form.get('dry_run')).toBe('false');
    expect(form.get('project_id')).toBe('PRJ-002');
    expect(form.get('sheet')).toBe('Plan');
    expect(JSON.parse(form.get('column_map') as string)).toEqual({ PIC: null });
  });

  it('parameter kosong tidak dikirim supaya backend memakai bawaannya', () => {
    const form = buildForm({ file, projectId: '', sheet: null, overrides: {}, dryRun: true });
    expect(form.get('dry_run')).toBe('true');
    expect(form.has('project_id')).toBe(false);
    expect(form.has('sheet')).toBe(false);
    expect(form.has('column_map')).toBe(false);
  });
});

describe('pesan error unggah', () => {
  it('memetakan status penting ke pesan yang jelas', () => {
    expect(uploadErrorMessage(new ApiError(409, [{ field: null, message: 'x' }]))).toMatch(/sedang berjalan/);
    expect(uploadErrorMessage(new ApiError(413, []))).toMatch(/5 MB/);
    expect(uploadErrorMessage(new TypeError('fetch'))).toMatch(/API belum terhubung/);
  });

  it('error validasi kolom ditampilkan apa adanya, kegagalan job diberi petunjuk', () => {
    expect(uploadErrorMessage(new ApiError(422, [{ field: 'project_id', message: 'Gunakan format PRJ-xxx' }]))).toBe('Gunakan format PRJ-xxx');
    expect(uploadErrorMessage(new ApiError(422, [{ field: null, message: 'Impor Project Plan gagal' }]))).toMatch(/riwayat job impor/);
  });
});
