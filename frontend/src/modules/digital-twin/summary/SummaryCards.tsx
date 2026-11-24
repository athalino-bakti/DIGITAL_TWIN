import { useEffect, useState } from 'react';
import { formatShort } from '../../data/availability/dates';
import { STATUS_LABEL } from '../../data/projects/api';
import { getSummary, type BaselineSummary } from './api';
import { buildCards, type CardKey } from './cards';

const count = new Intl.NumberFormat('id-ID');
const TITLE: Record<CardKey, string> = {
  active: 'Proyek aktif',
  late: 'Proyek yang proyeksi selesainya melewati target',
  overload: 'Resource overload',
  multi: 'Anggota multi-role',
};

/** Kartu ringkasan baseline di atas tab Digital Twin, dengan daftar detail (DIG-40: DIG-176). */
export function SummaryCards() {
  const [summary, setSummary] = useState<BaselineSummary | null>(null);
  const [failed, setFailed] = useState(false);
  const [open, setOpen] = useState<CardKey | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    getSummary(controller.signal)
      .then(setSummary)
      .catch((error: unknown) => { if (!(error instanceof DOMException && error.name === 'AbortError')) setFailed(true); });
    return () => controller.abort();
  }, []);

  const cards = buildCards(summary).map((card) => (failed ? { ...card, note: 'Data belum bisa dimuat', clickable: false } : card));

  return <>
    <section className="metric-grid" aria-label="Ringkasan baseline">
      {cards.map((card, index) => {
        const body = <><h2>{card.label}</h2><strong>{card.value === null ? '—' : count.format(card.value)}</strong><p>{card.note}</p></>;
        return card.clickable
          ? <button key={card.key} type="button" className={`metric-card metric-${index} metric-button ${open === card.key ? 'is-open' : ''}`} aria-expanded={open === card.key} aria-controls="summary-detail" onClick={() => setOpen(open === card.key ? null : card.key)}>{body}</button>
          : <article key={card.key} className={`metric-card metric-${index}`} title={card.key === 'overload' ? summary?.overloaded_resources.reason : undefined}>{body}</article>;
      })}
    </section>

    {summary && open && (
      <section id="summary-detail" className="module-panel summary-detail" aria-labelledby="summary-detail-title">
        <div className="panel-heading">
          <div>
            <h2 id="summary-detail-title">{TITLE[open]}</h2>
            <p className="panel-subtitle">
              {open === 'late' && <>Proyeksi selesai = tanggal paling akhir dari task proyek yang tidak dibatalkan; task yang belum selesai dan sudah lewat rencana dihitung paling cepat selesai hari ini. Per {formatShort(summary.as_of)}.</>}
              {open === 'active' && <>Proyek berstatus planning, development, atau testing, urut prioritas.</>}
              {open === 'multi' && <>Anggota dengan peran rangkap, atau yang sedang mengerjakan task dengan peran berbeda dari peran utamanya.</>}
            </p>
          </div>
          <button type="button" className="button button-ghost" onClick={() => setOpen(null)}>Tutup</button>
        </div>
        <div className="table-scroll">
          {open === 'active' && (
            <table className="data-table">
              <thead><tr><th scope="col">Proyek</th><th scope="col">Status</th><th scope="col" className="num">Prioritas</th><th scope="col">Target rilis</th></tr></thead>
              <tbody>{summary.active_projects.items.map((p) => <tr key={p.project_id}><td><span className="cell-title">{p.project_name}</span><span className="cell-sub text-data">{p.project_id}</span></td><td><span className={`status-pill status-${p.status}`}>{STATUS_LABEL[p.status]}</span></td><td className="num">{p.priority_rank}</td><td className="nowrap">{formatShort(p.target_launch_date)}</td></tr>)}</tbody>
            </table>
          )}
          {open === 'late' && (
            <table className="data-table">
              <thead><tr><th scope="col">Proyek</th><th scope="col">Target rilis</th><th scope="col">Proyeksi selesai</th><th scope="col" className="num">Telat</th><th scope="col" className="num">Task terbuka</th></tr></thead>
              <tbody>{summary.late_projects.items.map((p) => <tr key={p.project_id}><td><span className="cell-title">{p.project_name}</span><span className="cell-sub">{STATUS_LABEL[p.status]}</span></td><td className="nowrap">{formatShort(p.target_launch_date)}</td><td className="nowrap">{formatShort(p.projected_finish)}</td><td className="num nowrap text-danger">{count.format(p.days_late)} hari</td><td className="num">{p.open_tasks}{p.late_open_tasks > 0 && <span className="cell-sub">{p.late_open_tasks} lewat rencana</span>}</td></tr>)}</tbody>
            </table>
          )}
          {open === 'multi' && (
            <table className="data-table">
              <thead><tr><th scope="col">Anggota</th><th scope="col">Peran utama</th><th scope="col">Peran rangkap</th><th scope="col">Sedang menjalankan peran lain</th></tr></thead>
              <tbody>{summary.multi_role_resources.items.map((r) => <tr key={r.resource_id}><td><span className="cell-title">{r.resource_name}</span><span className="cell-sub text-data">{r.resource_id}</span></td><td className="text-data">{r.primary_role_id}</td><td className="text-data">{r.secondary_role_ids.join(', ') || <span className="cell-sub">-</span>}</td><td className="text-data">{r.other_active_roles.join(', ') || <span className="cell-sub">-</span>}</td></tr>)}</tbody>
            </table>
          )}
        </div>
      </section>
    )}
  </>;
}
