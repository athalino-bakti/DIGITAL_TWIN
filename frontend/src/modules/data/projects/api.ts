import { apiDelete, apiGet, apiPatch, apiPost } from '../../../shared/api/client';

export const PROJECT_STATUSES = ['planning', 'development', 'testing', 'released', 'on_hold'] as const;
export type ProjectStatus = (typeof PROJECT_STATUSES)[number];

export const STATUS_LABEL: Record<ProjectStatus, string> = {
  planning: 'Perencanaan',
  development: 'Pengembangan',
  testing: 'Pengujian',
  released: 'Rilis',
  on_hold: 'Ditunda',
};

/** D-01 projects, ditambah penanda hitungan server. */
export type Project = {
  project_id: string;
  project_name: string;
  process_owner: string;
  priority_rank: number;
  start_date: string;
  target_launch_date: string;
  actual_launch_date: string | null;
  status: ProjectStatus;
  dor_fulfilled: boolean;
  is_active: boolean;
  is_overdue: boolean;
};

export type ProjectInput = Omit<Project, 'project_id' | 'is_active' | 'is_overdue'> & { project_id?: string };

const BASE = '/data/projects';

export const listProjects = (signal?: AbortSignal) => apiGet<Project[]>(BASE, signal);
export const createProject = (input: ProjectInput) => apiPost<Project>(BASE, input);
export const updateProject = (id: string, input: Partial<ProjectInput>) => apiPatch<Project>(`${BASE}/${id}`, input);
export const deleteProject = (id: string) => apiDelete(`${BASE}/${id}`);
