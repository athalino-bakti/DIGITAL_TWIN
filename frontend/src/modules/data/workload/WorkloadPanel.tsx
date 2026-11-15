import { useCallback, useEffect, useState } from 'react';
import { NavLink } from 'react-router-dom';
import { ApiError } from '../../../shared/api/client';
import { useCan } from '../../../shared/auth/usePermission';
import { PERM } from '../../../shared/auth/permissions';
import { listProjects, type Project } from '../projects/api';
import { listResources, type Resource } from '../resources/api';
import { WorkloadForm } from './WorkloadForm';
import { WorkloadImport } from './WorkloadImport';
import { createWorkload, deleteWorkload, ITEM_TYPE_LABEL, ITEM_TYPES, listWorkload, SEVERITY_LABEL, STATUS_LABEL, updateWorkload, type ImportResult, type ItemType, type WorkloadInput, type WorkloadItem } from './api';

type Load = { state: 'loading' } | { state: 'error' } | { state: 'ready'; items: WorkloadItem[]; resources: Resource[]; projects: Project[] };
type Filters = { resource_id: string; item_type: ItemType | ''; open_only: boolean };

const dateFormat = new Intl.DateTimeFormat('id-ID', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' });
const formatDate = (value: string | null) => (value ? dateFormat.format(new Date(`${value}T00:00:00Z`)) : '');

export function WorkloadPanel() {
  const [filters, setFilters] = useState<Filters>({ resource_id: '', item_type: '', open_only: false });
  const [load, setLoad] = useState<Load>({ state: 'loading' });
  const canWrite = useCan(PERM.masterDataWrite);
  const canImport = useCan(PERM.importRun);
  const [editing, setEditing] = useState<WorkloadItem | 'new' | null>(null);
  const [importing, setImporting] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const [notice, setNotice] = useState<{ tone: 'success' | 'danger'; text: string } | null>(null);

  const refresh = useCallback((signal?: AbortSignal) => {
    Promise.all([listWorkload(filters, signal), listResources(signal), listProjects(signal)])
      .then(([items, resources, projects]) => setLoad({ state: 'ready', items, resources, projects }))
      .catch((error: unknown) => { if (!(error instanceof DOMException && error.name === 'AbortError')) setLoad({ state: 'error' }); });
  }, [filters]);

  useEffect(() => {
    const controller = new AbortController();
    refresh(controller.signal);
    return () => controller.abort();
  }, [refresh]);

  const ready = load.state === 'ready';
  const items = ready ? load.items : [];
  const resources = ready ? load.resources : [];
  const projects = ready ? load.projects : [];
  const openCount = items.filter((item) => item.status !== 'resolved').length;
  const hotfixCount = items.filter((item) => item.is_hotfix).length;
  const filtered = Boolean(filters.resource_id || filters.item_type || filters.open_only);

  async function save(input: WorkloadInput) {
    const saved = editing === 'new' || editing === null ? await createWorkload(input) : await updateWorkload(editing.item_id, input);
    setEditing(null);
    setNotice({ tone: 'success', text: `${saved.item_id} ${saved.resource_name} tersimpan.` });
    refresh();
  }

  async function remove(item: WorkloadItem) {
    try {
      await deleteWorkload(item.item_id);
      setNotice({ tone: 'success', text: `${item.item_id} dihapus.` });
      refresh();
    } catch (error) {
      setNotice({ tone: 'danger', text: error instanceof ApiError ? error.message : 'API belum terhubung. Coba lagi.' });
    } finally {
      setConfirmDelete(null);
    }
  }

  function imported(result: ImportResult) {
    setImporting(false);
    setNotice({ tone: 'success', text: `Impor selesai: ${result.inserted} item baru, ${result.updated} item diperbarui.` });
    refresh();
  }

  const setFilter = <K extends keyof Filters>(key: K, value: Filters[K]) => setFilters((current) => ({ ...current, [key]: value }));

  return (
    <section className="module-panel" aria-labelledby="workload-title">
      <div className="panel-heading panel-heading-wrap">
        <div>
          <h2 id="workload-title">Beban non-proyek</h2>
          <p className="panel-subtitle">D-08 workload_items. Tiket dan pekerjaan operasional yang ikut menyita kapasitas anggota di luar task proyek.</p>
        </div>
        <div className="row-actions">
          {canImport && <button type="button" className="button button-ghost" disabled={!ready || resources.length === 0} onClick={() => { setNotice(null); setImporting(true); }}>Impor CSV</button>}
          {canWrite && <button type="button" className="button" disabled={!ready || resources.length === 0} onClick={() => { setNotice(null); setEditing('new'); }}>Tambah item</button>}
        </div>
      </div>

      <div className="panel-toolbar">
        {ready ? <p className="toolbar-summary"><strong>{items.length}</strong> item{filtered ? ' sesuai filter' : ''} · <strong>{openCount}</strong> belum selesai · <strong>{hotfixCount}</strong> hotfix</p> : <span />}
        <div className="workload-filters">
          <label className="visually-hidden" htmlFor="workload-filter-resource">Filter anggota</label>
          <select id="workload-filter-resource" className="workload-select" value={filters.resource_id} disabled={!ready && load.state !== 'error'} onChange={(e) => setFilter('resource_id', e.target.value)}>
            <option value="">Semua anggota</option>
            {resources.map((r) => <option key={r.resource_id} value={r.resource_id}>{r.resource_name}</option>)}
          </select>
          <label className="visually-hidden" htmlFor="workload-filter-type">Filter jenis</label>
          <select id="workload-filter-type" className="workload-select" value={filters.item_type} onChange={(e) => setFilter('item_type', e.target.value as ItemType | '')}>
            <option value="">Semua jenis</option>
            {ITEM_TYPES.map((type) => <option key={type} value={type}>{ITEM_TYPE_LABEL[type]}</option>)}
          </select>
          <label className="checkbox" htmlFor="workload-filter-open">
            <input id="workload-filter-open" type="checkbox" checked={filters.open_only} onChange={(e) => setFilter('open_only', e.target.checked)} />
            <span>Belum selesai saja</span>
          </label>
        </div>
      </div>

      {notice && <p className={`inline-notice ${notice.tone}`} role="status">{notice.text}<button type="button" className="link-button" onClick={() => setNotice(null)}>Tutup</button></p>}

      {load.state === 'loading' && <div className="empty-state"><p>Memuat beban non-proyek…</p></div>}
      {load.state === 'error' && (
        <div className="empty-state">
          <h3>Data belum bisa dimuat</h3>
          <p>Pastikan API dan basis data sudah berjalan.</p>
          <button type="button" className="button button-ghost" onClick={() => { setLoad({ state: 'loading' }); refresh(); }}>Coba lagi</button>
        </div>
      )}
      {ready && resources.length === 0 && (
        <div className="empty-state">
          <h3>Belum ada anggota</h3>
          <p>Beban non-proyek dicatat per anggota. Tambahkan anggota dulu di tab <NavLink to="/data/anggota">Anggota</NavLink>.</p>
        </div>
      )}
      {ready && resources.length > 0 && items.length === 0 && (
        <div className="empty-state">
          <h3>{filtered ? 'Tidak ada item yang sesuai filter' : 'Belum ada beban non-proyek'}</h3>
          <p>{filtered ? 'Ubah atau kosongkan filter di atas.' : 'Tambahkan tiket atau pekerjaan operasional satu per satu, atau impor dari CSV D-08.'}</p>
        </div>
      )}

      {items.length > 0 && (
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th scope="col">Item</th>
                <th scope="col">Anggota</th>
                <th scope="col">Aplikasi</th>
                <th scope="col">Diterima</th>
                <th scope="col">Mulai</th>
                <th scope="col">Selesai</th>
                <th scope="col">Status</th>
                <th scope="col"><span className="visually-hidden">Aksi</span></th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.item_id}>
                  <td className="cell-project">
                    <strong className="cell-title">
                      {ITEM_TYPE_LABEL[item.item_type]}
                      {item.severity && <span className={`status-pill severity severity-${item.severity}`}>{SEVERITY_LABEL[item.severity]}</span>}
                      {item.is_hotfix && <span className="status-pill danger">Hotfix</span>}
                    </strong>
                    <span className="text-data cell-sub">{item.item_id}</span>
                  </td>
                  <td>{item.resource_name}<span className="text-data cell-sub">{item.resource_id}</span></td>
                  <td>{item.project_name ?? <span className="text-muted">Tidak terkait</span>}{item.related_project_id && <span className="text-data cell-sub">{item.related_project_id}</span>}</td>
                  <td className="nowrap">{formatDate(item.received_date)}</td>
                  <td className="nowrap">{formatDate(item.started_date)}</td>
                  <td className="nowrap">{formatDate(item.resolved_date)}</td>
                  <td><span className={`status-pill workload-${item.status}`}>{STATUS_LABEL[item.status]}</span></td>
                  <td>
                    {canWrite && <div className="row-actions">
                      {confirmDelete === item.item_id ? (
                        <>
                          <span className="text-body-sm">Hapus?</span>
                          <button type="button" className="button button-ghost button-danger" onClick={() => remove(item)}>Ya, hapus</button>
                          <button type="button" className="button button-ghost" onClick={() => setConfirmDelete(null)}>Batal</button>
                        </>
                      ) : (
                        <>
                          <button type="button" className="button button-ghost" onClick={() => { setNotice(null); setEditing(item); }}>Ubah</button>
                          <button type="button" className="button button-ghost" aria-label={`Hapus ${item.item_id}`} onClick={() => setConfirmDelete(item.item_id)}>Hapus</button>
                        </>
                      )}
                    </div>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {editing !== null && <WorkloadForm item={editing === 'new' ? null : editing} resources={resources} projects={projects} onSubmit={save} onClose={() => setEditing(null)} />}
      {importing && <WorkloadImport onImported={imported} onClose={() => setImporting(false)} />}
    </section>
  );
}
