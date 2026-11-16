import { describe, expect, it } from 'vitest';
import type { BaselineSummary } from './api';
import { buildCards } from './cards';

const summary = (overrides: Partial<BaselineSummary> = {}): BaselineSummary => ({
  as_of: '2026-11-16',
  active_projects: { count: 2, items: [] },
  late_projects: {
    count: 1,
    items: [{ project_id: 'PRJ-001', project_name: 'SIKEP', status: 'development', priority_rank: 1, target_launch_date: '2026-06-30', projected_finish: '2026-07-07', days_late: 7, open_tasks: 3, late_open_tasks: 1 }],
  },
  overloaded_resources: { count: null, reason: 'Menunggu RLI' },
  multi_role_resources: {
    count: 2,
    items: [
      { resource_id: 'RES-001', resource_name: 'Sari', primary_role_id: 'ROLE-BE', secondary_role_ids: ['ROLE-QA'], other_active_roles: [] },
      { resource_id: 'RES-002', resource_name: 'Budi', primary_role_id: 'ROLE-BE', secondary_role_ids: [], other_active_roles: ['ROLE-FE'] },
    ],
  },
  ...overrides,
});

describe('buildCards', () => {
  it('menampilkan empat kartu dengan angka dan keterangan', () => {
    const cards = buildCards(summary());
    expect(cards.map((card) => [card.key, card.value])).toEqual([['active', 2], ['late', 1], ['overload', null], ['multi', 2]]);
    expect(cards[1].note).toBe('Paling telat SIKEP, 7 hari');
    expect(cards[3].note).toBe('1 sedang menjalankan peran lain');
  });

  it('kartu overload tidak bisa diklik selama RLI belum ada', () => {
    const overload = buildCards(summary())[2];
    expect(overload.clickable).toBe(false);
    expect(overload.note).toContain('RLI');
  });

  it('kartu bernilai nol tidak bisa diklik', () => {
    const cards = buildCards(summary({ late_projects: { count: 0, items: [] }, active_projects: { count: 0, items: [] }, multi_role_resources: { count: 0, items: [] } }));
    expect(cards.filter((card) => card.clickable)).toEqual([]);
    expect(cards[1].note).toBe('Semua proyek aktif sesuai target');
  });

  it('sebelum data datang semua kartu kosong', () => {
    expect(buildCards(null).every((card) => card.value === null && !card.clickable)).toBe(true);
  });
});
