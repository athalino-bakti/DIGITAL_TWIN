import { clearSession, getAccessToken } from '../auth/session';

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/$/, '');

/** Satu pesan dari `detail` FastAPI. `field` terisi bila pesan milik kolom tertentu. */
export type ApiIssue = { field: string | null; message: string };

export class ApiError extends Error {
  readonly status: number;
  readonly issues: ApiIssue[];

  constructor(status: number, issues: ApiIssue[]) {
    super(issues[0]?.message ?? `API mengembalikan status ${status}`);
    this.status = status;
    this.issues = issues;
  }

  /** Pesan per kolom, untuk ditampilkan di bawah input form. */
  fieldErrors(): Record<string, string> {
    const result: Record<string, string> = {};
    for (const issue of this.issues) if (issue.field && !result[issue.field]) result[issue.field] = issue.message;
    return result;
  }
}

type DetailItem = { loc?: (string | number)[]; msg?: string };

// Pesan bawaan Pydantic yang bisa lolos ke UI, dipetakan ke Bahasa Indonesia.
const PYDANTIC_MESSAGES: [RegExp, (match: RegExpMatchArray) => string][] = [
  [/^Field required$/, () => 'Wajib diisi'],
  [/^String should have at most (\d+) characters?$/, (m) => `Maksimal ${m[1]} karakter`],
  [/^String should have at least (\d+) characters?$/, (m) => `Minimal ${m[1]} karakter`],
  [/^Input should be a valid string$/, () => 'Harus berupa teks'],
];

function translate(message: string): string {
  for (const [pattern, toIndonesian] of PYDANTIC_MESSAGES) {
    const match = message.match(pattern);
    if (match) return toIndonesian(match);
  }
  return message;
}

function toIssues(detail: unknown): ApiIssue[] {
  const items: unknown[] = Array.isArray(detail) ? detail : detail === undefined ? [] : [detail];
  return items.map((item) => {
    if (typeof item === 'string') return { field: null, message: item };
    const { loc, msg } = item as DetailItem;
    const last = loc?.[loc.length - 1];
    return { field: loc && loc[0] === 'body' && typeof last === 'string' ? last : null, message: translate((msg ?? 'Permintaan ditolak').replace(/^Value error, /, '')) };
  });
}

/** Status dari proxy atau gateway saat backend tidak bisa dihubungi. */
const UNREACHABLE_STATUSES = new Set([502, 503, 504]);

/**
 * True bila API tidak bisa dihubungi: fetch gagal di jaringan, gateway membalas 502/503/504,
 * atau 500 tanpa `detail` JSON (proxy Vite saat backend mati). Error dari FastAPI selalu
 * membawa `detail`, jadi tidak ikut terhitung.
 */
export function isApiUnreachable(error: unknown): boolean {
  if (error instanceof ApiError) return UNREACHABLE_STATUSES.has(error.status) || (error.status === 500 && error.issues.length === 0);
  return error instanceof TypeError;
}

type RequestOptions = { signal?: AbortSignal; auth?: boolean };

async function request<T>(method: string, path: string, body?: unknown, { signal, auth = true }: RequestOptions = {}): Promise<T> {
  // POST /auth/login tidak mengirim token lama, jadi 401 di sana tidak pernah menghapus sesi.
  const token = auth ? getAccessToken() : null;
  // FormData (unggah berkas) dikirim apa adanya; browser yang mengisi Content-Type multipart
  // beserta boundary-nya.
  const form = body instanceof FormData;
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method,
    signal,
    headers: {
      Accept: 'application/json',
      ...(body === undefined || form ? {} : { 'Content-Type': 'application/json' }),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: body === undefined ? undefined : form ? body : JSON.stringify(body),
  });
  // Token ditolak (kedaluwarsa, rusak, akun nonaktif): hapus sesi supaya diarahkan ke login.
  // 403 (login tapi tidak berizin) tidak menghapus sesi.
  if (response.status === 401 && token) clearSession();
  if (!response.ok) {
    const payload = await response.json().catch(() => undefined) as { detail?: unknown } | undefined;
    throw new ApiError(response.status, toIssues(payload?.detail));
  }
  return (response.status === 204 ? undefined : await response.json()) as T;
}

export function apiGet<T>(path: string, signal?: AbortSignal): Promise<T> {
  return request<T>('GET', path, undefined, { signal });
}

export function apiPost<T>(path: string, body: unknown, options?: { auth?: boolean }): Promise<T> {
  return request<T>('POST', path, body, options);
}

/** POST multipart/form-data, untuk endpoint yang menerima berkas (`UploadFile`). */
export function apiPostForm<T>(path: string, form: FormData, signal?: AbortSignal): Promise<T> {
  return request<T>('POST', path, form, { signal });
}

export function apiPatch<T>(path: string, body: unknown): Promise<T> {
  return request<T>('PATCH', path, body);
}

export function apiDelete(path: string): Promise<void> {
  return request<void>('DELETE', path);
}
