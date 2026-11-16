import { describe, expect, it } from 'vitest';
import { effectAllowed, normalize, toDays, validate, type ChangeValues } from './rules';

const values = (overrides: Partial<ChangeValues> = {}): ChangeValues => ({
  event_id: '',
  project_id: 'PRJ-001',
  event_type: 'change_request',
  event_date: '2026-03-02',
  requested_by: 'Kaur',
  decision: '',
  resolution_mode: '',
  affected_task_id: '',
  extension_days: '',
  effect_status: '',
  effect_priority: '',
  ...overrides,
});

describe('validate', () => {
  it('isian minimum lolos', () => {
    expect(validate(values(), true)).toEqual({});
  });

  it('proyek, tanggal, dan format ID', () => {
    const errors = validate(values({ project_id: '', event_date: '', event_id: 'EV1', affected_task_id: 'T1' }), true);
    expect(Object.keys(errors).sort()).toEqual(['affected_task_id', 'event_date', 'event_id', 'project_id']);
  });

  it('tanggal tidak boleh sebelum proyek dimulai', () => {
    expect(validate(values({ event_date: '2026-01-04' }), true, '2026-01-05').event_date).toContain('2026-01-05');
    expect(validate(values({ event_date: '2026-01-05' }), true, '2026-01-05')).toEqual({});
  });

  it('mode resolusi butuh keputusan', () => {
    expect(validate(values({ resolution_mode: 'reshuffle' }), true).decision).toBeDefined();
  });

  it('perpanjang durasi wajib lebih dari 0 hari', () => {
    const extend = values({ decision: 'accept_now', resolution_mode: 'extend_duration' });
    expect(validate(extend, true).extension_days).toBeDefined();
    expect(validate({ ...extend, extension_days: '0' }, true).extension_days).toBeDefined();
    expect(validate({ ...extend, extension_days: '2,5' }, true)).toEqual({});
    expect(validate({ ...extend, extension_days: '400' }, true).extension_days).toContain('365');
  });

  it('prioritas baru harus bilangan bulat 1 sampai 999', () => {
    const swap = values({ decision: 'accept_now', resolution_mode: 'swap_task', affected_task_id: 'TSK-0001' });
    expect(validate({ ...swap, effect_priority: '0' }, true).effect_priority).toBeDefined();
    expect(validate({ ...swap, effect_priority: '1.5' }, true).effect_priority).toBeDefined();
    expect(validate({ ...swap, effect_priority: '3' }, true)).toEqual({});
  });
});

describe('effectAllowed', () => {
  it('hanya untuk diterima sekarang, tukar task atau atur ulang, dan ada task', () => {
    const base = { decision: 'accept_now' as const, resolution_mode: 'swap_task' as const, affected_task_id: 'TSK-0001' };
    expect(effectAllowed(base)).toBe(true);
    expect(effectAllowed({ ...base, resolution_mode: 'reshuffle' })).toBe(true);
    expect(effectAllowed({ ...base, decision: 'defer_next' })).toBe(false);
    expect(effectAllowed({ ...base, resolution_mode: 'extend_duration' })).toBe(false);
    expect(effectAllowed({ ...base, affected_task_id: ' ' })).toBe(false);
  });
});

describe('normalize', () => {
  it('membersihkan isian yang tidak lagi berlaku', () => {
    const next = normalize(values({ resolution_mode: 'reshuffle', extension_days: '3', effect_status: 'on_hold', effect_priority: '2' }));
    expect(next).toMatchObject({ resolution_mode: '', extension_days: '', effect_status: '', effect_priority: '' });
  });

  it('mempertahankan isian yang masih berlaku', () => {
    const kept = values({ decision: 'accept_now', resolution_mode: 'swap_task', affected_task_id: 'TSK-0001', effect_status: 'dropped', effect_priority: '4' });
    expect(normalize(kept)).toEqual(kept);
  });
});

describe('toDays', () => {
  it('menerima koma desimal dan kosong', () => {
    expect(toDays('2,5')).toBe(2.5);
    expect(toDays('')).toBeNull();
  });
});
