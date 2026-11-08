import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { ApiError } from '../../../shared/api/client';
import { listComplexityLevels, updateComplexityLevel, type ComplexityInput, type ComplexityLevel } from './api';

type Field = keyof ComplexityInput;
type Draft = Record<Field, string>;
type Errors = Partial<Record<Field | 'form', string>>;
type Load = { state: 'loading' } | { state: 'error' } | { state: 'ready'; levels: ComplexityLevel[] };

const FIELDS: { key: Field; label: string }[] = [
  { key: 'min_days', label: 'Hari minimum' },
  { key: 'max_days', label: 'Hari maksimum' },
  { key: 'load_weight', label: 'Bobot beban' },
];

const number = new Intl.NumberFormat('id-ID', { maximumFractionDigits: 2 });

/** Terima koma desimal ("2,5") seperti yang biasa diketik pengguna Indonesia. */
const toInput = (value: number) => String(value).replace('.', ',');
const parse = (value: string) => (value.trim() === '' ? Number.NaN : Number(value.replace(',', '.')));

function validate(draft: Draft): Errors {
  const errors: Errors = {};
  for (const { key } of FIELDS) {
    const value = parse(draft[key]);
    if (!Number.isFinite(value)) errors[key] = 'Isi dengan angka';
    else if (value < 0) errors[key] = 'Tidak boleh negatif';
  }
  if (!errors.min_days && !errors.max_days && parse(draft.min_days) > parse(draft.max_days)) {
    errors.max_days = 'Tidak boleh lebih kecil dari hari minimum';
  }
  return errors;
}

export function ComplexityPanel() {
  const [load, setLoad] = useState<Load>({ state: 'loading' });
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState<Draft>({ min_days: '', max_days: '', load_weight: '' });
  const [errors, setErrors] = useState<Errors>({});
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const refresh = useCallback((signal?: AbortSignal) => {
    listComplexityLevels(signal)
      .then((levels) => setLoad({ state: 'ready', levels }))
      .catch((error: unknown) => { if (!(error instanceof DOMException && error.name === 'AbortError')) setLoad({ state: 'error' }); });
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    refresh(controller.signal);
    return () => controller.abort();
  }, [refresh]);

  function startEdit(level: ComplexityLevel) {
    setNotice(null);
    setErrors({});
    setEditing(level.complexity_id);
    setDraft({ min_days: toInput(level.min_days), max_days: toInput(level.max_days), load_weight: toInput(level.load_weight) });
  }

  async function save(event: FormEvent, level: ComplexityLevel) {
    event.preventDefault();
    const found = validate(draft);
    setErrors(found);
    if (Object.keys(found).length) return;
    setSaving(true);
    try {
      const saved = await updateComplexityLevel(level.complexity_id, {
        min_days: parse(draft.min_days),
        max_days: parse(draft.max_days),
        load_weight: parse(draft.load_weight),
      });
      setEditing(null);
      setNotice(`${saved.complexity_name} (${saved.complexity_id}) tersimpan.`);
      refresh();
    } catch (error) {
      if (error instanceof ApiError) {
        const fields = error.fieldErrors();
        setErrors(Object.keys(fields).length ? fields : { form: error.message });
      } else {
        setErrors({ form: 'API belum terhubung. Periksa koneksi lalu coba lagi.' });
      }
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="module-panel" aria-labelledby="complexity-title">
      <div className="panel-heading">
        <div>
          <h2 id="complexity-title">Level kompleksitas</h2>
          <p className="panel-subtitle">D-04 complexity_levels. Rentang hari dipakai untuk estimasi, bobot dipakai untuk Resource Load Index.</p>
        </div>
      </div>

      {notice && <p className="inline-notice success" role="status">{notice}<button type="button" className="link-button" onClick={() => setNotice(null)}>Tutup</button></p>}

      {load.state === 'loading' && <div className="empty-state"><p>Memuat level kompleksitas…</p></div>}
      {load.state === 'error' && (
        <div className="empty-state">
          <h3>Level kompleksitas belum bisa dimuat</h3>
          <p>Pastikan API dan basis data sudah berjalan.</p>
          <button type="button" className="button button-ghost" onClick={() => { setLoad({ state: 'loading' }); refresh(); }}>Coba lagi</button>
        </div>
      )}

      {load.state === 'ready' && (
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th scope="col">Level</th>
                <th scope="col" className="num">Hari minimum</th>
                <th scope="col" className="num">Hari maksimum</th>
                <th scope="col" className="num">Bobot beban</th>
                <th scope="col" className="num">Dipakai task</th>
                <th scope="col"><span className="visually-hidden">Aksi</span></th>
              </tr>
            </thead>
            <tbody>
              {load.levels.map((level) => editing === level.complexity_id ? (
                <tr key={level.complexity_id} className="row-editing">
                  <td>
                    <strong className="cell-title">{level.complexity_name}</strong>
                    <span className="text-data cell-sub">{level.complexity_id}</span>
                  </td>
                  {FIELDS.map(({ key, label }) => (
                    <td key={key} className="num">
                      <input
                        form={`complexity-${level.complexity_id}`}
                        className="cell-input"
                        type="text"
                        inputMode="decimal"
                        aria-label={`${label} ${level.complexity_name}`}
                        aria-invalid={errors[key] ? true : undefined}
                        aria-describedby={errors[key] ? `complexity-${key}-error` : undefined}
                        value={draft[key]}
                        onChange={(e) => { setDraft((d) => ({ ...d, [key]: e.target.value })); setErrors((x) => ({ ...x, [key]: undefined, form: undefined })); }}
                      />
                      {errors[key] && <span className="field-error cell-error" id={`complexity-${key}-error`}>{errors[key]}</span>}
                    </td>
                  ))}
                  <td className="num text-data">{level.task_count}</td>
                  <td>
                    <form id={`complexity-${level.complexity_id}`} className="row-actions" onSubmit={(e) => save(e, level)} noValidate>
                      <button type="submit" className="button" disabled={saving}>{saving ? 'Menyimpan…' : 'Simpan'}</button>
                      <button type="button" className="button button-ghost" disabled={saving} onClick={() => setEditing(null)}>Batal</button>
                    </form>
                    {errors.form && <span className="field-error cell-error" role="alert">{errors.form}</span>}
                  </td>
                </tr>
              ) : (
                <tr key={level.complexity_id}>
                  <td>
                    <strong className="cell-title">{level.complexity_name}</strong>
                    <span className="text-data cell-sub">{level.complexity_id}</span>
                  </td>
                  <td className="num text-data">{number.format(level.min_days)} hari</td>
                  <td className="num text-data">{number.format(level.max_days)} hari</td>
                  <td className="num text-data">{number.format(level.load_weight)}</td>
                  <td className="num text-data">{level.task_count}</td>
                  <td>
                    <div className="row-actions">
                      <button type="button" className="button button-ghost" disabled={editing !== null} onClick={() => startEdit(level)}>Ubah</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
