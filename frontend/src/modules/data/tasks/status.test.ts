import { describe, expect, it } from 'vitest';
import type { TaskStatus } from './api';
import { checkStatus, quickChange } from './status';

const TODAY = '2026-11-15';
const task = (status: TaskStatus, actual_start: string | null = null, actual_finish: string | null = null, dod_fulfilled = false) =>
  ({ status, actual_start, actual_finish, dod_fulfilled });

describe('checkStatus (sama dengan backend DIG-161)', () => {
  it.each([
    task('not_started'),
    task('in_progress', '2026-11-02'),
    task('blocked', '2026-11-02'),
    task('in_qa', '2026-11-02'),
    task('on_hold'),
    task('on_hold', '2026-11-02'),
    task('dropped'),
    task('done', '2026-11-02', '2026-11-06', true),
  ])('pola dataset dosbim valid: %o', (values) => {
    expect(checkStatus(values)).toEqual({});
  });

  it('menolak kombinasi yang salah', () => {
    expect(Object.keys(checkStatus(task('not_started', '2026-11-02')))).toEqual(['actual_start']);
    expect(Object.keys(checkStatus(task('in_progress')))).toEqual(['actual_start']);
    expect(Object.keys(checkStatus(task('done', '2026-11-02')))).toEqual(['actual_finish']);
    expect(Object.keys(checkStatus(task('in_qa', '2026-11-02', '2026-11-06')))).toEqual(['actual_finish']);
    expect(Object.keys(checkStatus(task('done', '2026-11-06', '2026-11-02')))).toEqual(['actual_finish']);
    expect(Object.keys(checkStatus(task('in_qa', '2026-11-02', null, true)))).toEqual(['dod_fulfilled']);
  });
});

describe('quickChange (DIG-163)', () => {
  it('mulai dikerjakan mengisi tanggal mulai hari ini', () => {
    expect(quickChange(task('not_started'), 'in_progress', TODAY)).toEqual({ status: 'in_progress', actual_start: TODAY });
  });

  it('tanggal mulai yang sudah ada dipertahankan', () => {
    expect(quickChange(task('in_progress', '2026-11-02'), 'in_qa', TODAY)).toEqual({ status: 'in_qa' });
  });

  it('selesai mengisi tanggal selesai hari ini', () => {
    expect(quickChange(task('in_qa', '2026-11-02'), 'done', TODAY)).toEqual({ status: 'done', actual_finish: TODAY });
  });

  it('langsung selesai dari belum dimulai mengisi kedua tanggal', () => {
    expect(quickChange(task('not_started'), 'done', TODAY)).toEqual({ status: 'done', actual_start: TODAY, actual_finish: TODAY });
  });

  it('dibuka lagi dari selesai mengosongkan tanggal selesai dan DoD', () => {
    expect(quickChange(task('done', '2026-11-02', '2026-11-06', true), 'in_progress', TODAY)).toEqual({ status: 'in_progress', actual_finish: null, dod_fulfilled: false });
  });

  it('kembali ke belum dimulai mengosongkan tanggal mulai', () => {
    expect(quickChange(task('in_progress', '2026-11-02'), 'not_started', TODAY)).toEqual({ status: 'not_started', actual_start: null });
  });

  it('ditunda dan dibatalkan tidak mengisi tanggal mulai', () => {
    expect(quickChange(task('not_started'), 'on_hold', TODAY)).toEqual({ status: 'on_hold' });
    expect(quickChange(task('not_started'), 'dropped', TODAY)).toEqual({ status: 'dropped' });
  });

  it.each(['not_started', 'in_progress', 'blocked', 'on_hold', 'in_qa', 'done', 'dropped'] as TaskStatus[])('hasilnya selalu lolos aturan, dari in_qa ke %s', (next) => {
    const before = task('in_qa', '2026-11-02');
    expect(checkStatus({ ...before, ...quickChange(before, next, TODAY) })).toEqual({});
  });
});
