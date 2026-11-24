import { useCallback, useEffect, useState } from 'react';
import { ApiError } from '../../../shared/api/client';
import { formatLong } from '../availability/dates';
import { TASK_STATUS_LABEL } from '../changes/api';
import { PHASE_LABEL } from '../../digital-twin/timeline/api';
import { listTrelloLists, rebuildEventLog, TASK_PHASES, TASK_STATUSES, updateTrelloList, type Mapping, type TaskPhase, type TaskStatus, type TrelloList } from './api';
import { groupByBoard, listKey, sameMapping, suggestMapping } from './rules';

type Load = { state: 'loading' } | { state: 'error' } | { state: 'ready'; lists: TrelloList[] };
type Notice = { tone: 'success' | 'danger'; text: string; rebuild?: boolean };

const failure = (error: unknown) => error instanceof ApiError ? error.message : 'API belum terhubung. Coba lagi.';
const saved = (list: TrelloList): Mapping => ({ status: list.status, phase: list.phase });

/**
 * Tab Pemetaan Trello (DIG-120): list Trello per papan dipetakan ke status dan phase task.
 * Event log memakai status ini untuk aktivitas perpindahan kartu, jadi setelah menyimpan admin
 * ditawari membentuk ulang event log.
 */
export function TrelloListsPanel() {
  const [load, setLoad] = useState<Load>({ state: 'loading' });
  const [drafts, setDrafts] = useState<Record<string, Mapping>>({});
  const [unmappedOnly, setUnmappedOnly] = useState(false);
  const [saving, setSaving] = useState(false);
  const [rebuilding, setRebuilding] = useState(false);
  const [notice, setNotice] = useState<Notice | null>(null);

  const refresh = useCallback((signal?: AbortSignal) => {
    listTrelloLists(signal)
      .then((lists) => setLoad({ state: 'ready', lists }))
      .catch((error: unknown) => { if (!(error instanceof DOMException && error.name === 'AbortError')) setLoad({ state: 'error' }); });
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    refresh(controller.signal);
    return () => controller.abort();
  }, [refresh]);

  const lists = load.state === 'ready' ? load.lists : [];
  const current = (list: TrelloList) => drafts[listKey(list)] ?? saved(list);
  const changed = lists.filter((list) => drafts[listKey(list)] && !sameMapping(drafts[listKey(list)], saved(list)));
  const unmapped = lists.filter((list) => list.status === null);
  const suggestable = unmapped.filter((list) => !drafts[listKey(list)] && suggestMapping(list.list_name).status !== null);
  const shown = unmappedOnly ? lists.filter((list) => list.status === null || drafts[listKey(list)]) : lists;

  function edit(list: TrelloList, patch: Partial<Mapping>) {
    setDrafts((all) => ({ ...all, [listKey(list)]: { ...current(list), ...patch } }));
  }

  function applySuggestions() {
    setDrafts((all) => {
      const next = { ...all };
      for (const list of suggestable) {
        const guess = suggestMapping(list.list_name);
        next[listKey(list)] = { status: guess.status, phase: list.phase ?? guess.phase };
      }
      return next;
    });
    setNotice({ tone: 'success', text: `${suggestable.length} list diisi dari usulan nama. Periksa lalu simpan.` });
  }

  async function saveAll() {
    setSaving(true);
    setNotice(null);
    const results = await Promise.allSettled(changed.map((list) => updateTrelloList(list, drafts[listKey(list)])));
    const failed = results.flatMap((result, i) => result.status === 'rejected' ? [[changed[i], result.reason] as const] : []);
    setDrafts((all) => {
      const next = { ...all };
      results.forEach((result, i) => { if (result.status === 'fulfilled') delete next[listKey(changed[i])]; });
      return next;
    });
    const ok = results.length - failed.length;
    if (failed.length) {
      const [list, reason] = failed[0];
      setNotice({ tone: 'danger', text: `${ok} list tersimpan, ${failed.length} gagal (${list.list_name}: ${failure(reason)}).`, rebuild: ok > 0 });
    } else {
      setNotice({ tone: 'success', text: `${ok} list tersimpan. Bentuk ulang event log supaya perpindahan kartu memakai pemetaan baru.`, rebuild: true });
    }
    setSaving(false);
    refresh();
  }

  async function rebuild() {
    setRebuilding(true);
    try {
      const report = await rebuildEventLog();
      setNotice({ tone: 'success', text: `Event log dibentuk ulang: ${report.events} event dari ${report.cases} task.` });
    } catch (error) {
      setNotice({ tone: 'danger', text: failure(error), rebuild: true });
    } finally {
      setRebuilding(false);
    }
  }

  return (
    <section className="module-panel" aria-labelledby="trello-lists-title">
      <div className="panel-heading">
        <div>
          <h2 id="trello-lists-title">Pemetaan list Trello</h2>
          <p className="panel-subtitle">Tabel internal J&amp;C trello_list_mapping. Tentukan status dan phase task untuk tiap list, agar perpindahan kartu terbaca di event log dan Process Map. List baru muncul otomatis setelah impor Trello.</p>
        </div>
        <div className="row-actions">
          <button type="button" className="button button-ghost trello-nowrap" disabled={suggestable.length === 0 || saving} onClick={applySuggestions}>Isi dari usulan{suggestable.length ? ` (${suggestable.length})` : ''}</button>
          <button type="button" className="button trello-nowrap" disabled={changed.length === 0 || saving} onClick={saveAll}>{saving ? 'Menyimpan…' : `Simpan${changed.length ? ` ${changed.length} perubahan` : ''}`}</button>
        </div>
      </div>

      <div className="panel-toolbar">
        <label className="checkbox" htmlFor="trello-unmapped">
          <input id="trello-unmapped" type="checkbox" checked={unmappedOnly} onChange={(e) => setUnmappedOnly(e.target.checked)} />
          <span>Hanya yang belum dipetakan</span>
        </label>
        {load.state === 'ready' && <p className="toolbar-summary"><strong>{lists.length}</strong> list · <strong>{unmapped.length}</strong> belum dipetakan</p>}
      </div>

      {notice && (
        <p className={`inline-notice ${notice.tone}`} role="status">
          <span>{notice.text}</span>
          <span className="row-actions">
            {notice.rebuild && <button type="button" className="link-button" disabled={rebuilding} onClick={rebuild}>{rebuilding ? 'Membentuk ulang…' : 'Bentuk ulang event log'}</button>}
            <button type="button" className="link-button" onClick={() => setNotice(null)}>Tutup</button>
          </span>
        </p>
      )}

      {load.state === 'loading' && <div className="empty-state"><p>Memuat list Trello…</p></div>}
      {load.state === 'error' && (
        <div className="empty-state">
          <h3>List Trello belum bisa dimuat</h3>
          <p>Pastikan API dan basis data sudah berjalan.</p>
          <button type="button" className="button button-ghost" onClick={() => { setLoad({ state: 'loading' }); refresh(); }}>Coba lagi</button>
        </div>
      )}
      {load.state === 'ready' && lists.length === 0 && (
        <div className="empty-state">
          <h3>Belum ada list Trello</h3>
          <p>List papan terdaftar otomatis saat ekspor Trello diimpor.</p>
        </div>
      )}
      {load.state === 'ready' && lists.length > 0 && shown.length === 0 && <p className="trello-empty">Semua list sudah dipetakan.</p>}

      {groupByBoard(shown).map((board) => (
        <div key={board.board_id}>
          <h3 className="trello-board-title">{board.board_name ?? 'Papan tanpa nama'} <span className="text-data cell-sub">{board.board_id}</span></h3>
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th scope="col">List</th>
                  <th scope="col" className="num">Aktivitas</th>
                  <th scope="col">Terakhir dipakai</th>
                  <th scope="col">Status task</th>
                  <th scope="col">Phase</th>
                </tr>
              </thead>
              <tbody>
                {board.lists.map((list) => {
                  const value = current(list);
                  const dirty = !sameMapping(value, saved(list));
                  const id = listKey(list).replace('/', '-');
                  return (
                    <tr key={listKey(list)}>
                      <td className="trello-list">
                        {list.list_name}
                        {list.status === null && !dirty && <span className="status-pill danger">Belum dipetakan</span>}
                        {dirty && <span className="status-pill status-planning">Belum disimpan</span>}
                        <span className="text-data cell-sub">{list.list_id}</span>
                      </td>
                      <td className="num text-data">{list.actions}</td>
                      <td className="nowrap">{list.last_seen ? formatLong(list.last_seen.slice(0, 10)) : '-'}</td>
                      <td>
                        <label className="visually-hidden" htmlFor={`status-${id}`}>Status untuk {list.list_name}</label>
                        <select id={`status-${id}`} className="toolbar-select" value={value.status ?? ''} disabled={saving} onChange={(e) => edit(list, { status: (e.target.value || null) as TaskStatus | null })}>
                          <option value="">Belum dipetakan</option>
                          {TASK_STATUSES.map((s) => <option key={s} value={s}>{TASK_STATUS_LABEL[s] ?? s}</option>)}
                        </select>
                      </td>
                      <td>
                        <label className="visually-hidden" htmlFor={`phase-${id}`}>Phase untuk {list.list_name}</label>
                        <select id={`phase-${id}`} className="toolbar-select" value={value.phase ?? ''} disabled={saving} onChange={(e) => edit(list, { phase: (e.target.value || null) as TaskPhase | null })}>
                          <option value="">Tidak ditentukan</option>
                          {TASK_PHASES.map((p) => <option key={p} value={p}>{PHASE_LABEL[p] ?? p}</option>)}
                        </select>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      ))}
    </section>
  );
}
