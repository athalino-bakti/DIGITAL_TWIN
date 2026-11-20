import { describe, expect, it } from 'vitest';
import { clip, connectedIds, DEFAULT_SIZE, edgePath, layersOf, layoutGraph, type Link } from './layout';

const link = (from: string, to: string): Link => ({ from, to });
const SIZE = { nodeWidth: 100, nodeHeight: 40, gapX: 50, gapY: 10, padding: 10 };

describe('connectedIds', () => {
  it('mengumpulkan kedua ujung tiap dependency', () => {
    expect([...connectedIds([link('A', 'B'), link('B', 'C')])].sort()).toEqual(['A', 'B', 'C']);
    expect(connectedIds([]).size).toBe(0);
  });
});

describe('layersOf', () => {
  it('memakai jalur terpanjang dari task tanpa prasyarat', () => {
    const layers = layersOf(['A', 'B', 'C', 'D'], [link('A', 'B'), link('B', 'C'), link('A', 'C'), link('A', 'D')]);
    expect(Object.fromEntries(layers)).toEqual({ A: 0, B: 1, C: 2, D: 1 });
  });

  it('task tanpa dependency ada di kolom 0', () => {
    expect(layersOf(['A', 'B'], []).get('B')).toBe(0);
  });

  it('mengabaikan dependency ke task yang tidak ditampilkan dan ke diri sendiri', () => {
    const layers = layersOf(['A', 'B'], [link('X', 'A'), link('A', 'A'), link('A', 'B')]);
    expect(Object.fromEntries(layers)).toEqual({ A: 0, B: 1 });
  });

  it('tidak macet pada dependency melingkar', () => {
    const layers = layersOf(['A', 'B', 'C'], [link('A', 'B'), link('B', 'A'), link('B', 'C')]);
    expect(layers.get('A')).toBe(0);
    expect(layers.get('B')).toBe(0);
    expect(layers.size).toBe(3);
  });
});

describe('layoutGraph', () => {
  it('menaruh kolom dari kiri ke kanan dan baris dari atas ke bawah', () => {
    const { points, width, height } = layoutGraph(['A', 'B', 'C'], [link('A', 'B'), link('A', 'C')], SIZE);
    expect(points.get('A')).toEqual({ x: 10, y: 10, layer: 0, row: 0 });
    expect(points.get('B')).toEqual({ x: 160, y: 10, layer: 1, row: 0 });
    expect(points.get('C')).toEqual({ x: 160, y: 60, layer: 1, row: 1 });
    expect(width).toBe(270); // 2 kolom + 1 jarak + padding kiri kanan
    expect(height).toBe(110); // 2 baris + 1 jarak + padding atas bawah
  });

  it('mengurutkan penerus mengikuti prasyaratnya supaya garis tidak bersilang', () => {
    // Urutan masukan sengaja terbalik: Y (penerus B) datang sebelum X (penerus A).
    const { points } = layoutGraph(['A', 'B', 'Y', 'X'], [link('A', 'X'), link('B', 'Y')], SIZE);
    expect(points.get('X')?.row).toBe(0);
    expect(points.get('Y')?.row).toBe(1);
  });

  it('graf kosong berukuran nol', () => {
    expect(layoutGraph([], [], SIZE)).toMatchObject({ width: 0, height: 0 });
  });

  it('tiap task mendapat posisi yang berbeda', () => {
    const ids = ['A', 'B', 'C', 'D', 'E'];
    const { points } = layoutGraph(ids, [link('A', 'C'), link('B', 'C'), link('C', 'D'), link('A', 'E')]);
    const seen = new Set(ids.map((id) => `${points.get(id)?.x}:${points.get(id)?.y}`));
    expect(seen.size).toBe(ids.length);
  });
});

describe('edgePath', () => {
  it('berangkat dari sisi kanan prasyarat dan berhenti sebelum sisi kiri penerus', () => {
    const path = edgePath({ x: 0, y: 0, layer: 0, row: 0 }, { x: 300, y: 100, layer: 1, row: 2 }, SIZE);
    expect(path.startsWith('M 100 20 C')).toBe(true);
    expect(path.endsWith('294 120')).toBe(true);
  });

  it('memakai ukuran bawaan bila tidak diberi', () => {
    const start = DEFAULT_SIZE.nodeWidth;
    expect(edgePath({ x: 0, y: 0, layer: 0, row: 0 }, { x: 400, y: 0, layer: 1, row: 0 }).startsWith(`M ${start} `)).toBe(true);
  });
});

describe('clip', () => {
  it('membiarkan teks pendek dan memotong teks panjang dengan elipsis', () => {
    expect(clip('Login', 10)).toBe('Login');
    expect(clip('Integrasi pembayaran', 10)).toBe('Integrasi…');
    expect(clip('Integrasi pembayaran', 10).length).toBeLessThanOrEqual(10);
  });
});
