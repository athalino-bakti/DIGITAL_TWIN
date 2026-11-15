import { useEffect, useRef, useState, type FormEvent } from 'react';
import { ApiError } from '../../../shared/api/client';
import type { Project } from '../projects/api';
import type { Resource } from '../resources/api';
import { ITEM_TYPE_LABEL, ITEM_TYPES, SEVERITIES, SEVERITY_LABEL, type ItemType, type Severity, type WorkloadInput, type WorkloadItem } from './api';

type Props = {
  item: WorkloadItem | null;
  resources: Resource[];
  projects: Project[];
  onSubmit: (input: WorkloadInput) => Promise<void>;
  onClose: () => void;
};

type Values = {
  item_id: string;
  resource_id: string;
  item_type: ItemType;
  related_project_id: string;
  received_date: string;
  started_date: string;
  resolved_date: string;
  severity: Severity | '';
  is_hotfix: boolean;
};

type Errors = Partial<Record<keyof Values | 'form', string>>;
const KEYS: (keyof Values)[] = ['item_id', 'resource_id', 'item_type', 'related_project_id', 'received_date', 'started_date', 'resolved_date', 'severity', 'is_hotfix'];

function initialValues(item: WorkloadItem | null): Values {
  return {
    item_id: item?.item_id ?? '',
    resource_id: item?.resource_id ?? '',
    item_type: item?.item_type ?? 'ticket',
    related_project_id: item?.related_project_id ?? '',
    received_date: item?.received_date ?? '',
    started_date: item?.started_date ?? '',
    resolved_date: item?.resolved_date ?? '',
    severity: item?.severity ?? '',
    is_hotfix: item?.is_hotfix ?? false,
  };
}

/** Aturan yang sama dengan backend (DIG-138), supaya pengguna langsung tahu sebelum menyimpan. */
function validate(values: Values, isNew: boolean): Errors {
  const errors: Errors = {};
  if (isNew && values.item_id && !/^WLI-\d{4,}$/.test(values.item_id)) errors.item_id = 'Format WLI-0001, atau kosongkan agar diisi otomatis';
  if (!values.resource_id) errors.resource_id = 'Pilih anggota';
  if (!values.received_date) errors.received_date = 'Tanggal diterima wajib diisi';
  if (values.started_date && values.received_date && values.started_date < values.received_date) errors.started_date = 'Tidak boleh sebelum tanggal diterima';
  if (values.resolved_date && values.received_date && values.resolved_date < values.received_date) errors.resolved_date = 'Tidak boleh sebelum tanggal diterima';
  else if (values.resolved_date && values.started_date && values.resolved_date < values.started_date) errors.resolved_date = 'Tidak boleh sebelum tanggal mulai';
  return errors;
}

