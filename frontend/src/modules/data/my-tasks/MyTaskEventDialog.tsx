import { useEffect, useRef, useState, type FormEvent } from 'react';
import { ApiError } from '../../../shared/api/client';
import { formatLong, todayIso } from '../availability/dates';
import { checkDate, dateBounds, effectNote, type TaskAction } from './actions';
import type { MyTask } from './api';

type Props = {
  task: MyTask;
  action: TaskAction;
  onSubmit: (date: string) => Promise<void>;
  onClose: () => void;
};

const TITLE: Record<string, string> = {
  'blocker:record': 'Tandai task terhambat',
  'blocker:resolve': 'Hambatan selesai',
  'overrun:record': 'Catat overrun',
  'overrun:resolve': 'Overrun selesai',
};

/** Konfirmasi mencatat atau menyelesaikan blocker/overrun pada task sendiri (DIG-155). */
export function MyTaskEventDialog({ task, action, onSubmit, onClose }: Props) {
  const dialog = useRef<HTMLDialogElement>(null);
  const today = todayIso();
  const [date, setDate] = useState(today);
  const [error, setError] = useState<{ field?: string; form?: string }>({});
  const [saving, setSaving] = useState(false);
  const bounds = dateBounds(action, today);
  const resolving = action.mode === 'resolve';

  useEffect(() => { dialog.current?.showModal(); }, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const invalid = checkDate(action, date, today);
    if (invalid) { setError({ field: invalid }); return; }
    setError({});
    setSaving(true);
    try {
      await onSubmit(date);
    } catch (caught) {
      const fields = caught instanceof ApiError ? caught.fieldErrors() : {};
      const field = fields.event_date ?? fields.resolved_date;
      setError(field ? { field } : { form: caught instanceof ApiError ? caught.message : 'API belum terhubung. Coba lagi.' });
      setSaving(false);
    }
  }

  return (
    <dialog ref={dialog} className="dialog dialog-narrow" aria-labelledby="my-task-event-title" onCancel={(event) => { event.preventDefault(); if (!saving) onClose(); }}>
      <form onSubmit={submit} noValidate>
        <div className="dialog-heading">
          <h2 id="my-task-event-title">{TITLE[`${action.kind}:${action.mode}`]}</h2>
          <p className="panel-subtitle"><span className="text-data">{task.task_id}</span> {task.task_name} · {task.project_name}</p>
        </div>
        <div className="dialog-body form-grid">
          {error.form && <p className="form-alert" role="alert">{error.form}</p>}
          <p id="my-task-event-note">{effectNote(task, action)}</p>
          {resolving && <p className="panel-subtitle">Dicatat {formatLong(action.event.event_date)}{action.event.requested_by ? ` oleh ${action.event.requested_by}` : ''} ({action.event.event_id}).</p>}
          <label className="field" htmlFor="my-task-event-date">
            <span>{resolving ? 'Tanggal selesai' : action.kind === 'blocker' ? 'Terhambat sejak' : 'Melewati rencana sejak'}</span>
            <input id="my-task-event-date" type="date" value={date} min={bounds.min} max={bounds.max} aria-invalid={error.field ? true : undefined} aria-describedby={error.field ? 'my-task-event-date-error' : 'my-task-event-note'} onChange={(e) => setDate(e.target.value)} />
            {error.field && <span className="field-error" id="my-task-event-date-error">{error.field}</span>}
          </label>
        </div>
        <div className="dialog-actions">
          <button type="button" className="button button-ghost" disabled={saving} onClick={onClose}>Batal</button>
          <button type="submit" className="button" disabled={saving}>{saving ? 'Menyimpan…' : action.label}</button>
        </div>
      </form>
    </dialog>
  );
}
