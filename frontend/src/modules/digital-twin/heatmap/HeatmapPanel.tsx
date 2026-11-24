import { useCallback, useEffect, useMemo, useState } from 'react';
import { ApiError, isApiUnreachable } from '../../../shared/api/client';
import { PERM } from '../../../shared/auth/permissions';
import { useCan } from '../../../shared/auth/usePermission';
import { listProjects, type Project } from '../../data/projects/api';
import { listResources, listRoles, type Resource, type Role } from '../../data/resources/api';
import { getWorkloadHeatmap, type HeatmapCell, type HeatmapRow, type WorkloadHeatmap } from './api';
import { categoryOf, cellAt, cellDetails, DEFAULT_WEEKS, describeCell, formatRli, holidayNote, rangeLabel, shortDate, summaryText, visibleRows, WEEK_OPTIONS, weekLabel } from './rules';

type Options = { projects: Project[]; resources: Resource[]; roles: Role[] };
type Load = { state: 'loading' } | { state: 'error'; message: string } | { state: 'ready'; data: WorkloadHeatmap };
type Selected = { resourceId: string; weekStart: string };

/** Tab Beban Resource: heatmap RLI per anggota per minggu (DIG-43: DIG-189). */
export function HeatmapPanel() {
  const canReadAll = useCan(PERM.workloadReadAll);
  const [options, setOptions] = useState<Options | null>(null);
  const [weeks, setWeeks] = useState<number>(DEFAULT_WEEKS);
  const [roleId, setRoleId] = useState('');
  const [projectId, setProjectId] = useState('');
  const [resourceId, setResourceId] = useState('');
  const [overloadOnly, setOverloadOnly] = useState(false);
  const [selected, setSelected] = useState<Selected | null>(null);
  const [load, setLoad] = useState<Load>({ state: 'loading' });

  // Pilihan filter. Anggota dan peran hanya untuk pemegang workload:read_all; yang lain hanya melihat dirinya.
  useEffect(() => {
    const controller = new AbortController();
    Promise.all([
      listProjects(controller.signal),
      canReadAll ? listResources(controller.signal) : Promise.resolve([]),
      canReadAll ? listRoles(controller.signal) : Promise.resolve([]),
    ])
      .then(([projects, resources, roles]) => setOptions({ projects, resources, roles }))
      .catch((error: unknown) => {
        if (!(error instanceof DOMException && error.name === 'AbortError')) setOptions({ projects: [], resources: [], roles: [] });
      });
    return () => controller.abort();
  }, [canReadAll]);

  const refresh = useCallback((signal?: AbortSignal) => {
    getWorkloadHeatmap({ weeks, role_id: roleId || undefined, project_id: projectId || undefined, resource_id: resourceId || undefined }, signal)
      .then((data) => setLoad({ state: 'ready', data }))
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === 'AbortError') return;
        setLoad({ state: 'error', message: error instanceof ApiError && !isApiUnreachable(error) ? error.message : 'Pastikan API dan basis data sudah berjalan.' });
      });
  }, [weeks, roleId, projectId, resourceId]);

  useEffect(() => {
    const controller = new AbortController();
    setLoad({ state: 'loading' });
    setSelected(null);
    refresh(controller.signal);
    return () => controller.abort();
  }, [refresh]);

  const data = load.state === 'ready' ? load.data : null;
  const rows = useMemo(() => (data ? visibleRows(data.rows, data.categories, overloadOnly) : []), [data, overloadOnly]);
  const picked: { row: HeatmapRow; cell: HeatmapCell } | null = useMemo(() => {
    // Hanya dari baris yang tampil: rincian hilang bila barisnya tersaring "Overload saja".
    if (!selected) return null;
    const row = rows.find((r) => r.resource_id === selected.resourceId);
    const cell = row && cellAt(row, selected.weekStart);
    return row && cell ? { row, cell } : null;
  }, [rows, selected]);

  return (
    <section className="module-panel" aria-labelledby="heatmap-title">
      <div className="panel-heading">
        <div>
          <h2 id="heatmap-title">Beban resource</h2>
          <p className="panel-subtitle">Resource Load Index (RLI) per anggota per minggu: beban proyek dan non-proyek dibagi kapasitas.{data && ` Posisi per ${shortDate(data.as_of)}.`}</p>
        </div>
      </div>

      {data?.provisional && <p className="heatmap-note" role="note">Formula RLI masih provisional ({data.formula_version}) sampai disepakati tWinner. Angka dan batas kategori bisa berubah.</p>}

      <div className="panel-toolbar">
        {data ? <p className="toolbar-summary"><strong className={data.summary.overloaded ? 'text-danger' : ''}>{summaryText(data.summary.overloaded, data.summary.resources, data.summary.week_start)}</strong></p> : <span className="toolbar-summary">&nbsp;</span>}
        <div className="workload-filters">
          <label className="visually-hidden" htmlFor="heatmap-weeks">Jumlah minggu</label>
          <select id="heatmap-weeks" className="workload-select" value={weeks} onChange={(e) => setWeeks(Number(e.target.value))}>
            {WEEK_OPTIONS.map((n) => <option key={n} value={n}>{n} minggu</option>)}
          </select>
          <label className="visually-hidden" htmlFor="heatmap-project">Filter proyek</label>
          <select id="heatmap-project" className="workload-select" value={projectId} disabled={!options} onChange={(e) => setProjectId(e.target.value)}>
            <option value="">Semua proyek</option>
            {options?.projects.map((p) => <option key={p.project_id} value={p.project_id}>{p.project_name}</option>)}
          </select>
          {canReadAll && <>
            <label className="visually-hidden" htmlFor="heatmap-role">Filter peran</label>
            <select id="heatmap-role" className="workload-select" value={roleId} disabled={!options} onChange={(e) => setRoleId(e.target.value)}>
              <option value="">Semua peran</option>
              {options?.roles.map((r) => <option key={r.role_id} value={r.role_id}>{r.role_name}</option>)}
            </select>
            <label className="visually-hidden" htmlFor="heatmap-resource">Filter anggota</label>
            <select id="heatmap-resource" className="workload-select" value={resourceId} disabled={!options} onChange={(e) => setResourceId(e.target.value)}>
              <option value="">Semua anggota</option>
              {options?.resources.map((r) => <option key={r.resource_id} value={r.resource_id}>{r.resource_name}</option>)}
            </select>
          </>}
          <label className="checkbox" htmlFor="heatmap-overload">
            <input id="heatmap-overload" type="checkbox" checked={overloadOnly} onChange={(e) => setOverloadOnly(e.target.checked)} />
            <span>Overload saja</span>
          </label>
        </div>
      </div>

      {load.state === 'loading' && <div className="empty-state"><p>Memuat heatmap…</p></div>}
      {load.state === 'error' && (
        <div className="empty-state">
          <h3>Heatmap belum bisa dimuat</h3>
          <p>{load.message}</p>
          <button type="button" className="button button-ghost" onClick={() => { setLoad({ state: 'loading' }); refresh(); }}>Coba lagi</button>
        </div>
      )}
      {data && rows.length === 0 && (
        <div className="empty-state">
          <h3>{overloadOnly ? 'Tidak ada anggota overload' : 'Belum ada anggota untuk ditampilkan'}</h3>
          <p>{overloadOnly ? 'Matikan filter "Overload saja" untuk melihat semua anggota.' : 'Ubah filter, atau pastikan data resource dan task sudah diimpor.'}</p>
        </div>
      )}
      {data && rows.length > 0 && <>
        <div className="heatmap" role="region" aria-label="Heatmap RLI per anggota per minggu" tabIndex={0}>
          <table className="heatmap-table">
            <thead>
              <tr>
                <th scope="col" className="heatmap-member">Anggota</th>
                {data.weeks.map((week) => {
                  const note = holidayNote(week);
                  return (
                    <th key={week.week_start} scope="col" className={week.week_start === data.summary.week_start ? 'heatmap-week current' : 'heatmap-week'} title={note ?? undefined}>
                      {weekLabel(week)}{note && <span className="heatmap-holiday" aria-label={note}> ●</span>}
                    </th>
                  );
                })}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.resource_id}>
                  <th scope="row" className="heatmap-member">
                    <strong>{row.resource_name}</strong>
                    <small>{row.primary_role_id}{row.is_onboarding ? ' · onboarding' : ''}</small>
                  </th>
                  {data.weeks.map((week) => {
                    const cell = cellAt(row, week.week_start);
                    if (!cell) return <td key={week.week_start} />;
                    const category = categoryOf(data.categories, cell.category);
                    const active = selected?.resourceId === row.resource_id && selected.weekStart === week.week_start;
                    return (
                      <td key={week.week_start}>
                        <button
                          type="button"
                          className={`heatmap-cell heat-${category ? cell.category : 'unknown'}${active ? ' active' : ''}`}
                          aria-pressed={active}
                          aria-label={describeCell(row, cell, category)}
                          title={`${category?.label ?? cell.category}`}
                          onClick={() => setSelected(active ? null : { resourceId: row.resource_id, weekStart: week.week_start })}
                        >
                          {formatRli(cell.rli)}
                        </button>
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <ul className="heatmap-legend" aria-label="Legenda kategori RLI">
          {data.categories.map((category) => (
            <li key={category.code}>
              <span className={`heatmap-swatch heat-${category.code}`} aria-hidden="true" />
              <strong>{category.label}</strong> <span className="heatmap-range">{rangeLabel(category)}</span>
            </li>
          ))}
        </ul>

        {picked && (
          <aside className="heatmap-detail" aria-live="polite">
            <div className="heatmap-detail-head">
              <h3>{picked.row.resource_name}, minggu {shortDate(picked.cell.week_start)}</h3>
              <button type="button" className="button button-ghost" onClick={() => setSelected(null)}>Tutup</button>
            </div>
            <p>RLI <strong>{formatRli(picked.cell.rli)}</strong>, {categoryOf(data.categories, picked.cell.category)?.label ?? picked.cell.category}.</p>
            <dl className="heatmap-detail-list">
              {cellDetails(picked.cell).map((item) => <div key={item.label}><dt>{item.label}</dt><dd>{item.value}</dd></div>)}
            </dl>
          </aside>
        )}
      </>}
    </section>
  );
}
