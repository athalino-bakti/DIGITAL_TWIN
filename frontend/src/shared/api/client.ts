const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/$/, '');

export async function apiGet<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, { signal, headers: { Accept: 'application/json' } });
  if (!response.ok) throw new Error(`API mengembalikan status ${response.status}`);
  return response.json() as Promise<T>;
}
