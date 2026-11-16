import { useCallback, useEffect, useMemo, useState } from 'react';
import { ApiError } from '../../../shared/api/client';
import { PERM } from '../../../shared/auth/permissions';
import { useCan } from '../../../shared/auth/usePermission';
import { formatShort } from '../availability/dates';
import { listProjects, type Project } from '../projects/api';
import { createChangeEvent, deleteChangeEvent, DECISION_LABEL, EVENT_LABEL, EVENT_TYPES, listChangeEvents, MODE_LABEL, TASK_STATUS_LABEL, updateChangeEvent, type ChangeEvent, type ChangeEventCreate, type EventType } from './api';
import { ChangeEventForm } from './ChangeEventForm';
import { TASK_ID } from './rules';

type Load = { state: 'loading' } | { state: 'error' } | { state: 'ready'; events: ChangeEvent[] };
type Filters = { project_id: string; event_type: EventType | ''; task: string };

// Pil jenis kejadian memakai warna status yang sudah ada di design system.
const TYPE_CLASS: Record<EventType, string> = {
  change_request: 'status-planning',
  priority_change: 'status-development',
  blocker: 'danger',
  overrun: 'status-on_hold',
  hotfix: 'danger',
};

const days = new Intl.NumberFormat('id-ID', { maximumFractionDigits: 1 });

