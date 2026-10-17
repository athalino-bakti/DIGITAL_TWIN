import { useState } from 'react';
import type { FormEvent } from 'react';
import { apiGet, apiPost } from '../../shared/api/client';

type SimulationRun = {
  id: number;
  baseline_id: number;
  name: string;
  status: string;
  scenario: Record<string, number>;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
};

type SimulationMetric = { metric_key: string; metric_value: number; details: Record<string, string> };

export function SimulasiPage() {
  const [baselineId, setBaselineId] = useState('');
  const [runId, setRunId] = useState('');
  const [durationMultiplier, setDurationMultiplier] = useState('1');
  const [extraAllocation, setExtraAllocation] = useState('0');
  const [state, setState] = useState<'idle' | 'loading' | 'success' | 'error'>('idle');
  const [error, setError] = useState('');
  const [run, setRun] = useState<SimulationRun | null>(null);
  const [metrics, setMetrics] = useState<SimulationMetric[]>([]);

  async function createRun(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setState('loading');
    setError('');
    try {
      const created = await apiPost<SimulationRun, { baseline_id: number; name: string; duration_multiplier: number; additional_allocation_percent: number }>('/simulasi/runs', {
        baseline_id: Number(baselineId),
        name: `Skenario baseline ${baselineId}`,
        duration_multiplier: Number(durationMultiplier),
        additional_allocation_percent: Number(extraAllocation),
      });
      setRun(created);
      setRunId(String(created.id));
      setState('success');
    } catch (reason) {
      setState('error');
      setError(reason instanceof Error ? reason.message : 'Gagal membuat run simulasi');
    }
  }

  async function loadRun() {
    setState('loading');
    setError('');
    try {
      const current = await apiGet<SimulationRun>(`/simulasi/runs/${runId}`);
      setRun(current);
      setMetrics(await apiGet<SimulationMetric[]>(`/simulasi/runs/${runId}/results`));
      setState('success');
    } catch (reason) {
      setState('error');
      setError(reason instanceof Error ? reason.message : 'Gagal memuat hasil simulasi');
    }
  }

  return (
    <>
      <section className="module-panel" aria-label="Form simulasi">
        <div className="panel-heading"><h2>Jalankan simulasi</h2><span className="subtle-badge">Tahap 3</span></div>
        <form className="form-grid" onSubmit={createRun}>
          <label>Baseline ID<input value={baselineId} onChange={(event) => setBaselineId(event.target.value)} required /></label>
          <label>Duration multiplier<input value={durationMultiplier} onChange={(event) => setDurationMultiplier(event.target.value)} required /></label>
          <label>Extra allocation %<input value={extraAllocation} onChange={(event) => setExtraAllocation(event.target.value)} required /></label>
          <button type="submit" disabled={state === 'loading'}>Buat run</button>
        </form>
        <div className="form-panel compact">
          <label>Run ID<input value={runId} onChange={(event) => setRunId(event.target.value)} /></label>
          <button type="button" onClick={() => void loadRun()} disabled={!runId || state === 'loading'}>Muat hasil</button>
        </div>
        {error && <p className="error-text">{error}</p>}
        {run && <p className="info-text">Run #{run.id} status: {run.status}</p>}
      </section>

      <section className="module-panel table-panel" aria-label="Hasil simulasi">
        <h3>Hasil simulasi</h3>
        {metrics.length === 0 ? <p className="empty-inline">Belum ada metrik simulasi.</p> : (
          <table>
            <thead><tr><th>Metrik</th><th>Nilai</th></tr></thead>
            <tbody>{metrics.map((metric) => <tr key={metric.metric_key}><td>{metric.metric_key}</td><td>{metric.metric_value.toFixed(2)}</td></tr>)}</tbody>
          </table>
        )}
      </section>
    </>
  );
}
