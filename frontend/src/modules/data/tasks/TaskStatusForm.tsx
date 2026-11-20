import { useEffect, useRef, useState, type FormEvent } from 'react';
import { ApiError, isApiUnreachable } from '../../../shared/api/client';
import { TASK_STATUSES, TASK_STATUS_LABEL, type Task, type TaskStatus, type TaskStatusInput } from './api';
import { checkStatus, type StatusErrors } from './status';

type Props = {
  task: Task;
  onSubmit: (input: TaskStatusInput) => Promise<void>;
  onClose: () => void;
};

type Values = Pick<Task, 'status' | 'actual_start' | 'actual_finish' | 'dod_fulfilled'>;
type Errors = StatusErrors & { form?: string };

/** Ubah status beserta tanggal aktual dan DoD secara lengkap (DIG-163). */
export function TaskStatusForm({ task, onSubmit, onClose }: Props) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [values, setValues] = useState<Values>({ status: task.status, actual_start: task.actual_start, actual_finish: task.actual_finish, dod_fulfilled: task.dod_fulfilled });
  const [errors, setErrors] = useState<Errors>({});
  const [saving, setSaving] = useState(false);

  useEffect(() => { dialog.current?.showModal(); }, []);

  function set<K extends keyof Values>(key: K, value: Values[K]) {
    setValues((current) => ({ ...current, [key]: value }));
    setErrors((current) => ({ ...current, [key]: undefined, form: undefined }));
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    const found = checkStatus(values);
    setErrors(found);
    if (Object.keys(found).length) return;
    setSaving(true);
    try {
      await onSubmit(values);
    } catch (error) {
      if (error instanceof ApiError && !isApiUnreachable(error)) {
        const fields = error.fieldErrors();
        setErrors({ actual_start: fields.actual_start, actual_finish: fields.actual_finish, dod_fulfilled: fields.dod_fulfilled, form: fields.actual_start || fields.actual_finish || fields.dod_fulfilled ? undefined : error.message });
      } else {
        setErrors({ form: 'API belum terhubung. Coba lagi.' });
      }
      setSaving(false);
    }
  }

  const id = (key: string) => `task-status-${key}`;
  const message = (key: keyof StatusErrors) => errors[key] && <span id={`${id(key)}-error`} className="field-error">{errors[key]}</span>;
  const describe = (key: keyof StatusErrors) => ({ 'aria-invalid': Boolean(errors[key]), 'aria-describedby': errors[key] ? `${id(key)}-error` : undefined });

  return (
    <dialog ref={dialog} className="dialog" aria-labelledby="task-status-title" onCancel={(event) => { event.preventDefault(); if (!saving) onClose(); }}>
      <form onSubmit={submit} noValidate>
        <div className="dialog-heading">
          <h2 id="task-status-title">Status {task.task_id}</h2>
          <p className="text-body-sm text-muted">{task.task_name} · {task.project_name}</p>
        </div>
        <div className="dialog-body form-grid">
          {errors.form && <p className="form-alert" role="alert">{errors.form}</p>}
          <label className="field" htmlFor={id('status')}>
            <span>Status</span>
            <select id={id('status')} value={values.status} onChange={(e) => set('status', e.target.value as TaskStatus)}>
              {TASK_STATUSES.map((status) => <option key={status} value={status}>{TASK_STATUS_LABEL[status]}</option>)}
            </select>
          </label>
          <div className="field-row">
            <label className="field" htmlFor={id('actual_start')}>
              <span>Mulai aktual</span>
              <input id={id('actual_start')} type="date" value={values.actual_start ?? ''} onChange={(e) => set('actual_start', e.target.value || null)} {...describe('actual_start')} />
              {message('actual_start')}
            </label>
            <label className="field" htmlFor={id('actual_finish')}>
              <span>Selesai aktual</span>
              <input id={id('actual_finish')} type="date" value={values.actual_finish ?? ''} min={values.actual_start ?? undefined} onChange={(e) => set('actual_finish', e.target.value || null)} {...describe('actual_finish')} />
              {message('actual_finish')}
            </label>
          </div>
          <label className="checkbox" htmlFor={id('dod_fulfilled')}>
            <input id={id('dod_fulfilled')} type="checkbox" checked={values.dod_fulfilled} onChange={(e) => set('dod_fulfilled', e.target.checked)} {...describe('dod_fulfilled')} />
            <span>Definition of Done terpenuhi</span>
          </label>
          {message('dod_fulfilled')}
          <p className="field-hint">Selesai wajib punya tanggal mulai dan selesai. Selain selesai, tanggal selesai dikosongkan.</p>
        </div>
        <div className="dialog-actions">
          <button type="button" className="button button-ghost" onClick={onClose} disabled={saving}>Batal</button>
          <button type="submit" className="button" disabled={saving}>{saving ? 'Menyimpan…' : 'Simpan'}</button>
        </div>
      </form>
    </dialog>
  );
}
