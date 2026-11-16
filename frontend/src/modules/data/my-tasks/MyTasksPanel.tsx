import { useCallback, useEffect, useState } from 'react';
import { PERM } from '../../../shared/auth/permissions';
import { useCan } from '../../../shared/auth/usePermission';
import { formatShort } from '../availability/dates';
import { actionsFor, type TaskAction } from './actions';
import { listMyTasks, recordMyTaskEvent, resolveMyTaskEvent, TASK_STATUS_LABEL, type MyTask, type MyTasks } from './api';
import { MyTaskEventDialog } from './MyTaskEventDialog';

type Load = { state: 'loading' } | { state: 'error' } | { state: 'ready'; data: MyTasks };

// Kelas pil status yang sudah ada di design system, supaya tidak menambah warna baru.
const STATUS_CLASS: Record<string, string> = {
  in_progress: 'status-development',
  in_qa: 'status-planning',
  on_hold: 'status-on_hold',
  blocked: 'danger',
};

/** Tab "Task saya": task yang ditugaskan ke pengguna, dengan tombol blocker dan overrun (DIG-155). */
export function MyTasksPanel() {
  const canRecord = useCan(PERM.changeEventWriteOwn);
  const [load, setLoad] = useState<Load>({ state: 'loading' });
  const [active, setActive] = useState<{ task: MyTask; action: TaskAction } | null>(null);
  const [notice, setNotice] = useState<{ tone: 'success' | 'danger'; text: string } | null>(null);

  const refresh = useCallback((signal?: AbortSignal) => {
    listMyTasks(signal)
      .then((data) => setLoad({ state: 'ready', data }))
      .catch((error: unknown) => { if (!(error instanceof DOMException && error.name === 'AbortError')) setLoad({ state: 'error' }); });
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    refresh(controller.signal);
    return () => controller.abort();
  }, [refresh]);

  const data = load.state === 'ready' ? load.data : null;
  const tasks = data?.tasks ?? [];
  const blocked = tasks.filter((task) => task.open_blocker).length;
  const late = tasks.filter((task) => task.is_past_plan).length;

  async function submit(date: string) {
    if (!active) return;
    const { task, action } = active;
    const result = action.mode === 'resolve'
      ? await resolveMyTaskEvent(task.task_id, action.event.event_id, date)
      : await recordMyTaskEvent(task.task_id, action.kind, date);
    const what = action.kind === 'blocker' ? 'Hambatan' : 'Overrun';
    const status = result.task_status_changed ? ` Status task sekarang ${(TASK_STATUS_LABEL[result.task_status] ?? result.task_status).toLowerCase()}.` : '';
    setActive(null);
    setNotice({ tone: 'success', text: `${what} pada ${task.task_id} ${action.mode === 'resolve' ? 'ditandai selesai' : 'dicatat'} (${result.event_id}).${status}` });
    refresh();
  }

  return (
    <section className="module-panel" aria-labelledby="my-tasks-title">
      <div className="panel-heading">
        <div>
          <h2 id="my-tasks-title">Task saya</h2>
          <p className="panel-subtitle">Task yang sedang ditugaskan kepada {data?.resource_name ?? 'kamu'} dan belum selesai. Tandai bila ada yang terhambat atau melewati rencana supaya terlihat System Analyst dan Kaur/Asman.</p>
        </div>
      </div>

      {data?.resource_id && (
        <div className="panel-toolbar">
          <p className="toolbar-summary"><strong>{tasks.length}</strong> task · <strong className={blocked ? 'text-danger' : ''}>{blocked}</strong> terhambat · <strong className={late ? 'text-danger' : ''}>{late}</strong> lewat rencana</p>
        </div>
      )}

      {notice && <p className={`inline-notice ${notice.tone}`} role="status">{notice.text}<button type="button" className="link-button" onClick={() => setNotice(null)}>Tutup</button></p>}

      {load.state === 'loading' && <div className="empty-state"><p>Memuat task…</p></div>}
      {load.state === 'error' && (
        <div className="empty-state">
          <h3>Task belum bisa dimuat</h3>
          <p>Pastikan API dan basis data sudah berjalan.</p>
          <button type="button" className="button button-ghost" onClick={() => { setLoad({ state: 'loading' }); refresh(); }}>Coba lagi</button>
        </div>
      )}
      {data && !data.resource_id && (
        <div className="empty-state">
          <h3>Akun belum dihubungkan ke anggota tim</h3>
          <p>Daftar ini diambil dari penugasan anggota. Minta Admin IT menghubungkan akun kamu ke data anggota supaya task kamu muncul di sini.</p>
        </div>
      )}
      {data?.resource_id && tasks.length === 0 && (
        <div className="empty-state">
          <h3>Tidak ada task yang sedang ditugaskan</h3>
          <p>Task yang sudah selesai, dibatalkan, atau dialihkan ke anggota lain tidak ditampilkan.</p>
        </div>
      )}

      {tasks.length > 0 && (
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th scope="col">Task</th>
                <th scope="col">Proyek</th>
                <th scope="col">Status</th>
                <th scope="col">Rencana selesai</th>
                <th scope="col">Hambatan</th>
                {canRecord && <th scope="col"><span className="visually-hidden">Aksi</span></th>}
              </tr>
            </thead>
            <tbody>
              {tasks.map((task) => (
                <tr key={task.task_id}>
                  <td className="cell-project"><span className="cell-title">{task.task_name}</span><span className="cell-sub text-data">{task.task_id}</span></td>
                  <td>{task.project_name}<span className="cell-sub">{task.feature_name}</span></td>
                  <td><span className={`status-pill ${STATUS_CLASS[task.status] ?? ''}`}>{TASK_STATUS_LABEL[task.status] ?? task.status}</span></td>
                  <td className="nowrap">{formatShort(task.planned_finish)}{task.is_past_plan && <span className="status-pill danger">Lewat rencana</span>}</td>
                  <td>
                    {!task.open_blocker && !task.open_overrun && <span className="cell-sub">Tidak ada</span>}
                    {task.open_blocker && <span className="cell-sub">Terhambat sejak {formatShort(task.open_blocker.event_date)}</span>}
                    {task.open_overrun && <span className="cell-sub">Overrun sejak {formatShort(task.open_overrun.event_date)}</span>}
                  </td>
                  {canRecord && (
                    <td>
                      <div className="row-actions">
                        {actionsFor(task).map((action) => (
                          <button key={`${action.kind}:${action.mode}`} type="button" className={`button button-ghost ${action.kind === 'blocker' && action.mode === 'record' ? 'button-danger' : ''}`} aria-label={`${action.label} untuk ${task.task_id}`} onClick={() => { setNotice(null); setActive({ task, action }); }}>
                            {action.label}
                          </button>
                        ))}
                      </div>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {active && <MyTaskEventDialog task={active.task} action={active.action} onSubmit={submit} onClose={() => setActive(null)} />}
    </section>
  );
}
