import { Navigate, NavLink, useParams } from 'react-router-dom';
import { ModulePlaceholder } from '../../shared/components/ModulePlaceholder';

const views = {
  timeline: { label: 'Timeline', title: 'Timeline proyek', description: 'Jadwal dan ringkasan proyek akan ditampilkan setelah model baseline tersedia.', areas: ['Gantt proyek', 'Fase iterasi', 'Ringkasan proyek'] },
  resource: { label: 'Beban Resource', title: 'Beban resource', description: 'Alokasi dan kapasitas resource akan ditampilkan setelah model baseline tersedia.', areas: ['Beban per minggu', 'Resource overload', 'Beban non-proyek'] },
  dependency: { label: 'Dependency', title: 'Dependency graph', description: 'Hubungan antar task akan ditampilkan setelah model baseline tersedia.', areas: ['Hard dependency', 'Soft dependency', 'Critical path'] },
} as const;

export function DigitalTwinPage() {
  const { view = 'timeline' } = useParams();
  if (!Object.hasOwn(views, view)) return <Navigate to="/digital-twin/timeline" replace />;
  const selected = views[view as keyof typeof views];
  return <>
    <section className="metric-grid" aria-label="Ringkasan baseline">
      {['Proyek aktif', 'Proyek lewat target', 'Resource overload', 'Resource multi-role'].map((label, index) => <article className={`metric-card metric-${index}`} key={label}><h2>{label}</h2><strong>—</strong><p>Data belum tersedia</p></article>)}
    </section>
    <nav className="tabs" aria-label="Tampilan Digital Twin">
      {Object.entries(views).map(([key, item]) => <NavLink key={key} to={`/digital-twin/${key}`} className={({ isActive }) => isActive ? 'tab active' : 'tab'}>{item.label}{key === 'dependency' && <span className="optional-badge">opsional</span>}</NavLink>)}
    </nav>
    <ModulePlaceholder title={selected.title} description={selected.description} areas={selected.areas} />
  </>;
}
