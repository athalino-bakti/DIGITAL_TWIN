import { apiDelete, apiGet, apiPatch, apiPost } from '../../../shared/api/client';

export const ITEM_TYPES = ['ticket', 'operational'] as const;
export type ItemType = (typeof ITEM_TYPES)[number];
export const ITEM_TYPE_LABEL: Record<ItemType, string> = { ticket: 'Tiket', operational: 'Operasional' };

export const SEVERITIES = ['critical', 'high', 'medium', 'low'] as const;
export type Severity = (typeof SEVERITIES)[number];
export const SEVERITY_LABEL: Record<Severity, string> = { critical: 'Kritis', high: 'Tinggi', medium: 'Sedang', low: 'Rendah' };

export type WorkloadStatus = 'waiting' | 'in_progress' | 'resolved';
export const STATUS_LABEL: Record<WorkloadStatus, string> = { waiting: 'Menunggu', in_progress: 'Dikerjakan', resolved: 'Selesai' };

/** D-08 workload_items, ditambah nama anggota, nama proyek, dan status turunan dari server. */
export type WorkloadItem = {
  item_id: string;
  resource_id: string;
  resource_name: string;
  item_type: ItemType;
  related_project_id: string | null;
  project_name: string | null;
  received_date: string;
  started_date: string | null;
  resolved_date: string | null;
  severity: Severity | null;
  is_hotfix: boolean;
  status: WorkloadStatus;
};

export type WorkloadInput = Omit<WorkloadItem, 'item_id' | 'resource_name' | 'project_name' | 'status'> & { item_id?: string };

export type ImportRowError = { row: number; item_id: string | null; field: string | null; message: string };
export type ImportResult = {
  dry_run: boolean;
  applied: boolean;
  total: number;
  inserted: number;
  updated: number;
  error_count: number;
  errors: ImportRowError[];
};

type Filters = { resource_id?: string; item_type?: ItemType | ''; open_only?: boolean };

function query(filters: Filters): string {
  const search = new URLSearchParams();
  if (filters.resource_id) search.set('resource_id', filters.resource_id);
  if (filters.item_type) search.set('item_type', filters.item_type);
  if (filters.open_only) search.set('open_only', 'true');
  const text = search.toString();
  return text ? `?${text}` : '';
}

const BASE = '/data/workload-items';
export const listWorkload = (filters: Filters, signal?: AbortSignal) => apiGet<WorkloadItem[]>(`${BASE}${query(filters)}`, signal);
export const createWorkload = (input: WorkloadInput) => apiPost<WorkloadItem>(BASE, input);
export const updateWorkload = (id: string, input: Partial<WorkloadInput>) => apiPatch<WorkloadItem>(`${BASE}/${id}`, input);
export const deleteWorkload = (id: string) => apiDelete(`${BASE}/${id}`);
/** Berkas CSV dikirim sebagai teks di body JSON, sehingga tidak perlu multipart. */
export const importWorkload = (content: string, dryRun: boolean) => apiPost<ImportResult>(`${BASE}/import`, { content, dry_run: dryRun });