/** Riwayat kejadian perubahan per proyek dan per task, plus form pencatatan (DIG-33: DIG-151, DIG-152). */
export function ChangeEventsPanel() {
  const canWrite = useCan(PERM.changeEventWrite);
  const [projects, setProjects] = useState<Project[]>([]);
  const [filters, setFilters] = useState<Filters>({ project_id: '', event_type: '', task: '' });
  const [taskText, setTaskText] = useState('');
  const [load, setLoad] = useState<Load>({ state: 'loading' });
  const [editing, setEditing] = useState<ChangeEvent | 'new' | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const [notice, setNotice] = useState<{ tone: 'success' | 'danger'; text: string } | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    listProjects(controller.signal).then(setProjects).catch(() => undefined);
    return () => controller.abort();
  }, []);

  // Kode task diketik dulu; filter baru dipakai setelah formatnya lengkap atau dikosongkan.
  useEffect(() => {
    const value = taskText.trim().toUpperCase();
    const timer = window.setTimeout(() => { if (value === '' || TASK_ID.test(value)) setFilters((f) => (f.task === value ? f : { ...f, task: value })); }, 300);
    return () => window.clearTimeout(timer);
  }, [taskText]);

  const refresh = useCallback((signal?: AbortSignal) => {
    listChangeEvents({ project_id: filters.project_id || undefined, event_type: filters.event_type ? [filters.event_type] : undefined, affected_task_id: filters.task || undefined }, signal)
      .then((events) => setLoad({ state: 'ready', events }))
      .catch((error: unknown) => { if (!(error instanceof DOMException && error.name === 'AbortError')) setLoad({ state: 'error' }); });
  }, [filters]);

  useEffect(() => {
    const controller = new AbortController();
    refresh(controller.signal);
    return () => controller.abort();
  }, [refresh]);

  const events = useMemo(() => (load.state === 'ready' ? load.events : []), [load]);
  const counts = useMemo(() => {
    const result = new Map<EventType, number>();
    for (const event of events) result.set(event.event_type, (result.get(event.event_type) ?? 0) + 1);
    return result;
  }, [events]);
  // Riwayat satu task: info task diambil dari kejadian terbaru (status dan prioritas saat ini).
  const focusTask = filters.task ? events.find((event) => event.affected_task_id === filters.task) ?? null : null;
  const filtered = Boolean(filters.project_id || filters.event_type || filters.task);

  const showTask = (event: ChangeEvent) => { if (event.affected_task_id) { setTaskText(event.affected_task_id); setFilters((f) => ({ ...f, task: event.affected_task_id ?? '' })); } };
  const clearTask = () => { setTaskText(''); setFilters((f) => ({ ...f, task: '' })); };

  async function save(input: ChangeEventCreate) {
    const saved = editing === 'new' || editing === null
      ? await createChangeEvent(input)
      : await updateChangeEvent(editing.event_id, { project_id: input.project_id, event_type: input.event_type, event_date: input.event_date, requested_by: input.requested_by, decision: input.decision, resolution_mode: input.resolution_mode, affected_task_id: input.affected_task_id, extension_days: input.extension_days });
    const effect = input.task_effect && saved.affected_task_id
      ? ` ${saved.affected_task_id} sekarang ${(TASK_STATUS_LABEL[saved.affected_task_status ?? ''] ?? saved.affected_task_status ?? '').toLowerCase()}, prioritas ${saved.affected_task_priority_rank}.`
      : '';
    setEditing(null);
    setNotice({ tone: 'success', text: `${saved.event_id} ${EVENT_LABEL[saved.event_type].toLowerCase()} tersimpan.${effect}` });
    refresh();
  }

  async function remove(event: ChangeEvent) {
    try {
      await deleteChangeEvent(event.event_id);
      setNotice({ tone: 'success', text: `${event.event_id} dihapus.` });
      refresh();
    } catch (error) {
      setNotice({ tone: 'danger', text: error instanceof ApiError ? error.message : 'API belum terhubung. Coba lagi.' });
    } finally {
      setConfirmDelete(null);
    }
  }

  return (
    <section className="module-panel" aria-labelledby="changes-title">
      <div className="panel-heading panel-heading-wrap">
        <div>
          <h2 id="changes-title">Riwayat perubahan</h2>
          <p className="panel-subtitle">D-10 change_events. Change request, perubahan prioritas, blocker, overrun, dan hotfix beserta keputusannya, terbaru lebih dulu.</p>
        </div>
        {canWrite && <div className="row-actions"><button type="button" className="button" disabled={projects.length === 0} onClick={() => { setNotice(null); setEditing('new'); }}>Catat perubahan</button></div>}
      </div>

      <div className="panel-toolbar">
        {load.state === 'ready'
          ? <p className="toolbar-summary"><strong>{events.length}</strong> kejadian{filtered ? ' sesuai filter' : ''}{EVENT_TYPES.filter((t) => counts.get(t)).map((t) => <span key={t}> · <strong>{counts.get(t)}</strong> {EVENT_LABEL[t].toLowerCase()}</span>)}</p>
          : <span />}
        <div className="workload-filters">
          <label className="visually-hidden" htmlFor="changes-project">Filter proyek</label>
          <select id="changes-project" className="workload-select" value={filters.project_id} onChange={(e) => setFilters((f) => ({ ...f, project_id: e.target.value }))}>
            <option value="">Semua proyek</option>
            {projects.map((p) => <option key={p.project_id} value={p.project_id}>{p.project_name}</option>)}
          </select>
          <label className="visually-hidden" htmlFor="changes-type">Filter jenis</label>
          <select id="changes-type" className="workload-select" value={filters.event_type} onChange={(e) => setFilters((f) => ({ ...f, event_type: e.target.value as EventType | '' }))}>
            <option value="">Semua jenis</option>
            {EVENT_TYPES.map((type) => <option key={type} value={type}>{EVENT_LABEL[type]}</option>)}
          </select>
          <label className="visually-hidden" htmlFor="changes-task">Riwayat satu task</label>
          <input id="changes-task" className="workload-select text-data changes-task" value={taskText} placeholder="Kode task, TSK-0001" autoComplete="off" onChange={(e) => setTaskText(e.target.value)} />
        </div>
      </div>

      {notice && <p className={`inline-notice ${notice.tone}`} role="status">{notice.text}<button type="button" className="link-button" onClick={() => setNotice(null)}>Tutup</button></p>}

      {filters.task && (
        <div className="changes-task-head">
          <div>
            <h3><span className="text-data">{filters.task}</span> {focusTask?.affected_task_name ?? ''}</h3>
            <p className="panel-subtitle">{focusTask
              ? <>Riwayat perubahan task ini. Status saat ini <strong>{TASK_STATUS_LABEL[focusTask.affected_task_status ?? ''] ?? '-'}</strong>, prioritas <strong>{focusTask.affected_task_priority_rank ?? '-'}</strong>.</>
              : 'Belum ada kejadian yang tercatat untuk task ini.'}</p>
          </div>
          <div className="row-actions">
            {canWrite && focusTask && <button type="button" className="button button-ghost" onClick={() => { setNotice(null); setEditing('new'); }}>Catat untuk task ini</button>}
            <button type="button" className="button button-ghost" onClick={clearTask}>Semua task</button>
          </div>
        </div>
      )}

      {load.state === 'loading' && <div className="empty-state"><p>Memuat riwayat…</p></div>}
      {load.state === 'error' && (
        <div className="empty-state">
          <h3>Riwayat belum bisa dimuat</h3>
          <p>Pastikan API dan basis data sudah berjalan.</p>
          <button type="button" className="button button-ghost" onClick={() => { setLoad({ state: 'loading' }); refresh(); }}>Coba lagi</button>
        </div>
      )}
      {load.state === 'ready' && events.length === 0 && !filters.task && (
        <div className="empty-state">
          <h3>{filtered ? 'Tidak ada kejadian sesuai filter' : 'Belum ada kejadian perubahan'}</h3>
          <p>{filtered ? 'Ubah atau kosongkan filter di atas.' : 'Kejadian masuk dari impor dataset atau dicatat lewat tombol Catat perubahan.'}</p>
        </div>
      )}

      {events.length > 0 && (
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th scope="col">Tanggal</th>
                <th scope="col">Jenis</th>
                {!filters.task && <th scope="col">Task</th>}
                {!filters.project_id && !filters.task && <th scope="col">Proyek</th>}
                <th scope="col">Keputusan</th>
                <th scope="col">Diminta oleh</th>
                {canWrite && <th scope="col"><span className="visually-hidden">Aksi</span></th>}
              </tr>
            </thead>
            <tbody>
              {events.map((event) => (
                <tr key={event.event_id}>
                  <td className="nowrap">{formatShort(event.event_date)}<span className="cell-sub text-data">{event.event_id}</span></td>
                  <td><span className={`status-pill ${TYPE_CLASS[event.event_type]}`}>{EVENT_LABEL[event.event_type]}</span></td>
                  {!filters.task && (
                    <td className="cell-project">
                      {event.affected_task_id
                        ? <button type="button" className="link-button changes-task-link" title={`Lihat riwayat ${event.affected_task_id}`} onClick={() => showTask(event)}><span className="cell-title">{event.affected_task_name}</span><span className="cell-sub text-data">{event.affected_task_id}</span></button>
                        : <span className="cell-sub">Tingkat proyek</span>}
                    </td>
                  )}
                  {!filters.project_id && !filters.task && <td>{event.project_name}</td>}
                  <td>
                    {event.decision ? DECISION_LABEL[event.decision] : <span className="cell-sub">Belum ada</span>}
                    {event.resolution_mode && <span className="cell-sub">{MODE_LABEL[event.resolution_mode]}{event.extension_days ? `, +${days.format(event.extension_days)} hari` : ''}</span>}
                  </td>
                  <td>{event.requested_by ?? <span className="cell-sub">-</span>}</td>
                  {canWrite && (
                    <td>
                      <div className="row-actions">
                        {confirmDelete === event.event_id ? (
                          <>
                            <span className="cell-sub">Hapus {event.event_id}?</span>
                            <button type="button" className="button button-ghost button-danger" onClick={() => remove(event)}>Ya, hapus</button>
                            <button type="button" className="button button-ghost" onClick={() => setConfirmDelete(null)}>Batal</button>
                          </>
                        ) : (
                          <>
                            <button type="button" className="button button-ghost" aria-label={`Ubah ${event.event_id}`} onClick={() => { setNotice(null); setEditing(event); }}>Ubah</button>
                            <button type="button" className="button button-ghost button-danger" aria-label={`Hapus ${event.event_id}`} onClick={() => setConfirmDelete(event.event_id)}>Hapus</button>
                          </>
                        )}
                      </div>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {editing && (
        <ChangeEventForm
          event={editing === 'new' ? null : editing}
          projects={projects}
          preset={editing === 'new' && focusTask ? { project_id: focusTask.project_id, affected_task_id: focusTask.affected_task_id ?? '' } : undefined}
          onSubmit={save}
          onClose={() => setEditing(null)}
        />
      )}
    </section>
  );
}
