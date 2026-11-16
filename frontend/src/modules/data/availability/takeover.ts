import { apiGet, apiPost } from '../../../shared/api/client';

/** Task yang dipegang anggota selama ketidakhadirannya (DIG-157). */
export type AffectedTask = {
  task_id: string;
  task_name: string;
  project_id: string;
  project_name: string;
  status: string;
  required_role_id: string;
  planned_start: string;
  planned_finish: string;
  assignment_id: string;
  assigned_date: string;
};

export type RoleMatch = 'primary' | 'secondary' | 'cross';

export const MATCH_LABEL: Record<RoleMatch, string> = {
  primary: 'Peran utama sama',
  secondary: 'Peran rangkap',
  cross: 'Lintas peran',
};

/** Kandidat pengganti untuk sebuah task (DIG-159). */
export type Candidate = {
  resource_id: string;
  resource_name: string;
  primary_role_id: string;
  seniority: string;
  match: RoleMatch;
  active_assignments: number;
};

type AssignmentRead = { assignment_id: string; resource_id: string; resource_name: string; assigned_date: string; released_date: string | null };
export type TakeoverResult = { released: AssignmentRead; created: AssignmentRead };
export type TakeoverInput = { from_resource_id: string; to_resource_id: string; takeover_date: string };

export const listAffectedTasks = (availabilityId: string, signal?: AbortSignal) =>
  apiGet<AffectedTask[]>(`/data/availability/${availabilityId}/affected-tasks`, signal);
export const listCandidates = (taskId: string, on: string, signal?: AbortSignal) =>
  apiGet<Candidate[]>(`/data/tasks/${taskId}/replacement-candidates?on=${on}`, signal);
export const takeOver = (taskId: string, input: TakeoverInput) => apiPost<TakeoverResult>(`/data/tasks/${taskId}/takeover`, input);
