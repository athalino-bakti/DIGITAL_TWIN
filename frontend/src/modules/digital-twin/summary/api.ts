import { apiGet } from '../../../shared/api/client';
import type { ProjectStatus } from '../../data/projects/api';

/** Respons GET /digital-twin/summary (DIG-175). */
export type ActiveProject = { project_id: string; project_name: string; status: ProjectStatus; priority_rank: number; target_launch_date: string };
export type LateProject = ActiveProject & { projected_finish: string; days_late: number; open_tasks: number; late_open_tasks: number };
export type MultiRoleResource = { resource_id: string; resource_name: string; primary_role_id: string; secondary_role_ids: string[]; other_active_roles: string[] };

export type BaselineSummary = {
  as_of: string;
  active_projects: { count: number; items: ActiveProject[] };
  late_projects: { count: number; items: LateProject[] };
  overloaded_resources: { count: null; reason: string };
  multi_role_resources: { count: number; items: MultiRoleResource[] };
};

export const getSummary = (signal?: AbortSignal) => apiGet<BaselineSummary>('/digital-twin/summary', signal);
