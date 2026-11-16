import { apiDelete, apiGet, apiPatch, apiPost } from '../../../shared/api/client';

/** D-10 change_events (DIG-149, DIG-150). */
export const EVENT_TYPES = ['change_request', 'priority_change', 'blocker', 'overrun', 'hotfix'] as const;
export const DECISIONS = ['accept_now', 'defer_next', 'reject'] as const;
export const RESOLUTION_MODES = ['swap_task', 'extend_duration', 'scope_addition', 'reshuffle'] as const;

export type EventType = (typeof EVENT_TYPES)[number];
export type Decision = (typeof DECISIONS)[number];
export type ResolutionMode = (typeof RESOLUTION_MODES)[number];

export const EVENT_LABEL: Record<EventType, string> = {
  change_request: 'Change request',
  priority_change: 'Perubahan prioritas',
  blocker: 'Blocker',
  overrun: 'Overrun',
  hotfix: 'Hotfix',
};

export const DECISION_LABEL: Record<Decision, string> = {
  accept_now: 'Diterima sekarang',
  defer_next: 'Ditunda ke iterasi berikutnya',
  reject: 'Ditolak',
};

export const MODE_LABEL: Record<ResolutionMode, string> = {
  swap_task: 'Tukar task',
  extend_duration: 'Perpanjang durasi',
  scope_addition: 'Tambah lingkup',
  reshuffle: 'Atur ulang prioritas',
};

export const TASK_STATUS_LABEL: Record<string, string> = {
  not_started: 'Belum dimulai',
  in_progress: 'Dikerjakan',
  blocked: 'Terhambat',
  on_hold: 'Ditunda',
  in_qa: 'Dalam QA',
  done: 'Selesai',
  dropped: 'Dibatalkan',
};

/** Isian requested_by yang muncul di dataset dosbim; kolomnya tetap teks bebas. */
export const REQUESTERS = ['Kaur', 'Asisten Manajer', 'System Analyst', 'Pemilik proses'] as const;

export type ChangeEvent = {
  event_id: string;
  project_id: string;
  project_name: string;
  event_type: EventType;
  event_date: string;
  requested_by: string | null;
  decision: Decision | null;
  resolution_mode: ResolutionMode | null;
  affected_task_id: string | null;
  affected_task_name: string | null;
  affected_task_status: string | null;
  affected_task_priority_rank: number | null;
  extension_days: number | null;
};

export type TaskEffect = { status?: 'on_hold' | 'dropped' | null; priority_rank?: number | null };

export type ChangeEventInput = {
  project_id: string;
  event_type: EventType;
  event_date: string;
  requested_by: string | null;
  decision: Decision | null;
  resolution_mode: ResolutionMode | null;
  affected_task_id: string | null;
  extension_days: number | null;
};

export type ChangeEventCreate = ChangeEventInput & { event_id?: string; task_effect?: TaskEffect };

export type ChangeEventFilters = { project_id?: string; event_type?: EventType[]; affected_task_id?: string; date_from?: string; date_to?: string };

const BASE = '/data/change-events';

export function changeEventSearch(filters: ChangeEventFilters): string {
  const search = new URLSearchParams();
  if (filters.project_id) search.set('project_id', filters.project_id);
  for (const type of filters.event_type ?? []) search.append('event_type', type);
  if (filters.affected_task_id) search.set('affected_task_id', filters.affected_task_id);
  if (filters.date_from) search.set('date_from', filters.date_from);
  if (filters.date_to) search.set('date_to', filters.date_to);
  const text = search.toString();
  return text ? `?${text}` : '';
}

export const listChangeEvents = (filters: ChangeEventFilters, signal?: AbortSignal) => apiGet<ChangeEvent[]>(`${BASE}${changeEventSearch(filters)}`, signal);
export const createChangeEvent = (input: ChangeEventCreate) => apiPost<ChangeEvent>(BASE, input);
export const updateChangeEvent = (id: string, input: Partial<ChangeEventInput>) => apiPatch<ChangeEvent>(`${BASE}/${id}`, input);
export const deleteChangeEvent = (id: string) => apiDelete(`${BASE}/${id}`);
