import { useEffect, useRef, useState, type FormEvent } from 'react';
import { ApiError } from '../../../shared/api/client';
import { todayIso } from '../availability/dates';
import type { Project } from '../projects/api';
import { DECISION_LABEL, DECISIONS, EVENT_LABEL, EVENT_TYPES, MODE_LABEL, REQUESTERS, RESOLUTION_MODES, TASK_STATUS_LABEL, type ChangeEvent, type ChangeEventCreate, type Decision, type EventType, type ResolutionMode } from './api';
import { effectAllowed, needsExtension, normalize, toDays, validate, type ChangeErrors, type ChangeValues } from './rules';

type Props = {
  event: ChangeEvent | null;
  projects: Project[];
  /** Isian awal saat mencatat dari riwayat satu task. */
  preset?: { project_id: string; affected_task_id: string };
  onSubmit: (input: ChangeEventCreate) => Promise<void>;
  onClose: () => void;
};

const KEYS: (keyof ChangeValues)[] = ['event_id', 'project_id', 'event_type', 'event_date', 'requested_by', 'decision', 'resolution_mode', 'affected_task_id', 'extension_days', 'effect_status', 'effect_priority'];
// Nama kolom dari backend yang berbeda dengan nama isian form.
const SERVER_FIELD: Record<string, keyof ChangeValues> = { task_effect: 'effect_status', 'task_effect.status': 'effect_status', status: 'effect_status', priority_rank: 'effect_priority' };

function initialValues(event: ChangeEvent | null, preset: Props['preset']): ChangeValues {
  return {
    event_id: '',
    project_id: event?.project_id ?? preset?.project_id ?? '',
    event_type: event?.event_type ?? 'change_request',
    event_date: event?.event_date ?? todayIso(),
    requested_by: event?.requested_by ?? '',
    decision: event?.decision ?? '',
    resolution_mode: event?.resolution_mode ?? '',
    affected_task_id: event?.affected_task_id ?? preset?.affected_task_id ?? '',
    extension_days: event?.extension_days ? String(event.extension_days).replace('.', ',') : '',
    effect_status: '',
    effect_priority: '',
  };
}

