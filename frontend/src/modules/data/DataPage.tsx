import { ModulePlaceholder } from '../../shared/components/ModulePlaceholder';

export function DataPage() {
  return <ModulePlaceholder title="Pengelolaan data" description="Dataset proyek akan ditampilkan di sini setelah modul data tersedia." areas={['Unggah dataset CSV', 'Kualitas data', 'Baris ditolak', 'Master data']} />;
}
