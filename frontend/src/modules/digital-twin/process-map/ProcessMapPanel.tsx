import { useCallback, useEffect, useMemo, useState } from 'react';
import { ApiError, isApiUnreachable } from '../../../shared/api/client';
import { listProjects, type Project } from '../../data/projects/api';
import { EXTRA_KINDS, getProcessMap, type ProcessEdge, type ProcessMap, type ProcessNode } from './api';
import { DEFAULT_SIZE, edgeKey, END, formatDuration, layoutProcess, routeEdge, START, strokeWidth, type GraphEdge } from './graph';

type Status = { state: 'loading' } | { state: 'ready' } | { state: 'error'; message: string };
type Filters = { project_id: string; date_from: string; date_to: string; extra_kinds: string[] };
type Metric = 'frequency' | 'duration';

const count = new Intl.NumberFormat('id-ID');
const isAbort = (error: unknown) => error instanceof DOMException && error.name === 'AbortError';
const EMPTY: Filters = { project_id: '', date_from: '', date_to: '', extra_kinds: [] };

function edgeText(edge: { source: string; target: string; frequency: number; cases: number; mean_hours?: number; median_hours?: number }): string {
  const from = edge.source === START ? 'Mulai' : edge.source;
  const to = edge.target === END ? 'Selesai' : edge.target;
  const time = edge.mean_hours === undefined ? '' : `, rata-rata ${formatDuration(edge.mean_hours)}, median ${formatDuration(edge.median_hours ?? 0)}`;
  return `${from} ke ${to}: ${count.format(edge.frequency)} kali di ${count.format(edge.cases)} case${time}`;
}

