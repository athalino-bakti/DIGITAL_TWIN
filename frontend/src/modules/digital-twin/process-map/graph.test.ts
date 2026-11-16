import { describe, expect, it } from 'vitest';
import { backEdges, bezierMid, edgeKey, END, formatDuration, layersOf, layoutProcess, routeEdge, START, strokeWidth, type GraphEdge } from './graph';

const e = (source: string, target: string, weight = 1): GraphEdge => ({ source, target, weight });
const n = (id: string, weight = 1) => ({ id, weight });

describe('backEdges', () => {
  it('menemukan edge yang menutup siklus', () => {
    const edges = [e(START, 'A', 10), e('A', 'B', 9), e('B', 'C', 8), e('C', 'B', 3)];
    expect([...backEdges([n('A'), n('B'), n('C')], edges, [START])]).toEqual([edgeKey('C', 'B')]);
  });

  it('jalur yang lebih sering dianggap maju', () => {
    // A -> B lebih sering daripada B -> A, jadi yang balik adalah B -> A.
    const edges = [e(START, 'A', 5), e(START, 'B', 1), e('A', 'B', 9), e('B', 'A', 2)];
    expect([...backEdges([n('A', 5), n('B', 1)], edges, [START])]).toEqual([edgeKey('B', 'A')]);
  });

  it('graf tanpa siklus tidak punya edge balik', () => {
    expect(backEdges([n('A'), n('B')], [e(START, 'A'), e('A', 'B')], [START]).size).toBe(0);
  });
});

describe('layersOf', () => {
  it('memakai jalur maju terpanjang', () => {
    const layers = layersOf([START, 'A', 'B', 'C'], [e(START, 'A'), e('A', 'B'), e('B', 'C'), e(START, 'C')]);
    expect(Object.fromEntries(layers)).toEqual({ [START]: 0, A: 1, B: 2, C: 3 });
  });
});

describe('layoutProcess', () => {
  // Alur status khas: dibuat, dikerjakan, QA, kadang kembali dikerjakan, lalu selesai.
  const nodes = [n('Dibuat', 100), n('Dikerjakan', 120), n('QA', 80), n('Selesai', 70)];
  const edges = [
    e(START, 'Dibuat', 100), e('Dibuat', 'Dikerjakan', 95), e('Dikerjakan', 'QA', 80),
    e('QA', 'Dikerjakan', 20), e('QA', 'Selesai', 70), e('Selesai', END, 70), e('Dikerjakan', 'Dikerjakan', 3),
  ];
  const layout = layoutProcess(nodes, edges);

  it('kolom mengikuti alur, Mulai paling kiri dan Selesai paling kanan', () => {
    const layer = (id: string) => layout.boxes.get(id)?.layer;
    expect([START, 'Dibuat', 'Dikerjakan', 'QA', 'Selesai', END].map(layer)).toEqual([0, 1, 2, 3, 4, 5]);
  });

  it('QA kembali ke Dikerjakan ditandai edge balik', () => {
    expect([...layout.back]).toEqual([edgeKey('QA', 'Dikerjakan')]);
  });

  it('menyisakan ruang di bawah untuk lengkung edge balik', () => {
    const lowest = Math.max(...[...layout.boxes.values()].map((box) => box.y + box.height));
    expect(layout.height).toBeGreaterThan(lowest + 36);
  });

  it('aktivitas tanpa edge masuk tetap di kolom sesudah Mulai', () => {
    const lonely = layoutProcess([n('A'), n('B')], [e(START, 'A'), e('A', END)]);
    expect(lonely.boxes.get('B')?.layer).toBe(1);
    expect(lonely.boxes.get(END)?.layer).toBe(2);
  });

  it('tiap node punya posisi berbeda', () => {
    const seen = new Set([...layout.boxes.values()].map((box) => `${box.x}:${box.y}`));
    expect(seen.size).toBe(layout.boxes.size);
  });
});

describe('routeEdge', () => {
  const a = { x: 0, y: 100, width: 100, height: 40, layer: 1 };
  const b = { x: 300, y: 100, width: 100, height: 40, layer: 2 };

  it('edge maju dari sisi kanan ke sisi kiri', () => {
    const route = routeEdge(a, b, false);
    expect(route.kind).toBe('forward');
    expect(route.path.startsWith('M 100 120 C')).toBe(true);
    expect(route.labelX).toBeCloseTo(198);
  });

  it('edge balik melengkung di bawah kedua kotak', () => {
    const route = routeEdge(b, a, true);
    expect(route.kind).toBe('back');
    expect(route.labelY).toBeGreaterThan(140);
  });

  it('edge ke diri sendiri berupa simpul di atas kotak', () => {
    const route = routeEdge(a, a, false);
    expect(route.kind).toBe('self');
    expect(route.labelY).toBeLessThan(a.y);
  });
});

describe('format', () => {
  it('bezierMid di tengah', () => {
    expect(bezierMid(0, 0, 10, 10)).toBe(5);
  });

  it('tebal garis naik dengan frekuensi dan dibatasi', () => {
    expect(strokeWidth(0, 100)).toBe(1.25);
    expect(strokeWidth(100, 100)).toBe(7);
    expect(strokeWidth(500, 100)).toBe(7);
    expect(strokeWidth(25, 100)).toBeGreaterThan(strokeWidth(5, 100));
    expect(strokeWidth(3, 0)).toBe(1.25);
  });

  it('durasi dalam menit, jam, atau hari', () => {
    expect(formatDuration(0.5)).toBe('30 mnt');
    expect(formatDuration(5)).toBe('5 jam');
    expect(formatDuration(36.25)).toBe('36,3 jam');
    expect(formatDuration(72)).toBe('3 hari');
  });
});
