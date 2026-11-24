import { Navigate, NavLink, useParams } from 'react-router-dom';
import { ModulePlaceholder } from '../../shared/components/ModulePlaceholder';
import { DependencyPanel } from './dependency/DependencyPanel';
import { ProcessMapPanel } from './process-map/ProcessMapPanel';
import { TimelinePanel } from './timeline/TimelinePanel';
import { SummaryCards } from './summary/SummaryCards';

const views = {
  timeline: { label: 'Timeline', title: 'Timeline proyek', description: 'Jadwal dan ringkasan proyek akan ditampilkan setelah model baseline tersedia.', areas: ['Gantt proyek', 'Fase iterasi', 'Ringkasan proyek'] },
  resource: { label: 'Beban Resource', title: 'Beban resource', description: 'Alokasi dan kapasitas resource akan ditampilkan setelah model baseline tersedia.', areas: ['Beban per minggu', 'Resource overload', 'Beban non-proyek'] },
  dependency: { label: 'Dependency', title: 'Dependency graph', description: 'Hubungan antar task akan ditampilkan setelah model baseline tersedia.', areas: ['Hard dependency', 'Soft dependency', 'Critical path'] },
  process: { label: 'Process Map', title: 'Process map', description: 'Alur kerja aktual dari event log.', areas: ['Directly-follows graph', 'Filter frekuensi', 'Durasi antar aktivitas'] },
} as const;

export function DigitalTwinPage() {
  const { view = 'timeline' } = useParams();
  if (!Object.hasOwn(views, view)) return <Navigate to="/digital-twin/timeline" replace />;
  const selected = views[view as keyof typeof views];
  return <>
    <SummaryCards />
    <nav className="tabs" aria-label="Tampilan Digital Twin">
      {Object.entries(views).map(([key, item]) => <NavLink key={key} to={`/digital-twin/${key}`} className={({ isActive }) => isActive ? 'tab active' : 'tab'}>{item.label}</NavLink>)}
    </nav>
    {view === 'timeline' ? <TimelinePanel /> : view === 'dependency' ? <DependencyPanel /> : view === 'process' ? <ProcessMapPanel /> : <ModulePlaceholder title={selected.title} description={selected.description} areas={selected.areas} />}
  </>;
}
