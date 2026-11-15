import { useEffect, useRef, useState, type ChangeEvent } from 'react';
import { ApiError } from '../../../shared/api/client';
import { importWorkload, type ImportResult } from './api';

type Props = { onImported: (result: ImportResult) => void; onClose: () => void };

const MAX_BYTES = 5_000_000;
const COLUMNS = 'item_id, resource_id, item_type, related_project_id, received_date, started_date, resolved_date, severity, is_hotfix';

/** Impor CSV D-08: pilih berkas, periksa (dry run), lalu simpan bila tidak ada kesalahan. */
export function WorkloadImport({ onImported, onClose }: Props) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [file, setFile] = useState<{ name: string; content: string } | null>(null);
  const [preview, setPreview] = useState<ImportResult | null>(null);
  const [busy, setBusy] = useState<'checking' | 'saving' | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { dialog.current?.showModal(); }, []);

  async function choose(event: ChangeEvent<HTMLInputElement>) {
    const chosen = event.target.files?.[0];
    setPreview(null);
    setError(null);
    setFile(null);
    if (!chosen) return;
    if (chosen.size > MAX_BYTES) { setError('Berkas lebih dari 5 MB. Pecah menjadi beberapa berkas.'); return; }
    const content = await chosen.text();
    setFile({ name: chosen.name, content });
    setBusy('checking');
    try {
      setPreview(await importWorkload(content, true));
    } catch (failure) {
      setError(failure instanceof ApiError ? failure.message : 'API belum terhubung. Periksa koneksi lalu coba lagi.');
    } finally {
      setBusy(null);
    }
  }

  async function save() {
    if (!file) return;
    setBusy('saving');
    try {
      const result = await importWorkload(file.content, false);
      if (result.applied) onImported(result);
      else { setPreview(result); setBusy(null); }
    } catch (failure) {
      setError(failure instanceof ApiError ? failure.message : 'API belum terhubung. Periksa koneksi lalu coba lagi.');
      setBusy(null);
    }
  }

  const ready = preview !== null && preview.error_count === 0 && preview.total > 0;

  return (
    <dialog ref={dialog} className="dialog" aria-labelledby="workload-import-title" onCancel={(event) => { event.preventDefault(); if (!busy) onClose(); }}>
      <div className="dialog-heading">
        <h2 id="workload-import-title">Impor beban non-proyek</h2>
      </div>
      <div className="dialog-body form-grid">
        <p className="field-hint">
          CSV UTF-8 berpemisah koma, baris pertama berisi kolom D-08: <span className="text-data">{COLUMNS}</span>.
          Tanggal YYYY-MM-DD dan is_hotfix true/false. Baris dengan item_id yang sudah ada akan diperbarui, item_id kosong diberi nomor otomatis.
        </p>
        <label className="field" htmlFor="workload-import-file">
          <span>Berkas CSV</span>
          <input id="workload-import-file" type="file" accept=".csv,text/csv" disabled={busy !== null} onChange={choose} />
        </label>

        {error && <p className="form-alert" role="alert">{error}</p>}
        {busy === 'checking' && <p className="field-hint" role="status">Memeriksa {file?.name}…</p>}

        {preview && preview.error_count === 0 && (
          <p className={preview.total ? 'import-summary ok' : 'form-alert'} role="status">
            {preview.total
              ? <><strong>{preview.total} baris siap diimpor:</strong> {preview.inserted} item baru, {preview.updated} item diperbarui.</>
              : 'Berkas tidak berisi baris data.'}
          </p>
        )}
        {preview && preview.error_count > 0 && (
          <>
            <p className="form-alert" role="alert">
              {preview.error_count} kesalahan di {preview.total} baris. Tidak ada data yang disimpan. Perbaiki berkasnya lalu pilih ulang.
            </p>
            <div className="table-scroll import-errors">
              <table className="data-table">
                <thead>
                  <tr><th scope="col" className="num">Baris</th><th scope="col">ID</th><th scope="col">Kolom</th><th scope="col">Kesalahan</th></tr>
                </thead>
                <tbody>
                  {preview.errors.map((e, index) => (
                    <tr key={index}>
                      <td className="num">{e.row}</td>
                      <td className="text-data">{e.item_id ?? ''}</td>
                      <td className="text-data">{e.field ?? ''}</td>
                      <td>{e.message}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {preview.error_count > preview.errors.length && <p className="field-hint">Menampilkan {preview.errors.length} kesalahan pertama.</p>}
          </>
        )}
      </div>
      <div className="dialog-actions">
        <button type="button" className="button button-ghost" onClick={onClose} disabled={busy !== null}>Batal</button>
        <button type="button" className="button" disabled={!ready || busy !== null} onClick={save}>{busy === 'saving' ? 'Mengimpor…' : 'Impor'}</button>
      </div>
    </dialog>
  );
}
