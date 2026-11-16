import { useCallback, useEffect, useMemo, useState } from 'react';
import { NavLink } from 'react-router-dom';
import { ApiError } from '../../../shared/api/client';
import { useCan } from '../../../shared/auth/usePermission';
import { PERM } from '../../../shared/auth/permissions';
import { listResources, type Resource } from '../resources/api';
import { AvailabilityForm } from './AvailabilityForm';
import { TakeoverDialog } from './TakeoverDialog';
import { listAffectedTasks } from './takeover';
import { ABSENCE_LABEL, ABSENCE_TYPES, createAvailability, deleteAvailability, listAvailability, listHolidays, updateAvailability, type Availability, type AvailabilityInput, type Holiday } from './api';
import { addDays, countWorkingDays, formatLong, formatMonth, formatRange, monthBounds, monthGrid, monthOf, shiftMonth, todayIso, WEEKDAY_SHORT, type Month } from './dates';

type Load = { state: 'loading' } | { state: 'error' } | { state: 'ready'; items: Availability[]; resources: Resource[]; holidays: Holiday[] };
type Editing = { item: Availability | null; defaultDate?: string } | null;

/** Jumlah chip per hari sebelum diringkas menjadi "+N lainnya". */
const MAX_CHIPS = 3;

export function AvailabilityPanel() {
  const today = todayIso();
  const [month, setMonth] = useState<Month>(() => monthOf(today));
  const [resourceFilter, setResourceFilter] = useState('');
  const [load, setLoad] = useState<Load>({ state: 'loading' });
  const canWrite = useCan(PERM.availabilityWrite);
  // Pengalihan butuh melihat beban anggota lain (kandidat) dan mencatat ketidakhadiran.
  const canTakeover = useCan(PERM.workloadReadAll) && canWrite;
  const [takeover, setTakeover] = useState<{ item: Availability; intro?: string } | null>(null);
  const [editing, setEditing] = useState<Editing>(null);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const [notice, setNotice] = useState<{ tone: 'success' | 'danger'; text: string } | null>(null);

  const grid = useMemo(() => monthGrid(month), [month]);
  const { first, last } = monthBounds(month);

  const refresh = useCallback((signal?: AbortSignal) => {
    Promise.all([
      listAvailability({ date_from: grid[0], date_to: grid[grid.length - 1] }, signal),
      listResources(signal),
      listHolidays(undefined, signal),
    ])
      .then(([items, resources, holidays]) => setLoad({ state: 'ready', items, resources, holidays }))
      .catch((error: unknown) => { if (!(error instanceof DOMException && error.name === 'AbortError')) setLoad({ state: 'error' }); });
  }, [grid]);

  useEffect(() => {
    const controller = new AbortController();
    refresh(controller.signal);
    return () => controller.abort();
  }, [refresh]);

  const ready = load.state === 'ready';
  const resources = ready ? load.resources : [];
  const holidays = ready ? load.holidays : [];
  const holidayNames = useMemo(() => new Map(holidays.map((h) => [h.holiday_date, h.holiday_name])), [holidays]);
  const holidaySet = useMemo(() => new Set(holidayNames.keys()), [holidayNames]);
  const items = useMemo(
    () => (ready ? load.items : []).filter((item) => !resourceFilter || item.resource_id === resourceFilter),
    [ready, load, resourceFilter],
  );

  /** Catatan per tanggal di kalender. */
  const byDay = useMemo(() => {
    const map = new Map<string, Availability[]>();
    for (const item of items) {
      const start = item.date_start > grid[0] ? item.date_start : grid[0];
      const end = item.date_end < grid[grid.length - 1] ? item.date_end : grid[grid.length - 1];
      for (let day = start; day <= end; day = addDays(day, 1)) map.set(day, [...(map.get(day) ?? []), item]);
    }
    return map;
  }, [items, grid]);

  const monthItems = items.filter((item) => item.date_end >= first && item.date_start <= last);
  const workingDaysInMonth = countWorkingDays(first, last, holidaySet);
  const holidaysInMonth = holidays.filter((h) => h.holiday_date >= first && h.holiday_date <= last);

  async function save(input: AvailabilityInput) {
    const target = editing?.item;
    const saved = target ? await updateAvailability(target.availability_id, input) : await createAvailability(input);
    setEditing(null);
    setNotice({ tone: 'success', text: `${saved.availability_id} ${saved.resource_name} tersimpan (${saved.working_days} hari kerja).` });
    refresh();
    // DIG-160: ketidakhadiran baru langsung menawarkan pengalihan bila ada task yang terdampak.
    if (!target && canTakeover && saved.absence_type !== 'rotation_in') {
      listAffectedTasks(saved.availability_id)
        .then((tasks) => {
          if (tasks.length > 0) setTakeover({ item: saved, intro: `${saved.resource_name} memegang ${tasks.length} task aktif selama periode ini. Alihkan sekarang, atau tutup dan lakukan nanti dari tombol Task terdampak.` });
        })
        .catch(() => undefined);
    }
  }

  async function remove(item: Availability) {
    try {
      await deleteAvailability(item.availability_id);
      setNotice({ tone: 'success', text: `${item.availability_id} dihapus.` });
      refresh();
    } catch (error) {
      setNotice({ tone: 'danger', text: error instanceof ApiError ? error.message : 'API belum terhubung. Coba lagi.' });
    } finally {
      setConfirmDelete(null);
    }
  }

  function openNew(defaultDate?: string) {
    setNotice(null);
    setEditing({ item: null, defaultDate });
  }

  return (
    <section className="module-panel" aria-labelledby="availability-title">
      <div className="panel-heading">
        <div>
          <h2 id="availability-title">Ketersediaan</h2>
          <p className="panel-subtitle">D-09 availability. Cuti, izin mendadak, dan rotasi anggota, dibaca bersama hari libur D-11.</p>
        </div>
        {canWrite && <button type="button" className="button" disabled={!ready || resources.length === 0} onClick={() => openNew()}>Catat ketidakhadiran</button>}
      </div>

      <div className="panel-toolbar">
        <div className="month-nav">
          <button type="button" className="button button-ghost" aria-label="Bulan sebelumnya" onClick={() => setMonth(shiftMonth(month, -1))}>‹</button>
          <strong aria-live="polite">{formatMonth(month)}</strong>
          <button type="button" className="button button-ghost" aria-label="Bulan berikutnya" onClick={() => setMonth(shiftMonth(month, 1))}>›</button>
          <button type="button" className="button button-ghost" onClick={() => setMonth(monthOf(today))}>Hari ini</button>
        </div>
        <div className="toolbar-filters">
          {ready && <p className="toolbar-summary"><strong>{workingDaysInMonth}</strong> hari kerja · <strong>{holidaysInMonth.length}</strong> hari libur · <strong>{monthItems.length}</strong> catatan</p>}
          <label className="visually-hidden" htmlFor="availability-filter">Filter anggota</label>
          <select id="availability-filter" className="toolbar-select" value={resourceFilter} onChange={(e) => setResourceFilter(e.target.value)} disabled={!ready}>
            <option value="">Semua anggota</option>
            {resources.map((r) => <option key={r.resource_id} value={r.resource_id}>{r.resource_name}</option>)}
          </select>
        </div>
      </div>

      {notice && <p className={`inline-notice ${notice.tone}`} role="status">{notice.text}<button type="button" className="link-button" onClick={() => setNotice(null)}>Tutup</button></p>}

      {load.state === 'loading' && <div className="empty-state"><p>Memuat kalender…</p></div>}
      {load.state === 'error' && (
        <div className="empty-state">
          <h3>Kalender belum bisa dimuat</h3>
          <p>Pastikan API dan basis data sudah berjalan.</p>
          <button type="button" className="button button-ghost" onClick={() => { setLoad({ state: 'loading' }); refresh(); }}>Coba lagi</button>
        </div>
      )}
      {ready && resources.length === 0 && (
        <div className="empty-state">
          <h3>Belum ada anggota</h3>
          <p>Ketidakhadiran dicatat per anggota. Tambahkan anggota dulu di tab <NavLink to="/data/anggota">Anggota</NavLink>.</p>
        </div>
      )}

      {ready && resources.length > 0 && (
        <>
          <div className="calendar">
            <div className="calendar-head" aria-hidden="true">{WEEKDAY_SHORT.map((name) => <span key={name}>{name}</span>)}</div>
            <ol className="calendar-grid" aria-label={`Kalender ${formatMonth(month)}`}>
              {grid.map((day, index) => {
                const outside = day < first || day > last;
                const holiday = holidayNames.get(day);
                const dayItems = byDay.get(day) ?? [];
                const classes = ['calendar-day', index % 7 >= 5 && 'is-weekend', holiday && 'is-holiday', outside && 'is-outside', day === today && 'is-today'].filter(Boolean).join(' ');
                const label = [formatLong(day), holiday && `libur: ${holiday}`, dayItems.length && `${dayItems.length} catatan ketersediaan`].filter(Boolean).join(', ');
                return (
                  <li key={day} className={classes}>
                    {canWrite
                      ? <button type="button" className="calendar-date" aria-label={`${label}. Catat ketidakhadiran mulai tanggal ini`} onClick={() => openNew(day)}>{Number(day.slice(8))}</button>
                      : <span className="calendar-date" aria-label={label}>{Number(day.slice(8))}</span>}
                    {holiday && <span className="calendar-holiday" title={holiday}>{holiday}</span>}
                    {dayItems.length > 0 && (
                      <span className="calendar-events">
                        {dayItems.slice(0, MAX_CHIPS).map((item) => (
                          <button key={item.availability_id} type="button" className={`absence-chip absence-${item.absence_type}`} title={`${item.resource_name}: ${ABSENCE_LABEL[item.absence_type]}, ${formatRange(item.date_start, item.date_end)}`} disabled={!canWrite} onClick={() => { setNotice(null); setEditing({ item }); }}>
                            {item.resource_name}
                          </button>
                        ))}
                        {dayItems.length > MAX_CHIPS && <span className="calendar-more">+{dayItems.length - MAX_CHIPS} lainnya</span>}
                      </span>
                    )}
                  </li>
                );
              })}
            </ol>
            <p className="calendar-legend">
              {ABSENCE_TYPES.map((type) => <span key={type}><span className={`legend-swatch absence-${type}`} />{ABSENCE_LABEL[type]}</span>)}
              <span><span className="legend-swatch legend-holiday" />Hari libur</span>
            </p>
          </div>

          {monthItems.length === 0 ? (
            <div className="empty-state compact">
              <h3>Tidak ada catatan di {formatMonth(month)}</h3>
              <p>Klik tanggal di kalender atau tombol Catat ketidakhadiran untuk menambah.</p>
            </div>
          ) : (
            <div className="table-scroll">
              <table className="data-table">
                <thead>
                  <tr>
                    <th scope="col">Anggota</th>
                    <th scope="col">Jenis</th>
                    <th scope="col">Periode</th>
                    <th scope="col" className="num">Hari kerja</th>
                    <th scope="col">Saat planning</th>
                    <th scope="col"><span className="visually-hidden">Aksi</span></th>
                  </tr>
                </thead>
                <tbody>
                  {monthItems.map((item) => (
                    <tr key={item.availability_id}>
                      <td className="cell-project">
                        <strong className="cell-title">{item.resource_name}</strong>
                        <span className="text-data cell-sub">{item.availability_id} · {item.resource_id}</span>
                      </td>
                      <td><span className={`status-pill absence-${item.absence_type}`}>{ABSENCE_LABEL[item.absence_type]}</span></td>
                      <td className="nowrap">{formatRange(item.date_start, item.date_end)}<span className="cell-sub">{item.calendar_days} hari kalender</span></td>
                      <td className="num">{item.absence_type === 'rotation_in' ? <span className="text-muted">Hadir</span> : item.working_days}</td>
                      <td>{item.is_known_at_planning ? 'Sudah diketahui' : 'Mendadak'}</td>
                      <td>
                        {canWrite && <div className="row-actions">
                          {confirmDelete === item.availability_id ? (
                            <>
                              <span className="text-body-sm">Hapus?</span>
                              <button type="button" className="button button-ghost button-danger" onClick={() => remove(item)}>Ya, hapus</button>
                              <button type="button" className="button button-ghost" onClick={() => setConfirmDelete(null)}>Batal</button>
                            </>
                          ) : (
                            <>
                              {canTakeover && item.absence_type !== 'rotation_in' && (
                                <button type="button" className="button button-ghost" onClick={() => { setNotice(null); setTakeover({ item }); }}>Task terdampak</button>
                              )}
                              <button type="button" className="button button-ghost" onClick={() => { setNotice(null); setEditing({ item }); }}>Ubah</button>
                              <button type="button" className="button button-ghost" aria-label={`Hapus ${item.availability_id}`} onClick={() => setConfirmDelete(item.availability_id)}>Hapus</button>
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
        </>
      )}

      {takeover !== null && (
        <TakeoverDialog availability={takeover.item} intro={takeover.intro} onClose={() => { setTakeover(null); refresh(); }} />
      )}
      {editing !== null && (
        <AvailabilityForm availability={editing.item} defaultDate={editing.defaultDate} resources={resources} holidays={holidaySet} onSubmit={save} onClose={() => setEditing(null)} />
      )}
    </section>
  );
}
