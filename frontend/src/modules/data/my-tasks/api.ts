import { apiGet, apiPost } from '../../../shared/api/client';

/** Respons GET /data/my-tasks (DIG-153). */
export type MyTaskEvent = { event_id: string; event_type: EventKind; event_date: string; requested_by: string | null };

export type MyTask = {
  task_id: string;
  task_name: string;
  feature_name: string;
  project_id: string;
  project_name: string;
  phase: string;
  status: string;
  priority_rank: number;
  planned_start: string;
  planned_finish: string;
  actual_start: string | null;
  role_in_task: string;
  assigned_date: string;
  is_past_plan: boolean;
  open_blocker: MyTaskEvent | null;
  open_overrun: MyTaskEvent | null;
};

export type MyTasks = { resource_id: string | null; resource_name: string | null; as_of: string; tasks: MyTask[] };

export type EventKind = 'blocker' | 'overrun';

export type MyTaskEventResult = {
  event_id: string;
  event_type: EventKind;
  event_date: string;
  resolved_date: string | null;
  task_id: string;
  task_status: string;
  task_status_changed: boolean;
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

const BASE = '/data/my-tasks';

export const listMyTasks = (signal?: AbortSignal) => apiGet<MyTasks>(BASE, signal);

export const recordMyTaskEvent = (taskId: string, kind: EventKind, eventDate: string) =>
  apiPost<MyTaskEventResult>(`${BASE}/${taskId}/events`, { event_type: kind, event_date: eventDate });

export const resolveMyTaskEvent = (taskId: string, eventId: string, resolvedDate: string) =>
  apiPost<MyTaskEventResult>(`${BASE}/${taskId}/events/${eventId}/resolve`, { resolved_date: resolvedDate });
