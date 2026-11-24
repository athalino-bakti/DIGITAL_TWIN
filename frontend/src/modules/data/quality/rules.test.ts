import { describe, expect, it } from 'vitest';
import { characteristicLabel, formatRate, hasFilter, levelLabel, NO_FILTER, pageCount, rangeText, rejectedRowsPath, rowLabel, sourceLabel, summaryPath } from './rules';

describe('formatRate', () => {
  it.each([
    [1, '100%'],
    [0, '0%'],
    [0.9825, '98,3%'],
    [0.5, '50%'],
    [0.8333, '83,3%'],
  ])('%s menjadi %s', (rate, text) => {
    expect(formatRate(rate)).toBe(text);
  });

  it('null berarti belum diperiksa', () => {
    expect(formatRate(null)).toBe('-');
  });
});

describe('pageCount dan rangeText', () => {
  it('minimal satu halaman', () => {
    expect(pageCount(0, 50)).toBe(1);
    expect(pageCount(50, 50)).toBe(1);
    expect(pageCount(51, 50)).toBe(2);
  });

  it('rentang baris pada halaman', () => {
    expect(rangeText(1, 50, 120)).toBe('1-50 dari 120');
    expect(rangeText(3, 50, 120)).toBe('101-120 dari 120');
    expect(rangeText(1, 50, 0)).toBe('0 baris');
  });
});

describe('rowLabel', () => {
  it('nomor baris lebih dulu, lalu kunci baris', () => {
    expect(rowLabel({ row_number: 12, row_key: 'TSK-1' })).toBe('Baris 12');
    expect(rowLabel({ row_number: null, row_key: 'card-9' })).toBe('card-9');
    expect(rowLabel({ row_number: null, row_key: null })).toBe('-');
  });
});

describe('path query', () => {
  it('ringkasan memakai sumber', () => {
    expect(summaryPath('trello')).toBe('/data/quality/summary?source=trello');
  });

  it('filter kosong tidak dikirim', () => {
    expect(rejectedRowsPath(7, NO_FILTER, 1, 50)).toBe('/data/quality/rejected-rows?job_id=7&page=1&page_size=50');
  });

  it('filter terisi ikut dikirim', () => {
    const path = rejectedRowsPath(7, { level: 'tolak', characteristic: 'consistency', ruleId: 'R-12' }, 2, 50);
    const params = new URL(path, 'http://x').searchParams;
    expect(params.get('job_id')).toBe('7');
    expect(params.get('page')).toBe('2');
    expect(params.get('level')).toBe('tolak');
    expect(params.get('characteristic')).toBe('consistency');
    expect(params.get('rule_id')).toBe('R-12');
  });
});

describe('label dan filter', () => {
  it('label dikenal dan cadangan ke kunci', () => {
    expect(sourceLabel('project_plan')).toBe('Project Plan');
    expect(characteristicLabel('currentness')).toBe('Kemutakhiran');
    expect(levelLabel('tolak')).toBe('Ditolak');
    expect(levelLabel('lain')).toBe('lain');
  });

  it('hasFilter', () => {
    expect(hasFilter(NO_FILTER)).toBe(false);
    expect(hasFilter({ ...NO_FILTER, ruleId: 'R-1' })).toBe(true);
  });
});
