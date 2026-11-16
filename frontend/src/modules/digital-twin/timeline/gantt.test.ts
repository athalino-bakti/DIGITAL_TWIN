import { describe, expect, it } from 'vitest';
import { actualBarOf, barOf, dayNumber, inScale, isoOf, makeScale, monthSegments, offsetOf } from './gantt';

const scale = makeScale(['2026-03-10', '2026-01-15', '2026-02-20'], 4)!;

describe('makeScale', () => {
  it('melebar ke awal dan akhir bulan', () => {
    expect([scale.start, scale.end]).toEqual(['2026-01-01', '2026-03-31']);
    expect(scale.days).toBe(31 + 28 + 31);
    expect(scale.width).toBe(90 * 4);
  });

  it('tanpa tanggal tidak ada skala', () => {
    expect(makeScale([], 4)).toBeNull();
  });

  it('melewati pergantian tahun dan tahun kabisat', () => {
    const wide = makeScale(['2027-12-20', '2028-02-10'], 2)!;
    expect([wide.start, wide.end]).toEqual(['2027-12-01', '2028-02-29']);
    expect(wide.days).toBe(31 + 31 + 29);
  });
});

describe('posisi batang', () => {
  it('dayNumber dan isoOf saling membalik', () => {
    expect(isoOf(dayNumber('2026-03-06'))).toBe('2026-03-06');
    expect(dayNumber('2026-03-07') - dayNumber('2026-03-06')).toBe(1);
  });

  it('offset dihitung dari awal skala', () => {
    expect(offsetOf(scale, '2026-01-01')).toBe(0);
    expect(offsetOf(scale, '2026-02-01')).toBe(31 * 4);
  });

  it('batang mencakup kedua ujung', () => {
    expect(barOf(scale, '2026-01-05', '2026-01-05')).toEqual({ left: 16, width: 4 });
    expect(barOf(scale, '2026-01-05', '2026-01-09')).toEqual({ left: 16, width: 20 });
  });

  it('tanggal terbalik tetap menghasilkan batang yang sah', () => {
    expect(barOf(scale, '2026-01-09', '2026-01-05')).toEqual({ left: 16, width: 20 });
  });
});

describe('actualBarOf', () => {
  it('task belum mulai tidak punya batang aktual', () => {
    expect(actualBarOf(scale, null, null, '2026-03-20')).toBeNull();
  });

  it('task selesai digambar sampai tanggal selesainya', () => {
    expect(actualBarOf(scale, '2026-01-05', '2026-01-09', '2026-03-20')).toEqual({ left: 16, width: 20, open: false });
  });

  it('task berjalan digambar sampai tanggal acuan dan ditandai open', () => {
    expect(actualBarOf(scale, '2026-01-05', null, '2026-01-07')).toEqual({ left: 16, width: 12, open: true });
  });

  it('tanggal acuan sebelum mulai: batang satu hari', () => {
    expect(actualBarOf(scale, '2026-01-05', null, '2026-01-01')).toEqual({ left: 16, width: 4, open: true });
  });
});

describe('monthSegments', () => {
  it('satu kolom per bulan, bersambung tanpa celah', () => {
    const segments = monthSegments(scale);
    expect(segments.map((s) => [s.month, s.width])).toEqual([[0, 124], [1, 112], [2, 124]]);
    expect(segments[1].left).toBe(124);
    expect(segments.reduce((sum, s) => sum + s.width, 0)).toBe(scale.width);
  });
});

describe('inScale', () => {
  it('membatasi penanda ke rentang skala', () => {
    expect(inScale(scale, '2026-03-31')).toBe(true);
    expect(inScale(scale, '2026-04-01')).toBe(false);
  });
});
