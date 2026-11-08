import { useCallback, useEffect, useState } from 'react';
import { ApiError } from '../../../shared/api/client';
import { ResourceForm } from './ResourceForm';
import { createResource, deleteResource, listResources, listRoles, SENIORITY_LABEL, updateResource, type Resource, type ResourceInput, type Role } from './api';

type Load = { state: 'loading' } | { state: 'error' } | { state: 'ready'; resources: Resource[]; roles: Role[] };

const dateFormat = new Intl.DateTimeFormat('id-ID', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' });
const formatDate = (value: string) => dateFormat.format(new Date(`${value}T00:00:00Z`));

/** "1 thn 3 bln", "4 bln", atau "12 hari" dari jumlah hari sejak bergabung. */
function formatTenure(days: number): string {
  if (days < 0) return 'Belum bergabung';
  if (days < 31) return `${days} hari`;
  const months = Math.floor(days / 30.44);
  const years = Math.floor(months / 12);
  const rest = months % 12;
  if (!years) return `${months} bln`;
  return rest ? `${years} thn ${rest} bln` : `${years} thn`;
}

export function ResourcesPanel() {
  const [load, setLoad] = useState<Load>({ state: 'loading' });
  const [editing, setEditing] = useState<Resource | 'new' | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const [notice, setNotice] = useState<{ tone: 'success' | 'danger'; text: string } | null>(null);

  const refresh = useCallback((signal?: AbortSignal) => {
    Promise.all([listResources(signal), listRoles(signal)])
      .then(([resources, roles]) => setLoad({ state: 'ready', resources, roles }))
      .catch((error: unknown) => { if (!(error instanceof DOMException && error.name === 'AbortError')) setLoad({ state: 'error' }); });
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    refresh(controller.signal);
    return () => controller.abort();
  }, [refresh]);

  const resources = load.state === 'ready' ? load.resources : [];
  const roles = load.state === 'ready' ? load.roles : [];
  const roleName = (id: string) => roles.find((role) => role.role_id === id)?.role_name ?? id;
  const onboardingCount = resources.filter((r) => r.is_onboarding).length;

  async function save(input: ResourceInput) {
    const saved = editing === 'new' || editing === null ? await createResource(input) : await updateResource(editing.resource_id, input);
    setEditing(null);
    setNotice({ tone: 'success', text: `${saved.resource_id} ${saved.resource_name} tersimpan.` });
    refresh();
  }

  async function remove(resource: Resource) {
    try {
      await deleteResource(resource.resource_id);
      setNotice({ tone: 'success', text: `${resource.resource_id} dihapus.` });
      refresh();
    } catch (error) {
      setNotice({ tone: 'danger', text: error instanceof ApiError ? error.message : 'API belum terhubung. Coba lagi.' });
    } finally {
      setConfirmDelete(null);
    }
  }

  return (
    <section className="module-panel" aria-labelledby="resources-title">
      <div className="panel-heading">
        <div>
          <h2 id="resources-title">Anggota</h2>
          <p className="panel-subtitle">D-02 resources. Peran utama, peran rangkap, dan masa onboarding.</p>
        </div>
        <button type="button" className="button" disabled={load.state !== 'ready'} onClick={() => { setNotice(null); setEditing('new'); }}>Tambah anggota</button>
      </div>

      {load.state === 'ready' && resources.length > 0 && (
        <div className="panel-toolbar">
          <p className="toolbar-summary"><strong>{resources.length}</strong> anggota · <strong>{onboardingCount}</strong> masa onboarding (kurang dari 90 hari)</p>
        </div>
      )}

      {notice && <p className={`inline-notice ${notice.tone}`} role="status">{notice.text}<button type="button" className="link-button" onClick={() => setNotice(null)}>Tutup</button></p>}

      {load.state === 'loading' && <div className="empty-state"><p>Memuat anggota…</p></div>}
      {load.state === 'error' && (
        <div className="empty-state">
          <h3>Daftar anggota belum bisa dimuat</h3>
          <p>Pastikan API dan basis data sudah berjalan.</p>
          <button type="button" className="button button-ghost" onClick={() => { setLoad({ state: 'loading' }); refresh(); }}>Coba lagi</button>
        </div>
      )}
      {load.state === 'ready' && resources.length === 0 && (
        <div className="empty-state">
          <h3>Belum ada anggota</h3>
          <p>Tambahkan anggota tim beserta peran utama dan peran rangkapnya.</p>
        </div>
      )}

      {resources.length > 0 && (
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th scope="col">Anggota</th>
                <th scope="col">Peran utama</th>
                <th scope="col">Peran rangkap</th>
                <th scope="col">Senioritas</th>
                <th scope="col">Bergabung</th>
                <th scope="col">Lintas peran</th>
                <th scope="col"><span className="visually-hidden">Aksi</span></th>
              </tr>
            </thead>
            <tbody>
              {resources.map((resource) => (
                <tr key={resource.resource_id}>
                  <td className="cell-project">
                    <strong className="cell-title">{resource.resource_name}</strong>
                    <span className="text-data cell-sub">{resource.resource_id}</span>
                  </td>
                  <td>{roleName(resource.primary_role_id)}</td>
                  <td>
                    {resource.secondary_role_ids.length
                      ? <span className="chip-list">{resource.secondary_role_ids.map((id) => <span key={id} className="status-pill">{roleName(id)}</span>)}</span>
                      : <span className="text-muted">—</span>}
                  </td>
                  <td>{SENIORITY_LABEL[resource.seniority]}</td>
                  <td className="nowrap">
                    {formatDate(resource.join_date)}
                    <span className="cell-sub">{formatTenure(resource.tenure_days)}</span>
                    {resource.is_onboarding && <span className="status-pill status-planning">Onboarding</span>}
                  </td>
                  <td>{resource.cross_role_capable ? 'Ya' : 'Tidak'}</td>
                  <td>
                    <div className="row-actions">
                      {confirmDelete === resource.resource_id ? (
                        <>
                          <span className="text-body-sm">Hapus?</span>
                          <button type="button" className="button button-ghost button-danger" onClick={() => remove(resource)}>Ya, hapus</button>
                          <button type="button" className="button button-ghost" onClick={() => setConfirmDelete(null)}>Batal</button>
                        </>
                      ) : (
                        <>
                          <button type="button" className="button button-ghost" onClick={() => { setNotice(null); setEditing(resource); }}>Ubah</button>
                          <button type="button" className="button button-ghost" aria-label={`Hapus ${resource.resource_id}`} onClick={() => setConfirmDelete(resource.resource_id)}>Hapus</button>
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

      {editing !== null && <ResourceForm resource={editing === 'new' ? null : editing} roles={roles} onSubmit={save} onClose={() => setEditing(null)} />}
    </section>
  );
}
