import { describe, expect, it } from 'vitest';
import { actionsFor, checkDate, dateBounds, effectNote, type TaskAction } from './actions';
import type { MyTask, MyTaskEvent } from './api';

const event = (kind: 'blocker' | 'overrun', date = '2026-11-10'): MyTaskEvent => ({ event_id: 'EVT-001', event_type: kind, event_date: date, requested_by: 'Sari' });

const task = (overrides: Partial<MyTask> = {}): MyTask => ({
  task_id: 'TSK-0001',
  task_name: 'Form cuti',
  feature_name: 'Cuti',
  project_id: 'PRJ-001',
  project_name: 'SIKEP',
  phase: 'be_dev',
  status: 'in_progress',
  priority_rank: 1,
  planned_start: '2026-11-02',
  planned_finish: '2026-11-20',
  actual_start: '2026-11-02',
  role_in_task: 'ROLE-BE',
  assigned_date: '2026-11-01',
  is_past_plan: false,
  open_blocker: null,
  open_overrun: null,
  ...overrides,
});

const labels = (value: MyTask) => actionsFor(value).map((action) => action.label);

describe('actionsFor', () => {
  it('task biasa hanya bisa ditandai terhambat', () => {
    expect(labels(task())).toEqual(['Tandai terhambat']);
  });

  it('task lewat rencana juga bisa dicatat overrun', () => {
    expect(labels(task({ is_past_plan: true }))).toEqual(['Tandai terhambat', 'Catat overrun']);
  });

  it('kejadian yang masih terbuka diganti tombol selesai', () => {
    const value = task({ status: 'blocked', is_past_plan: true, open_blocker: event('blocker'), open_overrun: event('overrun') });
    expect(labels(value)).toEqual(['Hambatan selesai', 'Overrun selesai']);
    const [first] = actionsFor(value);
    expect(first.mode === 'resolve' && first.event.event_id).toBe('EVT-001');
  });

  it('overrun terbuka tetap bisa diselesaikan walau task tidak lagi lewat rencana', () => {
    expect(labels(task({ open_overrun: event('overrun') }))).toEqual(['Tandai terhambat', 'Overrun selesai']);
  });
});

describe('effectNote', () => {
  const record: TaskAction = { kind: 'blocker', mode: 'record', label: 'Tandai terhambat' };
  const resolve: TaskAction = { kind: 'blocker', mode: 'resolve', label: 'Hambatan selesai', event: event('blocker') };

  it('menjelaskan perubahan status untuk task yang sedang dikerjakan', () => {
    expect(effectNote(task(), record)).toContain('berubah menjadi Terhambat');
    expect(effectNote(task({ status: 'in_qa' }), record)).toContain('berubah menjadi Terhambat');
  });

  it('task yang belum dikerjakan tidak berubah status', () => {
    expect(effectNote(task({ status: 'not_started' }), record)).toContain('status task tetap');
    expect(effectNote(task({ status: 'on_hold' }), record)).toContain('status task tetap');
  });

  it('menyelesaikan hambatan mengembalikan task yang terhambat', () => {
    expect(effectNote(task({ status: 'blocked' }), resolve)).toContain('kembali berstatus Dikerjakan');
    expect(effectNote(task({ status: 'not_started' }), resolve)).toContain('tidak berubah');
  });

  it('overrun tidak pernah mengubah status', () => {
    expect(effectNote(task(), { kind: 'overrun', mode: 'record', label: 'Catat overrun' })).toContain('tidak berubah');
    expect(effectNote(task(), { kind: 'overrun', mode: 'resolve', label: 'Overrun selesai', event: event('overrun') })).toContain('tidak berubah');
  });
});

describe('tanggal', () => {
  const today = '2026-11-16';
  const record: TaskAction = { kind: 'blocker', mode: 'record', label: 'Tandai terhambat' };
  const resolve: TaskAction = { kind: 'blocker', mode: 'resolve', label: 'Hambatan selesai', event: event('blocker', '2026-11-10') };

  it('batas tanggal mengikuti jenis aksi', () => {
    expect(dateBounds(record, today)).toEqual({ max: today });
    expect(dateBounds(resolve, today)).toEqual({ min: '2026-11-10', max: today });
  });

  it('menolak tanggal kosong, masa depan, dan selesai sebelum kejadian', () => {
    expect(checkDate(record, '', today)).toBe('Isi tanggal');
    expect(checkDate(record, '2026-11-17', today)).toContain('akan datang');
    expect(checkDate(resolve, '2026-11-09', today)).toContain('sebelum tanggal kejadian');
    expect(checkDate(resolve, '2026-11-10', today)).toBeNull();
    expect(checkDate(record, today, today)).toBeNull();
  });
});