/** Tab Process Map: directly-follows graph dari event log dengan filter frekuensi (DIG-38: DIG-170, DIG-171). */
export function ProcessMapPanel() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [filters, setFilters] = useState<Filters>(EMPTY);
  const [minFrequency, setMinFrequency] = useState(1);
  const [sliderValue, setSliderValue] = useState(1);
  const [metric, setMetric] = useState<Metric>('frequency');
  const [data, setData] = useState<ProcessMap | null>(null);
  const [status, setStatus] = useState<Status>({ state: 'loading' });
  const [focus, setFocus] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    listProjects(controller.signal).then(setProjects).catch(() => undefined);
    return () => controller.abort();
  }, []);

  // Slider digeser dulu, baru dikirim setelah berhenti sebentar supaya API tidak dipanggil tiap piksel.
  useEffect(() => {
    const timer = window.setTimeout(() => setMinFrequency(sliderValue), 250);
    return () => window.clearTimeout(timer);
  }, [sliderValue]);

  const dateInvalid = Boolean(filters.date_from && filters.date_to && filters.date_from > filters.date_to);

  const refresh = useCallback((signal?: AbortSignal) => {
    if (dateInvalid) return;
    setStatus({ state: 'loading' });
    getProcessMap({ ...filters, min_frequency: minFrequency }, signal)
      .then((result) => { setData(result); setStatus({ state: 'ready' }); })
      .catch((error: unknown) => {
        if (isAbort(error)) return;
        setStatus({ state: 'error', message: error instanceof ApiError && !isApiUnreachable(error) ? error.message : 'Pastikan API dan basis data sudah berjalan.' });
      });
  }, [filters, minFrequency, dateInvalid]);

  useEffect(() => {
    const controller = new AbortController();
    refresh(controller.signal);
    return () => controller.abort();
  }, [refresh]);

  const setFilter = <K extends keyof Filters>(key: K, value: Filters[K]) => { setFocus(null); setFilters((current) => ({ ...current, [key]: value })); };
  const toggleKind = (kind: string, on: boolean) => setFilter('extra_kinds', on ? [...filters.extra_kinds, kind] : filters.extra_kinds.filter((k) => k !== kind));

  // Batas slider mengikuti frekuensi edge terbesar dari hasil terakhir.
  const sliderMax = Math.max(1, data?.max_edge_frequency ?? 1);
  useEffect(() => { if (sliderValue > sliderMax) setSliderValue(sliderMax); }, [sliderMax, sliderValue]);

  const graph = useMemo(() => {
    if (!data || data.nodes.length === 0) return null;
    const terminals: (GraphEdge & { cases: number })[] = [
      ...data.start_activities.map((item) => ({ source: START, target: item.activity, weight: item.cases, cases: item.cases })),
      ...data.end_activities.map((item) => ({ source: item.activity, target: END, weight: item.cases, cases: item.cases })),
    ];
    const edges: GraphEdge[] = [...terminals, ...data.edges.map((edge) => ({ source: edge.source, target: edge.target, weight: edge.frequency }))];
    const layout = layoutProcess(data.nodes.map((node) => ({ id: node.id, weight: node.frequency })), edges);
    return { layout, terminals };
  }, [data]);

  const maxShown = Math.max(1, ...(data?.edges ?? []).map((edge) => edge.frequency));
  const sorted = useMemo(() => [...(data?.edges ?? [])].sort((a, b) => b.frequency - a.frequency || a.source.localeCompare(b.source)), [data]);
  const touches = (edge: { source: string; target: string }) => focus !== null && (edge.source === focus || edge.target === focus);
  const filtered = Boolean(filters.project_id || filters.date_from || filters.date_to);
  const { nodeWidth, nodeHeight } = DEFAULT_SIZE;

  function edgeLabel(edge: ProcessEdge): string {
    return metric === 'frequency' ? count.format(edge.frequency) : formatDuration(edge.mean_hours);
  }

  function nodeLine(node: ProcessNode): string {
    return `${count.format(node.frequency)} kali · ${count.format(node.cases)} case`;
  }

  return (
    <section className="module-panel" aria-labelledby="process-map-title">
      <div className="panel-heading panel-heading-wrap">
        <div>
          <h2 id="process-map-title">Process map</h2>
          <p className="panel-subtitle">Alur kerja aktual dari event log. Panah berarti aktivitas tujuan langsung terjadi sesudah aktivitas asal pada task yang sama; makin tebal, makin sering.</p>
        </div>
        <div className="segmented" role="group" aria-label="Angka di panah">
          <button type="button" className={metric === 'frequency' ? 'active' : ''} aria-pressed={metric === 'frequency'} onClick={() => setMetric('frequency')}>Frekuensi</button>
          <button type="button" className={metric === 'duration' ? 'active' : ''} aria-pressed={metric === 'duration'} onClick={() => setMetric('duration')}>Durasi rata-rata</button>
        </div>
      </div>

      <div className="panel-toolbar pm-toolbar">
        <div className="workload-filters">
          <label className="visually-hidden" htmlFor="pm-project">Proyek</label>
          <select id="pm-project" className="workload-select" value={filters.project_id} onChange={(e) => setFilter('project_id', e.target.value)}>
            <option value="">Semua proyek</option>
            {projects.map((project) => <option key={project.project_id} value={project.project_id}>{project.project_name}</option>)}
          </select>
          <label className="pm-date" htmlFor="pm-from"><span>Dari</span><input id="pm-from" type="date" className="workload-select" value={filters.date_from} max={filters.date_to || undefined} onChange={(e) => setFilter('date_from', e.target.value)} /></label>
          <label className="pm-date" htmlFor="pm-to"><span>Sampai</span><input id="pm-to" type="date" className="workload-select" value={filters.date_to} min={filters.date_from || undefined} aria-invalid={dateInvalid || undefined} aria-describedby={dateInvalid ? 'pm-date-error' : undefined} onChange={(e) => setFilter('date_to', e.target.value)} /></label>
          {EXTRA_KINDS.map(({ kind, label }) => (
            <label key={kind} className="checkbox" htmlFor={`pm-kind-${kind}`}>
              <input id={`pm-kind-${kind}`} type="checkbox" checked={filters.extra_kinds.includes(kind)} onChange={(e) => toggleKind(kind, e.target.checked)} />
              <span>{label}</span>
            </label>
          ))}
          {(filtered || filters.extra_kinds.length > 0) && <button type="button" className="link-button" onClick={() => { setFocus(null); setFilters(EMPTY); }}>Hapus filter</button>}
        </div>
        {dateInvalid && <p className="field-error" id="pm-date-error">Tanggal akhir tidak boleh sebelum tanggal awal.</p>}
      </div>

      {data && data.event_log_events > 0 && (
        <div className="pm-filter">
          <label htmlFor="pm-min">
            <span>Sembunyikan jalur yang terjadi kurang dari <strong>{count.format(sliderValue)}</strong> kali</span>
            <input id="pm-min" type="range" min="1" max={sliderMax} step="1" value={Math.min(sliderValue, sliderMax)} aria-describedby="pm-hidden" onChange={(e) => setSliderValue(Number(e.target.value))} />
          </label>
          <p id="pm-hidden" className="toolbar-summary" aria-live="polite">
            <strong>{count.format(data.cases)}</strong> case · <strong>{count.format(data.events)}</strong> event · <strong>{data.edges.length}</strong> jalur tampil
            {data.hidden.edges > 0 && <> · <strong className="text-danger">{data.hidden.edges}</strong> jalur ({count.format(data.hidden.edge_frequency)} perpindahan){data.hidden.nodes > 0 ? ` dan ${data.hidden.nodes} aktivitas` : ''} disembunyikan</>}
          </p>
        </div>
      )}

      {!data && status.state === 'loading' && <div className="empty-state"><p>Memuat process map…</p></div>}
      {status.state === 'error' && (
        <div className="empty-state compact" role="alert">
          <h3>Process map belum bisa dimuat</h3>
          <p>{status.message}</p>
          <button type="button" className="button button-ghost" onClick={() => refresh()}>Coba lagi</button>
        </div>
      )}
      {data && data.event_log_events === 0 && (
        <div className="empty-state">
          <h3>Event log belum dibentuk</h3>
          <p>Process map dihitung dari event log. Administrator Data perlu membentuknya dulu dari data Trello dan kejadian perubahan (POST /data/event-log/rebuild).</p>
        </div>
      )}
      {data && data.event_log_events > 0 && data.nodes.length === 0 && (
        <div className="empty-state">
          <h3>Tidak ada event pada filter ini</h3>
          <p>{filtered ? 'Ubah proyek atau rentang tanggal, atau hapus filter.' : 'Geser slider ke kiri untuk menampilkan jalur yang jarang terjadi.'}</p>
        </div>
      )}

      {data && graph && (
        <>
          <div className={`pm-canvas ${status.state === 'loading' ? 'is-busy' : ''}`} aria-busy={status.state === 'loading'}>
            <svg className={`pm-svg ${focus ? 'has-focus' : ''}`} style={{ maxWidth: graph.layout.width, minWidth: Math.min(graph.layout.width, Math.max(720, graph.layout.width * 0.8)) }} viewBox={`0 0 ${graph.layout.width} ${graph.layout.height}`} role="img" aria-label={`Process map: ${data.nodes.length} aktivitas dan ${data.edges.length} jalur. Rincian ada di tabel di bawah.`}>
              <defs>
                <marker id="pm-arrow" className="pm-arrow" viewBox="0 0 8 8" refX="1" refY="4" markerWidth="6" markerHeight="6" orient="auto" markerUnits="userSpaceOnUse"><path d="M 0 0 L 8 4 L 0 8 z" /></marker>
                <marker id="pm-arrow-terminal" className="pm-arrow arrow-terminal" viewBox="0 0 8 8" refX="1" refY="4" markerWidth="6" markerHeight="6" orient="auto" markerUnits="userSpaceOnUse"><path d="M 0 0 L 8 4 L 0 8 z" /></marker>
              </defs>
              {graph.terminals.map((edge) => {
                const from = graph.layout.boxes.get(edge.source); const to = graph.layout.boxes.get(edge.target);
                if (!from || !to) return null;
                const route = routeEdge(from, to, false);
                return <g key={edgeKey(edge.source, edge.target)} className={`pm-edge edge-terminal ${touches(edge) ? 'is-touched' : ''}`}><title>{edgeText({ ...edge, frequency: edge.cases })}</title><path d={route.path} markerEnd="url(#pm-arrow-terminal)" /></g>;
              })}
              {data.edges.map((edge) => {
                const from = graph.layout.boxes.get(edge.source); const to = graph.layout.boxes.get(edge.target);
                if (!from || !to) return null;
                const route = routeEdge(from, to, graph.layout.back.has(edgeKey(edge.source, edge.target)));
                const label = edgeLabel(edge);
                return (
                  <g key={edgeKey(edge.source, edge.target)} className={`pm-edge edge-${route.kind} ${touches(edge) ? 'is-touched' : ''}`}>
                    <title>{edgeText(edge)}</title>
                    <path d={route.path} strokeWidth={strokeWidth(edge.frequency, maxShown)} markerEnd="url(#pm-arrow)" />
                    <rect className="pm-label-bg" x={route.labelX - (label.length * 3.6 + 6)} y={route.labelY - 9} width={label.length * 7.2 + 12} height="18" rx="9" />
                    <text className="pm-label" x={route.labelX} y={route.labelY + 4} textAnchor="middle">{label}</text>
                  </g>
                );
              })}
              {[START, END].map((id) => {
                const box = graph.layout.boxes.get(id);
                if (!box) return null;
                return <g key={id} className={`pm-terminal ${id === START ? 'is-start' : 'is-end'}`}><circle cx={box.x + box.width / 2} cy={box.y + box.height / 2} r={box.width / 2} /><text x={box.x + box.width / 2} y={box.y + box.height + 14} textAnchor="middle">{id === START ? 'Mulai' : 'Selesai'}</text></g>;
              })}
              {data.nodes.map((node) => {
                const box = graph.layout.boxes.get(node.id);
                if (!box) return null;
                const selected = focus === node.id;
                const text = `${node.label}: ${nodeLine(node)}. Mengawali ${count.format(node.start_cases)} case, mengakhiri ${count.format(node.end_cases)} case.`;
                return (
                  <g key={node.id} className={`pm-node ${selected ? 'is-selected' : ''} ${focus && !selected && !data.edges.some((edge) => touches(edge) && (edge.source === node.id || edge.target === node.id)) ? 'is-faded' : ''}`} transform={`translate(${box.x} ${box.y})`} role="button" tabIndex={0} aria-pressed={selected} aria-label={text} onClick={() => setFocus(selected ? null : node.id)} onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); setFocus(selected ? null : node.id); } }}>
                    <title>{text}</title>
                    <rect width={nodeWidth} height={nodeHeight} rx="10" />
                    <text className="pm-node-name" x={nodeWidth / 2} y="22" textAnchor="middle">{node.label.length > 22 ? `${node.label.slice(0, 21)}…` : node.label}</text>
                    <text className="pm-node-count" x={nodeWidth / 2} y="39" textAnchor="middle">{nodeLine(node)}</text>
                  </g>
                );
              })}
            </svg>
          </div>
          <p className="pm-hint">{focus ? <>Menyorot jalur masuk dan keluar <strong>{focus}</strong>. <button type="button" className="link-button" onClick={() => setFocus(null)}>Hapus sorotan</button></> : 'Klik satu aktivitas untuk menyorot jalur masuk dan keluarnya. Arahkan kursor ke panah untuk melihat rinciannya.'}</p>

          <div className="table-scroll">
            <table className="data-table">
              <caption className="visually-hidden">Jalur antar aktivitas, urut dari yang paling sering</caption>
              <thead><tr><th scope="col">Dari</th><th scope="col">Ke</th><th scope="col" className="num">Frekuensi</th><th scope="col" className="num">Case</th><th scope="col" className="num">Rata-rata</th><th scope="col" className="num">Median</th></tr></thead>
              <tbody>
                {sorted.filter((edge) => !focus || touches(edge)).map((edge) => (
                  <tr key={edgeKey(edge.source, edge.target)}>
                    <td>{edge.source}</td><td>{edge.target}{edge.source === edge.target && <span className="cell-sub">berulang</span>}</td>
                    <td className="num">{count.format(edge.frequency)}</td><td className="num">{count.format(edge.cases)}</td>
                    <td className="num nowrap">{formatDuration(edge.mean_hours)}</td><td className="num nowrap">{formatDuration(edge.median_hours)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  );
}
