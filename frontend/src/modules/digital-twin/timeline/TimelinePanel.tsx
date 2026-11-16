import { useCallback, useEffect, useMemo, useState } from 'react';
import { ApiError, isApiUnreachable } from '../../../shared/api/client';
import { PERM } from '../../../shared/auth/permissions';
import { useCan } from '../../../shared/auth/usePermission';
import { listProjects, type Project } from '../../data/projects/api';
import { listResources, type Resource } from '../../data/resources/api';
import { EVENT_LABEL, getTimeline, PHASE_LABEL, TASK_STATUS_LABEL, type Timeline, type TimelineEvent, type TimelineProject, type TimelineTask } from './api';
import { actualBarOf, barOf, inScale, makeScale, monthSegments, offsetOf, type Scale } from './gantt';

type Options = { projects: Project[]; resources: Resource[] };
type Load = { state: 'loading' } | { state: 'error'; message: string } | { state: 'ready'; data: Timeline };

const DAY_WIDTH = 5;
const monthName = new Intl.DateTimeFormat('id-ID', { month: 'short', year: '2-digit', timeZone: 'UTC' });
const dateFormat = new Intl.DateTimeFormat('id-ID', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' });
const fmt = (iso: string | null) => (iso ? dateFormat.format(new Date(`${iso}T00:00:00Z`)) : 'belum');

function describeTask(task: TimelineTask): string {
  const late = task.is_late ? `, terlambat ${task.delay_days} hari (${task.delay_working_days} hari kerja)` : '';
  const who = task.assignees.length ? `, pelaksana ${task.assignees.join(', ')}` : '';
  return `${task.task_id} ${task.task_name}: ${TASK_STATUS_LABEL[task.status] ?? task.status}. Rencana ${fmt(task.planned_start)} s.d. ${fmt(task.planned_finish)}. Aktual ${fmt(task.actual_start)} s.d. ${fmt(task.actual_finish)}${late}${who}.`;
}

/** Tab Timeline: Gantt rencana vs aktual (DIG-41: DIG-178, DIG-179). */
export function TimelinePanel() {
  const canSeeMembers = useCan(PERM.masterDataRead);
  const [options, setOptions] = useState<Options | null>(null);
  const [projectId, setProjectId] = useState<string | null>(null);
  const [resourceId, setResourceId] = useState('');
  const [lateOnly, setLateOnly] = useState(false);
  const [collapsed, setCollapsed] = useState<ReadonlySet<string>>(new Set());
  const [load, setLoad] = useState<Load>({ state: 'loading' });

  // Pilihan filter. Proyek prioritas tertinggi dibuka lebih dulu supaya Gantt tidak terlalu panjang.
  useEffect(() => {
    const controller = new AbortController();
    Promise.all([listProjects(controller.signal), canSeeMembers ? listResources(controller.signal) : Promise.resolve([])])
      .then(([projects, resources]) => {
        setOptions({ projects, resources });
        setProjectId((current) => current ?? projects[0]?.project_id ?? '');
      })
      .catch((error: unknown) => {
        if (!(error instanceof DOMException && error.name === 'AbortError')) { setOptions({ projects: [], resources: [] }); setProjectId((current) => current ?? ''); }
      });
    return () => controller.abort();
  }, [canSeeMembers]);

  const refresh = useCallback((signal?: AbortSignal) => {
    if (projectId === null) return;
    getTimeline({ project_id: projectId || undefined, resource_id: resourceId || undefined }, signal)
      .then((data) => setLoad({ state: 'ready', data }))
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === 'AbortError') return;
        setLoad({ state: 'error', message: error instanceof ApiError && !isApiUnreachable(error) ? error.message : 'Pastikan API dan basis data sudah berjalan.' });
      });
  }, [projectId, resourceId]);

  useEffect(() => {
    const controller = new AbortController();
    setLoad({ state: 'loading' });
    refresh(controller.signal);
    return () => controller.abort();
  }, [refresh]);

  const data = load.state === 'ready' ? load.data : null;
  const projects = useMemo(() => {
    if (!data) return [];
    if (!lateOnly) return data.projects;
    return data.projects
      .map((project) => ({ ...project, phases: project.phases.map((phase) => ({ ...phase, tasks: phase.tasks.filter((t) => t.is_late) })).filter((phase) => phase.tasks.length > 0) }))
      .filter((project) => project.phases.length > 0);
  }, [data, lateOnly]);

  const scale = useMemo(() => {
    if (!data) return null;
    const dates = [data.as_of];
    for (const project of projects) {
      dates.push(project.start_date, project.target_launch_date);
      if (project.actual_launch_date) dates.push(project.actual_launch_date);
      for (const phase of project.phases) for (const task of phase.tasks) {
        dates.push(task.planned_start, task.planned_finish);
        if (task.actual_start) dates.push(task.actual_start);
        if (task.actual_finish) dates.push(task.actual_finish);
      }
    }
    return projects.length ? makeScale(dates, DAY_WIDTH) : null;
  }, [data, projects]);

  const eventsByTask = useMemo(() => {
    const map = new Map<string, TimelineEvent[]>();
    for (const event of data?.events ?? []) {
      const key = event.affected_task_id ?? `project:${event.project_id}`;
      map.set(key, [...(map.get(key) ?? []), event]);
    }
    return map;
  }, [data]);

  const taskCount = projects.reduce((sum, p) => sum + p.phases.reduce((n, ph) => n + ph.tasks.length, 0), 0);
  const lateCount = data ? data.projects.reduce((sum, p) => sum + p.late_count, 0) : 0;
  const toggle = (key: string) => setCollapsed((current) => { const next = new Set(current); if (next.has(key)) next.delete(key); else next.add(key); return next; });

  return (
    <section className="module-panel" aria-labelledby="timeline-title">
      <div className="panel-heading">
        <div>
          <h2 id="timeline-title">Timeline proyek</h2>
          <p className="panel-subtitle">Rencana dan aktual per task, dikelompokkan per proyek dan phase.{data && ` Posisi per ${fmt(data.as_of)}.`}</p>
        </div>
      </div>

      <div className="panel-toolbar">
        {data ? <p className="toolbar-summary"><strong>{taskCount}</strong> task{lateOnly ? ' terlambat' : ''} · <strong className={lateCount ? 'text-danger' : ''}>{lateCount}</strong> lewat rencana · <strong>{data.events.length}</strong> kejadian</p> : <span />}
        <div className="workload-filters">
          <label className="visually-hidden" htmlFor="timeline-project">Filter proyek</label>
          <select id="timeline-project" className="workload-select" value={projectId ?? ''} disabled={!options} onChange={(e) => setProjectId(e.target.value)}>
            <option value="">Semua proyek</option>
            {options?.projects.map((p) => <option key={p.project_id} value={p.project_id}>{p.project_name}</option>)}
          </select>
          {canSeeMembers && <>
            <label className="visually-hidden" htmlFor="timeline-resource">Filter anggota</label>
            <select id="timeline-resource" className="workload-select" value={resourceId} disabled={!options} onChange={(e) => setResourceId(e.target.value)}>
              <option value="">Semua anggota</option>
              {options?.resources.map((r) => <option key={r.resource_id} value={r.resource_id}>{r.resource_name}</option>)}
            </select>
          </>}
          <label className="checkbox" htmlFor="timeline-late">
            <input id="timeline-late" type="checkbox" checked={lateOnly} onChange={(e) => setLateOnly(e.target.checked)} />
            <span>Terlambat saja</span>
          </label>
        </div>
      </div>

      {load.state === 'loading' && <div className="empty-state"><p>Memuat timeline…</p></div>}
      {load.state === 'error' && (
        <div className="empty-state">
          <h3>Timeline belum bisa dimuat</h3>
          <p>{load.message}</p>
          <button type="button" className="button button-ghost" onClick={() => { setLoad({ state: 'loading' }); refresh(); }}>Coba lagi</button>
        </div>
      )}
      {data && !scale && (
        <div className="empty-state">
          <h3>{lateOnly ? 'Tidak ada task yang terlambat' : 'Belum ada task untuk ditampilkan'}</h3>
          <p>{lateOnly || resourceId || projectId ? 'Ubah atau kosongkan filter di atas.' : 'Task masuk dari impor Project Plan.'}</p>
        </div>
      )}

      {data && scale && (
        <>
          <div className="gantt" style={{ '--gantt-width': `${scale.width}px` } as React.CSSProperties}>
            <div className="gantt-row gantt-head">
              <div className="gantt-label">Task</div>
              <div className="gantt-track" aria-hidden="true">
                {monthSegments(scale).map((m) => <span key={m.key} className="gantt-month" style={{ left: m.left, width: m.width }}>{monthName.format(Date.UTC(m.year, m.month, 1))}</span>)}
              </div>
            </div>
            <div className="gantt-body">
              <Backdrop scale={scale} data={data} />
              {projects.map((project) => {
                const closed = collapsed.has(project.project_id);
                return (
                  <div key={project.project_id} className="gantt-group">
                    <ProjectRow project={project} scale={scale} closed={closed} events={eventsByTask.get(`project:${project.project_id}`) ?? []} onToggle={() => toggle(project.project_id)} />
                    {!closed && project.phases.map((phase) => {
                      const key = `${project.project_id}/${phase.phase}`;
                      const phaseClosed = collapsed.has(key);
                      const late = phase.tasks.filter((t) => t.is_late).length;
                      return (
                        <div key={key}>
                          <div className="gantt-row gantt-phase">
                            <div className="gantt-label">
                              <button type="button" className="gantt-toggle" aria-expanded={!phaseClosed} onClick={() => toggle(key)}>
                                <span className="gantt-caret" aria-hidden="true">{phaseClosed ? '▸' : '▾'}</span>
                                <span className="gantt-toggle-text">
                                  {PHASE_LABEL[phase.phase] ?? phase.phase}
                                  <small>{phase.tasks.length} task{late > 0 && <span className="text-danger"> · {late} terlambat</span>}</small>
                                </span>
                              </button>
                            </div>
                            <div className="gantt-track" />
                          </div>
                          {!phaseClosed && phase.tasks.map((task) => <TaskRow key={task.task_id} task={task} scale={scale} asOf={data.as_of} events={eventsByTask.get(task.task_id) ?? []} />)}
                        </div>
                      );
                    })}
                  </div>
                );
              })}
            </div>
          </div>
          <p className="calendar-legend gantt-legend">
            <span><span className="legend-swatch gantt-swatch-planned" />Rencana</span>
            <span><span className="legend-swatch gantt-swatch-actual" />Aktual</span>
            <span><span className="legend-swatch gantt-swatch-late" />Lewat rencana</span>
            <span><span className="legend-swatch gantt-swatch-open" />Masih berjalan</span>
            <span><span className="gantt-event event-change_request legend-event" />CR / prioritas</span>
            <span><span className="gantt-event event-blocker legend-event" />Blocker / overrun</span>
            <span><span className="gantt-event event-hotfix legend-event" />Hotfix</span>
            <span><span className="legend-swatch legend-holiday" />Hari libur</span>
            <span><span className="legend-swatch gantt-swatch-today" />Hari ini</span>
          </p>
        </>
      )}
    </section>
  );
}

