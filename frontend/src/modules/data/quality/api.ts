import { apiGet } from '../../../shared/api/client';
import { rejectedRowsPath, summaryPath, type RejectedFilters } from './rules';

/**
 * Laporan kualitas data per impor (DIG-147). Kontrak respons mengikuti backend DIG-146
 * (`GET /data/quality/summary` dan `GET /data/quality/rejected-rows`), izin `data_quality:read`.
 */
export type Source = 'project_plan' | 'trello' | 'teamgit';
export type Level = 'tolak' | 'peringatan';
export type Characteristic = 'completeness' | 'consistency' | 'currentness' | 'traceability';

export type CharacteristicScore = {
  characteristic: Characteristic;
  label: string;
  checked: number;
  violated: number;
  pass_rate: number | null;
};

export type RuleResult = {
  rule_id: string;
  table: string;
  characteristic: Characteristic;
  level: Level;
  text: string;
  checked: number;
  violated: number;
};

export type QualitySummary = {
  job_id: number | null;
  source: Source;
  file_name: string | null;
  project_id: string | null;
  validated_at: string | null;
  rows_checked: number;
  rows_rejected: number;
  rows_with_warning: number;
  pass_rate: number | null;
  characteristics: CharacteristicScore[];
  rules: RuleResult[];
};

export type RowFinding = {
  rule_id: string;
  characteristic: Characteristic;
  level: Level;
  column: string | null;
  value: string | null;
  message: string;
};

export type RejectedItem = {
  source: Source;
  table: string;
  row_number: number | null;
  row_key: string | null;
  level: Level;
  findings: RowFinding[];
};

export type RejectedPage = {
  job_id: number;
  total: number;
  page: number;
  page_size: number;
  items: RejectedItem[];
};

export const getQualitySummary = (source: Source, signal?: AbortSignal) =>
  apiGet<QualitySummary>(summaryPath(source), signal);

export const getRejectedRows = (jobId: number, filters: RejectedFilters, page: number, pageSize: number, signal?: AbortSignal) =>
  apiGet<RejectedPage>(rejectedRowsPath(jobId, filters, page, pageSize), signal);
