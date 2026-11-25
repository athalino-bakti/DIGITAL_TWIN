import { apiGet } from '../../../shared/api/client';

/** Respons GET /digital-twin/workload-heatmap (DIG-188). Formula RLI masih provisional. */
export type HeatmapWeek = {
  week_start: string;
  week_end: string;
  working_days: number;
  holidays: string[];
};

export type HeatmapCategory = {
  code: string;
  label: string;
  min: number | null;
  max: number | null;
  overload: boolean;
};

export type HeatmapSummary = {
  week_start: string;
  overloaded: number;
  resources: number;
};

export type HeatmapCell = {
  week_start: string;
  rli: number | null;
  category: string;
  project_load: number;
  non_project_load: number;
  capacity: number;
  available_days: number;
  onboarding_factor: number;
  tasks: number;
  workload_items: number;
};

export type HeatmapRow = {
  resource_id: string;
  resource_name: string;
  primary_role_id: string;
  capacity_reference: number;
  is_onboarding: boolean;
  cells: HeatmapCell[];
};

export type WorkloadHeatmap = {
  as_of: string;
  formula_version: string;
  provisional: boolean;
  weeks: HeatmapWeek[];
  categories: HeatmapCategory[];
  summary: HeatmapSummary;
  rows: HeatmapRow[];
};

export type HeatmapParams = {
  weeks?: number;
  role_id?: string;
  project_id?: string;
  resource_id?: string;
};

export function getWorkloadHeatmap(params: HeatmapParams, signal?: AbortSignal) {
  const search = new URLSearchParams();
  if (params.weeks) search.set('weeks', String(params.weeks));
  if (params.role_id) search.set('role_id', params.role_id);
  if (params.project_id) search.set('project_id', params.project_id);
  if (params.resource_id) search.set('resource_id', params.resource_id);
  const text = search.toString();
  return apiGet<WorkloadHeatmap>(`/digital-twin/workload-heatmap${text ? `?${text}` : ''}`, signal);
}
