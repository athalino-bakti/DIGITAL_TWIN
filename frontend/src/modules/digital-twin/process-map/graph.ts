/**
 * Tata letak directly-follows graph untuk tab Process Map (DIG-171).
 *
 * Berbeda dengan graf dependency, DFG boleh punya siklus (QA kembali ke In Progress) dan
 * edge ke diri sendiri. Langkahnya:
 * 1. Cari edge balik dengan DFS dari aktivitas awal (paling banyak case lebih dulu, lalu edge
 *    paling sering). Edge balik tidak dipakai untuk menentukan kolom.
 * 2. Kolom = jalur terpanjang dari node "Mulai" lewat edge maju. Node "Selesai" di kolom paling kanan.
 * 3. Urutan dalam kolom mengikuti rata-rata posisi tetangga supaya garis tidak banyak bersilang.
 * Edge maju digambar lengkung kiri ke kanan, edge balik melengkung di bawah, dan edge ke diri
 * sendiri berupa simpul kecil di atas kotak.
 */

export const START = '__start__';
export const END = '__end__';

export type GraphNode = { id: string; weight: number };
export type GraphEdge = { source: string; target: string; weight: number };
export type Size = { nodeWidth: number; nodeHeight: number; terminal: number; gapX: number; gapY: number; padding: number };
export type Box = { x: number; y: number; width: number; height: number; layer: number };
export type Route = { path: string; labelX: number; labelY: number; kind: 'forward' | 'back' | 'self' };
export type Layout = { boxes: Map<string, Box>; width: number; height: number; back: Set<string> };

export const DEFAULT_SIZE: Size = { nodeWidth: 160, nodeHeight: 52, terminal: 28, gapX: 110, gapY: 28, padding: 24 };

export const edgeKey = (source: string, target: string) => `${source}\u0000${target}`;

/** Edge yang menutup siklus pada DFS; dikembalikan sebagai kunci `edgeKey`. */
export function backEdges(nodes: GraphNode[], edges: GraphEdge[], starts: string[]): Set<string> {
  const next = new Map<string, GraphEdge[]>();
  // Edge ke diri sendiri digambar terpisah, jadi bukan edge balik.
  for (const edge of edges) if (edge.source !== edge.target) next.set(edge.source, [...(next.get(edge.source) ?? []), edge]);
  for (const list of next.values()) list.sort((a, b) => b.weight - a.weight || a.target.localeCompare(b.target));
  const state = new Map<string, 'open' | 'done'>();
  const back = new Set<string>();
  const visit = (root: string) => {
    // Iteratif supaya graf besar tidak menghabiskan stack.
    const stack: { id: string; index: number }[] = [{ id: root, index: 0 }];
    state.set(root, 'open');
    while (stack.length) {
      const top = stack[stack.length - 1];
      const out = next.get(top.id) ?? [];
      if (top.index >= out.length) { state.set(top.id, 'done'); stack.pop(); continue; }
      const edge = out[top.index++];
      const seen = state.get(edge.target);
      if (seen === 'open') back.add(edgeKey(edge.source, edge.target));
      else if (!seen) { state.set(edge.target, 'open'); stack.push({ id: edge.target, index: 0 }); }
    }
  };
  const order = [...starts, ...[...nodes].sort((a, b) => b.weight - a.weight || a.id.localeCompare(b.id)).map((node) => node.id)];
  for (const id of order) if (!state.has(id)) visit(id);
  return back;
}

