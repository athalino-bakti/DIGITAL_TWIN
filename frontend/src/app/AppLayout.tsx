import { useState } from 'react';
import { NavLink, Outlet, useLocation } from 'react-router-dom';
import { navigation } from './navigation';
import { Icon } from '../shared/components/Icon';
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
          <span className="brand-mark"><Icon name="folder-open-dot" /></span>
          <span className="brand-text"><strong>Digital Twin PuTI</strong><small>Simulasi proyek</small></span>
        </NavLink>
        <div className="navigation-section">
          <p className="eyebrow">Halaman</p>
          <nav aria-label="Navigasi utama">
            {navigation.map((item) => (
              <NavLink key={item.path} to={item.path} onClick={() => setMenuOpen(false)} className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
                <Icon name={item.icon} />
                <span>{item.label}</span>
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
        <div className="sidebar-footer"><span className="workspace-avatar">P</span><div><strong>Workspace PuTI</strong><small>Perencanaan &amp; simulasi</small></div></div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <button type="button" className="menu-toggle" aria-controls="sidebar" aria-expanded={menuOpen} onClick={() => setMenuOpen(!menuOpen)}>Menu</button>
          <div className="topbar-title"><strong>{current?.label ?? 'Digital Twin PuTI'}</strong><small>Workspace PuTI</small></div>
          <div className="topbar-actions">
            <span className="selector"><Icon name="calendar-days" size="sm" />Belum ada dataset<Icon name="chevron-down" size="sm" /></span>
            <span className="topbar-avatar" title="Workspace PuTI"><Icon name="user" size="lg" /></span>
          </div>
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
