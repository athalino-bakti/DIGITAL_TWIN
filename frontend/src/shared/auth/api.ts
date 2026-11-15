import { apiGet, apiPost } from '../api/client';

/** Sama dengan UserRead di backend/app/modules/auth/schemas.py. */
export type AuthUser = {
  user_id: number;
  username: string;
  full_name: string;
  resource_id: string | null;
  last_login_at: string | null;
  /** Kode peran aplikasi (RBAC). */
  roles: string[];
  /** Gabungan izin dari semua peran, untuk menyaring menu dan tombol. */
  permissions: string[];
};

type TokenResponse = {
  access_token: string;
  token_type: 'bearer';
  expires_in: number;
  user: AuthUser;
};

export const login = (username: string, password: string) => apiPost<TokenResponse>('/auth/login', { username, password }, { auth: false });
export const fetchMe = (signal?: AbortSignal) => apiGet<AuthUser>('/auth/me', signal);
