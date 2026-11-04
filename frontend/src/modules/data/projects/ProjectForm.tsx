import { useEffect, useRef, useState, type FormEvent } from 'react';
import { ApiError } from '../../../shared/api/client';
import { PROJECT_STATUSES, STATUS_LABEL, type Project, type ProjectInput, type ProjectStatus } from './api';

type Props = {
  project: Project | null;
  onSubmit: (input: ProjectInput) => Promise<void>;
  onClose: () => void;
};

type Values = {
  project_id: string;
  project_name: string;
  process_owner: string;
  priority_rank: string;
  start_date: string;
  target_launch_date: string;
  actual_launch_date: string;
  status: ProjectStatus;
  dor_fulfilled: boolean;
};

type Errors = Partial<Record<keyof Values | 'form', string>>;

function initialValues(project: Project | null): Values {
  return {
    project_id: project?.project_id ?? '',
    project_name: project?.project_name ?? '',
    process_owner: project?.process_owner ?? '',
    priority_rank: project ? String(project.priority_rank) : '',
    start_date: project?.start_date ?? '',
    target_launch_date: project?.target_launch_date ?? '',
    actual_launch_date: project?.actual_launch_date ?? '',
    status: project?.status ?? 'planning',
    dor_fulfilled: project?.dor_fulfilled ?? false,
  };
}

/** Aturan yang sama dengan backend, supaya pengguna langsung tahu sebelum menyimpan. */
function validate(values: Values, isNew: boolean): Errors {
  const errors: Errors = {};
  if (isNew && values.project_id && !/^PRJ-\d{3}$/.test(values.project_id)) errors.project_id = 'Format PRJ-001, atau kosongkan agar diisi otomatis';
  if (!values.project_name.trim()) errors.project_name = 'Nama aplikasi wajib diisi';
  if (!values.process_owner.trim()) errors.process_owner = 'Pemilik proses wajib diisi';
  if (!/^\d+$/.test(values.priority_rank) || Number(values.priority_rank) < 1) errors.priority_rank = 'Isi bilangan bulat mulai dari 1';
  if (!values.start_date) errors.start_date = 'Tanggal mulai wajib diisi';
  if (!values.target_launch_date) errors.target_launch_date = 'Target launching wajib diisi';
  else if (values.start_date && values.target_launch_date < values.start_date) errors.target_launch_date = 'Tidak boleh lebih awal dari tanggal mulai';
  if (values.status === 'released' && !values.actual_launch_date) errors.actual_launch_date = 'Wajib diisi bila status Rilis';
  else if (values.actual_launch_date && values.start_date && values.actual_launch_date < values.start_date) errors.actual_launch_date = 'Tidak boleh lebih awal dari tanggal mulai';
  return errors;
}

