import { useState } from 'react';
import { NavLink, Outlet, useLocation } from 'react-router-dom';
import { navigation } from './navigation';
import { ServiceStatus } from '../shared/components/ServiceStatus';

export function AppLayout() {
  const [menuOpen, setMenuOpen] = useState(false);
  const { pathname } = useLocation();
  const current = navigation.find((item) => pathname === item.path || pathname.startsWith(`${item.path}/`));

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">Lewati ke konten</a>
      <aside id="sidebar" className={`sidebar ${menuOpen ? 'is-open' : ''}`}>
        <NavLink className="brand" to="/" onClick={() => setMenuOpen(false)}>
          <span className="brand-mark">DT</span>
          <span><strong>Digital Twin PuTI</strong><small>simulasi proyek</small></span>
        </NavLink>
        <div className="navigation-section">
          <p className="eyebrow">Halaman</p>
          <nav aria-label="Navigasi utama">
            {navigation.map((item, index) => (
              <NavLink key={item.path} to={item.path} onClick={() => setMenuOpen(false)} className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
                <span className="nav-symbol" aria-hidden="true">{item.symbol}</span>
                <span>{item.label}</span><span className="nav-number">{index + 1}</span>
              </NavLink>
            ))}
          </nav>
        </div>
        <div className="context-section">
          <p className="eyebrow">Konteks</p>
          <dl className="context-card">
            <div><dt>Dataset</dt><dd>Belum tersedia</dd></div>
            <div><dt>Proyek aktif</dt><dd>—</dd></div>
            <div><dt>Resource</dt><dd>—</dd></div>
            <div><dt>Simulasi terakhir</dt><dd>—</dd></div>
          </dl>
        </div>
        <div className="sidebar-footer"><span className="workspace-avatar">P</span><div><strong>Workspace PuTI</strong><small>Perencanaan & simulasi</small></div></div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <button type="button" className="menu-toggle" aria-controls="sidebar" aria-expanded={menuOpen} onClick={() => setMenuOpen(!menuOpen)}>Menu</button>
          <div className="breadcrumb"><span>Digital Twin PuTI</span><span aria-hidden="true">/</span><strong>{current?.label ?? 'Halaman'}</strong></div>
          <span className="dataset-badge"><span className="status-dot" />Belum ada dataset</span>
        </header>
        <main id="main-content" className="page-content" tabIndex={-1}>
          {current && <div className="page-heading"><p className="eyebrow">Workspace / PuTI</p><h1>{current.label}</h1><p>{current.description}</p></div>}
          <Outlet />
        </main>
        <footer className="main-footer"><span>Digital Twin PuTI</span><ServiceStatus /></footer>
      </div>
    </div>
  );
}
