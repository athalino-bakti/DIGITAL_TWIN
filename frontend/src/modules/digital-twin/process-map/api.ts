import { apiGet } from '../../../shared/api/client';

/** Respons GET /digital-twin/process-map (DIG-169). */
export type ProcessNode = { id: string; label: string; frequency: number; cases: number; start_cases: number; end_cases: number };
export type ProcessEdge = { source: string; target: string; frequency: number; cases: number; mean_hours: number; median_hours: number };
export type ActivityCount = { activity: string; cases: number };

export type ProcessMap = {
  project_id: string | null;
  date_from: string | null;
  date_to: string | null;
  activity_kinds: string[];
  min_frequency: number;
  event_log_events: number;
  cases: number;
  events: number;
  max_edge_frequency: number;
  nodes: ProcessNode[];
  edges: ProcessEdge[];
  start_activities: ActivityCount[];
  end_activities: ActivityCount[];
  hidden: { edges: number; nodes: number; edge_frequency: number };
};

/** Alur status selalu ikut; dua jenis ini bisa ditambahkan dari filter. */
export const BASE_KINDS = ['created', 'status', 'archived', 'deleted'] as const;
export const EXTRA_KINDS = [
  { kind: 'assignment', label: 'Penugasan anggota' },
  { kind: 'change_event', label: 'Kejadian perubahan (D-10)' },
] as const;

export type ProcessMapQuery = { project_id?: string; date_from?: string; date_to?: string; extra_kinds: string[]; min_frequency: number };

export function processMapSearch(query: ProcessMapQuery): string {
  const search = new URLSearchParams();
  if (query.project_id) search.set('project_id', query.project_id);
  if (query.date_from) search.set('date_from', query.date_from);
  if (query.date_to) search.set('date_to', query.date_to);
  for (const kind of [...BASE_KINDS, ...query.extra_kinds]) search.append('activity_kinds', kind);
  search.set('min_frequency', String(query.min_frequency));
  return search.toString();
}

export const getProcessMap = (query: ProcessMapQuery, signal?: AbortSignal) =>
  apiGet<ProcessMap>(`/digital-twin/process-map?${processMapSearch(query)}`, signal);
