import type { Decision, EventType, ResolutionMode } from './api';

/**
 * Aturan form kejadian perubahan, sama dengan validator backend (DIG-149, DIG-150), supaya
 * kesalahan terlihat sebelum dikirim. Backend tetap pemeriksa terakhir.
 */
export type ChangeValues = {
  event_id: string;
  project_id: string;
  event_type: EventType;
  event_date: string;
  requested_by: string;
  decision: Decision | '';
  resolution_mode: ResolutionMode | '';
  affected_task_id: string;
  extension_days: string;
  effect_status: '' | 'on_hold' | 'dropped';
  effect_priority: string;
};

export type ChangeErrors = Partial<Record<keyof ChangeValues | 'form', string>>;

export const EVENT_ID = /^EVT-[0-9]{3,}$/;
export const TASK_ID = /^TSK-[0-9]{4,}$/;
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

/** Efek ke task hanya untuk CR yang diterima sekarang dengan mode tukar task atau atur ulang prioritas. */
export function effectAllowed(values: Pick<ChangeValues, 'decision' | 'resolution_mode' | 'affected_task_id'>): boolean {
  return values.decision === 'accept_now' && (values.resolution_mode === 'swap_task' || values.resolution_mode === 'reshuffle') && values.affected_task_id.trim() !== '';
}

export function needsExtension(mode: ResolutionMode | ''): boolean {
  return mode === 'extend_duration';
}

/** Nilai yang tidak lagi relevan dibersihkan, misalnya tambahan hari saat mode diganti. */
export function normalize(values: ChangeValues): ChangeValues {
  const next = { ...values };
  if (!next.decision) next.resolution_mode = '';
  if (!needsExtension(next.resolution_mode)) next.extension_days = '';
  if (!effectAllowed(next)) { next.effect_status = ''; next.effect_priority = ''; }
  return next;
}

export function validate(values: ChangeValues, isNew: boolean, projectStart?: string): ChangeErrors {
  const errors: ChangeErrors = {};
  if (isNew && values.event_id && !EVENT_ID.test(values.event_id)) errors.event_id = 'Format EVT-001';
  if (!values.project_id) errors.project_id = 'Pilih proyek';
  if (!ISO_DATE.test(values.event_date)) errors.event_date = 'Isi tanggal kejadian';
  else if (projectStart && values.event_date < projectStart) errors.event_date = `Tidak boleh sebelum proyek dimulai (${projectStart})`;
  if (values.requested_by.length > 100) errors.requested_by = 'Maksimal 100 karakter';
  const task = values.affected_task_id.trim();
  if (task && !TASK_ID.test(task)) errors.affected_task_id = 'Format TSK-0001';
  if (values.resolution_mode && !values.decision) errors.decision = 'Isi keputusan bila mode resolusi diisi';
  if (needsExtension(values.resolution_mode)) {
    const days = Number(values.extension_days.replace(',', '.'));
    if (!values.extension_days.trim() || !Number.isFinite(days) || days <= 0) errors.extension_days = 'Isi tambahan hari, lebih dari 0';
    else if (days > 365) errors.extension_days = 'Maksimal 365 hari';
  }
  if (isNew && effectAllowed(values)) {
    if (values.effect_priority.trim()) {
      const rank = Number(values.effect_priority);
      if (!Number.isInteger(rank) || rank < 1 || rank > 999) errors.effect_priority = 'Bilangan bulat 1 sampai 999';
    }
  }
  return errors;
}

export function toDays(text: string): number | null {
  if (!text.trim()) return null;
  return Number(text.replace(',', '.'));
}
