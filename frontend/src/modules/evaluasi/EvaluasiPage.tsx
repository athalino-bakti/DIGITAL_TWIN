import { useState } from 'react';
import type { FormEvent } from 'react';
import { apiGet, apiPost } from '../../shared/api/client';

type EvaluationResult = {
  id: number;
  baseline_id: number;
  run_id: number;
  status: string;
  kpi: Record<string, number>;
  ranking_score: number;
  created_at: string;
  finished_at: string | null;
};

export function EvaluasiPage() {
  const [baselineId, setBaselineId] = useState('');
  const [runId, setRunId] = useState('');
  const [reportId, setReportId] = useState('');
  const [result, setResult] = useState<EvaluationResult | null>(null);
  const [state, setState] = useState<'idle' | 'loading' | 'success' | 'error'>('idle');
  const [error, setError] = useState('');

  async function createReport(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setState('loading');
    setError('');
    try {
      const created = await apiPost<EvaluationResult, { baseline_id: number; run_id: number }>('/evaluasi/reports', {
        baseline_id: Number(baselineId),
        run_id: Number(runId),
      });
      setResult(created);
      setReportId(String(created.id));
      setState('success');
    } catch (reason) {
      setState('error');
      setError(reason instanceof Error ? reason.message : 'Gagal membuat evaluasi');
    }
  }

  async function loadReport() {
    setState('loading');
    setError('');
    try {
      const current = await apiGet<EvaluationResult>(`/evaluasi/reports/${reportId}`);
      setResult(current);
      setState('success');
    } catch (reason) {
      setState('error');
      setError(reason instanceof Error ? reason.message : 'Gagal memuat hasil evaluasi');
    }
  }

  return (
    <>
      <section className="module-panel" aria-label="Form evaluasi">
        <div className="panel-heading"><h2>Buat evaluasi skenario</h2><span className="subtle-badge">Tahap 4</span></div>
        <form className="form-grid" onSubmit={createReport}>
          <label>Baseline ID<input value={baselineId} onChange={(event) => setBaselineId(event.target.value)} required /></label>
          <label>Run ID<input value={runId} onChange={(event) => setRunId(event.target.value)} required /></label>
          <button type="submit" disabled={state === 'loading'}>Generate evaluasi</button>
        </form>
        <div className="form-panel compact">
          <label>Report ID<input value={reportId} onChange={(event) => setReportId(event.target.value)} /></label>
          <button type="button" onClick={() => void loadReport()} disabled={!reportId || state === 'loading'}>Muat report</button>
        </div>
        {error && <p className="error-text">{error}</p>}
      </section>

      <section className="module-panel table-panel" aria-label="KPI evaluasi">
        <h3>KPI evaluasi</h3>
        {!result ? <p className="empty-inline">Belum ada hasil evaluasi.</p> : (
          <>
            <div className="result-grid">
              <article><h3>Status</h3><p>{result.status}</p></article>
              <article><h3>Ranking score</h3><p>{result.ranking_score.toFixed(2)}</p></article>
            </div>
            <table>
              <thead><tr><th>KPI</th><th>Nilai</th></tr></thead>
              <tbody>{Object.entries(result.kpi).map(([key, value]) => <tr key={key}><td>{key}</td><td>{Number(value).toFixed(2)}</td></tr>)}</tbody>
            </table>
          </>
        )}
      </section>
    </>
  );
}
