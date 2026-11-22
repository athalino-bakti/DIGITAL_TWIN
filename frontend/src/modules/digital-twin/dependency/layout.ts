/** Tata letak diagram jaringan dependency (DIG-183): kolom per kedalaman, kiri ke kanan. */

export type Link = { from: string; to: string };
export type Point = { x: number; y: number; layer: number; row: number };
export type Size = { nodeWidth: number; nodeHeight: number; gapX: number; gapY: number; padding: number };
export type Layout = { points: Map<string, Point>; width: number; height: number };

export const DEFAULT_SIZE: Size = { nodeWidth: 190, nodeHeight: 44, gapX: 80, gapY: 12, padding: 16 };

/** Task yang punya minimal satu dependency (sebagai prasyarat atau penerus). */
export function connectedIds(links: Link[]): Set<string> {
  const ids = new Set<string>();
  for (const link of links) { ids.add(link.from); ids.add(link.to); }
  return ids;
}

/** Kedalaman tiap task: 0 untuk task tanpa prasyarat, selainnya 1 + kedalaman prasyarat terdalam.
 *  Task di dalam dependency melingkar tidak pernah "siap", jadi ditaruh di kolom 0. */
export function layersOf(ids: string[], links: Link[]): Map<string, number> {
  const known = new Set(ids);
  const next = new Map<string, string[]>();
  const waiting = new Map<string, number>(ids.map((id) => [id, 0]));
  for (const link of links) {
    if (!known.has(link.from) || !known.has(link.to) || link.from === link.to) continue;
    next.set(link.from, [...(next.get(link.from) ?? []), link.to]);
    waiting.set(link.to, (waiting.get(link.to) ?? 0) + 1);
  }
  const layers = new Map<string, number>(ids.map((id) => [id, 0]));
  const queue = ids.filter((id) => waiting.get(id) === 0);
  for (let index = 0; index < queue.length; index += 1) {
    const id = queue[index];
    for (const child of next.get(id) ?? []) {
      layers.set(child, Math.max(layers.get(child) ?? 0, (layers.get(id) ?? 0) + 1));
      const left = (waiting.get(child) ?? 0) - 1;
      waiting.set(child, left);
      if (left === 0) queue.push(child);
    }
  }
  const done = new Set(queue);
  for (const id of ids) if (!done.has(id)) layers.set(id, 0);
  return layers;
}

function average(values: number[]): number | null {
  return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null;
}

/** Urutan dalam kolom mengikuti rata-rata posisi tetangganya, supaya garis tidak banyak bersilang. */
export function layoutGraph(ids: string[], links: Link[], size: Size = DEFAULT_SIZE): Layout {
  const layers = layersOf(ids, links);
  const columns: string[][] = [];
  for (const id of ids) {
    const layer = layers.get(id) ?? 0;
    (columns[layer] ??= []).push(id);
  }
  for (let layer = 0; layer < columns.length; layer += 1) columns[layer] ??= [];

  const before = new Map<string, string[]>();
  const after = new Map<string, string[]>();
  for (const link of links) {
    if (!layers.has(link.from) || !layers.has(link.to)) continue;
    before.set(link.to, [...(before.get(link.to) ?? []), link.from]);
    after.set(link.from, [...(after.get(link.from) ?? []), link.to]);
  }

  const row = new Map<string, number>();
  const number = (column: string[]) => column.forEach((id, index) => row.set(id, index));
  columns.forEach(number);
  const sortBy = (column: string[], neighbours: Map<string, string[]>) => {
    const key = new Map(column.map((id) => [id, average((neighbours.get(id) ?? []).map((other) => row.get(other) ?? 0)) ?? row.get(id) ?? 0]));
    const order = new Map(column.map((id, index) => [id, index]));
    column.sort((a, b) => (key.get(a) ?? 0) - (key.get(b) ?? 0) || (order.get(a) ?? 0) - (order.get(b) ?? 0));
    number(column);
  };
  for (let sweep = 0; sweep < 2; sweep += 1) {
    for (let layer = 1; layer < columns.length; layer += 1) sortBy(columns[layer], before);
    for (let layer = columns.length - 2; layer >= 0; layer -= 1) sortBy(columns[layer], after);
  }

  const points = new Map<string, Point>();
  columns.forEach((column, layer) => column.forEach((id, index) => points.set(id, {
    x: size.padding + layer * (size.nodeWidth + size.gapX),
    y: size.padding + index * (size.nodeHeight + size.gapY),
    layer,
    row: index,
  })));
  const tallest = Math.max(0, ...columns.map((column) => column.length));
  return {
    points,
    width: columns.length ? size.padding * 2 + columns.length * size.nodeWidth + (columns.length - 1) * size.gapX : 0,
    height: tallest ? size.padding * 2 + tallest * size.nodeHeight + (tallest - 1) * size.gapY : 0,
  };
}

/** Garis lengkung dari sisi kanan task prasyarat ke sisi kiri task penerus. */
export function edgePath(from: Point, to: Point, size: Size = DEFAULT_SIZE): string {
  const x1 = from.x + size.nodeWidth;
  const y1 = from.y + size.nodeHeight / 2;
  const x2 = to.x - 6; // ruang untuk kepala panah
  const y2 = to.y + size.nodeHeight / 2;
  const bend = Math.max(24, Math.abs(x2 - x1) / 2);
  return `M ${x1} ${y1} C ${x1 + bend} ${y1}, ${x2 - bend} ${y2}, ${x2} ${y2}`;
}

/** Potong nama panjang supaya muat di kotak task. */
export function clip(text: string, max: number): string {
  return text.length <= max ? text : `${text.slice(0, Math.max(0, max - 1)).trimEnd()}…`;
}