export function WorkloadForm({ item, resources, projects, onSubmit, onClose }: Props) {
  const isNew = item === null;
  const dialog = useRef<HTMLDialogElement>(null);
  const [values, setValues] = useState(() => initialValues(item));
  const [errors, setErrors] = useState<Errors>({});
  const [saving, setSaving] = useState(false);

  useEffect(() => { dialog.current?.showModal(); }, []);

  function set<K extends keyof Values>(key: K, value: Values[K]) {
    setValues((current) => ({ ...current, [key]: value }));
    setErrors((current) => ({ ...current, [key]: undefined, form: undefined }));
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    const found = validate(values, isNew);
    setErrors(found);
    if (Object.keys(found).length) return;
    const input: WorkloadInput = {
      resource_id: values.resource_id,
      item_type: values.item_type,
      related_project_id: values.related_project_id || null,
      received_date: values.received_date,
      started_date: values.started_date || null,
      resolved_date: values.resolved_date || null,
      severity: values.severity || null,
      is_hotfix: values.is_hotfix,
      ...(isNew && values.item_id ? { item_id: values.item_id } : {}),
    };
    setSaving(true);
    try {
      await onSubmit(input);
    } catch (error) {
      if (error instanceof ApiError) {
        const fields = error.fieldErrors();
        const general = error.issues.find((issue) => !issue.field || !KEYS.includes(issue.field as keyof Values));
        setErrors({ ...fields, form: general?.message ?? (Object.keys(fields).length ? undefined : error.message) });
      } else {
        setErrors({ form: 'API belum terhubung. Periksa koneksi lalu coba lagi.' });
      }
      setSaving(false);
    }
  }

  const field = (key: keyof Values) => ({
    id: `workload-${key}`,
    'aria-invalid': errors[key] ? true : undefined,
    'aria-describedby': errors[key] ? `workload-${key}-error` : undefined,
  });
  const message = (key: keyof Values) => errors[key] && <span className="field-error" id={`workload-${key}-error`}>{errors[key]}</span>;

  return (
    <dialog ref={dialog} className="dialog" aria-labelledby="workload-form-title" onCancel={(event) => { event.preventDefault(); if (!saving) onClose(); }}>
      <form onSubmit={submit} noValidate>
        <div className="dialog-heading">
          <h2 id="workload-form-title">{isNew ? 'Tambah beban non-proyek' : `Ubah ${item.item_id}`}</h2>
        </div>
        <div className="dialog-body form-grid">
          {errors.form && <p className="form-alert" role="alert">{errors.form}</p>}

          <div className="field-row">
            <label className="field" htmlFor="workload-resource_id">
              <span>Anggota</span>
              <select {...field('resource_id')} value={values.resource_id} onChange={(e) => set('resource_id', e.target.value)}>
                <option value="" disabled>Pilih anggota</option>
                {resources.map((r) => <option key={r.resource_id} value={r.resource_id}>{r.resource_name} ({r.resource_id})</option>)}
              </select>
              {message('resource_id')}
            </label>
            <label className="field" htmlFor="workload-item_type">
              <span>Jenis</span>
              <select {...field('item_type')} value={values.item_type} onChange={(e) => set('item_type', e.target.value as ItemType)}>
                {ITEM_TYPES.map((type) => <option key={type} value={type}>{ITEM_TYPE_LABEL[type]}</option>)}
              </select>
              {message('item_type')}
            </label>
            <label className="field" htmlFor="workload-severity">
              <span>Severity <small>opsional</small></span>
              <select {...field('severity')} value={values.severity} onChange={(e) => set('severity', e.target.value as Severity | '')}>
                <option value="">Tidak diisi</option>
                {SEVERITIES.map((s) => <option key={s} value={s}>{SEVERITY_LABEL[s]}</option>)}
              </select>
              {message('severity')}
            </label>
          </div>

          <label className="field" htmlFor="workload-related_project_id">
            <span>Aplikasi terkait <small>opsional</small></span>
            <select {...field('related_project_id')} value={values.related_project_id} onChange={(e) => set('related_project_id', e.target.value)}>
              <option value="">Tidak terkait aplikasi</option>
              {projects.map((p) => <option key={p.project_id} value={p.project_id}>{p.project_name} ({p.project_id}){p.actual_launch_date ? '' : ', belum rilis'}</option>)}
            </select>
            {message('related_project_id')}
          </label>

          <div className="field-row">
            <label className="field" htmlFor="workload-received_date">
              <span>Diterima</span>
              <input {...field('received_date')} type="date" value={values.received_date} onChange={(e) => set('received_date', e.target.value)} />
              {message('received_date')}
            </label>
            <label className="field" htmlFor="workload-started_date">
              <span>Mulai dikerjakan <small>opsional</small></span>
              <input {...field('started_date')} type="date" value={values.started_date} min={values.received_date || undefined} onChange={(e) => set('started_date', e.target.value)} />
              {message('started_date')}
            </label>
            <label className="field" htmlFor="workload-resolved_date">
              <span>Selesai <small>opsional</small></span>
              <input {...field('resolved_date')} type="date" value={values.resolved_date} min={values.started_date || values.received_date || undefined} onChange={(e) => set('resolved_date', e.target.value)} />
              {message('resolved_date')}
            </label>
          </div>

          {isNew && (
            <label className="field" htmlFor="workload-item_id">
              <span>ID <small>opsional</small></span>
              <input {...field('item_id')} value={values.item_id} placeholder="Otomatis" onChange={(e) => set('item_id', e.target.value.toUpperCase())} />
              {message('item_id')}
            </label>
          )}

          <label className="checkbox" htmlFor="workload-is_hotfix">
            <input id="workload-is_hotfix" type="checkbox" checked={values.is_hotfix} aria-describedby="workload-is_hotfix-hint" onChange={(e) => set('is_hotfix', e.target.checked)} />
            <span>Hotfix</span>
          </label>
          {errors.is_hotfix ? message('is_hotfix') : <span className="field-hint" id="workload-is_hotfix-hint">Item darurat yang memicu preemption task proyek.</span>}
        </div>
        <div className="dialog-actions">
          <button type="button" className="button button-ghost" onClick={onClose} disabled={saving}>Batal</button>
          <button type="submit" className="button" disabled={saving}>{saving ? 'Menyimpan…' : 'Simpan'}</button>
        </div>
      </form>
    </dialog>
  );
}
