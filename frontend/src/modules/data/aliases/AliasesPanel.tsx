import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from 'react';
import { ApiError } from '../../../shared/api/client';
import { formatLong } from '../availability/dates';
import { listResources, type Resource } from '../resources/api';
import {
  ALIAS_HINT, createAlias, deleteAlias, IDENTITY_SOURCES, listAliases, listUnmapped, SOURCE_LABEL, updateAlias,
  type AliasInput, type IdentitySource, type ResourceAlias, type UnmappedIdentity,
} from './api';
import { aliasCount, aliasError, identityLabel, suggestResource } from './rules';

type Data = { aliases: ResourceAlias[]; unmapped: UnmappedIdentity[]; resources: Resource[] };
type Load = { state: 'loading' } | { state: 'error' } | { state: 'ready'; data: Data };
type Notice = { tone: 'success' | 'danger'; text: string };

const failure = (error: unknown) => error instanceof ApiError ? error.message : 'API belum terhubung. Coba lagi.';
const day = (iso: string) => formatLong(iso.slice(0, 10));

/** Tab Alias identitas (DIG-112): memetakan identitas Trello, TeamGit, dan Project Plan ke D-02. */
export function AliasesPanel() {
  const [load, setLoad] = useState<Load>({ state: 'loading' });
  const [source, setSource] = useState<IdentitySource | ''>('');
  const [notice, setNotice] = useState<Notice | null>(null);
  const [adding, setAdding] = useState(false);

  const refresh = useCallback((signal?: AbortSignal) => {
    Promise.all([listAliases(signal), listUnmapped(signal), listResources(signal)])
      .then(([aliases, unmapped, resources]) => setLoad({ state: 'ready', data: { aliases, unmapped, resources } }))
      .catch((error: unknown) => { if (!(error instanceof DOMException && error.name === 'AbortError')) setLoad({ state: 'error' }); });
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    refresh(controller.signal);
    return () => controller.abort();
  }, [refresh]);

  const data = load.state === 'ready' ? load.data : null;
  const names = useMemo(() => new Map((data?.resources ?? []).map((r) => [r.resource_id, r.resource_name])), [data]);
  const unmapped = (data?.unmapped ?? []).filter((item) => !source || item.source === source);
  const aliases = (data?.aliases ?? []).filter((item) => !source || item.source === source);
  const withoutAlias = data ? data.resources.filter((r) => !aliasCount(data.aliases).has(r.resource_id)).length : 0;

  async function run(action: () => Promise<unknown>, success: string) {
    try {
      await action();
      setNotice({ tone: 'success', text: success });
      refresh();
    } catch (error) {
      setNotice({ tone: 'danger', text: failure(error) });
      throw error;
    }
  }

  return (
    <section className="module-panel" aria-labelledby="aliases-title">
      <div className="panel-heading">
        <div>
          <h2 id="aliases-title">Alias identitas</h2>
          <p className="panel-subtitle">Tabel internal J&amp;C resource_alias. Petakan akun Trello, email commit TeamGit, dan nama PIC Project Plan ke anggota di D-02 agar impor mengenali pelakunya.</p>
        </div>
        <button type="button" className="button alias-add" disabled={!data} onClick={() => { setNotice(null); setAdding(true); }}>Tambah alias</button>
      </div>

      <div className="panel-toolbar">
        <div className="toolbar-filters">
          <label className="visually-hidden" htmlFor="aliases-source">Filter sumber</label>
          <select id="aliases-source" className="toolbar-select" value={source} onChange={(e) => setSource(e.target.value as IdentitySource | '')}>
            <option value="">Semua sumber</option>
            {IDENTITY_SOURCES.map((s) => <option key={s} value={s}>{SOURCE_LABEL[s]}</option>)}
          </select>
        </div>
        {data && <p className="toolbar-summary"><strong>{unmapped.length}</strong> belum terpetakan · <strong>{aliases.length}</strong> alias · <strong>{withoutAlias}</strong> anggota tanpa alias</p>}
      </div>

      {notice && <p className={`inline-notice ${notice.tone}`} role="status">{notice.text}<button type="button" className="link-button" onClick={() => setNotice(null)}>Tutup</button></p>}

      {load.state === 'loading' && <div className="empty-state"><p>Memuat alias identitas…</p></div>}
      {load.state === 'error' && (
        <div className="empty-state">
          <h3>Alias identitas belum bisa dimuat</h3>
          <p>Pastikan API dan basis data sudah berjalan.</p>
          <button type="button" className="button button-ghost" onClick={() => { setLoad({ state: 'loading' }); refresh(); }}>Coba lagi</button>
        </div>
      )}

      {data && <>
        <h3 className="alias-section-title">Belum terpetakan</h3>
        {unmapped.length === 0 ? (
          <p className="alias-empty">Semua identitas di data staging sudah dipetakan. Identitas baru muncul di sini setelah impor berikutnya.</p>
        ) : (
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th scope="col">Identitas</th>
                  <th scope="col">Sumber</th>
                  <th scope="col" className="num">Kemunculan</th>
                  <th scope="col">Terakhir muncul</th>
                  <th scope="col">Anggota</th>
                </tr>
              </thead>
              <tbody>
                {unmapped.map((item) => (
                  <UnmappedRow
                    key={`${item.source}:${item.alias_key}`}
                    item={item}
                    resources={data.resources}
                    onMap={(resource_id) => run(
                      () => createAlias({ resource_id, source: item.source, alias: item.alias, alias_ref: item.alias_ref, username: item.username, display_name: item.display_name }),
                      `${identityLabel(item)} dipetakan ke ${names.get(resource_id) ?? resource_id}.`,
                    )}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}

        <h3 className="alias-section-title">Sudah terpetakan</h3>
        {aliases.length === 0 ? (
          <p className="alias-empty">Belum ada alias{source ? ` untuk ${SOURCE_LABEL[source]}` : ''}.</p>
        ) : (
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th scope="col">Anggota</th>
                  <th scope="col">Sumber</th>
                  <th scope="col">Alias</th>
                  <th scope="col">Dipetakan</th>
                  <th scope="col"><span className="visually-hidden">Aksi</span></th>
                </tr>
              </thead>
              <tbody>
                {aliases.map((alias) => (
                  <AliasRow
                    key={alias.alias_id}
                    alias={alias}
                    resources={data.resources}
                    name={names.get(alias.resource_id) ?? alias.resource_id}
                    onMove={(resource_id) => run(() => updateAlias(alias.alias_id, resource_id), `${identityLabel(alias)} dipindah ke ${names.get(resource_id) ?? resource_id}.`)}
                    onDelete={() => run(() => deleteAlias(alias.alias_id), `Alias ${identityLabel(alias)} dihapus dan kembali ke daftar belum terpetakan bila masih ada di staging.`)}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </>}

      {adding && data && (
        <AliasForm
          resources={data.resources}
          onClose={() => setAdding(false)}
          onSubmit={async (input) => {
            await createAlias(input);
            setAdding(false);
            setNotice({ tone: 'success', text: `Alias ${input.alias} dipetakan ke ${names.get(input.resource_id) ?? input.resource_id}.` });
            refresh();
          }}
        />
      )}
    </section>
  );
}

function ResourceSelect({ id, label, value, resources, onChange, disabled }: { id: string; label: string; value: string; resources: readonly Resource[]; onChange: (value: string) => void; disabled?: boolean }) {
  return <>
    <label className="visually-hidden" htmlFor={id}>{label}</label>
    <select id={id} className="toolbar-select" value={value} disabled={disabled} onChange={(e) => onChange(e.target.value)}>
      <option value="">Pilih anggota</option>
      {resources.map((r) => <option key={r.resource_id} value={r.resource_id}>{r.resource_name} ({r.resource_id})</option>)}
    </select>
  </>;
}

function UnmappedRow({ item, resources, onMap }: { item: UnmappedIdentity; resources: readonly Resource[]; onMap: (resourceId: string) => Promise<void> }) {
  const suggested = useMemo(() => suggestResource(item, resources), [item, resources]);
  const [choice, setChoice] = useState(suggested ?? '');
  const [saving, setSaving] = useState(false);
  const id = `unmapped-${item.source}-${item.alias_key}`.replace(/[^a-zA-Z0-9-]/g, '-');

  async function map() {
    setSaving(true);
    try { await onMap(choice); } catch { setSaving(false); }
  }

  return (
    <tr>
      <td>
        {identityLabel(item)}
        <span className="text-data cell-sub">{item.username && item.display_name ? `@${item.username} · ` : ''}{item.alias}</span>
      </td>
      <td><span className="status-pill">{SOURCE_LABEL[item.source]}</span></td>
      <td className="num text-data">{item.occurrences}</td>
      <td className="nowrap">{day(item.last_seen)}</td>
      <td>
        <div className="row-actions">
          <ResourceSelect id={id} label={`Anggota untuk ${identityLabel(item)}`} value={choice} resources={resources} onChange={setChoice} disabled={saving} />
          <button type="button" className="button button-ghost" disabled={!choice || saving} onClick={map}>{saving ? 'Menyimpan…' : 'Petakan'}</button>
        </div>
        {suggested && choice === suggested && <span className="field-hint">Usulan dari kemiripan nama, periksa sebelum memetakan</span>}
      </td>
    </tr>
  );
}

type AliasRowProps = {
  alias: ResourceAlias;
  resources: readonly Resource[];
  name: string;
  onMove: (resourceId: string) => Promise<void>;
  onDelete: () => Promise<void>;
};

function AliasRow({ alias, resources, name, onMove, onDelete }: AliasRowProps) {
  const [mode, setMode] = useState<'view' | 'move' | 'delete'>('view');
  const [choice, setChoice] = useState(alias.resource_id);
  const [saving, setSaving] = useState(false);

  async function act(action: () => Promise<void>) {
    setSaving(true);
    try { await action(); } catch { setSaving(false); }
  }

  return (
    <tr>
      <td>
        {mode === 'move' ? (
          <ResourceSelect id={`alias-move-${alias.alias_id}`} label={`Anggota baru untuk ${identityLabel(alias)}`} value={choice} resources={resources} onChange={setChoice} disabled={saving} />
        ) : (
          <>{name}<span className="text-data cell-sub">{alias.resource_id}</span></>
        )}
      </td>
      <td><span className="status-pill">{SOURCE_LABEL[alias.source]}</span></td>
      <td>
        {identityLabel(alias)}
        <span className="text-data cell-sub">{alias.alias}</span>
      </td>
      <td className="nowrap">{day(alias.updated_at)}</td>
      <td>
        <div className="row-actions">
          {mode === 'view' && <>
            <button type="button" className="button button-ghost" onClick={() => setMode('move')}>Pindahkan</button>
            <button type="button" className="button button-ghost" aria-label={`Hapus alias ${identityLabel(alias)}`} onClick={() => setMode('delete')}>Hapus</button>
          </>}
          {mode === 'move' && <>
            <button type="button" className="button button-ghost" disabled={saving || !choice || choice === alias.resource_id} onClick={() => act(() => onMove(choice))}>{saving ? 'Menyimpan…' : 'Simpan'}</button>
            <button type="button" className="button button-ghost" disabled={saving} onClick={() => { setChoice(alias.resource_id); setMode('view'); }}>Batal</button>
          </>}
          {mode === 'delete' && <>
            <span className="text-body-sm">Hapus?</span>
            <button type="button" className="button button-ghost button-danger" disabled={saving} onClick={() => act(onDelete)}>Ya, hapus</button>
            <button type="button" className="button button-ghost" disabled={saving} onClick={() => setMode('view')}>Batal</button>
          </>}
        </div>
      </td>
    </tr>
  );
}

type Errors = { resource_id?: string; alias?: string; form?: string };

function AliasForm({ resources, onSubmit, onClose }: { resources: readonly Resource[]; onSubmit: (input: AliasInput) => Promise<void>; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [source, setSource] = useState<IdentitySource>('teamgit');
  const [alias, setAlias] = useState('');
  const [resourceId, setResourceId] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [errors, setErrors] = useState<Errors>({});
  const [saving, setSaving] = useState(false);

  useEffect(() => { dialog.current?.showModal(); }, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const found: Errors = {};
    const aliasProblem = aliasError(source, alias);
    if (aliasProblem) found.alias = aliasProblem;
    if (!resourceId) found.resource_id = 'Pilih anggota';
    setErrors(found);
    if (Object.keys(found).length) return;
    setSaving(true);
    try {
      await onSubmit({ source, alias: alias.trim(), resource_id: resourceId, display_name: displayName.trim() || null });
    } catch (error) {
      if (error instanceof ApiError) {
        const fields = error.fieldErrors();
        setErrors({ alias: fields.alias, resource_id: fields.resource_id, form: fields.alias || fields.resource_id ? undefined : error.message });
      } else {
        setErrors({ form: 'API belum terhubung. Periksa koneksi lalu coba lagi.' });
      }
      setSaving(false);
    }
  }

  const describe = (key: 'alias' | 'resource_id') => ({
    'aria-invalid': errors[key] ? true : undefined,
    'aria-describedby': errors[key] ? `alias-${key}-error` : `alias-${key}-hint`,
  });

  return (
    <dialog ref={dialog} className="dialog dialog-narrow" aria-labelledby="alias-form-title" onCancel={(event) => { event.preventDefault(); if (!saving) onClose(); }}>
      <form onSubmit={submit} noValidate>
        <div className="dialog-heading">
          <h2 id="alias-form-title">Tambah alias</h2>
        </div>
        <div className="dialog-body form-grid">
          {errors.form && <p className="form-alert" role="alert">{errors.form}</p>}
          <label className="field" htmlFor="alias-source">
            <span>Sumber</span>
            <select id="alias-source" value={source} onChange={(e) => { setSource(e.target.value as IdentitySource); setErrors({}); }}>
              {IDENTITY_SOURCES.map((s) => <option key={s} value={s}>{SOURCE_LABEL[s]}</option>)}
            </select>
          </label>
          <label className="field" htmlFor="alias-value">
            <span>Alias</span>
            <input id="alias-value" value={alias} maxLength={200} onChange={(e) => { setAlias(e.target.value); setErrors({}); }} {...describe('alias')} />
            {errors.alias ? <span className="field-error" id="alias-alias-error">{errors.alias}</span> : <span className="field-hint" id="alias-alias-hint">{ALIAS_HINT[source]}</span>}
          </label>
          <label className="field" htmlFor="alias-display">
            <span>Nama tampilan (opsional)</span>
            <input id="alias-display" value={displayName} maxLength={200} onChange={(e) => setDisplayName(e.target.value)} />
          </label>
          <label className="field" htmlFor="alias-resource">
            <span>Anggota</span>
            <select id="alias-resource" value={resourceId} onChange={(e) => { setResourceId(e.target.value); setErrors({}); }} {...describe('resource_id')}>
              <option value="">Pilih anggota</option>
              {resources.map((r) => <option key={r.resource_id} value={r.resource_id}>{r.resource_name} ({r.resource_id})</option>)}
            </select>
            {errors.resource_id ? <span className="field-error" id="alias-resource_id-error">{errors.resource_id}</span> : <span className="field-hint" id="alias-resource_id-hint">Satu anggota boleh punya beberapa alias</span>}
          </label>
        </div>
        <div className="dialog-actions">
          <button type="button" className="button button-ghost" onClick={onClose} disabled={saving}>Batal</button>
          <button type="submit" className="button" disabled={saving}>{saving ? 'Menyimpan…' : 'Simpan'}</button>
        </div>
      </form>
    </dialog>
  );
}
