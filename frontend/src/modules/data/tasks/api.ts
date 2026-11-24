import { apiGet, apiPatch } from '../../../shared/api/client';

export const TASK_STATUSES = ['not_started', 'in_progress', 'blocked', 'on_hold', 'in_qa', 'done', 'dropped'] as const;
export type TaskStatus = (typeof TASK_STATUSES)[number];

export const TASK_STATUS_LABEL: Record<TaskStatus, string> = {
  not_started: 'Belum dimulai',
  in_progress: 'Dikerjakan',
  blocked: 'Terhambat',
  on_hold: 'Ditunda',
  in_qa: 'Dalam QA',
  done: 'Selesai',
  dropped: 'Dibatalkan',
};

/** D-05 tasks, ditambah nama proyek dari server (DIG-161). */
export type Task = {
  task_id: string;
  project_id: string;
  project_name: string;
  feature_name: string;
  task_name: string;
  required_role_id: string;
  complexity_id: string;
  priority_rank: number;
  estimated_days: number;
  phase: string;
  planned_start: string;
  planned_finish: string;
  actual_start: string | null;
  actual_finish: string | null;
  status: TaskStatus;
  qa_reject_count: number;
  dod_fulfilled: boolean;
};

export type TaskStatusInput = Partial<Pick<Task, 'status' | 'actual_start' | 'actual_finish' | 'dod_fulfilled'>>;

type TaskQuery = { project_id?: string; status?: TaskStatus[] };

export function listTasks(params: TaskQuery, signal?: AbortSignal) {
  const search = new URLSearchParams();
  if (params.project_id) search.set('project_id', params.project_id);
  for (const status of params.status ?? []) search.append('status', status);
  const text = search.toString();
  return apiGet<Task[]>(`/data/tasks${text ? `?${text}` : ''}`, signal);
}

export const updateTaskStatus = (taskId: string, input: TaskStatusInput) => apiPatch<Task>(`/data/tasks/${taskId}/status`, input);
