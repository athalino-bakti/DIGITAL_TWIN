import { useEffect, useRef, useState, type FormEvent } from 'react';
import { ApiError } from '../../../shared/api/client';
import { SENIORITIES, SENIORITY_LABEL, type Resource, type ResourceInput, type Role, type Seniority } from './api';

type Props = {
  resource: Resource | null;
  roles: Role[];
  onSubmit: (input: ResourceInput) => Promise<void>;
  onClose: () => void;
};

type Values = {
  resource_id: string;
  resource_name: string;
  primary_role_id: string;
  secondary_role_ids: string[];
  cross_role_capable: boolean;
  join_date: string;
  seniority: Seniority;
};

type Errors = Partial<Record<keyof Values | 'form', string>>;
const KEYS: (keyof Values)[] = ['resource_id', 'resource_name', 'primary_role_id', 'secondary_role_ids', 'cross_role_capable', 'join_date', 'seniority'];

function initialValues(resource: Resource | null): Values {
  return {
    resource_id: resource?.resource_id ?? '',
    resource_name: resource?.resource_name ?? '',
    primary_role_id: resource?.primary_role_id ?? '',
    secondary_role_ids: resource?.secondary_role_ids ?? [],
    cross_role_capable: resource?.cross_role_capable ?? false,
    join_date: resource?.join_date ?? '',
    seniority: resource?.seniority ?? 'mid',
  };
}

function validate(values: Values, isNew: boolean): Errors {
  const errors: Errors = {};
  if (isNew && values.resource_id && !/^RES-\d{3,}$/.test(values.resource_id)) errors.resource_id = 'Format RES-001, atau kosongkan agar diisi otomatis';
  if (!values.resource_name.trim()) errors.resource_name = 'Nama anggota wajib diisi';
  if (!values.primary_role_id) errors.primary_role_id = 'Pilih peran utama';
  if (!values.join_date) errors.join_date = 'Tanggal bergabung wajib diisi';
  return errors;
}

export function ResourceForm({ resource, roles, onSubmit, onClose }: Props) {
  const isNew = resource === null;
  const dialog = useRef<HTMLDialogElement>(null);
  const [values, setValues] = useState(() => initialValues(resource));
  const [errors, setErrors] = useState<Errors>({});
  const [saving, setSaving] = useState(false);

  useEffect(() => { dialog.current?.showModal(); }, []);

  function set<K extends keyof Values>(key: K, value: Values[K]) {
    setValues((current) => {
      const next = { ...current, [key]: value };
      // Peran utama tidak perlu dipilih lagi sebagai peran rangkap.
      if (key === 'primary_role_id') next.secondary_role_ids = current.secondary_role_ids.filter((id) => id !== value);
      return next;
    });
    setErrors((current) => ({ ...current, [key]: undefined, form: undefined }));
  }

  function toggleSecondary(roleId: string, checked: boolean) {
    const current = values.secondary_role_ids;
    // Simpan mengikuti urutan daftar peran agar hasilnya konsisten.
    const next = roles.map((r) => r.role_id).filter((id) => (id === roleId ? checked : current.includes(id)));
    set('secondary_role_ids', next);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    const found = validate(values, isNew);
    setErrors(found);
    if (Object.keys(found).length) return;
    const input: ResourceInput = {
      resource_name: values.resource_name.trim(),
      primary_role_id: values.primary_role_id,
      secondary_role_ids: values.secondary_role_ids,
      cross_role_capable: values.cross_role_capable,
      join_date: values.join_date,
      seniority: values.seniority,
      ...(isNew && values.resource_id ? { resource_id: values.resource_id } : {}),
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
    id: `resource-${key}`,
    'aria-invalid': errors[key] ? true : undefined,
    'aria-describedby': errors[key] ? `resource-${key}-error` : undefined,
  });
  const message = (key: keyof Values) => errors[key] && <span className="field-error" id={`resource-${key}-error`}>{errors[key]}</span>;

  return (
    <dialog ref={dialog} className="dialog" aria-labelledby="resource-form-title" onCancel={(event) => { event.preventDefault(); if (!saving) onClose(); }}>
      <form onSubmit={submit} noValidate>
        <div className="dialog-heading">
          <h2 id="resource-form-title">{isNew ? 'Tambah anggota' : `Ubah ${resource.resource_id}`}</h2>
        </div>
        <div className="dialog-body form-grid">
          {errors.form && <p className="form-alert" role="alert">{errors.form}</p>}

          <div className="field-row">
            <label className="field" htmlFor="resource-resource_name">
              <span>Nama anggota</span>
              <input {...field('resource_name')} value={values.resource_name} maxLength={200} onChange={(e) => set('resource_name', e.target.value)} />
              {message('resource_name')}
            </label>
            {isNew && <label className="field" htmlFor="resource-resource_id">
              <span>ID anggota <small>opsional</small></span>
              <input {...field('resource_id')} value={values.resource_id} placeholder="Otomatis" onChange={(e) => set('resource_id', e.target.value.toUpperCase())} />
              {message('resource_id')}
            </label>}
          </div>

          <div className="field-row">
            <label className="field" htmlFor="resource-primary_role_id">
              <span>Peran utama</span>
              <select {...field('primary_role_id')} value={values.primary_role_id} onChange={(e) => set('primary_role_id', e.target.value)}>
                <option value="" disabled>Pilih peran</option>
                {roles.map((role) => <option key={role.role_id} value={role.role_id}>{role.role_name}</option>)}
              </select>
              {message('primary_role_id')}
            </label>
            <label className="field" htmlFor="resource-seniority">
              <span>Senioritas</span>
              <select {...field('seniority')} value={values.seniority} onChange={(e) => set('seniority', e.target.value as Seniority)}>
                {SENIORITIES.map((s) => <option key={s} value={s}>{SENIORITY_LABEL[s]}</option>)}
              </select>
            </label>
            <label className="field" htmlFor="resource-join_date">
              <span>Tanggal bergabung</span>
              <input {...field('join_date')} type="date" value={values.join_date} onChange={(e) => set('join_date', e.target.value)} />
              {message('join_date') ?? <span className="field-hint">Dasar penanda masa onboarding</span>}
            </label>
          </div>

          <fieldset className="field" aria-describedby={errors.secondary_role_ids ? 'resource-secondary_role_ids-error' : undefined}>
            <legend>Peran rangkap <small>opsional, bisa lebih dari satu</small></legend>
            <div className="choice-grid">
              {roles.filter((role) => role.role_id !== values.primary_role_id).map((role) => (
                <label key={role.role_id} className="checkbox choice">
                  <input type="checkbox" checked={values.secondary_role_ids.includes(role.role_id)} onChange={(e) => toggleSecondary(role.role_id, e.target.checked)} />
                  <span>{role.role_name}</span>
                </label>
              ))}
            </div>
            {message('secondary_role_ids')}
          </fieldset>

          <label className="checkbox" htmlFor="resource-cross_role_capable">
            <input id="resource-cross_role_capable" type="checkbox" checked={values.cross_role_capable} onChange={(e) => set('cross_role_capable', e.target.checked)} />
            <span>Bisa mengambil alih task lintas peran</span>
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
