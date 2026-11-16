import { describe, expect, it } from 'vitest';
import type { ResourceAlias } from './api';
import { aliasCount, aliasError, identityLabel, suggestResource } from './rules';

const resources = [
  { resource_id: 'RES-001', resource_name: 'Sari Puspitasari' },
  { resource_id: 'RES-002', resource_name: 'Bagas Haris' },
  { resource_id: 'RES-003', resource_name: 'Bagas Pratama' },
  { resource_id: 'RES-004', resource_name: 'Dédi Kurniawan' },
];
const identity = (display_name: string | null, username: string | null = null) => ({ display_name, username });

describe('suggestResource', () => {
  it('nama tampilan sama persis, abaikan huruf besar dan aksen', () => {
    expect(suggestResource(identity('sari puspitasari'), resources)).toBe('RES-001');
    expect(suggestResource(identity('Dedi Kurniawan'), resources)).toBe('RES-004');
  });

  it('awal kata yang hanya cocok dengan satu anggota', () => {
    expect(suggestResource(identity('Sari P.'), resources)).toBe('RES-001');
    expect(suggestResource(identity('Bagas H'), resources)).toBe('RES-002');
  });

  it('tidak mengusulkan bila lebih dari satu anggota cocok', () => {
    expect(suggestResource(identity('Bagas'), resources)).toBeNull();
  });

  it('username digabung dengan nama anggota', () => {
    expect(suggestResource(identity(null, 'bagas.haris'), resources)).toBe('RES-002');
    expect(suggestResource(identity(null, 'bh'), resources)).toBeNull();
  });

  it('tidak ada yang cocok', () => {
    expect(suggestResource(identity('Rina'), resources)).toBeNull();
    expect(suggestResource(identity(null), resources)).toBeNull();
  });
});

describe('identityLabel', () => {
  it('urutan nama tampilan, username, alias', () => {
    expect(identityLabel({ display_name: 'Sari', username: 'sari', alias: 'abc' })).toBe('Sari');
    expect(identityLabel({ display_name: null, username: 'sari', alias: 'abc' })).toBe('@sari');
    expect(identityLabel({ display_name: null, username: null, alias: 'abc' })).toBe('abc');
  });
});

describe('aliasError', () => {
  it('trello harus 24 heksadesimal', () => {
    expect(aliasError('trello', '5f1a2b3c4d5e6f7a8b9c0d1e')).toBeNull();
    expect(aliasError('trello', ' 5F1A2B3C4D5E6F7A8B9C0D1E ')).toBeNull();
    expect(aliasError('trello', 'sari')).toMatch(/24 karakter/);
  });

  it('teamgit harus email', () => {
    expect(aliasError('teamgit', 'sari@puti.ac.id')).toBeNull();
    expect(aliasError('teamgit', 'sari')).toMatch(/email/);
  });

  it('project_plan teks bebas, tidak boleh kosong', () => {
    expect(aliasError('project_plan', 'Sari P.')).toBeNull();
    expect(aliasError('project_plan', '  ')).toBe('Alias wajib diisi');
  });
});

describe('aliasCount', () => {
  it('menghitung alias per anggota', () => {
    const row = (resource_id: string) => ({ resource_id }) as ResourceAlias;
    expect(aliasCount([row('RES-001'), row('RES-001'), row('RES-002')])).toEqual(new Map([['RES-001', 2], ['RES-002', 1]]));
  });
});
