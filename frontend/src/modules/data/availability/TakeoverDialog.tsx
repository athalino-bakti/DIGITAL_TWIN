import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react';
import { ApiError, isApiUnreachable } from '../../../shared/api/client';
import { ABSENCE_LABEL, type Availability } from './api';
import { formatLong, formatRange, isValidIso } from './dates';
import { listAffectedTasks, listCandidates, MATCH_LABEL, takeOver, type AffectedTask, type Candidate } from './takeover';

type Props = {
  availability: Availability;
  /** Ditampilkan di atas daftar, misalnya setelah ketidakhadiran baru dicatat. */
  intro?: string;
  onClose: () => void;
};

type Load<T> = { state: 'loading' } | { state: 'error'; message: string } | { state: 'ready'; items: T };

const errorText = (error: unknown) =>
  error instanceof ApiError && !isApiUnreachable(error) ? error.message : 'API belum terhubung. Coba lagi.';

/** DIG-160: task yang terdampak ketidakhadiran dan pengalihannya ke anggota lain. */
export function TakeoverDialog({ availability, intro, onClose }: Props) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [tasks, setTasks] = useState<Load<AffectedTask[]>>({ state: 'loading' });
  const [selected, setSelected] = useState<AffectedTask | null>(null);
  const [done, setDone] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => { dialog.current?.showModal(); }, []);

  const refresh = useCallback((signal?: AbortSignal) => {
    listAffectedTasks(availability.availability_id, signal)
      .then((items) => setTasks({ state: 'ready', items }))
      .catch((error: unknown) => {
        if (!(error instanceof DOMException && error.name === 'AbortError')) setTasks({ state: 'error', message: errorText(error) });
      });
  }, [availability.availability_id]);

  useEffect(() => {
    const controller = new AbortController();
    refresh(controller.signal);
    return () => controller.abort();
  }, [refresh]);

  function finished(message: string) {
    setDone((current) => [...current, message]);
    setSelected(null);
    setTasks({ state: 'loading' });
    refresh();
  }

  return (
    <dialog ref={dialog} className="dialog" aria-labelledby="takeover-title" onCancel={(event) => { event.preventDefault(); if (!busy) onClose(); }}>
      <div className="dialog-heading">
        <h2 id="takeover-title">Task terdampak</h2>
        <p className="text-body-sm text-muted">
          {availability.resource_name} · {ABSENCE_LABEL[availability.absence_type]} · {formatRange(availability.date_start, availability.date_end)}
        </p>
      </div>
      <div className="dialog-body form-grid">
        {intro && <p className="inline-notice">{intro}</p>}
        {done.map((text) => <p key={text} className="inline-notice success" role="status">{text}</p>)}

        {tasks.state === 'loading' && <p className="text-muted" role="status">Memuat task…</p>}
        {tasks.state === 'error' && (
          <div className="form-alert" role="alert">
            {tasks.message}{' '}
            <button type="button" className="link-button" onClick={() => { setTasks({ state: 'loading' }); refresh(); }}>Coba lagi</button>
          </div>
        )}
        {tasks.state === 'ready' && tasks.items.length === 0 && (
          <div className="empty-state compact">
            <h3>Tidak ada task terdampak</h3>
            <p>{availability.resource_name} tidak memegang task aktif selama periode ini, atau semuanya sudah dialihkan.</p>
          </div>
        )}
        {tasks.state === 'ready' && tasks.items.length > 0 && (
          <ul className="takeover-list">
            {tasks.items.map((task) => (
              <li key={task.task_id} className={selected?.task_id === task.task_id ? 'is-open' : ''}>
                <div className="takeover-task">
                  <div>
                    <strong className="cell-title">{task.task_name}</strong>
                    <span className="text-data cell-sub">{task.task_id} · {task.project_name} · {task.required_role_id}</span>
                    <span className="cell-sub">Jadwal {formatRange(task.planned_start, task.planned_finish)}</span>
                  </div>
                  {selected?.task_id !== task.task_id && (
                    <button type="button" className="button button-ghost" disabled={busy} onClick={() => setSelected(task)}>Alihkan</button>
                  )}
                </div>
                {selected?.task_id === task.task_id && (
                  <TakeoverForm
                    task={task}
                    availability={availability}
                    onBusy={setBusy}
                    onCancel={() => setSelected(null)}
                    onDone={finished}
                  />
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
      <div className="dialog-actions">
        <button type="button" className="button" onClick={onClose} disabled={busy}>Selesai</button>
      </div>
    </dialog>
  );
}

type FormProps = {
  task: AffectedTask;
  availability: Availability;
  onBusy: (busy: boolean) => void;
  onCancel: () => void;
  onDone: (message: string) => void;
};

/** Tanggal pengalihan bawaan: hari pertama ketidakhadiran, tetapi tidak sebelum penugasan dimulai. */
const defaultDate = (task: AffectedTask, availability: Availability) =>
  availability.date_start > task.assigned_date ? availability.date_start : task.assigned_date;

function TakeoverForm({ task, availability, onBusy, onCancel, onDone }: FormProps) {
  const [day, setDay] = useState(() => defaultDate(task, availability));
  const [candidates, setCandidates] = useState<Load<Candidate[]>>({ state: 'loading' });
  const [choice, setChoice] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const validDay = isValidIso(day) && day >= task.assigned_date;

  useEffect(() => {
    if (!validDay) return;
    const controller = new AbortController();
    setCandidates({ state: 'loading' });
    listCandidates(task.task_id, day, controller.signal)
      .then((items) => {
        setCandidates({ state: 'ready', items });
        setChoice((current) => (items.some((c) => c.resource_id === current) ? current : ''));
      })
      .catch((err: unknown) => {
        if (!(err instanceof DOMException && err.name === 'AbortError')) setCandidates({ state: 'error', message: errorText(err) });
      });
    return () => controller.abort();
  }, [task.task_id, day, validDay]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!choice) { setError('Pilih anggota pengganti'); return; }
    setError(null);
    setSaving(true);
    onBusy(true);
    try {
      const result = await takeOver(task.task_id, { from_resource_id: availability.resource_id, to_resource_id: choice, takeover_date: day });
      onDone(`${task.task_id} dialihkan ke ${result.created.resource_name} mulai ${formatLong(day)} (${result.created.assignment_id}).`);
    } catch (err) {
      setError(err instanceof ApiError && !isApiUnreachable(err) ? (err.fieldErrors().to_resource_id ?? err.message) : 'API belum terhubung. Coba lagi.');
    } finally {
      setSaving(false);
      onBusy(false);
    }
  }

  const name = `takeover-${task.task_id}`;
  return (
    <form className="takeover-form form-grid" onSubmit={submit} noValidate aria-label={`Alihkan ${task.task_id}`}>
      {error && <p className="form-alert" role="alert">{error}</p>}
      <label className="field" htmlFor={`${name}-date`}>
        <span>Tanggal pengalihan</span>
        <input id={`${name}-date`} type="date" value={day} min={task.assigned_date} onChange={(e) => setDay(e.target.value)} aria-invalid={!validDay} aria-describedby={`${name}-date-hint`} />
        <span id={`${name}-date-hint`} className={validDay ? 'field-hint' : 'field-error'}>
          {validDay ? 'Penugasan lama ditutup dan pengganti mulai pada tanggal ini' : `Tidak boleh sebelum ${formatLong(task.assigned_date)}`}
        </span>
      </label>

      <fieldset className="field">
        <legend>Pengganti</legend>
        {candidates.state === 'loading' && validDay && <p className="text-muted" role="status">Mencari kandidat…</p>}
        {candidates.state === 'error' && <p className="field-error">{candidates.message}</p>}
        {candidates.state === 'ready' && candidates.items.length === 0 && (
          <p className="field-hint">Tidak ada anggota dengan peran {task.required_role_id} atau lintas peran yang hadir pada tanggal ini.</p>
        )}
        {candidates.state === 'ready' && candidates.items.length > 0 && (
          <div className="candidate-list">
            {candidates.items.map((c) => (
              <label key={c.resource_id} className={`candidate ${choice === c.resource_id ? 'is-selected' : ''}`} htmlFor={`${name}-${c.resource_id}`}>
                <input id={`${name}-${c.resource_id}`} type="radio" name={name} value={c.resource_id} checked={choice === c.resource_id} onChange={() => setChoice(c.resource_id)} />
                <span className="candidate-text">
                  <strong>{c.resource_name}</strong>
                  <span className="cell-sub">{MATCH_LABEL[c.match]} · {c.primary_role_id} · {c.seniority} · {c.active_assignments} task aktif</span>
                </span>
              </label>
            ))}
          </div>
        )}
      </fieldset>

      <div className="row-actions">
        <button type="button" className="button button-ghost" onClick={onCancel} disabled={saving}>Batal</button>
        <button type="submit" className="button" disabled={saving || !validDay || candidates.state !== 'ready' || candidates.items.length === 0}>{saving ? 'Mengalihkan…' : 'Alihkan task'}</button>
      </div>
    </form>
  );
}
