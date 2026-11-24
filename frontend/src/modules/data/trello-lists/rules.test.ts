import { describe, expect, it } from 'vitest';
import type { TrelloList } from './api';
import { groupByBoard, sameMapping, suggestMapping } from './rules';

describe('suggestMapping', () => {
  it.each([
    ['To Do', 'not_started'],
    ['Backlog', 'not_started'],
    ['Doing', 'in_progress'],
    ['Sedang dikerjakan', 'in_progress'],
    ['QA', 'in_qa'],
    ['Review', 'in_qa'],
    ['Done', 'done'],
    ['Selesai ✅', 'done'],
    ['Blocked', 'blocked'],
    ['Ditunda', 'on_hold'],
    ['Dibatalkan', 'dropped'],
  ])('status %s', (name, status) => {
    expect(suggestMapping(name).status).toBe(status);
  });

  it('urutan aturan: blocked dan done menang atas QA', () => {
    expect(suggestMapping('Blocked QA').status).toBe('blocked');
    expect(suggestMapping('Done Testing').status).toBe('done');
  });

  it('phase dari nama list', () => {
    expect(suggestMapping('Doing Backend').phase).toBe('be_dev');
    expect(suggestMapping('FE In Progress').phase).toBe('fe_dev');
    expect(suggestMapping('UI/UX').phase).toBe('uiux');
    expect(suggestMapping('Testing').phase).toBe('testing');
    expect(suggestMapping('Bugfix').phase).toBe('bugfix');
    expect(suggestMapping('Dokumentasi').phase).toBe('documentation');
  });

  it('tidak menebak bila nama tidak dikenal', () => {
    expect(suggestMapping('Sprint 4')).toEqual({ status: null, phase: null });
    // "be" di tengah kata tidak dianggap backend
    expect(suggestMapping('Bebas').phase).toBeNull();
    expect(suggestMapping('Backlog').phase).toBeNull();
  });
});

describe('sameMapping', () => {
  it('membandingkan status dan phase', () => {
    expect(sameMapping({ status: 'done', phase: null }, { status: 'done', phase: null })).toBe(true);
    expect(sameMapping({ status: 'done', phase: null }, { status: 'done', phase: 'testing' })).toBe(false);
  });
});

describe('groupByBoard', () => {
  const list = (board_id: string, list_id: string, status: TrelloList['status'], board_name: string | null = null) =>
    ({ board_id, list_id, list_name: list_id, board_name, status, phase: null, updated_at: '', actions: 0, last_seen: null }) as TrelloList;

  it('papan dengan list belum dipetakan lebih dulu, nama papan dari list mana saja', () => {
    const groups = groupByBoard([
      list('a', '1', 'done', 'Alpha'),
      list('b', '1', null),
      list('b', '2', null, 'Beta'),
      list('a', '2', 'in_progress'),
    ]);
    expect(groups.map((g) => [g.board_id, g.board_name, g.lists.length])).toEqual([['b', 'Beta', 2], ['a', 'Alpha', 2]]);
  });
});
