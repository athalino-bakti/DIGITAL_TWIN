import { createBrowserRouter, Link, Navigate } from 'react-router-dom';
import { AppLayout } from './AppLayout';
import { DataPage } from '../modules/data/DataPage';
import { DigitalTwinPage } from '../modules/digital-twin/DigitalTwinPage';
import { SimulasiPage } from '../modules/simulasi/SimulasiPage';
import { EvaluasiPage } from '../modules/evaluasi/EvaluasiPage';

export const router = createBrowserRouter([
  {
    element: <AppLayout />,
    children: [
      { index: true, element: <Navigate to="/digital-twin/timeline" replace /> },
      { path: 'data', element: <DataPage /> },
      {
        path: 'digital-twin',
        children: [
          { index: true, element: <Navigate to="timeline" replace /> },
          { path: ':view', element: <DigitalTwinPage /> },
        ],
      },
      { path: 'simulasi', element: <SimulasiPage /> },
      { path: 'evaluasi', element: <EvaluasiPage /> },
      { path: '*', element: <section className="empty-state"><h2>Halaman tidak ditemukan</h2><Link to="/digital-twin">Kembali ke Digital Twin</Link></section> },
    ],
  },
]);
