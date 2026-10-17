import { useMemo, useState } from 'react';
import type { FormEvent } from 'react';
import { apiGet, apiUpload } from '../../shared/api/client';

type UploadSummary = {
  id: number;
  source_filename: string;
  status: string;
  total_rows: number;
  accepted_rows: number;
  rejected_rows: number;
  created_at: string;
  processed_at: string | null;
};

type UploadDetail = UploadSummary & {
  errors: { row_number: number; message: string; raw_data: string }[];
};

type ProjectItem = { id: number; name: string; created_at: string };
type ResourceItem = { id: number; name: string; role: string; capacity_hours_per_week: number };
type TaskItem = {
  id: number;
  project_id: number;
  name: string;
  start_date: string;
  end_date: string;
  duration_days: number;
  priority: number;
  status: string;
};

export function DataPage() {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploadState, setUploadState] = useState<'idle' | 'loading' | 'success' | 'error'>('idle');
  const [uploadError, setUploadError] = useState<string>('');
  const [uploadSummary, setUploadSummary] = useState<UploadSummary | null>(null);
  const [uploadDetail, setUploadDetail] = useState<UploadDetail | null>(null);
  const [masterState, setMasterState] = useState<'idle' | 'loading' | 'success' | 'error'>('idle');
  const [masterError, setMasterError] = useState<string>('');
  const [projects, setProjects] = useState<ProjectItem[]>([]);
  const [resources, setResources] = useState<ResourceItem[]>([]);
  const [tasks, setTasks] = useState<TaskItem[]>([]);

  const totals = useMemo(
    () => ({ projects: projects.length, resources: resources.length, tasks: tasks.length }),
    [projects.length, resources.length, tasks.length],
  );

  async function handleUpload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedFile) return;
    setUploadState('loading');
    setUploadError('');
    try {
      const summary = await apiUpload<UploadSummary>('/data/uploads', selectedFile);
      setUploadSummary(summary);
      const detail = await apiGet<UploadDetail>(`/data/uploads/${summary.id}`);
      setUploadDetail(detail);
      setUploadState('success');
      await loadMasterData();
    } catch (error) {
      setUploadError(error instanceof Error ? error.message : 'Upload gagal');
      setUploadState('error');
    }
  }

  async function loadMasterData() {
    setMasterState('loading');
    setMasterError('');
    try {
      const [nextProjects, nextResources, nextTasks] = await Promise.all([
        apiGet<ProjectItem[]>('/data/master/projects'),
        apiGet<ResourceItem[]>('/data/master/resources'),
        apiGet<TaskItem[]>('/data/master/tasks'),
      ]);
      setProjects(nextProjects);
      setResources(nextResources);
      setTasks(nextTasks);
      setMasterState('success');
    } catch (error) {
      setMasterError(error instanceof Error ? error.message : 'Gagal memuat master data');
      setMasterState('error');
    }
  }

  return (
    <>
      <section className="module-panel" aria-label="Upload dataset">
        <div className="panel-heading">
          <h2>Upload dataset proyek (CSV)</h2>
          <span className="subtle-badge">Maks 2MB</span>
        </div>
        <form className="form-panel" onSubmit={handleUpload}>
          <input type="file" accept=".csv" onChange={(event) => setSelectedFile(event.target.files?.[0] ?? null)} />
          <button type="submit" disabled={!selectedFile || uploadState === 'loading'}>
            {uploadState === 'loading' ? 'Mengunggah…' : 'Upload CSV'}
          </button>
        </form>
        {uploadState === 'error' && <p className="error-text">{uploadError}</p>}
        {uploadSummary && (
          <div className="result-grid">
            <article><h3>Upload ID</h3><p>{uploadSummary.id}</p></article>
            <article><h3>Total baris</h3><p>{uploadSummary.total_rows}</p></article>
            <article><h3>Valid</h3><p>{uploadSummary.accepted_rows}</p></article>
            <article><h3>Ditolak</h3><p>{uploadSummary.rejected_rows}</p></article>
          </div>
        )}
        {uploadDetail && uploadDetail.errors.length > 0 && (
          <div className="table-panel">
            <h3>Baris ditolak</h3>
            <table>
              <thead><tr><th>Baris</th><th>Alasan</th></tr></thead>
              <tbody>
                {uploadDetail.errors.slice(0, 10).map((error) => (
                  <tr key={`${error.row_number}-${error.message}`}>
                    <td>{error.row_number}</td>
                    <td>{error.message}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="module-panel" aria-label="Master data">
        <div className="panel-heading">
          <h2>Master data</h2>
          <button type="button" onClick={() => void loadMasterData()}>
            {masterState === 'loading' ? 'Memuat…' : 'Muat data'}
          </button>
        </div>
        {masterState === 'error' && <p className="error-text">{masterError}</p>}
        <div className="result-grid">
          <article><h3>Project</h3><p>{totals.projects}</p></article>
          <article><h3>Resource</h3><p>{totals.resources}</p></article>
          <article><h3>Task</h3><p>{totals.tasks}</p></article>
        </div>
      </section>
    </>
  );
}
