import { apiDelete, apiGet, apiPatch, apiPost } from '../../../shared/api/client';

/** Tabel internal J&C resource_alias (DIG-110, DIG-111). Hanya Administrator Data. */
export const IDENTITY_SOURCES = ['trello', 'teamgit', 'project_plan'] as const;
export type IdentitySource = (typeof IDENTITY_SOURCES)[number];

export const SOURCE_LABEL: Record<IdentitySource, string> = {
  trello: 'Trello',
  teamgit: 'TeamGit',
  project_plan: 'Project Plan',
};

/** Isi kolom alias per sumber, sama dengan docstring ResourceAliasCreate di backend. */
export const ALIAS_HINT: Record<IdentitySource, string> = {
  trello: 'Id member Trello, 24 karakter heksadesimal',
  teamgit: 'Email author commit',
  project_plan: 'Nama PIC persis seperti di Project Plan',
};

export type ResourceAlias = {
  alias_id: number;
  resource_id: string;
  source: IdentitySource;
  alias: string;
  alias_key: string;
  username: string | null;
  display_name: string | null;
  mapped_by_user_id: number | null;
  created_at: string;
  updated_at: string;
};

export type UnmappedIdentity = {
  source: IdentitySource;
  alias_key: string;
  alias: string;
  username: string | null;
  display_name: string | null;
  occurrences: number;
  last_seen: string;
};

export type AliasInput = {
  resource_id: string;
  source: IdentitySource;
  alias: string;
  username?: string | null;
  display_name?: string | null;
};

export const listAliases = (signal?: AbortSignal) => apiGet<ResourceAlias[]>('/data/resource-aliases', signal);
export const listUnmapped = (signal?: AbortSignal) => apiGet<UnmappedIdentity[]>('/data/resource-aliases/unmapped', signal);
export const createAlias = (input: AliasInput) => apiPost<ResourceAlias>('/data/resource-aliases', input);
export const updateAlias = (id: number, resource_id: string) => apiPatch<ResourceAlias>(`/data/resource-aliases/${id}`, { resource_id });
export const deleteAlias = (id: number) => apiDelete(`/data/resource-aliases/${id}`);