export function ProjectForm({ project, onSubmit, onClose }: Props) {
  const isNew = project === null;
  const dialog = useRef<HTMLDialogElement>(null);
  const [values, setValues] = useState(() => initialValues(project));
  const [errors, setErrors] = useState<Errors>({});
  const [saving, setSaving] = useState(false);

  useEffect(() => { dialog.current?.showModal(); }, []);

  function set<K extends keyof Values>(key: K, value: Values[K]) {
    setValues((current) => {
      const next = { ...current, [key]: value };
      // Tanggal aktual hanya bermakna untuk proyek yang sudah rilis.
      if (key === 'status' && value !== 'released') next.actual_launch_date = '';
      return next;
    });
    setErrors((current) => ({ ...current, [key]: undefined, form: undefined }));
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    const found = validate(values, isNew);
    setErrors(found);
    if (Object.keys(found).length) return;

    const input: ProjectInput = {
      project_name: values.project_name.trim(),
      process_owner: values.process_owner.trim(),
      priority_rank: Number(values.priority_rank),
      start_date: values.start_date,
      target_launch_date: values.target_launch_date,
      actual_launch_date: values.status === 'released' ? values.actual_launch_date : null,
      status: values.status,
      dor_fulfilled: values.dor_fulfilled,
      ...(isNew && values.project_id ? { project_id: values.project_id } : {}),
    };
    setSaving(true);
    try {
      await onSubmit(input);
    } catch (error) {
      if (error instanceof ApiError) {
        const fields = error.fieldErrors();
        const general = error.issues.find((issue) => !issue.field || !(issue.field in initialValues(null)));
        setErrors({ ...fields, form: general?.message ?? (Object.keys(fields).length ? undefined : error.message) });
      } else {
        setErrors({ form: 'API belum terhubung. Periksa koneksi lalu coba lagi.' });
      }
      setSaving(false);
    }
  }

  const field = (key: keyof Values) => ({
    id: `project-${key}`,
    'aria-invalid': errors[key] ? true : undefined,
    'aria-describedby': errors[key] ? `project-${key}-error` : undefined,
  });
  const message = (key: keyof Values) => errors[key] && <span className="field-error" id={`project-${key}-error`}>{errors[key]}</span>;

  return (
    <dialog ref={dialog} className="dialog" aria-labelledby="project-form-title" onCancel={(event) => { event.preventDefault(); if (!saving) onClose(); }}>
      <form onSubmit={submit} noValidate>
        <div className="dialog-heading">
          <h2 id="project-form-title">{isNew ? 'Tambah proyek' : `Ubah ${project.project_id}`}</h2>
        </div>
        <div className="dialog-body form-grid">
          {errors.form && <p className="form-alert" role="alert">{errors.form}</p>}

          <label className="field" htmlFor="project-project_name">
            <span>Nama aplikasi</span>
            <input {...field('project_name')} value={values.project_name} maxLength={200} onChange={(e) => set('project_name', e.target.value)} />
            {message('project_name')}
          </label>
          <label className="field" htmlFor="project-process_owner">
            <span>Pemilik proses</span>
            <input {...field('process_owner')} value={values.process_owner} maxLength={200} placeholder="Unit yang mengajukan aplikasi" onChange={(e) => set('process_owner', e.target.value)} />
            {message('process_owner')}
          </label>

          <div className="field-row">
            {isNew && <label className="field" htmlFor="project-project_id">
              <span>ID proyek <small>opsional</small></span>
              <input {...field('project_id')} value={values.project_id} placeholder="Otomatis" onChange={(e) => set('project_id', e.target.value.toUpperCase())} />
              {message('project_id')}
            </label>}
            <label className="field" htmlFor="project-priority_rank">
              <span>Prioritas</span>
              <input {...field('priority_rank')} type="number" min={1} step={1} inputMode="numeric" value={values.priority_rank} onChange={(e) => set('priority_rank', e.target.value)} />
              {message('priority_rank') ?? <span className="field-hint">1 = tertinggi, unik di antara proyek aktif</span>}
            </label>
            <label className="field" htmlFor="project-status">
              <span>Status</span>
              <select {...field('status')} value={values.status} onChange={(e) => set('status', e.target.value as ProjectStatus)}>
                {PROJECT_STATUSES.map((status) => <option key={status} value={status}>{STATUS_LABEL[status]}</option>)}
              </select>
              {message('status')}
            </label>
          </div>

          <div className="field-row">
            <label className="field" htmlFor="project-start_date">
              <span>Tanggal mulai</span>
              <input {...field('start_date')} type="date" value={values.start_date} onChange={(e) => set('start_date', e.target.value)} />
              {message('start_date')}
            </label>
            <label className="field" htmlFor="project-target_launch_date">
              <span>Target launching</span>
              <input {...field('target_launch_date')} type="date" min={values.start_date || undefined} value={values.target_launch_date} onChange={(e) => set('target_launch_date', e.target.value)} />
              {message('target_launch_date')}
            </label>
            <label className="field" htmlFor="project-actual_launch_date">
              <span>Launching aktual</span>
              <input {...field('actual_launch_date')} type="date" disabled={values.status !== 'released'} min={values.start_date || undefined} value={values.actual_launch_date} onChange={(e) => set('actual_launch_date', e.target.value)} />
              {message('actual_launch_date') ?? <span className="field-hint">Diisi saat status Rilis</span>}
            </label>
          </div>

          <label className="checkbox" htmlFor="project-dor_fulfilled">
            <input id="project-dor_fulfilled" type="checkbox" checked={values.dor_fulfilled} onChange={(e) => set('dor_fulfilled', e.target.checked)} />
            <span>Definition of Ready terpenuhi</span>
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
