import { apiGet, apiPatch } from '../../../shared/api/client';

/** D-04 complexity_levels, ditambah jumlah task yang memakai level ini. */
export type ComplexityLevel = {
  complexity_id: string;
  complexity_name: string;
  min_days: number;
  max_days: number;
  load_weight: number;
  task_count: number;
};

export type ComplexityInput = Pick<ComplexityLevel, 'min_days' | 'max_days' | 'load_weight'>;

const BASE = '/data/complexity-levels';

export const listComplexityLevels = (signal?: AbortSignal) => apiGet<ComplexityLevel[]>(BASE, signal);
export const updateComplexityLevel = (id: string, input: Partial<ComplexityInput>) => apiPatch<ComplexityLevel>(`${BASE}/${id}`, input);
