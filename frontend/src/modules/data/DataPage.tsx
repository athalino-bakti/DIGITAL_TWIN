import { Navigate, NavLink, useParams } from 'react-router-dom';
import { useAuth } from '../../shared/auth/AuthProvider';
import { allowed } from '../../shared/auth/permissions';
import { AliasesPanel } from './aliases/AliasesPanel';
import { AvailabilityPanel } from './availability/AvailabilityPanel';
import { HolidaysPanel } from './availability/HolidaysPanel';
import { ChangeEventsPanel } from './changes/ChangeEventsPanel';
import { ComplexityPanel } from './complexity/ComplexityPanel';
import { ProjectPlanImportPanel } from './imports/ProjectPlanImportPanel';
import { MyTasksPanel } from './my-tasks/MyTasksPanel';
import { ProjectsPanel } from './projects/ProjectsPanel';
import { TrelloListsPanel } from './trello-lists/TrelloListsPanel';
import { ResourcesPanel } from './resources/ResourcesPanel';
import { RolesPanel } from './resources/RolesPanel';
import { TasksPanel } from './tasks/TasksPanel';
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
    {view === 'task' && <TasksPanel />}
    {view === 'beban' && <WorkloadPanel />}
    {view === 'perubahan' && <ChangeEventsPanel />}
    {view === 'kompleksitas' && <ComplexityPanel />}
    {view === 'ketersediaan' && <AvailabilityPanel />}
    {view === 'libur' && <HolidaysPanel />}
    {view === 'impor' && <ProjectPlanImportPanel />}
    {view === 'alias' && <AliasesPanel />}
    {view === 'trello' && <TrelloListsPanel />}
    {view === 'task-saya' && <MyTasksPanel />}
  </>;
}
