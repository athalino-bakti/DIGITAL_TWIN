import { describe, expect, it } from 'vitest';
import { safeRedirect } from './redirect';

const ORIGIN = 'http://localhost:5173';
const redirect = (from: unknown) => safeRedirect({ from }, ORIGIN);

describe('safeRedirect', () => {
  it.each([
    ['/data/proyek', '/data/proyek'],
    ['/data/proyek?tab=aktif#atas', '/data/proyek?tab=aktif#atas'],
    ['/simulasi', '/simulasi'],
  ])('menerima path internal %s', (from, expected) => {
    expect(redirect(from)).toBe(expected);
  });

  it.each([
    ['//contoh.com', 'protocol-relative'],
    ['/\\contoh.com', 'backslash'],
    ['/\t/contoh.com', 'tab'],
    ['/\n/contoh.com', 'baris baru'],
    ['https://contoh.com/data', 'URL absolut'],
    ['javascript:alert(1)', 'skema javascript'],
    ['data/proyek', 'path relatif'],
    ['/login', 'halaman login'],
    ['/login?next=/data', 'halaman login dengan query'],
  ])('menolak %s (%s)', (from) => {
    expect(redirect(from)).toBe('/');
  });

  it.each([null, undefined, {}, { from: 42 }])('state tidak valid jadi /', (state) => {
    expect(safeRedirect(state, ORIGIN)).toBe('/');
  });
});
