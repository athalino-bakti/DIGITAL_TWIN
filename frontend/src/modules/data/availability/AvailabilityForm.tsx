import { useEffect, useRef, useState, type FormEvent } from 'react';
import { ApiError } from '../../../shared/api/client';
import type { Resource } from '../resources/api';
import { ABSENCE_LABEL, ABSENCE_TYPES, type AbsenceType, type Availability, type AvailabilityInput } from './api';
import { calendarDays, countWorkingDays, isValidIso } from './dates';

type Props = {
  availability: Availability | null;
  resources: Resource[];
  holidays: ReadonlySet<string>;
  /** Tanggal awal bawaan saat menambah dari kalender. */
  defaultDate?: string;
  onSubmit: (input: AvailabilityInput) => Promise<void>;
  onClose: () => void;
};

type Values = {
  availability_id: string;
  resource_id: string;
  absence_type: AbsenceType;
  date_start: string;
  date_end: string;
  is_known_at_planning: boolean;
};

type Errors = Partial<Record<keyof Values | 'form', string>>;
const KEYS: (keyof Values)[] = ['availability_id', 'resource_id', 'absence_type', 'date_start', 'date_end', 'is_known_at_planning'];

/** Izin mendadak per definisi belum diketahui saat sprint planning; jenis lain biasanya sudah. */
const knownByDefault = (type: AbsenceType) => type !== 'sudden_leave';

function initialValues(item: Availability | null, defaultDate?: string): Values {
  return {
    availability_id: item?.availability_id ?? '',
    resource_id: item?.resource_id ?? '',
    absence_type: item?.absence_type ?? 'planned_leave',
    date_start: item?.date_start ?? defaultDate ?? '',
    date_end: item?.date_end ?? defaultDate ?? '',
    is_known_at_planning: item?.is_known_at_planning ?? true,
  };
}

function validate(values: Values, isNew: boolean): Errors {
  const errors: Errors = {};
  if (isNew && values.availability_id && !/^AVL-\d{3,}$/.test(values.availability_id)) errors.availability_id = 'Format AVL-001, atau kosongkan agar diisi otomatis';
  if (!values.resource_id) errors.resource_id = 'Pilih anggota';
  if (!values.date_start) errors.date_start = 'Tanggal mulai wajib diisi';
  if (!values.date_end) errors.date_end = 'Tanggal akhir wajib diisi';
  else if (values.date_start && values.date_end < values.date_start) errors.date_end = 'Tidak boleh lebih awal dari tanggal mulai';
  return errors;
}

export function AvailabilityForm({ availability, resources, holidays, defaultDate, onSubmit, onClose }: Props) {
  const isNew = availability === null;
  const dialog = useRef<HTMLDialogElement>(null);
  const [values, setValues] = useState(() => initialValues(availability, defaultDate));
  const [knownTouched, setKnownTouched] = useState(!isNew);
  const [errors, setErrors] = useState<Errors>({});
  const [saving, setSaving] = useState(false);

  useEffect(() => { dialog.current?.showModal(); }, []);

  function set<K extends keyof Values>(key: K, value: Values[K]) {
    setValues((current) => {
      const next = { ...current, [key]: value };
      if (key === 'absence_type' && !knownTouched) next.is_known_at_planning = knownByDefault(value as AbsenceType);
      // Tanggal akhir ikut maju bila belum diisi atau jadi lebih awal dari tanggal mulai.
      if (key === 'date_start' && typeof value === 'string' && (!current.date_end || current.date_end < value)) next.date_end = value;
      return next;
    });
    if (key === 'is_known_at_planning') setKnownTouched(true);
    setErrors((current) => ({ ...current, [key]: undefined, form: undefined }));
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    const found = validate(values, isNew);
    setErrors(found);
    if (Object.keys(found).length) return;
    const input: AvailabilityInput = {
      resource_id: values.resource_id,
      absence_type: values.absence_type,
      date_start: values.date_start,
      date_end: values.date_end,
      is_known_at_planning: values.is_known_at_planning,
      ...(isNew && values.availability_id ? { availability_id: values.availability_id } : {}),
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

  const rangeReady = isValidIso(values.date_start) && isValidIso(values.date_end) && values.date_end >= values.date_start;
  const field = (key: keyof Values) => ({
    id: `availability-${key}`,
    'aria-invalid': errors[key] ? true : undefined,
    'aria-describedby': errors[key] ? `availability-${key}-error` : undefined,
  });
  const message = (key: keyof Values) => errors[key] && <span className="field-error" id={`availability-${key}-error`}>{errors[key]}</span>;

  return (
    <dialog ref={dialog} className="dialog" aria-labelledby="availability-form-title" onCancel={(event) => { event.preventDefault(); if (!saving) onClose(); }}>
      <form onSubmit={submit} noValidate>
        <div className="dialog-heading">
          <h2 id="availability-form-title">{isNew ? 'Catat ketidakhadiran' : `Ubah ${availability.availability_id}`}</h2>
        </div>
        <div className="dialog-body form-grid">
          {errors.form && <p className="form-alert" role="alert">{errors.form}</p>}

          <div className="field-row">
            <label className="field" htmlFor="availability-resource_id">
              <span>Anggota</span>
              <select {...field('resource_id')} value={values.resource_id} onChange={(e) => set('resource_id', e.target.value)}>
                <option value="" disabled>Pilih anggota</option>
                {resources.map((r) => <option key={r.resource_id} value={r.resource_id}>{r.resource_name} ({r.resource_id})</option>)}
              </select>
              {message('resource_id')}
            </label>
            <label className="field" htmlFor="availability-absence_type">
              <span>Jenis</span>
              <select {...field('absence_type')} value={values.absence_type} onChange={(e) => set('absence_type', e.target.value as AbsenceType)}>
                {ABSENCE_TYPES.map((type) => <option key={type} value={type}>{ABSENCE_LABEL[type]}</option>)}
              </select>
              {values.absence_type === 'rotation_in' && <span className="field-hint">Anggota hadir dari tim lain, tidak dihitung sebagai ketidakhadiran</span>}
            </label>
          </div>

          <div className="field-row">
            <label className="field" htmlFor="availability-date_start">
              <span>Tanggal mulai</span>
              <input {...field('date_start')} type="date" value={values.date_start} onChange={(e) => set('date_start', e.target.value)} />
              {message('date_start')}
            </label>
            <label className="field" htmlFor="availability-date_end">
              <span>Tanggal akhir</span>
              <input {...field('date_end')} type="date" value={values.date_end} min={values.date_start || undefined} onChange={(e) => set('date_end', e.target.value)} />
              {message('date_end')}
            </label>
            {isNew && <label className="field" htmlFor="availability-availability_id">
              <span>ID <small>opsional</small></span>
              <input {...field('availability_id')} value={values.availability_id} placeholder="Otomatis" onChange={(e) => set('availability_id', e.target.value.toUpperCase())} />
              {message('availability_id')}
            </label>}
          </div>

          {rangeReady && (
            <p className="form-preview" role="status">
              {calendarDays(values.date_start, values.date_end)} hari kalender, <strong>{countWorkingDays(values.date_start, values.date_end, holidays)} hari kerja</strong> (tanpa Sabtu, Minggu, dan hari libur)
            </p>
          )}

          <label className="checkbox" htmlFor="availability-is_known_at_planning">
            <input id="availability-is_known_at_planning" type="checkbox" checked={values.is_known_at_planning} onChange={(e) => set('is_known_at_planning', e.target.checked)} />
            <span>Sudah diketahui saat sprint planning</span>
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