/** Kolom tiap node: "Mulai" di 0, aktivitas sesudahnya mengikuti jalur maju terpanjang. */
export function layersOf(ids: string[], forward: GraphEdge[]): Map<string, number> {
  const known = new Set(ids);
  const next = new Map<string, string[]>();
  const waiting = new Map<string, number>(ids.map((id) => [id, 0]));
  for (const edge of forward) {
    if (!known.has(edge.source) || !known.has(edge.target) || edge.source === edge.target) continue;
    next.set(edge.source, [...(next.get(edge.source) ?? []), edge.target]);
    waiting.set(edge.target, (waiting.get(edge.target) ?? 0) + 1);
  }
  const layers = new Map<string, number>(ids.map((id) => [id, 0]));
  const queue = ids.filter((id) => waiting.get(id) === 0);
  for (let index = 0; index < queue.length; index += 1) {
    for (const child of next.get(queue[index]) ?? []) {
      layers.set(child, Math.max(layers.get(child) ?? 0, (layers.get(queue[index]) ?? 0) + 1));
      const left = (waiting.get(child) ?? 0) - 1;
      waiting.set(child, left);
      if (left === 0) queue.push(child);
    }
  }
  return layers;
}

export function layoutProcess(nodes: GraphNode[], edges: GraphEdge[], size: Size = DEFAULT_SIZE): Layout {
  const ids = [START, ...nodes.map((node) => node.id), END];
  const starts = edges.filter((edge) => edge.source === START).sort((a, b) => b.weight - a.weight).map((edge) => edge.target);
  const all = [{ id: START, weight: Infinity }, ...nodes, { id: END, weight: -Infinity }];
  const back = backEdges(all, edges, [START]);
  const forward = edges.filter((edge) => edge.source !== edge.target && !back.has(edgeKey(edge.source, edge.target)));
  const layers = layersOf(ids, forward);
  // Node tanpa edge maju masuk tetap sesudah "Mulai"; "Selesai" selalu paling kanan.
  for (const node of nodes) if ((layers.get(node.id) ?? 0) === 0) layers.set(node.id, 1);
  const last = Math.max(1, ...nodes.map((node) => layers.get(node.id) ?? 1)) + 1;
  layers.set(START, 0);
  layers.set(END, last);

  const columns: string[][] = Array.from({ length: last + 1 }, () => []);
  const weight = new Map(nodes.map((node) => [node.id, node.weight]));
  const ranked = [...nodes].sort((a, b) => (starts.indexOf(a.id) + 1 || Infinity) - (starts.indexOf(b.id) + 1 || Infinity) || b.weight - a.weight || a.id.localeCompare(b.id));
  columns[0].push(START);
  for (const node of ranked) columns[layers.get(node.id) ?? 1].push(node.id);
  columns[last].push(END);

  const row = new Map<string, number>();
  const number = () => columns.forEach((column) => column.forEach((id, index) => row.set(id, index)));
  number();
  const neighbours = (id: string, before: boolean) => forward
    .filter((edge) => (before ? edge.target === id : edge.source === id))
    .map((edge) => ({ at: row.get(before ? edge.source : edge.target) ?? 0, weight: edge.weight }));
  const sortColumn = (column: string[], before: boolean) => {
    const key = new Map(column.map((id) => {
      const list = neighbours(id, before).filter((item) => Number.isFinite(item.weight));
      const total = list.reduce((sum, item) => sum + item.weight, 0);
      return [id, total ? list.reduce((sum, item) => sum + item.at * item.weight, 0) / total : row.get(id) ?? 0];
    }));
    column.sort((a, b) => (key.get(a) ?? 0) - (key.get(b) ?? 0) || (weight.get(b) ?? 0) - (weight.get(a) ?? 0));
    number();
  };
  for (let sweep = 0; sweep < 2; sweep += 1) {
    for (let layer = 1; layer < last; layer += 1) sortColumn(columns[layer], true);
    for (let layer = last - 1; layer >= 1; layer -= 1) sortColumn(columns[layer], false);
  }

  const tallest = Math.max(...columns.map((column) => column.length));
  const columnHeight = tallest * size.nodeHeight + (tallest - 1) * size.gapY;
  const boxes = new Map<string, Box>();
  // Kolom Mulai dan Selesai cukup selebar lingkarannya, supaya tidak ada garis kosong panjang.
  const widthOf = (layer: number) => (layer === 0 || layer === last ? size.terminal : size.nodeWidth);
  const gapOf = (layer: number) => (layer === 0 || layer === last - 1 ? size.gapX * 0.6 : size.gapX);
  const left: number[] = [];
  let cursor = size.padding;
  for (let layer = 0; layer <= last; layer += 1) { left.push(cursor); cursor += widthOf(layer) + (layer < last ? gapOf(layer) : 0); }
  columns.forEach((column, layer) => {
    const height = column.length * size.nodeHeight + (column.length - 1) * size.gapY;
    const top = size.padding + 34 + (columnHeight - height) / 2; // 34: ruang simpul edge ke diri sendiri
    column.forEach((id, index) => {
      const terminal = id === START || id === END;
      const w = terminal ? size.terminal : size.nodeWidth;
      const h = terminal ? size.terminal : size.nodeHeight;
      const x = left[layer] + (widthOf(layer) - w) / 2;
      const y = top + index * (size.nodeHeight + size.gapY) + (size.nodeHeight - h) / 2;
      boxes.set(id, { x, y, width: w, height: h, layer });
    });
  });
  const backSpan = Math.max(0, ...edges.filter((edge) => back.has(edgeKey(edge.source, edge.target))).map((edge) => Math.abs((layers.get(edge.source) ?? 0) - (layers.get(edge.target) ?? 0))));
  return {
    boxes,
    back,
    width: cursor + size.padding,
    height: size.padding * 2 + 34 + columnHeight + (backSpan ? arcDepth(backSpan) + 24 : 0),
  };
}

