import { Navigate, NavLink, useParams } from 'react-router-dom';
import { useAuth } from '../../shared/auth/AuthProvider';
import { allowed } from '../../shared/auth/permissions';
import { ModulePlaceholder } from '../../shared/components/ModulePlaceholder';
import { AvailabilityPanel } from './availability/AvailabilityPanel';
import { HolidaysPanel } from './availability/HolidaysPanel';
import { ChangeEventsPanel } from './changes/ChangeEventsPanel';
import { ComplexityPanel } from './complexity/ComplexityPanel';
import { MyTasksPanel } from './my-tasks/MyTasksPanel';
import { ProjectsPanel } from './projects/ProjectsPanel';
import { ResourcesPanel } from './resources/ResourcesPanel';
import { RolesPanel } from './resources/RolesPanel';
import { dataViews } from './views';
import { WorkloadPanel } from './workload/WorkloadPanel';

export function DataPage() {
  const { view } = useParams();
  const { user } = useAuth();
  const views = allowed(dataViews, user);
  if (views.length === 0) return null; // tidak terjadi: /data sudah dijaga RequirePermission
  // Tab yang tidak dikenal atau tidak boleh dibuka dialihkan ke tab pertama yang boleh.
  if (!views.some((item) => item.key === view)) return <Navigate to={`/data/${views[0].key}`} replace />;
  return <>
    <nav className="tabs" aria-label="Tampilan Data">
      {views.map((item) => <NavLink key={item.key} to={`/data/${item.key}`} className={({ isActive }) => isActive ? 'tab active' : 'tab'}>{item.label}</NavLink>)}
    </nav>
    {view === 'proyek' && <ProjectsPanel />}
    {view === 'anggota' && <ResourcesPanel />}
    {view === 'peran' && <RolesPanel />}
    {view === 'beban' && <WorkloadPanel />}
    {view === 'perubahan' && <ChangeEventsPanel />}
    {view === 'kompleksitas' && <ComplexityPanel />}
    {view === 'ketersediaan' && <AvailabilityPanel />}
    {view === 'libur' && <HolidaysPanel />}
    {view === 'impor' && <ModulePlaceholder title="Impor dataset" description="Unggah Project Plan, ekspor Trello, dan riwayat commit akan tersedia di sini." areas={['Unggah dataset CSV', 'Kualitas data', 'Baris ditolak']} />}
    {view === 'task-saya' && <MyTasksPanel />}
  </>;
}
