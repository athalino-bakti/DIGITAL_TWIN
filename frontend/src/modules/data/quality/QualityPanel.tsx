import { useCallback, useEffect, useState } from 'react';
import { ApiError } from '../../../shared/api/client';
import { formatLong } from '../availability/dates';
import { getQualitySummary, getRejectedRows, type RejectedPage, type Source } from './api';
import { CHARACTERISTICS, characteristicLabel, formatRate, hasFilter, LEVELS, levelLabel, NO_FILTER, PAGE_SIZE, pageCount, rangeText, rowLabel, SOURCES, type RejectedFilters } from './rules';
import type { QualitySummary } from './api';

type Load<T> = { state: 'loading' } | { state: 'error'; message: string } | { state: 'ready'; data: T };

const failure = (error: unknown) => error instanceof ApiError ? error.message : 'API belum terhubung. Coba lagi.';
const aborted = (error: unknown) => error instanceof DOMException && error.name === 'AbortError';

/**
 * Tab Kualitas data (DIG-147): ringkasan skor per karakteristik ISO/IEC 25012, hasil per aturan,
 * dan daftar baris yang ditolak atau diberi peringatan pada impor terakhir tiap sumber.
 * Hanya membaca; angkanya dihitung backend (DIG-145, DIG-146).
 */
