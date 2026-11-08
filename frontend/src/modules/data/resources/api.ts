import { apiDelete, apiGet, apiPatch, apiPost } from '../../../shared/api/client';

export const SENIORITIES = ['junior', 'mid', 'senior'] as const;
export type Seniority = (typeof SENIORITIES)[number];
export const SENIORITY_LABEL: Record<Seniority, string> = { junior: 'Junior', mid: 'Mid', senior: 'Senior' };

/** D-02 resources. secondary_role_ids dikirim sebagai array, disimpan berpemisah titik koma. */
export type Resource = {
  resource_id: string;
  resource_name: string;
  primary_role_id: string;
  secondary_role_ids: string[];
  cross_role_capable: boolean;
  join_date: string;
  seniority: Seniority;
  tenure_days: number;
  is_onboarding: boolean;
};

export type ResourceInput = Omit<Resource, 'resource_id' | 'tenure_days' | 'is_onboarding'> & { resource_id?: string };

/** D-03 roles, ditambah jumlah anggota yang memakainya sebagai peran utama. */
export type Role = {
  role_id: string;
  role_name: string;
  capacity_reference: number;
  description: string | null;
  resource_count: number;
};

export type RoleInput = Pick<Role, 'capacity_reference' | 'description'>;

export const listResources = (signal?: AbortSignal) => apiGet<Resource[]>('/data/resources', signal);
export const createResource = (input: ResourceInput) => apiPost<Resource>('/data/resources', input);
export const updateResource = (id: string, input: Partial<ResourceInput>) => apiPatch<Resource>(`/data/resources/${id}`, input);
export const deleteResource = (id: string) => apiDelete(`/data/resources/${id}`);

export const listRoles = (signal?: AbortSignal) => apiGet<Role[]>('/data/roles', signal);
export const updateRole = (id: string, input: Partial<RoleInput>) => apiPatch<Role>(`/data/roles/${id}`, input);
