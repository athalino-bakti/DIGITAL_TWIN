import { useCallback, useEffect, useMemo, useState } from 'react';
import { ApiError } from '../../../shared/api/client';
import { ProjectForm } from './ProjectForm';
import { createProject, deleteProject, listProjects, STATUS_LABEL, updateProject, type Project, type ProjectInput, type ProjectStatus } from './api';

type Filter = 'all' | 'active' | ProjectStatus;
const FILTERS: { key: Filter; label: string }[] = [
  { key: 'all', label: 'Semua' },
  { key: 'active', label: 'Aktif' },
  { key: 'on_hold', label: 'Ditunda' },
  { key: 'released', label: 'Rilis' },
];

const dateFormat = new Intl.DateTimeFormat('id-ID', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' });
const formatDate = (value: string | null) => (value ? dateFormat.format(new Date(`${value}T00:00:00Z`)) : '—');

type Load = { state: 'loading' } | { state: 'error' } | { state: 'ready'; projects: Project[] };

export function ProjectsPanel() {
  const [load, setLoad] = useState<Load>({ state: 'loading' });
  const [filter, setFilter] = useState<Filter>('all');
  const [editing, setEditing] = useState<Project | 'new' | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const [notice, setNotice] = useState<{ tone: 'success' | 'danger'; text: string } | null>(null);

  const refresh = useCallback((signal?: AbortSignal) => {
    listProjects(signal)
      .then((projects) => setLoad({ state: 'ready', projects }))
      .catch((error: unknown) => { if (!(error instanceof DOMException && error.name === 'AbortError')) setLoad({ state: 'error' }); });
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    refresh(controller.signal);
    return () => controller.abort();
  }, [refresh]);

  const projects = useMemo(() => (load.state === 'ready' ? load.projects : []), [load]);
  const visible = projects.filter((p) => filter === 'all' || (filter === 'active' ? p.is_active : p.status === filter));
  const activeCount = projects.filter((p) => p.is_active).length;
  const overdueCount = projects.filter((p) => p.is_overdue).length;

  async function save(input: ProjectInput) {
    const saved = editing === 'new' || editing === null ? await createProject(input) : await updateProject(editing.project_id, input);
    setEditing(null);
    setNotice({ tone: 'success', text: `${saved.project_id} ${saved.project_name} tersimpan.` });
    refresh();
  }

  async function remove(project: Project) {
    try {
      await deleteProject(project.project_id);
      setNotice({ tone: 'success', text: `${project.project_id} dihapus.` });
      refresh();
    } catch (error) {
      setNotice({ tone: 'danger', text: error instanceof ApiError ? error.message : 'API belum terhubung. Coba lagi.' });
    } finally {
      setConfirmDelete(null);
    }
  }

  return (
    <section className="module-panel" aria-labelledby="projects-title">
      <div className="panel-heading">
        <div>
          <h2 id="projects-title">Proyek</h2>
          <p className="panel-subtitle">D-01 projects. Urut dari prioritas tertinggi.</p>
        </div>
        <button type="button" className="button" onClick={() => { setNotice(null); setEditing('new'); }}>Tambah proyek</button>
      </div>

      {load.state === 'ready' && projects.length > 0 && (
        <div className="panel-toolbar">
          <div className="segmented" role="group" aria-label="Saring proyek">
            {FILTERS.map((item) => (
              <button key={item.key} type="button" aria-pressed={filter === item.key} className={filter === item.key ? 'active' : ''} onClick={() => setFilter(item.key)}>{item.label}</button>
            ))}
          </div>
          <p className="toolbar-summary"><strong>{activeCount}</strong> aktif · <strong className={overdueCount ? 'text-danger' : ''}>{overdueCount}</strong> lewat target</p>
        </div>
      )}

      {notice && <p className={`inline-notice ${notice.tone}`} role="status">{notice.text}<button type="button" className="link-button" onClick={() => setNotice(null)}>Tutup</button></p>}

      {load.state === 'loading' && <div className="empty-state"><p>Memuat proyek…</p></div>}
      {load.state === 'error' && (
        <div className="empty-state">
          <h3>Daftar proyek belum bisa dimuat</h3>
          <p>Pastikan API dan basis data sudah berjalan.</p>
          <button type="button" className="button button-ghost" onClick={() => { setLoad({ state: 'loading' }); refresh(); }}>Coba lagi</button>
        </div>
      )}
      {load.state === 'ready' && projects.length === 0 && (
        <div className="empty-state">
          <h3>Belum ada proyek</h3>
          <p>Tambahkan proyek pertama beserta prioritas dan target launching-nya.</p>
        </div>
      )}
      {load.state === 'ready' && projects.length > 0 && visible.length === 0 && (
        <div className="empty-state"><p>Tidak ada proyek dengan filter ini.</p></div>
      )}

      {visible.length > 0 && (
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th scope="col" className="num">Prioritas</th>
                <th scope="col">Proyek</th>
                <th scope="col">Pemilik proses</th>
                <th scope="col">Mulai</th>
                <th scope="col">Target</th>
                <th scope="col">Aktual</th>
                <th scope="col">Status</th>
                <th scope="col">DoR</th>
                <th scope="col"><span className="visually-hidden">Aksi</span></th>
              </tr>
            </thead>
            <tbody>
              {visible.map((project) => (
                <tr key={project.project_id}>
                  <td className="num text-data">{project.priority_rank}</td>
                  <td className="cell-project">
                    <strong className="cell-title">{project.project_name}</strong>
                    <span className="text-data cell-sub">{project.project_id}</span>
                  </td>
                  <td>{project.process_owner}</td>
                  <td className="nowrap">{formatDate(project.start_date)}</td>
                  <td className="nowrap">
                    {formatDate(project.target_launch_date)}
                    {project.is_overdue && <span className="status-pill danger">Lewat target</span>}
                  </td>
                  <td className="nowrap">{formatDate(project.actual_launch_date)}</td>
                  <td><span className={`status-pill status-${project.status}`}>{STATUS_LABEL[project.status]}</span></td>
                  <td>{project.dor_fulfilled ? 'Ya' : 'Belum'}</td>
                  <td>
                    <div className="row-actions">
                    {confirmDelete === project.project_id ? (
                      <>
                        <span className="text-body-sm">Hapus?</span>
                        <button type="button" className="button button-ghost button-danger" onClick={() => remove(project)}>Ya, hapus</button>
                        <button type="button" className="button button-ghost" onClick={() => setConfirmDelete(null)}>Batal</button>
                      </>
                    ) : (
                      <>
                        <button type="button" className="button button-ghost" onClick={() => { setNotice(null); setEditing(project); }}>Ubah</button>
                        <button type="button" className="button button-ghost" aria-label={`Hapus ${project.project_id}`} onClick={() => setConfirmDelete(project.project_id)}>Hapus</button>
                      </>
                    )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {editing !== null && <ProjectForm project={editing === 'new' ? null : editing} onSubmit={save} onClose={() => setEditing(null)} />}
    </section>
  );
}