/** Garis hari libur dan hari ini di belakang semua baris (DIG-179). */
function Backdrop({ scale, data }: { scale: Scale; data: Timeline }) {
  return (
    <div className="gantt-backdrop" aria-hidden="true">
      {data.holidays.filter((h) => inScale(scale, h.holiday_date)).map((h) => (
        <span key={h.holiday_date} className="gantt-holiday" title={`${h.holiday_name}, ${fmt(h.holiday_date)}`} style={{ left: offsetOf(scale, h.holiday_date), width: scale.dayWidth }} />
      ))}
      {inScale(scale, data.as_of) && <span className="gantt-today" style={{ left: offsetOf(scale, data.as_of) }} />}
    </div>
  );
}

function EventMarkers({ events, scale }: { events: TimelineEvent[]; scale: Scale }) {
  return <>
    {events.filter((e) => inScale(scale, e.event_date)).map((event) => {
      const label = `${EVENT_LABEL[event.event_type] ?? event.event_type} ${event.event_id}, ${fmt(event.event_date)}`;
      return <span key={event.event_id} className={`gantt-event event-${event.event_type}`} role="img" aria-label={label} title={label} style={{ left: offsetOf(scale, event.event_date) + scale.dayWidth / 2 }} />;
    })}
  </>;
}

