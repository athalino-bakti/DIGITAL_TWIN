import { apiGet } from '../../../shared/api/client';

/** Respons GET /digital-twin/timeline (DIG-177). */
export type TimelineTask = {
  task_id: string;
  task_name: string;
  feature_name: string;
  required_role_id: string;
  status: string;
  planned_start: string;
  planned_finish: string;
  actual_start: string | null;
  actual_finish: string | null;
  is_late: boolean;
  delay_days: number;
  delay_working_days: number;
  assignees: string[];
};

export type TimelinePhase = { phase: string; tasks: TimelineTask[] };

export type TimelineProject = {
  project_id: string;
  project_name: string;
  priority_rank: number;
  status: string;
  start_date: string;
  target_launch_date: string;
  actual_launch_date: string | null;
  task_count: number;
  late_count: number;
  phases: TimelinePhase[];
};

export type TimelineEvent = { event_id: string; project_id: string; event_type: string; event_date: string; affected_task_id: string | null };
export type TimelineHoliday = { holiday_date: string; holiday_name: string };

export type Timeline = {
  as_of: string;
  range_start: string | null;
  range_end: string | null;
  projects: TimelineProject[];
  events: TimelineEvent[];
  holidays: TimelineHoliday[];
};

export const PHASE_LABEL: Record<string, string> = {
  planning: 'Perencanaan',
  uiux: 'UI/UX',
  dm_dev: 'Data model',
  be_dev: 'Backend',
  fe_dev: 'Frontend',
  testing: 'Pengujian',
  bugfix: 'Perbaikan bug',
  documentation: 'Dokumentasi',
};

export const EVENT_LABEL: Record<string, string> = {
  change_request: 'Change request',
  priority_change: 'Perubahan prioritas',
  blocker: 'Blocker',
  overrun: 'Overrun',
  hotfix: 'Hotfix',
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

export function getTimeline(params: { project_id?: string; resource_id?: string }, signal?: AbortSignal) {
  const search = new URLSearchParams();
  if (params.project_id) search.set('project_id', params.project_id);
  if (params.resource_id) search.set('resource_id', params.resource_id);
  const text = search.toString();
  return apiGet<Timeline>(`/digital-twin/timeline${text ? `?${text}` : ''}`, signal);
}