/** Form CR, perubahan prioritas, dan kejadian D-10 lain (DIG-33: DIG-151). */
export function ChangeEventForm({ event, projects, preset, onSubmit, onClose }: Props) {
  const dialog = useRef<HTMLDialogElement>(null);
  const isNew = event === null;
  const [values, setValues] = useState<ChangeValues>(() => initialValues(event, preset));
  const [errors, setErrors] = useState<ChangeErrors>({});
  const [saving, setSaving] = useState(false);
  const project = projects.find((p) => p.project_id === values.project_id);
  const showEffect = isNew && effectAllowed(values);

  useEffect(() => { dialog.current?.showModal(); }, []);

  function set<K extends keyof ChangeValues>(key: K, value: ChangeValues[K]) {
    setValues((current) => normalize({ ...current, [key]: value }));
    setErrors((current) => ({ ...current, [key]: undefined, form: undefined }));
  }

  async function submit(submitEvent: FormEvent) {
    submitEvent.preventDefault();
    const found = validate(values, isNew, project?.start_date);
    setErrors(found);
    if (Object.keys(found).length) return;
    const input: ChangeEventCreate = {
      project_id: values.project_id,
      event_type: values.event_type,
      event_date: values.event_date,
      requested_by: values.requested_by.trim() || null,
      decision: values.decision || null,
      resolution_mode: values.resolution_mode || null,
      affected_task_id: values.affected_task_id.trim() || null,
      extension_days: toDays(values.extension_days),
      ...(isNew && values.event_id ? { event_id: values.event_id } : {}),
      ...(showEffect && (values.effect_status || values.effect_priority)
        ? { task_effect: { status: values.effect_status || null, priority_rank: values.effect_priority ? Number(values.effect_priority) : null } }
        : {}),
    };
    setSaving(true);
    try {
      await onSubmit(input);
    } catch (error) {
      if (error instanceof ApiError) {
        const fields: ChangeErrors = {};
        for (const [key, message] of Object.entries(error.fieldErrors())) {
          const mapped = SERVER_FIELD[key] ?? (KEYS.includes(key as keyof ChangeValues) ? (key as keyof ChangeValues) : null);
          if (mapped && !fields[mapped]) fields[mapped] = message;
        }
        const general = error.issues.find((issue) => !issue.field || !(SERVER_FIELD[issue.field] || KEYS.includes(issue.field as keyof ChangeValues)));
        setErrors({ ...fields, form: general?.message ?? (Object.keys(fields).length ? undefined : error.message) });
      } else {
        setErrors({ form: 'API belum terhubung. Periksa koneksi lalu coba lagi.' });
      }
      setSaving(false);
    }
  }

  const field = (key: keyof ChangeValues) => ({
    id: `change-${key}`,
    'aria-invalid': errors[key] ? true : undefined,
    'aria-describedby': errors[key] ? `change-${key}-error` : undefined,
  });
  const message = (key: keyof ChangeValues) => errors[key] && <span className="field-error" id={`change-${key}-error`}>{errors[key]}</span>;

  return (
    <dialog ref={dialog} className="dialog" aria-labelledby="change-form-title" onCancel={(e) => { e.preventDefault(); if (!saving) onClose(); }}>
      <form onSubmit={submit} noValidate>
        <div className="dialog-heading">
          <h2 id="change-form-title">{isNew ? 'Catat perubahan' : `Ubah ${event.event_id}`}</h2>
        </div>
        <div className="dialog-body form-grid">
          {errors.form && <p className="form-alert" role="alert">{errors.form}</p>}

          <div className="field-row">
            <label className="field" htmlFor="change-event_type">
              <span>Jenis</span>
              <select {...field('event_type')} value={values.event_type} onChange={(e) => set('event_type', e.target.value as EventType)}>
                {EVENT_TYPES.map((type) => <option key={type} value={type}>{EVENT_LABEL[type]}</option>)}
              </select>
            </label>
            <label className="field" htmlFor="change-project_id">
              <span>Proyek</span>
              <select {...field('project_id')} value={values.project_id} onChange={(e) => set('project_id', e.target.value)}>
                <option value="" disabled>Pilih proyek</option>
                {projects.map((p) => <option key={p.project_id} value={p.project_id}>{p.project_name}</option>)}
              </select>
              {message('project_id')}
            </label>
          </div>

          <div className="field-row">
            <label className="field" htmlFor="change-event_date">
              <span>Tanggal kejadian</span>
              <input {...field('event_date')} type="date" value={values.event_date} min={project?.start_date} onChange={(e) => set('event_date', e.target.value)} />
              {message('event_date')}
            </label>
            <label className="field" htmlFor="change-requested_by">
              <span>Diminta oleh <small>opsional</small></span>
              <input {...field('requested_by')} list="change-requesters" maxLength={100} value={values.requested_by} placeholder="Misalnya Kaur" onChange={(e) => set('requested_by', e.target.value)} />
              <datalist id="change-requesters">{REQUESTERS.map((name) => <option key={name} value={name} />)}</datalist>
              {message('requested_by')}
            </label>
          </div>

          <div className="field-row">
            <label className="field" htmlFor="change-affected_task_id">
              <span>Task terdampak <small>opsional</small></span>
              <input {...field('affected_task_id')} className="text-data" value={values.affected_task_id} placeholder="TSK-0001" autoComplete="off" onChange={(e) => set('affected_task_id', e.target.value.toUpperCase())} />
              {message('affected_task_id')}
              {!isNew && event.affected_task_name && values.affected_task_id === event.affected_task_id && <span className="field-hint">{event.affected_task_name}</span>}
            </label>
            {isNew && (
              <label className="field" htmlFor="change-event_id">
                <span>ID <small>opsional</small></span>
                <input {...field('event_id')} className="text-data" value={values.event_id} placeholder="Otomatis" onChange={(e) => set('event_id', e.target.value.toUpperCase())} />
                {message('event_id')}
              </label>
            )}
          </div>

          <div className="field-row">
            <label className="field" htmlFor="change-decision">
              <span>Keputusan <small>opsional</small></span>
              <select {...field('decision')} value={values.decision} onChange={(e) => set('decision', e.target.value as Decision | '')}>
                <option value="">Belum ada keputusan</option>
                {DECISIONS.map((d) => <option key={d} value={d}>{DECISION_LABEL[d]}</option>)}
              </select>
              {message('decision')}
            </label>
            <label className="field" htmlFor="change-resolution_mode">
              <span>Mode resolusi <small>opsional</small></span>
              <select {...field('resolution_mode')} value={values.resolution_mode} disabled={!values.decision} onChange={(e) => set('resolution_mode', e.target.value as ResolutionMode | '')}>
                <option value="">{values.decision ? 'Tidak ada' : 'Isi keputusan dulu'}</option>
                {RESOLUTION_MODES.map((m) => <option key={m} value={m}>{MODE_LABEL[m]}</option>)}
              </select>
              {message('resolution_mode')}
            </label>
            {needsExtension(values.resolution_mode) && (
              <label className="field" htmlFor="change-extension_days">
                <span>Tambahan hari</span>
                <input {...field('extension_days')} inputMode="decimal" value={values.extension_days} placeholder="Misalnya 2" onChange={(e) => set('extension_days', e.target.value)} />
                {message('extension_days')}
              </label>
            )}
          </div>

          {showEffect && (
            <fieldset className="field change-effect">
              <legend>Perubahan pada {values.affected_task_id.trim()} <small>disimpan bersama kejadian ini</small></legend>
              <p className="field-hint">Kosongkan bila task tidak berubah. Sistem tidak menebak efeknya; pilih apa yang memang diputuskan.</p>
              <div className="field-row">
                <div className="field" role="radiogroup" aria-labelledby="change-effect-status-label">
                  <span id="change-effect-status-label">Status task</span>
                  <div className="radio-row">
                    {([['', 'Tetap'], ['on_hold', TASK_STATUS_LABEL.on_hold], ['dropped', TASK_STATUS_LABEL.dropped]] as const).map(([value, label]) => (
                      <label key={value || 'tetap'} className="checkbox" htmlFor={`change-effect-${value || 'tetap'}`}>
                        <input id={`change-effect-${value || 'tetap'}`} type="radio" name="effect_status" value={value} checked={values.effect_status === value} onChange={() => set('effect_status', value)} />
                        <span>{label}</span>
                      </label>
                    ))}
                  </div>
                  {message('effect_status')}
                </div>
                <label className="field" htmlFor="change-effect_priority">
                  <span>Prioritas baru <small>opsional</small></span>
                  <input {...field('effect_priority')} id="change-effect_priority" inputMode="numeric" value={values.effect_priority} placeholder="1 sampai 999" onChange={(e) => set('effect_priority', e.target.value)} />
                  {message('effect_priority')}
                </label>
              </div>
            </fieldset>
          )}
          {!isNew && <p className="field-hint">Perubahan status dan prioritas task hanya bisa dicatat saat kejadian baru dibuat. Ubah task lewat tab Task bila perlu.</p>}
        </div>
        <div className="dialog-actions">
          <button type="button" className="button button-ghost" disabled={saving} onClick={onClose}>Batal</button>
          <button type="submit" className="button" disabled={saving}>{saving ? 'Menyimpan…' : 'Simpan'}</button>
        </div>
      </form>
    </dialog>
  );
}
