import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { ApiError } from '../../../shared/api/client';
import { listRoles, updateRole, type Role } from './api';

type Load = { state: 'loading' } | { state: 'error' } | { state: 'ready'; roles: Role[] };
type Errors = { capacity_reference?: string; description?: string; form?: string };

const number = new Intl.NumberFormat('id-ID', { maximumFractionDigits: 2 });
const parse = (value: string) => (value.trim() === '' ? Number.NaN : Number(value.replace(',', '.')));

export function RolesPanel() {
  const [load, setLoad] = useState<Load>({ state: 'loading' });
  const [editing, setEditing] = useState<string | null>(null);
  const [capacity, setCapacity] = useState('');
  const [description, setDescription] = useState('');
  const [errors, setErrors] = useState<Errors>({});
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const refresh = useCallback((signal?: AbortSignal) => {
    listRoles(signal)
      .then((roles) => setLoad({ state: 'ready', roles }))
      .catch((error: unknown) => { if (!(error instanceof DOMException && error.name === 'AbortError')) setLoad({ state: 'error' }); });
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    refresh(controller.signal);
    return () => controller.abort();
  }, [refresh]);

  function startEdit(role: Role) {
    setNotice(null);
    setErrors({});
    setEditing(role.role_id);
    setCapacity(String(role.capacity_reference).replace('.', ','));
    setDescription(role.description ?? '');
  }

  async function save(event: FormEvent, role: Role) {
    event.preventDefault();
    const value = parse(capacity);
    if (!Number.isFinite(value) || value <= 0) {
      setErrors({ capacity_reference: 'Isi angka lebih dari 0' });
      return;
    }
    setSaving(true);
    try {
      const saved = await updateRole(role.role_id, { capacity_reference: value, description });
      setEditing(null);
      setNotice(`${saved.role_name} (${saved.role_id}) tersimpan.`);
      refresh();
    } catch (error) {
      if (error instanceof ApiError) {
        const fields = error.fieldErrors();
        setErrors(Object.keys(fields).length ? fields : { form: error.message });
      } else {
        setErrors({ form: 'API belum terhubung. Periksa koneksi lalu coba lagi.' });
      }
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="module-panel" aria-labelledby="roles-title">
      <div className="panel-heading">
        <div>
          <h2 id="roles-title">Peran</h2>
          <p className="panel-subtitle">D-03 roles. Kapasitas acuan adalah jumlah task paralel wajar per anggota (default 3).</p>
        </div>
      </div>

      {notice && <p className="inline-notice success" role="status">{notice}<button type="button" className="link-button" onClick={() => setNotice(null)}>Tutup</button></p>}

      {load.state === 'loading' && <div className="empty-state"><p>Memuat peran…</p></div>}
      {load.state === 'error' && (
        <div className="empty-state">
          <h3>Daftar peran belum bisa dimuat</h3>
          <p>Pastikan API dan basis data sudah berjalan.</p>
          <button type="button" className="button button-ghost" onClick={() => { setLoad({ state: 'loading' }); refresh(); }}>Coba lagi</button>
        </div>
      )}

      {load.state === 'ready' && (
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th scope="col">Peran</th>
                <th scope="col" className="num">Kapasitas acuan</th>
                <th scope="col">Deskripsi</th>
                <th scope="col" className="num">Anggota</th>
                <th scope="col"><span className="visually-hidden">Aksi</span></th>
              </tr>
            </thead>
            <tbody>
              {load.roles.map((role) => editing === role.role_id ? (
                <tr key={role.role_id} className="row-editing">
                  <td className="cell-project">
                    <strong className="cell-title">{role.role_name}</strong>
                    <span className="text-data cell-sub">{role.role_id}</span>
                  </td>
                  <td className="num">
                    <input form={`role-${role.role_id}`} className="cell-input" type="text" inputMode="decimal" aria-label={`Kapasitas acuan ${role.role_name}`}
                      aria-invalid={errors.capacity_reference ? true : undefined} value={capacity}
                      onChange={(e) => { setCapacity(e.target.value); setErrors({}); }} />
                    {errors.capacity_reference && <span className="field-error cell-error">{errors.capacity_reference}</span>}
                  </td>
                  <td>
                    <textarea form={`role-${role.role_id}`} className="cell-textarea" rows={3} maxLength={1000} aria-label={`Deskripsi ${role.role_name}`}
                      value={description} onChange={(e) => { setDescription(e.target.value); setErrors({}); }} />
                    {errors.description && <span className="field-error cell-error">{errors.description}</span>}
                  </td>
                  <td className="num text-data">{role.resource_count}</td>
                  <td>
                    <form id={`role-${role.role_id}`} className="row-actions" onSubmit={(e) => save(e, role)} noValidate>
                      <button type="submit" className="button" disabled={saving}>{saving ? 'Menyimpan…' : 'Simpan'}</button>
                      <button type="button" className="button button-ghost" disabled={saving} onClick={() => setEditing(null)}>Batal</button>
                    </form>
                    {errors.form && <span className="field-error cell-error" role="alert">{errors.form}</span>}
                  </td>
                </tr>
              ) : (
                <tr key={role.role_id}>
                  <td className="cell-project">
                    <strong className="cell-title">{role.role_name}</strong>
                    <span className="text-data cell-sub">{role.role_id}</span>
                  </td>
                  <td className="num text-data">{number.format(role.capacity_reference)}</td>
                  <td className="cell-description">{role.description ?? <span className="text-muted">—</span>}</td>
                  <td className="num text-data">{role.resource_count}</td>
                  <td>
                    <div className="row-actions">
                      <button type="button" className="button button-ghost" disabled={editing !== null} onClick={() => startEdit(role)}>Ubah</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
