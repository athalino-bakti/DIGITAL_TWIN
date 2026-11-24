// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { saveSession } from '../auth/session';
import { ApiError, apiGet, apiPost, apiPostForm, isApiUnreachable } from './client';

function respond(status: number, body?: unknown) {
  const fetchMock = vi.fn(async () => new Response(body === undefined ? null : JSON.stringify(body), { status }));
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

const headersOf = (fetchMock: ReturnType<typeof respond>) =>
  (fetchMock.mock.calls[0] as unknown as [string, RequestInit])[1].headers as Record<string, string>;

describe('client API', () => {
  beforeEach(() => localStorage.clear());
  afterEach(() => vi.unstubAllGlobals());

  it('mengirim token Bearer bila ada sesi', async () => {
    saveSession('abc', 3600);
    const fetchMock = respond(200, { ok: true });
    await apiGet('/auth/me');
    expect(headersOf(fetchMock).Authorization).toBe('Bearer abc');
  });

  it('login tidak mengirim token lama dan 401-nya tidak menghapus sesi', async () => {
    saveSession('abc', 3600);
    const fetchMock = respond(401, { detail: 'Username atau password salah' });
    await expect(apiPost('/auth/login', {}, { auth: false })).rejects.toBeInstanceOf(ApiError);
    expect(headersOf(fetchMock).Authorization).toBeUndefined();
    expect(localStorage.getItem('dt-puti.session')).not.toBeNull();
  });

  it('FormData dikirim apa adanya tanpa Content-Type JSON', async () => {
    saveSession('abc', 3600);
    const fetchMock = respond(200, { ok: true });
    const form = new FormData();
    form.append('dry_run', 'true');
    await apiPostForm('/data/imports/project-plan', form);
    const init = (fetchMock.mock.calls[0] as unknown as [string, RequestInit])[1];
    expect(init.body).toBe(form);
    expect(headersOf(fetchMock)['Content-Type']).toBeUndefined();
    expect(headersOf(fetchMock).Authorization).toBe('Bearer abc');
  });

  it('401 dengan token menghapus sesi, 403 tidak', async () => {
    saveSession('abc', 3600);
    respond(403, { detail: 'Anda tidak punya izin untuk tindakan ini' });
    await expect(apiGet('/data/projects')).rejects.toMatchObject({ status: 403 });
    expect(localStorage.getItem('dt-puti.session')).not.toBeNull();
    respond(401, { detail: 'Token tidak valid' });
    await expect(apiGet('/auth/me')).rejects.toMatchObject({ status: 401 });
    expect(localStorage.getItem('dt-puti.session')).toBeNull();
  });

  it('pesan Pydantic diterjemahkan', async () => {
    respond(422, { detail: [{ loc: ['body', 'username'], msg: 'String should have at most 50 characters' }] });
    const error = await apiPost('/auth/login', {}).catch((e: unknown) => e);
    expect((error as ApiError).fieldErrors()).toEqual({ username: 'Maksimal 50 karakter' });
  });

  it.each([
    [new TypeError('Failed to fetch'), true],
    [new ApiError(502, []), true],
    [new ApiError(503, []), true],
    [new ApiError(504, []), true],
    [new ApiError(500, []), true],
    [new ApiError(500, [{ field: null, message: 'Kesalahan server' }]), false],
    [new ApiError(401, [{ field: null, message: 'x' }]), false],
    [new ApiError(422, []), false],
  ])('isApiUnreachable(%s) = %s', (error, expected) => {
    expect(isApiUnreachable(error)).toBe(expected);
  });
});
