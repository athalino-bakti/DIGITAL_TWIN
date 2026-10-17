const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/$/, '');

export async function apiGet<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, { signal, headers: { Accept: 'application/json' } });
  if (!response.ok) throw new Error(`API mengembalikan status ${response.status}`);
  return response.json() as Promise<T>;
}

export async function apiPost<TResponse, TBody extends object>(
  path: string,
  body: TBody,
): Promise<TResponse> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(`API mengembalikan status ${response.status}`);
  return response.json() as Promise<TResponse>;
}

export async function apiUpload<TResponse>(path: string, file: File): Promise<TResponse> {
  const formData = new FormData();
  formData.append('file', file);
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: 'POST',
    body: formData,
    headers: { Accept: 'application/json' },
  });
  if (!response.ok) throw new Error(`API mengembalikan status ${response.status}`);
  return response.json() as Promise<TResponse>;
}
