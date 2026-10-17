import { FormEvent, useState } from 'react';
import { Navigate, NavLink, useParams } from 'react-router-dom';
import { apiGet, apiPost } from '../../shared/api/client';

type Baseline = { id: number; project_id: number; name: string; status: string; created_at: string };
type TimelineItem = { task_id: number; task_name: string; start_date: string; end_date: string; duration_days: number; priority: number };
type ResourceLoadItem = { resource_id: number; resource_name: string; total_allocation_percent: number };
type DependencyItem = {
  predecessor_task_id: number;
  predecessor_task_name: string;
  successor_task_id: number;
  successor_task_name: string;
  kind: string;
};

const views = {
  timeline: 'Timeline',
  resource: 'Beban Resource',
  dependency: 'Dependency',
} as const;

export function DigitalTwinPage() {
  const { view = 'timeline' } = useParams();
  if (!Object.hasOwn(views, view)) return <Navigate to="/digital-twin/timeline" replace />;

  const [projectId, setProjectId] = useState('');
  const [baselineId, setBaselineId] = useState('');
  const [requestState, setRequestState] = useState<'idle' | 'loading' | 'success' | 'error'>('idle');
  const [error, setError] = useState('');
  const [baseline, setBaseline] = useState<Baseline | null>(null);
  const [timeline, setTimeline] = useState<TimelineItem[]>([]);
  const [resourceLoad, setResourceLoad] = useState<ResourceLoadItem[]>([]);
  const [dependencies, setDependencies] = useState<DependencyItem[]>([]);

  async function createBaseline(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const value = Number(projectId);
    if (!Number.isInteger(value) || value <= 0) return;
    setRequestState('loading');
    setError('');
    try {
      const created = await apiPost<Baseline, { project_id: number; name: string }>('/digital-twin/baselines', {
        project_id: value,
        name: `Baseline project ${value}`,
      });
      setBaseline(created);
      setBaselineId(String(created.id));
      setRequestState('success');
    } catch (reason) {
      setRequestState('error');
      setError(reason instanceof Error ? reason.message : 'Gagal membuat baseline');
    }
  }

  async function loadCurrentView() {
    const id = Number(baselineId);
    if (!Number.isInteger(id) || id <= 0) return;
    setRequestState('loading');
    setError('');
    try {
      if (view === 'timeline') {
        setTimeline(await apiGet<TimelineItem[]>(`/digital-twin/${id}/timeline`));
      } else if (view === 'resource') {
        setResourceLoad(await apiGet<ResourceLoadItem[]>(`/digital-twin/${id}/resource-load`));
      } else {
        setDependencies(await apiGet<DependencyItem[]>(`/digital-twin/${id}/dependencies`));
      }
      setRequestState('success');
    } catch (reason) {
      setRequestState('error');
      setError(reason instanceof Error ? reason.message : 'Gagal memuat data digital twin');
    }
  }

  return (
    <>
      <section className="module-panel" aria-label="Baseline builder">
        <div className="panel-heading">
          <h2>Baseline Digital Twin</h2>
          <span className="subtle-badge">Tahap 2</span>
        </div>
        <form className="form-panel" onSubmit={createBaseline}>
          <label>
            Project ID
            <input value={projectId} onChange={(event) => setProjectId(event.target.value)} placeholder="contoh: 1" />
          </label>
          <button type="submit" disabled={requestState === 'loading'}>Buat baseline</button>
        </form>
        <div className="form-panel compact">
          <label>
            Baseline ID
            <input value={baselineId} onChange={(event) => setBaselineId(event.target.value)} placeholder="contoh: 1" />
          </label>
          <button type="button" onClick={() => void loadCurrentView()} disabled={requestState === 'loading'}>
            {requestState === 'loading' ? 'Memuat…' : `Muat ${views[view as keyof typeof views]}`}
          </button>
        </div>
        {baseline && <p className="info-text">Baseline {baseline.id} dibuat untuk project {baseline.project_id}.</p>}
        {error && <p className="error-text">{error}</p>}
      </section>

      <nav className="tabs" aria-label="Tampilan Digital Twin">
        {Object.entries(views).map(([key, label]) => (
          <NavLink key={key} to={`/digital-twin/${key}`} className={({ isActive }) => isActive ? 'tab active' : 'tab'}>
            {label}
          </NavLink>
        ))}
      </nav>

      {view === 'timeline' && (
        <section className="module-panel table-panel">
          <h3>Timeline</h3>
          {timeline.length === 0 ? <p className="empty-inline">Belum ada data timeline.</p> : (
            <table>
              <thead><tr><th>Task</th><th>Mulai</th><th>Selesai</th><th>Durasi</th></tr></thead>
              <tbody>{timeline.map((item) => <tr key={item.task_id}><td>{item.task_name}</td><td>{item.start_date}</td><td>{item.end_date}</td><td>{item.duration_days}</td></tr>)}</tbody>
            </table>
          )}
        </section>
      )}

      {view === 'resource' && (
        <section className="module-panel table-panel">
          <h3>Beban resource</h3>
          {resourceLoad.length === 0 ? <p className="empty-inline">Belum ada data beban resource.</p> : (
            <table>
              <thead><tr><th>Resource</th><th>Total alokasi (%)</th></tr></thead>
              <tbody>{resourceLoad.map((item) => <tr key={item.resource_id}><td>{item.resource_name}</td><td>{item.total_allocation_percent.toFixed(2)}</td></tr>)}</tbody>
            </table>
          )}
        </section>
      )}

      {view === 'dependency' && (
        <section className="module-panel table-panel">
          <h3>Dependency</h3>
          {dependencies.length === 0 ? <p className="empty-inline">Belum ada data dependency.</p> : (
            <table>
              <thead><tr><th>Predecessor</th><th>Successor</th><th>Jenis</th></tr></thead>
              <tbody>{dependencies.map((item) => <tr key={`${item.predecessor_task_id}-${item.successor_task_id}`}><td>{item.predecessor_task_name}</td><td>{item.successor_task_name}</td><td>{item.kind}</td></tr>)}</tbody>
            </table>
          )}
        </section>
      )}
    </>
  );
}
