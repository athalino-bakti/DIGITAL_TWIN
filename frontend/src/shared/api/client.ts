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

function toIssues(detail: unknown): ApiIssue[] {
  const items: unknown[] = Array.isArray(detail) ? detail : detail === undefined ? [] : [detail];
  return items.map((item) => {
    if (typeof item === 'string') return { field: null, message: item };
    const { loc, msg } = item as DetailItem;
    const last = loc?.[loc.length - 1];
    return { field: loc && loc[0] === 'body' && typeof last === 'string' ? last : null, message: (msg ?? 'Permintaan ditolak').replace(/^Value error, /, '') };
  });
}

async function request<T>(method: string, path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method,
    signal,
    headers: { Accept: 'application/json', ...(body === undefined ? {} : { 'Content-Type': 'application/json' }) },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => undefined) as { detail?: unknown } | undefined;
    throw new ApiError(response.status, toIssues(payload?.detail));
  }
  return (response.status === 204 ? undefined : await response.json()) as T;
}

export function apiGet<T>(path: string, signal?: AbortSignal): Promise<T> {
  return request<T>('GET', path, undefined, signal);
}

export function apiPost<T>(path: string, body: unknown): Promise<T> {
  return request<T>('POST', path, body);
}

export function apiPatch<T>(path: string, body: unknown): Promise<T> {
  return request<T>('PATCH', path, body);
}

export function apiDelete(path: string): Promise<void> {
  return request<void>('DELETE', path);
}
