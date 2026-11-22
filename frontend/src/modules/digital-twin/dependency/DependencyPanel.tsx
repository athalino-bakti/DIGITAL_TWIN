import { useCallback, useEffect, useMemo, useState, type KeyboardEvent } from 'react';
import { ApiError, isApiUnreachable } from '../../../shared/api/client';
import { listProjects, type Project } from '../../data/projects/api';
import { getDependencyGraph, TASK_STATUS_LABEL, type DependencyGraph, type DependencyNode } from './api';
import { clip, connectedIds, DEFAULT_SIZE, edgePath, layoutGraph } from './layout';

type Status = { state: 'loading' } | { state: 'ready' } | { state: 'error'; message: string };

const MAX_DELAY = 365;
const days = new Intl.NumberFormat('id-ID', { maximumFractionDigits: 2 });
const isAbort = (error: unknown) => error instanceof DOMException && error.name === 'AbortError';

/** Angka keterlambatan dari kolom isian; undefined berarti pakai keterlambatan task itu sendiri. */
function parseDelay(text: string): number | undefined {
  if (text.trim() === '') return undefined;
  const value = Number(text.replace(',', '.'));
  return Number.isFinite(value) && value >= 0 && value <= MAX_DELAY ? value : undefined;
}

function describeNode(node: DependencyNode, focused: boolean): string {
  const parts = [`${node.task_id} ${node.task_name}`, TASK_STATUS_LABEL[node.status] ?? node.status, `estimasi ${days.format(node.estimated_days)} hari`];
  if (node.is_critical) parts.push('di jalur kritis');
  if (node.is_late) parts.push(`terlambat ${node.delay_working_days} hari kerja`);
  if (node.impact_days !== null) parts.push(`terdampak ${days.format(node.impact_days)} hari kerja`);
  if (focused) parts.push('sedang dipilih');
  return `${parts.join(', ')}.`;
}