export function QualityPanel() {
  const [source, setSource] = useState<Source>('project_plan');
  const [summary, setSummary] = useState<Load<QualitySummary>>({ state: 'loading' });
  const [filters, setFilters] = useState<RejectedFilters>(NO_FILTER);
  const [page, setPage] = useState(1);
  const [rows, setRows] = useState<Load<RejectedPage>>({ state: 'loading' });
  const [reloadKey, setReloadKey] = useState(0);

  const jobId = summary.state === 'ready' ? summary.data.job_id : null;

  useEffect(() => {
    const controller = new AbortController();
    setSummary({ state: 'loading' });
    getQualitySummary(source, controller.signal)
      .then((data) => setSummary({ state: 'ready', data }))
      .catch((error: unknown) => { if (!aborted(error)) setSummary({ state: 'error', message: failure(error) }); });
    return () => controller.abort();
  }, [source, reloadKey]);

  useEffect(() => {
    if (jobId === null) return;
    const controller = new AbortController();
    setRows({ state: 'loading' });
    getRejectedRows(jobId, filters, page, PAGE_SIZE, controller.signal)
      .then((data) => setRows({ state: 'ready', data }))
      .catch((error: unknown) => { if (!aborted(error)) setRows({ state: 'error', message: failure(error) }); });
    return () => controller.abort();
  }, [jobId, filters, page, reloadKey]);

  const changeSource = useCallback((next: Source) => {
    setSource(next);
    setFilters(NO_FILTER);
    setPage(1);
  }, []);

  const changeFilters = useCallback((patch: Partial<RejectedFilters>) => {
    setFilters((current) => ({ ...current, ...patch }));
    setPage(1);
  }, []);

  const data = summary.state === 'ready' ? summary.data : null;
  const total = rows.state === 'ready' ? rows.data.total : 0;
  const pages = pageCount(total, PAGE_SIZE);

  return (
    <section className="module-panel" aria-labelledby="quality-title">
      <div className="panel-heading panel-heading-wrap">
        <div>
          <h2 id="quality-title">Kualitas data</h2>
          <p className="panel-subtitle">Hasil validasi impor terakhir tiap sumber terhadap aturan Data Dictionary, dikelompokkan menurut karakteristik ISO/IEC 25012. Baris yang ditolak tidak masuk ke tabel final; peringatan tetap masuk.</p>
        </div>
        <div className="toolbar-filters">
          <label className="field-inline" htmlFor="quality-source">
            <span>Sumber</span>
            <select id="quality-source" className="toolbar-select" value={source} onChange={(e) => changeSource(e.target.value as Source)}>
              {SOURCES.map((item) => <option key={item.key} value={item.key}>{item.label}</option>)}
            </select>
          </label>
        </div>
      </div>

      {summary.state === 'loading' && <div className="empty-state compact"><p>Memuat laporan kualitas…</p></div>}
      {summary.state === 'error' && (
        <div className="empty-state compact">
          <h3>Laporan kualitas belum bisa dimuat</h3>
          <p>{summary.message}</p>
          <button type="button" className="button button-ghost" onClick={() => setReloadKey((key) => key + 1)}>Coba lagi</button>
        </div>
      )}

      {data && data.job_id === null && (
        <div className="empty-state compact">
          <h3>Belum ada impor yang divalidasi</h3>
          <p>Laporan muncul setelah impor {SOURCES.find((item) => item.key === source)?.label} berhasil dan lolos validasi.</p>
        </div>
      )}

      {data && data.job_id !== null && (
        <>
          <div className="panel-toolbar">
            <p className="toolbar-summary">
              Impor <strong>#{data.job_id}</strong>
              {data.file_name && <> · {data.file_name}</>}
              {data.project_id && <> · {data.project_id}</>}
              {data.validated_at && <> · divalidasi {formatLong(data.validated_at.slice(0, 10))}</>}
            </p>
            <p className="toolbar-summary">
              <strong>{data.rows_checked}</strong> baris diperiksa · <strong>{data.rows_rejected}</strong> ditolak · <strong>{data.rows_with_warning}</strong> peringatan · lolos <strong>{formatRate(data.pass_rate)}</strong>
            </p>
          </div>

          <div className="metric-grid quality-metrics">
            {CHARACTERISTICS.map((item, index) => {
              const score = data.characteristics.find((entry) => entry.characteristic === item.key);
              return (
                <article key={item.key} className={`metric-card metric-${index}`}>
                  <h3>{item.label}</h3>
                  <strong>{formatRate(score?.pass_rate ?? null)}</strong>
                  <p>{score && score.checked > 0 ? `${score.violated} pelanggaran dari ${score.checked} pemeriksaan` : 'Belum ada pemeriksaan'}</p>
                </article>
              );
            })}
          </div>

          <h3 className="quality-section">Hasil per aturan</h3>
          {data.rules.length === 0 ? <p className="quality-empty">Belum ada hasil aturan untuk impor ini.</p> : (
            <div className="table-scroll">
              <table className="data-table">
                <thead>
                  <tr>
                    <th scope="col">Aturan</th>
                    <th scope="col">Tabel</th>
                    <th scope="col">Karakteristik</th>
                    <th scope="col">Dampak</th>
                    <th scope="col" className="num">Diperiksa</th>
                    <th scope="col" className="num">Pelanggaran</th>
                    <th scope="col"><span className="visually-hidden">Aksi</span></th>
                  </tr>
                </thead>
                <tbody>
                  {data.rules.map((rule) => (
                    <tr key={`${rule.rule_id}-${rule.table}`}>
                      <td>
                        <span className="text-data">{rule.rule_id}</span>
                        <span className="cell-sub">{rule.text}</span>
                      </td>
                      <td className="text-data">{rule.table}</td>
                      <td>{characteristicLabel(rule.characteristic)}</td>
                      <td><span className={`status-pill ${rule.level === 'tolak' ? 'danger' : 'status-on_hold'}`}>{levelLabel(rule.level)}</span></td>
                      <td className="num text-data">{rule.checked}</td>
                      <td className="num text-data">{rule.violated}</td>
                      <td>
                        {rule.violated > 0 && (
                          <button type="button" className="link-button" onClick={() => changeFilters({ ruleId: rule.rule_id })}>Lihat baris</button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <h3 className="quality-section">Baris ditolak dan peringatan</h3>
          <div className="panel-toolbar">
            <div className="toolbar-filters">
              <label className="field-inline" htmlFor="quality-level">
                <span>Dampak</span>
                <select id="quality-level" className="toolbar-select" value={filters.level} onChange={(e) => changeFilters({ level: e.target.value })}>
                  <option value="">Semua</option>
                  {LEVELS.map((item) => <option key={item.key} value={item.key}>{item.label}</option>)}
                </select>
              </label>
              <label className="field-inline" htmlFor="quality-characteristic">
                <span>Karakteristik</span>
                <select id="quality-characteristic" className="toolbar-select" value={filters.characteristic} onChange={(e) => changeFilters({ characteristic: e.target.value })}>
                  <option value="">Semua</option>
                  {CHARACTERISTICS.map((item) => <option key={item.key} value={item.key}>{item.label}</option>)}
                </select>
              </label>
              {filters.ruleId && <span className="badge badge-accent">Aturan {filters.ruleId}</span>}
              {hasFilter(filters) && <button type="button" className="link-button" onClick={() => changeFilters(NO_FILTER)}>Hapus filter</button>}
            </div>
            {rows.state === 'ready' && <p className="toolbar-summary">{rangeText(rows.data.page, rows.data.page_size, rows.data.total)}</p>}
          </div>

          {rows.state === 'loading' && <div className="empty-state compact"><p>Memuat baris…</p></div>}
          {rows.state === 'error' && (
            <div className="empty-state compact">
              <h3>Baris belum bisa dimuat</h3>
              <p>{rows.message}</p>
              <button type="button" className="button button-ghost" onClick={() => setReloadKey((key) => key + 1)}>Coba lagi</button>
            </div>
          )}
          {rows.state === 'ready' && rows.data.items.length === 0 && (
            <p className="quality-empty">{hasFilter(filters) ? 'Tidak ada baris yang cocok dengan filter.' : 'Tidak ada baris ditolak atau diberi peringatan pada impor ini.'}</p>
          )}
          {rows.state === 'ready' && rows.data.items.length > 0 && (
            <div className="table-scroll">
              <table className="data-table">
                <thead>
                  <tr>
                    <th scope="col">Baris</th>
                    <th scope="col">Tabel</th>
                    <th scope="col">Dampak</th>
                    <th scope="col">Temuan</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.data.items.map((item) => (
                    <tr key={`${item.table}-${item.row_number ?? item.row_key}`}>
                      <td className="nowrap text-data">{rowLabel(item)}</td>
                      <td className="text-data">{item.table}</td>
                      <td><span className={`status-pill ${item.level === 'tolak' ? 'danger' : 'status-on_hold'}`}>{levelLabel(item.level)}</span></td>
                      <td>
                        <ul className="quality-findings">
                          {item.findings.map((finding, index) => (
                            <li key={`${finding.rule_id}-${finding.column ?? ''}-${index}`}>
                              <span className="text-data">{finding.rule_id}</span> {finding.message}
                              {(finding.column || finding.value) && (
                                <span className="cell-sub">
                                  {finding.column && <>Kolom {finding.column}</>}
                                  {finding.column && finding.value && ' · '}
                                  {finding.value && <>Nilai &quot;{finding.value}&quot;</>}
                                </span>
                              )}
                            </li>
                          ))}
                        </ul>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {rows.state === 'ready' && pages > 1 && (
            <div className="panel-toolbar quality-pager">
              <button type="button" className="button button-ghost" disabled={page <= 1} onClick={() => setPage(page - 1)}>Sebelumnya</button>
              <span className="toolbar-summary">Halaman <strong>{page}</strong> dari <strong>{pages}</strong></span>
              <button type="button" className="button button-ghost" disabled={page >= pages} onClick={() => setPage(page + 1)}>Berikutnya</button>
            </div>
          )}
        </>
      )}
    </section>
  );
}