const arcDepth = (span: number) => 36 + 22 * Math.max(0, span - 1);

/** Titik tengah kurva Bezier kubik (t = 0,5), tempat label edge. */
export function bezierMid(p0: number, p1: number, p2: number, p3: number): number {
  return (p0 + 3 * p1 + 3 * p2 + p3) / 8;
}

export function routeEdge(from: Box, to: Box, isBack: boolean): Route {
  if (from === to) {
    const cx = from.x + from.width / 2;
    const top = from.y;
    return { kind: 'self', path: `M ${cx - 14} ${top} C ${cx - 26} ${top - 34}, ${cx + 26} ${top - 34}, ${cx + 14} ${top - 3}`, labelX: cx, labelY: top - 30 };
  }
  if (isBack || to.layer <= from.layer) {
    const x1 = from.x + from.width / 2;
    const y1 = from.y + from.height;
    const x2 = to.x + to.width / 2;
    const y2 = to.y + to.height + 4;
    const depth = arcDepth(Math.abs(from.layer - to.layer));
    const bottom = Math.max(y1, y2) + depth;
    return { kind: 'back', path: `M ${x1} ${y1} C ${x1} ${bottom}, ${x2} ${bottom}, ${x2} ${y2}`, labelX: bezierMid(x1, x1, x2, x2), labelY: bezierMid(y1, bottom, bottom, y2) };
  }
  const x1 = from.x + from.width;
  const y1 = from.y + from.height / 2;
  const x2 = to.x - 4;
  const y2 = to.y + to.height / 2;
  const bend = Math.max(30, (x2 - x1) / 2);
  return { kind: 'forward', path: `M ${x1} ${y1} C ${x1 + bend} ${y1}, ${x2 - bend} ${y2}, ${x2} ${y2}`, labelX: bezierMid(x1, x1 + bend, x2 - bend, x2), labelY: bezierMid(y1, y1, y2, y2) };
}

/** Tebal garis 1,25 sampai 7 px mengikuti frekuensi relatif. */
export function strokeWidth(frequency: number, max: number): number {
  if (max <= 0) return 1.25;
  return Math.round((1.25 + 5.75 * Math.sqrt(Math.min(1, frequency / max))) * 100) / 100;
}

const number = new Intl.NumberFormat('id-ID', { maximumFractionDigits: 1 });

/** Durasi dari jam: di bawah 1 jam dalam menit, di bawah 2 hari dalam jam, selebihnya hari. */
export function formatDuration(hours: number): string {
  if (hours < 1) return `${Math.round(hours * 60)} mnt`;
  if (hours < 48) return `${number.format(hours)} jam`;
  return `${number.format(hours / 24)} hari`;
}
