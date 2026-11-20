import { apiGet } from '../../../shared/api/client';

/** Respons GET /digital-twin/dependency (DIG-182). */
export type DependencyNode = {
  task_id: string;
  task_name: string;
  feature_name: string;
  phase: string;
  status: string;
  estimated_days: number;
  planned_start: string;
  planned_finish: string;
  earliest_start: number;
  earliest_finish: number;
  latest_start: number;
  latest_finish: number;
  total_float: number;
  is_critical: boolean;
  is_late: boolean;
  delay_working_days: number;
  impact_days: number | null;
};

export type DependencyEdge = {
  dependency_id: string;
  depends_on_task_id: string;
  task_id: string;
  dependency_type: 'hard' | 'soft';
  propagation_factor: number;
  is_critical: boolean;
};

export type DependencyFocus = { task_id: string; delay_days: number; affected_count: number };

export type DependencyGraph = {
  project_id: string;
  project_name: string;
  as_of: string;
  project_duration: number;
  critical_task_ids: string[];
  cycle_task_ids: string[];
  focus: DependencyFocus | null;
  nodes: DependencyNode[];
  edges: DependencyEdge[];
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

export type DependencyQuery = { project_id: string; task_id?: string; delay_days?: number };

export function getDependencyGraph(query: DependencyQuery, signal?: AbortSignal) {
  const search = new URLSearchParams({ project_id: query.project_id });
  if (query.task_id) search.set('task_id', query.task_id);
  if (query.task_id && query.delay_days !== undefined) search.set('delay_days', String(query.delay_days));
  return apiGet<DependencyGraph>(`/digital-twin/dependency?${search}`, signal);
}
