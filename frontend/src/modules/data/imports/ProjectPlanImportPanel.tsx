import { useEffect, useRef, useState, type ChangeEvent } from 'react';
import { listProjects, type Project } from '../projects/api';
import {
  ATTRIBUTE_LABEL,
  PLAN_ATTRIBUTES,
  REQUIRED_ATTRIBUTES,
  checkFile,
  chooseColumn,
  fileHeaders,
  previewAttributes,
  projectFromFileName,
  readyToImport,
  uploadErrorMessage,
  uploadProjectPlan,
  type ColumnOverrides,
  type PlanAttribute,
  type ProjectPlanResult,
} from './projectPlan';

type Busy = 'checking' | 'saving' | null;
const FROM_FILE = '';
const UNMAPPED = '';

/**
 * Unggah Project Plan CSV/XLSX (DIG-115, story DIG-25): pilih berkas, lihat pratinjau dan
 * pemetaan kolom hasil dry run, ubah pemetaan bila perlu, lalu simpan ke staging_project_plan.
 * Normalisasi dan load ke D-05/D-06 dikerjakan ETL DIG-29, bukan di sini.
 */
export function ProjectPlanImportPanel() {
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [projectId, setProjectId] = useState(FROM_FILE);
  const [file, setFile] = useState<File | null>(null);
  const [sheet, setSheet] = useState<string | null>(null);
  const [overrides, setOverrides] = useState<ColumnOverrides>({});
  const [preview, setPreview] = useState<ProjectPlanResult | null>(null);
  const [saved, setSaved] = useState<ProjectPlanResult | null>(null);
  const [busy, setBusy] = useState<Busy>(null);
  const [error, setError] = useState<string | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const pending = useRef<AbortController | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    listProjects(controller.signal).then(setProjects).catch(() => setProjects([]));
    return () => { controller.abort(); pending.current?.abort(); };
  }, []);

  async function check(next: { file: File; projectId: string; sheet: string | null; overrides: ColumnOverrides }) {
    pending.current?.abort();
    const controller = new AbortController();
    pending.current = controller;
    setBusy('checking');
    setError(null);
    try {
      const result = await uploadProjectPlan({ ...next, dryRun: true }, controller.signal);
      setPreview(result);
      setSheet(result.sheet_name);
    } catch (failure) {
      if (failure instanceof DOMException && failure.name === 'AbortError') return;
      setPreview(null);
      setError(uploadErrorMessage(failure));
    } finally {
      if (pending.current === controller) { pending.current = null; setBusy(null); }
    }
  }

  function choose(event: ChangeEvent<HTMLInputElement>) {
    const chosen = event.target.files?.[0] ?? null;
    setSaved(null);
    setPreview(null);
    setOverrides({});
    setSheet(null);
    setFile(null);
    setError(null);
    if (!chosen) return;
    const problem = checkFile(chosen);
    if (problem) { setError(problem); return; }
    if (!projectId && !projectFromFileName(chosen.name)) {
      setError('Pilih proyek, atau beri nama berkas berpola project_plan_PRJ-xxx.');
    }
    setFile(chosen);
    if (projectId || projectFromFileName(chosen.name)) void check({ file: chosen, projectId, sheet: null, overrides: {} });
  }

  function changeProject(value: string) {
    setProjectId(value);
    setSaved(null);
    if (file && (value || projectFromFileName(file.name))) void check({ file, projectId: value, sheet, overrides });
    else if (file) { setPreview(null); setError('Pilih proyek, atau beri nama berkas berpola project_plan_PRJ-xxx.'); }
  }

  function changeSheet(value: string) {
    if (!file) return;
    // Sheet lain berarti judul kolom lain, jadi pemetaan manual dimulai ulang.
    setOverrides({});
    void check({ file, projectId, sheet: value, overrides: {} });
  }

  function changeColumn(header: string, value: string) {
    if (!file || !preview) return;
    const next = chooseColumn(overrides, preview.mapping, header, value === UNMAPPED ? null : (value as PlanAttribute));
    setOverrides(next);
    void check({ file, projectId, sheet, overrides: next });
  }

  function resetColumns() {
    if (!file) return;
    setOverrides({});
    void check({ file, projectId, sheet, overrides: {} });
  }

  async function save() {
    if (!file || !readyToImport(preview)) return;
    setBusy('saving');
    setError(null);
    try {
      const result = await uploadProjectPlan({ file, projectId, sheet, overrides, dryRun: false });
      setSaved(result);
      setPreview(null);
      setFile(null);
      setOverrides({});
      if (input.current) input.current.value = '';
    } catch (failure) {
      setError(uploadErrorMessage(failure));
    } finally {
      setBusy(null);
    }
  }

  const headers = preview ? fileHeaders(preview) : [];
  const columns = preview ? previewAttributes(preview.mapping) : [];
  const projectName = (id: string) => projects?.find((item) => item.project_id === id)?.project_name;

  return (
    <section className="module-panel" aria-labelledby="plan-import-title">
      <div className="panel-heading">
        <div>
          <h2 id="plan-import-title">Impor Project Plan</h2>
          <p className="panel-subtitle">Unggah Project Plan CSV (UTF-8) atau XLSX ke staging. Periksa pratinjau dan pemetaan kolom sebelum menyimpan. Normalisasi ke D-05 dan D-06 dijalankan terpisah oleh ETL.</p>
        </div>
      </div>

      {saved && (
        <p className="inline-notice success" role="status">
          <span><strong>{saved.rows_written ?? saved.total_rows} baris</strong> dari {saved.file_name} tersimpan di staging untuk {saved.project_id} (job {saved.job_id}).</span>
          <button type="button" className="link-button" onClick={() => setSaved(null)}>Tutup</button>
        </p>
      )}

      <div className="plan-import-form field-row">
        <label className="field" htmlFor="plan-import-project">
          <span>Proyek</span>
          <select id="plan-import-project" value={projectId} disabled={busy !== null} onChange={(event) => changeProject(event.target.value)}>
            <option value={FROM_FILE}>Ambil dari nama berkas (project_plan_PRJ-xxx)</option>
            {(projects ?? []).map((item) => <option key={item.project_id} value={item.project_id}>{item.project_id} · {item.project_name}</option>)}
          </select>
        </label>
        <label className="field" htmlFor="plan-import-file">
          <span>Berkas Project Plan <small>.csv atau .xlsx, maks. 5 MB</small></span>
          <input ref={input} id="plan-import-file" type="file" accept=".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" disabled={busy === 'saving'} onChange={choose} />
        </label>
        {preview && preview.sheets.length > 1 && (
          <label className="field" htmlFor="plan-import-sheet">
            <span>Sheet</span>
            <select id="plan-import-sheet" value={sheet ?? ''} disabled={busy !== null} onChange={(event) => changeSheet(event.target.value)}>
              {preview.sheets.map((name) => <option key={name} value={name}>{name}</option>)}
            </select>
          </label>
        )}
      </div>

      {error && <p className="inline-notice danger" role="alert">{error}</p>}
      {busy === 'checking' && <p className="plan-import-status field-hint" role="status">Memeriksa {file?.name}…</p>}

      {!preview && !error && busy === null && !saved && (
        <div className="empty-state compact">
          <h3>Belum ada berkas</h3>
          <p>Kolom wajib: kode task dan nama task. Judul kolom templat (Kode, Task, PIC, Mulai Rencana, dan seterusnya) dikenali otomatis; kolom lain tetap disimpan di raw.</p>
        </div>
      )}

      {preview && (
        <>
          <div className="plan-import-summary">
            {preview.errors.length === 0
              ? <p className={preview.total_rows ? 'import-summary ok' : 'form-alert'} role="status">
                  {preview.total_rows
                    ? <><strong>{preview.total_rows} baris siap diimpor</strong> ke {preview.project_id}{projectName(preview.project_id) ? ` (${projectName(preview.project_id)})` : ''}{preview.project_id_source === 'file_name' ? ', proyek dari nama berkas' : ''}.</>
                    : 'Berkas tidak berisi baris data.'}
                </p>
              : <div className="form-alert" role="alert">
                  <p>Berkas belum bisa diimpor. Tidak ada data yang disimpan.</p>
                  <ul>{preview.errors.map((item, index) => <li key={index}>{item.message}</li>)}</ul>
                </div>}
            <p className="field-hint">
              {preview.file_type.toUpperCase()}
              {preview.delimiter && <> · pemisah <span className="text-data">{preview.delimiter}</span></>}
              {preview.sheet_name && <> · sheet {preview.sheet_name}</>}
              {preview.skipped_blank_rows.length > 0 && <> · {preview.skipped_blank_rows.length} baris kosong dilewati (baris {preview.skipped_blank_rows.slice(0, 5).join(', ')}{preview.skipped_blank_rows.length > 5 ? ', …' : ''})</>}
            </p>
            {preview.same_file_job_id !== null && (
              <p className="inline-notice warning plan-import-warning" role="status">Berkas yang sama persis sudah pernah diimpor untuk {preview.project_id} (job {preview.same_file_job_id}). Mengimpor lagi akan membuat batch staging baru.</p>
            )}
            {preview.missing_optional.length > 0 && (
              <p className="field-hint">Kolom opsional tidak ada di berkas: {preview.missing_optional.map((item) => ATTRIBUTE_LABEL[item]).join(', ')}.</p>
            )}
          </div>

          <div className="panel-toolbar">
            <h3 className="plan-import-subtitle">Pemetaan kolom</h3>
            {Object.keys(overrides).length > 0 && <button type="button" className="button button-ghost" disabled={busy !== null} onClick={resetColumns}>Kembalikan pemetaan otomatis</button>}
          </div>
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr><th scope="col">Kolom di berkas</th><th scope="col">Atribut staging</th><th scope="col">Contoh isi</th></tr>
              </thead>
              <tbody>
                {headers.map((header) => {
                  const attribute = preview.mapping[header] ?? null;
                  const sample = attribute ? preview.preview_rows.find((row) => row.values[attribute])?.values[attribute] : null;
                  return (
                    <tr key={header}>
                      <td className="text-data">{header}{preview.typed_cells[header] ? <small className="cell-sub"> {preview.typed_cells[header]} sel bertipe</small> : null}</td>
                      <td>
                        <select className="toolbar-select" aria-label={`Atribut untuk kolom ${header}`} value={attribute ?? UNMAPPED} disabled={busy !== null} onChange={(event) => changeColumn(header, event.target.value)}>
                          <option value={UNMAPPED}>Tidak dipetakan (simpan di raw)</option>
                          {PLAN_ATTRIBUTES.map((item) => (
                            <option key={item} value={item}>{ATTRIBUTE_LABEL[item]} ({item}){REQUIRED_ATTRIBUTES.includes(item) ? ' · wajib' : ''}</option>
                          ))}
                        </select>
                      </td>
                      <td className="text-data">{sample ?? (attribute ? '' : '—')}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {preview.preview_rows.length > 0 && (
            <>
              <div className="panel-toolbar">
                <h3 className="plan-import-subtitle">Pratinjau {preview.preview_rows.length} dari {preview.total_rows} baris</h3>
              </div>
              <div className="table-scroll">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th scope="col" className="num">Baris</th>
                      {columns.map((item) => <th key={item} scope="col">{ATTRIBUTE_LABEL[item]}</th>)}
                    </tr>
                  </thead>
                  <tbody>
                    {preview.preview_rows.map((row) => (
                      <tr key={row.row}>
                        <td className="num">{row.row}</td>
                        {columns.map((item) => <td key={item} className="nowrap">{row.values[item] ?? ''}</td>)}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}

          <div className="plan-import-actions">
            <p className="field-hint">Nilai disimpan apa adanya. Format tanggal, PIC, dan dependency diperiksa saat validasi dan ETL.</p>
            <button type="button" className="button" disabled={!readyToImport(preview) || busy !== null} onClick={save}>
              {busy === 'saving' ? 'Mengimpor…' : `Impor ${preview.total_rows} baris ke staging`}
            </button>
          </div>
        </>
      )}
    </section>
  );
}
