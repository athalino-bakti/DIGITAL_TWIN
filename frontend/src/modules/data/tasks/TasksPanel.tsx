import { useCallback, useEffect, useMemo, useState } from 'react';
import { ApiError, isApiUnreachable } from '../../../shared/api/client';
import { PERM } from '../../../shared/auth/permissions';
import { useCan } from '../../../shared/auth/usePermission';
import { formatRange, formatShort, todayIso } from '../availability/dates';
import { listProjects, type Project } from '../projects/api';
import { listTasks, TASK_STATUSES, TASK_STATUS_LABEL, updateTaskStatus, type Task, type TaskStatus, type TaskStatusInput } from './api';
import { quickChange } from './status';
import { TaskStatusForm } from './TaskStatusForm';

type Load = { state: 'loading' } | { state: 'error' } | { state: 'ready'; tasks: Task[]; projects: Project[] };
type Filters = { project_id: string; open_only: boolean };

const OPEN: TaskStatus[] = ['not_started', 'in_progress', 'blocked', 'on_hold', 'in_qa'];

/** Daftar task D-05 dan ubah status cepat (DIG-36: DIG-163). */
export function TasksPanel() {
  const [filters, setFilters] = useState<Filters>({ project_id: '', open_only: true });
  const [load, setLoad] = useState<Load>({ state: 'loading' });
  const canWrite = useCan(PERM.masterDataWrite);
  const [editing, setEditing] = useState<Task | null>(null);
  const [saving, setSaving] = useState<string | null>(null);
  const [notice, setNotice] = useState<{ tone: 'success' | 'danger'; text: string } | null>(null);

  const refresh = useCallback((signal?: AbortSignal) => {
    Promise.all([
      listTasks({ project_id: filters.project_id || undefined, status: filters.open_only ? OPEN : undefined }, signal),
      listProjects(signal),
    ])
      .then(([tasks, projects]) => setLoad({ state: 'ready', tasks, projects }))
      .catch((error: unknown) => { if (!(error instanceof DOMException && error.name === 'AbortError')) setLoad({ state: 'error' }); });
  }, [filters]);

  useEffect(() => {
    const controller = new AbortController();
    refresh(controller.signal);
    return () => controller.abort();
  }, [refresh]);

  const ready = load.state === 'ready';
  const tasks = useMemo(() => (ready ? load.tasks : []), [ready, load]);
  const projects = ready ? load.projects : [];
  const blocked = tasks.filter((t) => t.status === 'blocked').length;
  const late = tasks.filter((t) => t.status !== 'done' && t.status !== 'dropped' && t.planned_finish < todayIso()).length;

  function saved(task: Task) {
    // Baris langsung diganti dengan hasil server, lalu daftar dimuat ulang untuk filter.
    setLoad((current) => current.state === 'ready' ? { ...current, tasks: current.tasks.map((t) => (t.task_id === task.task_id ? task : t)) } : current);
    setNotice({ tone: 'success', text: `${task.task_id} sekarang ${TASK_STATUS_LABEL[task.status].toLowerCase()}.` });
    refresh();
  }

  async function quick(task: Task, next: TaskStatus) {
    if (next === task.status) return;
    setNotice(null);
    setSaving(task.task_id);
    try {
      saved(await updateTaskStatus(task.task_id, quickChange(task, next, todayIso())));
    } catch (error) {
      // Aturan yang tidak bisa dipenuhi otomatis: buka form lengkap supaya tanggalnya diisi manual.
      if (error instanceof ApiError && error.status === 422) setEditing({ ...task, status: next });
      else setNotice({ tone: 'danger', text: error instanceof ApiError && !isApiUnreachable(error) ? error.message : 'API belum terhubung. Coba lagi.' });
    } finally {
      setSaving(null);
    }
  }

  async function submit(input: TaskStatusInput) {
    if (!editing) return;
    const task = await updateTaskStatus(editing.task_id, input);
    setEditing(null);
    saved(task);
  }

  const setFilter = <K extends keyof Filters>(key: K, value: Filters[K]) => { setLoad({ state: 'loading' }); setFilters((current) => ({ ...current, [key]: value })); };

  return (
    <section className="module-panel" aria-labelledby="tasks-title">
      <div className="panel-heading">
        <div>
          <h2 id="tasks-title">Task</h2>
          <p className="panel-subtitle">D-05 tasks. Status diperbarui di sini di antara impor Project Plan.</p>
        </div>
      </div>

      <div className="panel-toolbar">
        {ready ? <p className="toolbar-summary"><strong>{tasks.length}</strong> task · <strong className={blocked ? 'text-danger' : ''}>{blocked}</strong> terhambat · <strong className={late ? 'text-danger' : ''}>{late}</strong> lewat jadwal</p> : <span />}
        <div className="workload-filters">
          <label className="visually-hidden" htmlFor="task-filter-project">Filter proyek</label>
          <select id="task-filter-project" className="workload-select" value={filters.project_id} onChange={(e) => setFilter('project_id', e.target.value)}>
            <option value="">Semua proyek</option>
            {projects.map((p) => <option key={p.project_id} value={p.project_id}>{p.project_name}</option>)}
          </select>
          <label className="checkbox" htmlFor="task-filter-open">
            <input id="task-filter-open" type="checkbox" checked={filters.open_only} onChange={(e) => setFilter('open_only', e.target.checked)} />
            <span>Belum selesai saja</span>
          </label>
        </div>
      </div>

      {notice && <p className={`inline-notice ${notice.tone}`} role="status">{notice.text}<button type="button" className="link-button" onClick={() => setNotice(null)}>Tutup</button></p>}

      {load.state === 'loading' && <div className="empty-state"><p>Memuat task…</p></div>}
      {load.state === 'error' && (
        <div className="empty-state">
          <h3>Daftar task belum bisa dimuat</h3>
          <p>Pastikan API dan basis data sudah berjalan.</p>
          <button type="button" className="button button-ghost" onClick={() => { setLoad({ state: 'loading' }); refresh(); }}>Coba lagi</button>
        </div>
      )}
      {ready && tasks.length === 0 && (
        <div className="empty-state">
          <h3>{filters.open_only || filters.project_id ? 'Tidak ada task yang sesuai filter' : 'Belum ada task'}</h3>
          <p>{filters.open_only || filters.project_id ? 'Ubah atau kosongkan filter di atas.' : 'Task masuk dari impor Project Plan (DIG-25).'}</p>
        </div>
      )}
      {ready && tasks.length > 0 && (
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th scope="col">Task</th>
                <th scope="col">Proyek</th>
                <th scope="col">Rencana</th>
                <th scope="col">Aktual</th>
                <th scope="col">Status</th>
                {canWrite && <th scope="col"><span className="visually-hidden">Aksi</span></th>}
              </tr>
            </thead>
            <tbody>
              {tasks.map((task) => (
                <tr key={task.task_id}>
                  <td className="cell-project">
                    <strong className="cell-title">{task.task_name}</strong>
                    <span className="text-data cell-sub">{task.task_id} · {task.feature_name} · {task.required_role_id}</span>
                  </td>
                  <td>{task.project_name}</td>
                  <td className="nowrap">{formatRange(task.planned_start, task.planned_finish)}</td>
                  <td className="nowrap">
                    {task.actual_start ? formatShort(task.actual_start) : '—'}{' → '}{task.actual_finish ? formatShort(task.actual_finish) : '—'}
                    {task.dod_fulfilled && <span className="cell-sub">DoD terpenuhi</span>}
                  </td>
                  <td>
                    {canWrite ? (
                      <>
                        <label className="visually-hidden" htmlFor={`task-status-${task.task_id}`}>Status {task.task_id}</label>
                        <select id={`task-status-${task.task_id}`} className={`status-select task-${task.status}`} value={task.status} disabled={saving === task.task_id} onChange={(e) => quick(task, e.target.value as TaskStatus)}>
                          {TASK_STATUSES.map((status) => <option key={status} value={status}>{TASK_STATUS_LABEL[status]}</option>)}
                        </select>
                      </>
                    ) : (
                      <span className={`status-pill task-${task.status}`}>{TASK_STATUS_LABEL[task.status]}</span>
                    )}
                  </td>
                  {canWrite && (
                    <td>
                      <div className="row-actions">
                        <button type="button" className="button button-ghost" aria-label={`Ubah tanggal ${task.task_id}`} onClick={() => { setNotice(null); setEditing(task); }}>Tanggal</button>
                      </div>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {editing && <TaskStatusForm task={editing} onSubmit={submit} onClose={() => setEditing(null)} />}
    </section>
  );
}