type ProjectRowProps = { project: TimelineProject; scale: Scale; closed: boolean; events: TimelineEvent[]; onToggle: () => void };

function ProjectRow({ project, scale, closed, events, onToggle }: ProjectRowProps) {
  const bar = barOf(scale, project.start_date, project.target_launch_date);
  const label = `${project.project_name}: ${fmt(project.start_date)} s.d. target ${fmt(project.target_launch_date)}${project.actual_launch_date ? `, rilis ${fmt(project.actual_launch_date)}` : ''}`;
  return (
    <div className="gantt-row gantt-project">
      <div className="gantt-label">
        <button type="button" className="gantt-toggle" aria-expanded={!closed} onClick={onToggle}>
          <span className="gantt-caret" aria-hidden="true">{closed ? '▸' : '▾'}</span>
          <span className="gantt-toggle-text">
            {project.project_name}
            <small>{project.task_count} task{project.late_count > 0 && <span className="text-danger"> · {project.late_count} terlambat</span>}</small>
          </span>
        </button>
      </div>
      <div className="gantt-track">
        <span className="gantt-bar bar-project" role="img" aria-label={label} title={label} style={{ left: bar.left, width: bar.width }} />
        {project.actual_launch_date && inScale(scale, project.actual_launch_date) && <span className="gantt-launch" title={`Rilis ${fmt(project.actual_launch_date)}`} style={{ left: offsetOf(scale, project.actual_launch_date) + scale.dayWidth / 2 }} />}
        <EventMarkers events={events} scale={scale} />
      </div>
    </div>
  );
}