/** Tab Dependency: diagram jaringan, jalur kritis, dan dampak keterlambatan (DIG-42: DIG-183). */
export function DependencyPanel() {
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [projectId, setProjectId] = useState<string | null>(null);
  const [focusId, setFocusId] = useState<string | null>(null);
  const [delayText, setDelayText] = useState('');
  const [delay, setDelay] = useState<number | undefined>(undefined);
  const [showLoose, setShowLoose] = useState(false);
  const [graph, setGraph] = useState<DependencyGraph | null>(null);
  const [status, setStatus] = useState<Status>({ state: 'loading' });

  useEffect(() => {
    const controller = new AbortController();
    listProjects(controller.signal)
      .then((list) => { setProjects(list); setProjectId((current) => current ?? list[0]?.project_id ?? ''); })
      .catch((error: unknown) => { if (!isAbort(error)) { setProjects([]); setProjectId((current) => current ?? ''); } });
    return () => controller.abort();
  }, []);

  // Angka diketik dulu, baru dikirim setelah berhenti sebentar, supaya tidak memanggil API tiap ketukan.
  useEffect(() => {
    const timer = window.setTimeout(() => setDelay(parseDelay(delayText)), 300);
    return () => window.clearTimeout(timer);
  }, [delayText]);

  const refresh = useCallback((signal?: AbortSignal) => {
    if (!projectId) return;
    setStatus({ state: 'loading' });
    getDependencyGraph({ project_id: projectId, task_id: focusId ?? undefined, delay_days: delay }, signal)
      .then((data) => { setGraph(data); setStatus({ state: 'ready' }); })
      .catch((error: unknown) => {
        if (isAbort(error)) return;
        setStatus({ state: 'error', message: error instanceof ApiError && !isApiUnreachable(error) ? error.message : 'Pastikan API dan basis data sudah berjalan.' });
      });
  }, [projectId, focusId, delay]);

  useEffect(() => {
    const controller = new AbortController();
    refresh(controller.signal);
    return () => controller.abort();
  }, [refresh]);

  const choose = (taskId: string | null) => { setFocusId(taskId); setDelayText(''); setDelay(undefined); };
  const changeProject = (id: string) => { setProjectId(id); setGraph(null); choose(null); };

  // Data proyek sebelumnya tidak dipakai saat proyek sudah diganti.
  const data = graph && graph.project_id === projectId ? graph : null;
  const byId = useMemo(() => new Map((data?.nodes ?? []).map((node) => [node.task_id, node])), [data]);
  const links = useMemo(() => (data?.edges ?? []).map((edge) => ({ from: edge.depends_on_task_id, to: edge.task_id })), [data]);
  const looseCount = useMemo(() => (data ? data.nodes.length - connectedIds(links).size : 0), [data, links]);
  const shown = useMemo(() => {
    if (!data) return [];
    if (showLoose) return data.nodes;
    const linked = connectedIds(links);
    return data.nodes.filter((node) => linked.has(node.task_id) || node.task_id === focusId);
  }, [data, links, showLoose, focusId]);
  const layout = useMemo(() => layoutGraph(shown.map((node) => node.task_id), links), [shown, links]);

  const focus = data?.focus && data.focus.task_id === focusId ? data.focus : null;
  const focusNode = focusId ? byId.get(focusId) ?? null : null;
  const affected = useMemo(() => (focus && data ? data.nodes.filter((node) => node.impact_days !== null).sort((a, b) => (b.impact_days ?? 0) - (a.impact_days ?? 0) || a.task_id.localeCompare(b.task_id)) : []), [data, focus]);
  const carries = (id: string) => id === focusId || (byId.get(id)?.impact_days ?? null) !== null;
  const delayInvalid = delayText.trim() !== '' && parseDelay(delayText) === undefined;

  const onNodeKey = (event: KeyboardEvent<SVGGElement>, taskId: string) => {
    if (event.key !== 'Enter' && event.key !== ' ') return;
    event.preventDefault();
    choose(taskId === focusId ? null : taskId);
  };

  const { nodeWidth, nodeHeight } = DEFAULT_SIZE;

  return (
    <section className="module-panel" aria-labelledby="dependency-title">
      <div className="panel-heading">
        <div>
          <h2 id="dependency-title">Dependency dan jalur kritis</h2>
          <p className="panel-subtitle">Panah mengarah dari task prasyarat ke task yang bergantung. Pilih satu task untuk melihat task turunan yang ikut terdampak bila task itu terlambat.</p>
        </div>
      </div>

      <div className="panel-toolbar">
        {data ? <p className="toolbar-summary"><strong>{data.nodes.length}</strong> task · <strong>{data.edges.length}</strong> dependency · jalur kritis <strong>{days.format(data.project_duration)}</strong> hari kerja ({data.critical_task_ids.length} task)</p> : <span />}
        <div className="workload-filters">
          <label className="visually-hidden" htmlFor="dependency-project">Proyek</label>
          <select id="dependency-project" className="workload-select" value={projectId ?? ''} disabled={!projects?.length} onChange={(event) => changeProject(event.target.value)}>
            {!projects?.length && <option value="">Belum ada proyek</option>}
            {projects?.map((project) => <option key={project.project_id} value={project.project_id}>{project.project_name}</option>)}
          </select>
          <label className="checkbox" htmlFor="dependency-loose">
            <input id="dependency-loose" type="checkbox" checked={showLoose} onChange={(event) => setShowLoose(event.target.checked)} />
            <span>Tampilkan task tanpa dependency{data && looseCount > 0 ? ` (${looseCount})` : ''}</span>
          </label>
        </div>
      </div>

      {projectId === '' && (
        <div className="empty-state">
          <h3>Belum ada proyek</h3>
          <p>Diagram dependency muncul setelah proyek dan Project Plan diimpor di modul Data.</p>
        </div>
      )}
      {!data && projectId !== '' && status.state !== 'error' && <div className="empty-state"><p>Memuat dependency…</p></div>}
      {status.state === 'error' && (
        <div className="empty-state compact" role="alert">
          <h3>Dependency belum bisa dimuat</h3>
          <p>{status.message}</p>
          <button type="button" className="button button-ghost" onClick={() => refresh()}>Coba lagi</button>
        </div>
      )}

      {data && data.cycle_task_ids.length > 0 && (
        <p className="dep-warning" role="alert">
          <strong>Ada dependency melingkar.</strong> Jalur kritis tidak bisa dihitung sampai lingkaran ini diputus di data sumber: {data.cycle_task_ids.join(', ')}.
        </p>
      )}

      {data && shown.length === 0 && (
        <div className="empty-state">
          <h3>{data.nodes.length === 0 ? 'Proyek ini belum punya task' : 'Belum ada dependency antar task'}</h3>
          <p>{data.nodes.length === 0 ? 'Task masuk dari impor Project Plan.' : 'Centang "Tampilkan task tanpa dependency" untuk tetap melihat semua task.'}</p>
        </div>
      )}

      {data && shown.length > 0 && (
        <>
          <div className={`dep-canvas ${status.state === 'loading' ? 'is-busy' : ''}`} aria-busy={status.state === 'loading'}>
            <svg className={`dep-svg ${focus ? 'has-focus' : ''}`} width={layout.width} height={layout.height} viewBox={`0 0 ${layout.width} ${layout.height}`} role="group" aria-label={`Diagram dependency ${data.project_name}`}>
              <defs>
                {['plain', 'critical', 'impact'].map((kind) => (
                  <marker key={kind} id={`dep-arrow-${kind}`} className={`dep-arrow arrow-${kind}`} viewBox="0 0 8 8" refX="1" refY="4" markerWidth="7" markerHeight="7" orient="auto" markerUnits="userSpaceOnUse">
                    <path d="M 0 0 L 8 4 L 0 8 z" />
                  </marker>
                ))}
              </defs>
              <g aria-hidden="true">
                {data.edges.map((edge) => {
                  const from = layout.points.get(edge.depends_on_task_id);
                  const to = layout.points.get(edge.task_id);
                  if (!from || !to) return null;
                  const hit = focus !== null && carries(edge.depends_on_task_id) && byId.get(edge.task_id)?.impact_days != null;
                  const kind = hit ? 'impact' : edge.is_critical ? 'critical' : 'plain';
                  return <path key={edge.dependency_id} className={`dep-edge edge-${edge.dependency_type} edge-${kind}`} d={edgePath(from, to)} markerEnd={`url(#dep-arrow-${kind})`} />;
                })}
              </g>
              {shown.map((node) => {
                const point = layout.points.get(node.task_id);
                if (!point) return null;
                const selected = node.task_id === focusId;
                const impacted = focus !== null && node.impact_days !== null;
                const tag = impacted ? `+${days.format(node.impact_days ?? 0)} hr` : node.is_late ? (node.delay_working_days > 0 ? `telat ${node.delay_working_days} hr` : 'telat') : node.is_critical ? 'kritis' : '';
                const classes = ['dep-node', node.is_critical && 'is-critical', node.is_late && 'is-late', selected && 'is-selected', impacted && 'is-impacted', (node.status === 'done' || node.status === 'dropped') && 'is-closed'].filter(Boolean).join(' ');
                const text = describeNode(node, selected);
                return (
                  <g key={node.task_id} className={classes} transform={`translate(${point.x} ${point.y})`} role="button" tabIndex={0} aria-pressed={selected} aria-label={text} onClick={() => choose(selected ? null : node.task_id)} onKeyDown={(event) => onNodeKey(event, node.task_id)}>
                    <title>{text}</title>
                    <rect className="dep-box" width={nodeWidth} height={nodeHeight} rx="8" />
                    {node.is_late && <rect className="dep-late-mark" x="0" y="6" width="4" height={nodeHeight - 12} rx="2" />}
                    <text className="dep-id" x="12" y="18">{node.task_id}</text>
                    {tag && <text className="dep-tag" x={nodeWidth - 10} y="18" textAnchor="end">{tag}</text>}
                    <text className="dep-name" x="12" y="34">{clip(node.task_name, 27)}</text>
                  </g>
                );
              })}
            </svg>
          </div>

          <ul className="calendar-legend dep-legend">
            <li><svg className="dep-key" width="34" height="10" aria-hidden="true"><line className="dep-edge edge-hard edge-plain" x1="0" y1="5" x2="34" y2="5" /></svg>Hard: harus selesai dulu</li>
            <li><svg className="dep-key" width="34" height="10" aria-hidden="true"><line className="dep-edge edge-soft edge-plain" x1="0" y1="5" x2="34" y2="5" /></svg>Soft: bisa dikerjakan sebagian</li>
            <li><span className="dep-key-box key-critical" aria-hidden="true" />Jalur kritis</li>
            <li><span className="dep-key-box key-late" aria-hidden="true" />Terlambat</li>
            <li><span className="dep-key-box key-impact" aria-hidden="true" />Terdampak task terpilih</li>
          </ul>

          <div className="dep-detail" aria-live="polite">
            {!focusNode && (
              <>
                <h3>Jalur kritis</h3>
                {data.critical_task_ids.length === 0 ? <p>Belum ada jalur kritis yang bisa dihitung.</p> : (
                  <>
                    <p>Rangkaian task terpanjang, {days.format(data.project_duration)} hari kerja. Mundur satu hari di sini berarti proyek ikut mundur. Pilih task untuk melihat dampaknya.</p>
                    <ol className="dep-path">
                      {data.critical_task_ids.map((id) => <li key={id}><button type="button" className="dep-chip" onClick={() => choose(id)}><span className="text-data">{id}</span> {clip(byId.get(id)?.task_name ?? '', 32)}</button></li>)}
                    </ol>
                  </>
                )}
              </>
            )}
            {focusNode && (
              <>
                <div className="dep-detail-head">
                  <div>
                    <h3><span className="text-data">{focusNode.task_id}</span> {focusNode.task_name}</h3>
                    <p>{TASK_STATUS_LABEL[focusNode.status] ?? focusNode.status} · estimasi {days.format(focusNode.estimated_days)} hari · {focusNode.is_critical ? 'di jalur kritis' : `kelonggaran ${days.format(focusNode.total_float)} hari`} · {focusNode.is_late ? <span className="text-danger">terlambat {focusNode.delay_working_days} hari kerja</span> : 'tidak terlambat'}</p>
                  </div>
                  <button type="button" className="button button-ghost" onClick={() => choose(null)}>Batalkan pilihan</button>
                </div>
                <label className="field dep-delay">
                  <span>Keterlambatan yang dirambatkan (hari kerja)</span>
                  <input type="number" inputMode="decimal" min="0" max={MAX_DELAY} step="0.5" value={delayText} placeholder={String(focusNode.delay_working_days)} aria-invalid={delayInvalid} aria-describedby="dependency-delay-help" onChange={(event) => setDelayText(event.target.value)} />
                  <small id="dependency-delay-help">{delayInvalid ? `Isi angka 0 sampai ${MAX_DELAY}.` : 'Kosongkan untuk memakai keterlambatan task saat ini.'}</small>
                </label>
                {focus && affected.length === 0 && <p className="dep-empty">{focus.delay_days === 0 ? 'Task ini belum terlambat, jadi belum ada dampak. Isi angka keterlambatan di atas untuk mencoba.' : 'Tidak ada task turunan yang masih berjalan, jadi keterlambatan ini tidak merambat.'}</p>}
                {focus && affected.length > 0 && (
                  <div className="table-scroll">
                    <table className="data-table">
                      <caption className="visually-hidden">Task turunan yang terdampak keterlambatan {days.format(focus.delay_days)} hari kerja pada {focusNode.task_id}</caption>
                      <thead><tr><th scope="col">Task terdampak ({affected.length})</th><th scope="col">Status</th><th scope="col">Jalur kritis</th><th scope="col" className="num">Estimasi dampak</th></tr></thead>
                      <tbody>
                        {affected.map((node) => (
                          <tr key={node.task_id}>
                            <td><span className="cell-title">{node.task_name}</span><span className="cell-sub text-data">{node.task_id}</span></td>
                            <td>{TASK_STATUS_LABEL[node.status] ?? node.status}</td>
                            <td>{node.is_critical ? 'Ya' : 'Tidak'}</td>
                            <td className="num nowrap">+{days.format(node.impact_days ?? 0)} hari kerja</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </>
            )}
          </div>
        </>
      )}
    </section>
  );
}
