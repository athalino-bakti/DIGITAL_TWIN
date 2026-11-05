import { Navigate, NavLink, useParams } from 'react-router-dom';
import { ModulePlaceholder } from '../../shared/components/ModulePlaceholder';
import { ProjectsPanel } from './projects/ProjectsPanel';

const views = {
  proyek: { label: 'Proyek' },
  impor: { label: 'Impor dataset' },
} as const;

export function DataPage() {
  const { view = 'proyek' } = useParams();
  if (!Object.hasOwn(views, view)) return <Navigate to="/data/proyek" replace />;
  return <>
    <nav className="tabs" aria-label="Tampilan Data">
      {Object.entries(views).map(([key, item]) => <NavLink key={key} to={`/data/${key}`} className={({ isActive }) => isActive ? 'tab active' : 'tab'}>{item.label}</NavLink>)}
    </nav>
    {view === 'proyek'
      ? <ProjectsPanel />
      : <ModulePlaceholder title="Impor dataset" description="Unggah Project Plan, ekspor Trello, dan riwayat commit akan tersedia di sini." areas={['Unggah dataset CSV', 'Kualitas data', 'Baris ditolak']} />}
  </>;
}