function TaskRow({ task, scale, asOf, events }: { task: TimelineTask; scale: Scale; asOf: string; events: TimelineEvent[] }) {
  const planned = barOf(scale, task.planned_start, task.planned_finish);
  const actual = task.status === 'dropped' && !task.actual_finish && task.actual_start ? { ...barOf(scale, task.actual_start, task.actual_start), open: false } : actualBarOf(scale, task.actual_start, task.actual_finish, asOf);
  const text = describeTask(task);
  return (
    <div className={`gantt-row gantt-task ${task.is_late ? 'is-late' : ''} ${task.status === 'dropped' ? 'is-dropped' : ''}`}>
      <div className="gantt-label" title={text}>
        <span className="gantt-task-name">{task.task_name}</span>
        <small className="text-data">{task.task_id}{task.assignees.length > 0 && ` · ${task.assignees.join(', ')}`}{task.is_late && <span className="text-danger"> · +{task.delay_days} hari</span>}</small>
      </div>
      <div className="gantt-track" role="img" aria-label={text}>
        <span className="gantt-bar bar-planned" title={`Rencana ${fmt(task.planned_start)} s.d. ${fmt(task.planned_finish)}`} style={{ left: planned.left, width: planned.width }} />
        {actual && <span className={`gantt-bar bar-actual ${task.is_late ? 'bar-late' : ''} ${actual.open ? 'bar-open' : ''}`} title={`Aktual ${fmt(task.actual_start)} s.d. ${actual.open ? 'sekarang' : fmt(task.actual_finish ?? task.actual_start)}`} style={{ left: actual.left, width: actual.width }} />}
        <EventMarkers events={events} scale={scale} />
      </div>
    </div>
  );
}
