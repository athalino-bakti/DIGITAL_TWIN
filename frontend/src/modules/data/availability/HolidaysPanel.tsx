import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react';
import { ApiError } from '../../../shared/api/client';
import { useCan } from '../../../shared/auth/usePermission';
import { PERM } from '../../../shared/auth/permissions';
import { createHoliday, deleteHoliday, listHolidays, updateHoliday, type Holiday } from './api';
import { formatLong, isValidIso, todayIso } from './dates';

type Load = { state: 'loading' } | { state: 'error' } | { state: 'ready'; holidays: Holiday[] };

export function HolidaysPanel() {
  const [year, setYear] = useState(() => Number(todayIso().slice(0, 4)));
  const [load, setLoad] = useState<Load>({ state: 'loading' });
  const canWrite = useCan(PERM.masterDataWrite);
  const [editing, setEditing] = useState<Holiday | 'new' | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const [notice, setNotice] = useState<{ tone: 'success' | 'danger'; text: string } | null>(null);

  const refresh = useCallback((signal?: AbortSignal) => {
    listHolidays(year, signal)
      .then((holidays) => setLoad({ state: 'ready', holidays }))
      .catch((error: unknown) => { if (!(error instanceof DOMException && error.name === 'AbortError')) setLoad({ state: 'error' }); });
  }, [year]);

  useEffect(() => {
    const controller = new AbortController();
    refresh(controller.signal);
    return () => controller.abort();
  }, [refresh]);

  const holidays = load.state === 'ready' ? load.holidays : [];
  const onWorkday = holidays.filter((h) => !h.is_weekend).length;

  async function save(input: Omit<Holiday, 'is_weekend'>) {
    const saved = editing === 'new' || editing === null ? await createHoliday(input) : await updateHoliday(editing.holiday_date, input.holiday_name);
    setEditing(null);
    setNotice({ tone: 'success', text: `${saved.holiday_name} (${formatLong(saved.holiday_date)}) tersimpan.` });
    const savedYear = Number(saved.holiday_date.slice(0, 4));
    if (savedYear !== year) setYear(savedYear);
    else refresh();
  }

  async function remove(holiday: Holiday) {
    try {
      await deleteHoliday(holiday.holiday_date);
      setNotice({ tone: 'success', text: `${holiday.holiday_name} dihapus.` });
      refresh();
    } catch (error) {
      setNotice({ tone: 'danger', text: error instanceof ApiError ? error.message : 'API belum terhubung. Coba lagi.' });
    } finally {
      setConfirmDelete(null);
    }
  }

  return (
    <section className="module-panel" aria-labelledby="holidays-title">
      <div className="panel-heading">
        <div>
          <h2 id="holidays-title">Hari libur</h2>
          <p className="panel-subtitle">D-11 holidays. Libur nasional dan cuti bersama, tidak dihitung sebagai hari kerja.</p>
        </div>
        {canWrite && <button type="button" className="button" disabled={load.state !== 'ready'} onClick={() => { setNotice(null); setEditing('new'); }}>Tambah hari libur</button>}
      </div>

      <div className="panel-toolbar">
        <div className="month-nav">
          <button type="button" className="button button-ghost" aria-label="Tahun sebelumnya" onClick={() => setYear(year - 1)}>‹</button>
          <strong aria-live="polite">{year}</strong>
          <button type="button" className="button button-ghost" aria-label="Tahun berikutnya" onClick={() => setYear(year + 1)}>›</button>
        </div>
        {load.state === 'ready' && <p className="toolbar-summary"><strong>{holidays.length}</strong> hari libur · <strong>{onWorkday}</strong> jatuh di hari kerja</p>}
      </div>

      {notice && <p className={`inline-notice ${notice.tone}`} role="status">{notice.text}<button type="button" className="link-button" onClick={() => setNotice(null)}>Tutup</button></p>}

      {load.state === 'loading' && <div className="empty-state"><p>Memuat hari libur…</p></div>}
      {load.state === 'error' && (
        <div className="empty-state">
          <h3>Hari libur belum bisa dimuat</h3>
          <p>Pastikan API dan basis data sudah berjalan.</p>
          <button type="button" className="button button-ghost" onClick={() => { setLoad({ state: 'loading' }); refresh(); }}>Coba lagi</button>
        </div>
      )}
      {load.state === 'ready' && holidays.length === 0 && (
        <div className="empty-state">
          <h3>Belum ada hari libur di {year}</h3>
          <p>Isi libur nasional dan cuti bersama sesuai SKB tiga menteri agar perhitungan hari kerja tepat.</p>
        </div>
      )}

      {holidays.length > 0 && (
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th scope="col">Tanggal</th>
                <th scope="col">Nama</th>
                <th scope="col"><span className="visually-hidden">Aksi</span></th>
              </tr>
            </thead>
            <tbody>
              {holidays.map((holiday) => (
                <tr key={holiday.holiday_date}>
                  <td className="nowrap">
                    {formatLong(holiday.holiday_date)}
                    <span className="text-data cell-sub">{holiday.holiday_date}</span>
                  </td>
                  <td>
                    {holiday.holiday_name}
                    {holiday.is_weekend && <span className="status-pill subtle-pill">Akhir pekan</span>}
                  </td>
                  <td>
                    {canWrite && <div className="row-actions">
                      {confirmDelete === holiday.holiday_date ? (
                        <>
                          <span className="text-body-sm">Hapus?</span>
                          <button type="button" className="button button-ghost button-danger" onClick={() => remove(holiday)}>Ya, hapus</button>
                          <button type="button" className="button button-ghost" onClick={() => setConfirmDelete(null)}>Batal</button>
                        </>
                      ) : (
                        <>
                          <button type="button" className="button button-ghost" onClick={() => { setNotice(null); setEditing(holiday); }}>Ubah</button>
                          <button type="button" className="button button-ghost" aria-label={`Hapus ${holiday.holiday_name}`} onClick={() => setConfirmDelete(holiday.holiday_date)}>Hapus</button>
                        </>
                      )}
                    </div>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {editing !== null && <HolidayForm holiday={editing === 'new' ? null : editing} onSubmit={save} onClose={() => setEditing(null)} />}
    </section>
  );
}

type FormProps = {
  holiday: Holiday | null;
  onSubmit: (input: Omit<Holiday, 'is_weekend'>) => Promise<void>;
  onClose: () => void;
};

type Errors = { holiday_date?: string; holiday_name?: string; form?: string };

function HolidayForm({ holiday, onSubmit, onClose }: FormProps) {
  const isNew = holiday === null;
  const dialog = useRef<HTMLDialogElement>(null);
  const [date, setDate] = useState(holiday?.holiday_date ?? '');
  const [name, setName] = useState(holiday?.holiday_name ?? '');
  const [errors, setErrors] = useState<Errors>({});
  const [saving, setSaving] = useState(false);

  useEffect(() => { dialog.current?.showModal(); }, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const found: Errors = {};
    if (!isValidIso(date)) found.holiday_date = 'Tanggal wajib diisi';
    if (!name.trim()) found.holiday_name = 'Nama hari libur wajib diisi';
    setErrors(found);
    if (Object.keys(found).length) return;
    setSaving(true);
    try {
      await onSubmit({ holiday_date: date, holiday_name: name.trim() });
    } catch (error) {
      if (error instanceof ApiError) {
        const fields = error.fieldErrors();
        setErrors({ holiday_date: fields.holiday_date, holiday_name: fields.holiday_name, form: fields.holiday_date || fields.holiday_name ? undefined : error.message });
      } else {
        setErrors({ form: 'API belum terhubung. Periksa koneksi lalu coba lagi.' });
      }
      setSaving(false);
    }
  }

  const describe = (key: 'holiday_date' | 'holiday_name') => ({
    'aria-invalid': errors[key] ? true : undefined,
    'aria-describedby': errors[key] ? `holiday-${key}-error` : undefined,
  });

  return (
    <dialog ref={dialog} className="dialog dialog-narrow" aria-labelledby="holiday-form-title" onCancel={(event) => { event.preventDefault(); if (!saving) onClose(); }}>
      <form onSubmit={submit} noValidate>
        <div className="dialog-heading">
          <h2 id="holiday-form-title">{isNew ? 'Tambah hari libur' : 'Ubah hari libur'}</h2>
        </div>
        <div className="dialog-body form-grid">
          {errors.form && <p className="form-alert" role="alert">{errors.form}</p>}
          <label className="field" htmlFor="holiday-date">
            <span>Tanggal</span>
            <input id="holiday-date" type="date" value={date} disabled={!isNew} onChange={(e) => { setDate(e.target.value); setErrors({}); }} {...describe('holiday_date')} />
            {errors.holiday_date ? <span className="field-error" id="holiday-holiday_date-error">{errors.holiday_date}</span> : !isNew && <span className="field-hint">Untuk memindah tanggal, hapus lalu tambahkan ulang</span>}
          </label>
          <label className="field" htmlFor="holiday-name">
            <span>Nama</span>
            <input id="holiday-name" value={name} maxLength={200} placeholder="Contoh: Cuti bersama Idulfitri" onChange={(e) => { setName(e.target.value); setErrors({}); }} {...describe('holiday_name')} />
            {errors.holiday_name && <span className="field-error" id="holiday-holiday_name-error">{errors.holiday_name}</span>}
          </label>
        </div>
        <div className="dialog-actions">
          <button type="button" className="button button-ghost" onClick={onClose} disabled={saving}>Batal</button>
          <button type="submit" className="button" disabled={saving}>{saving ? 'Menyimpan…' : 'Simpan'}</button>
        </div>
      </form>
    </dialog>
  );
}
