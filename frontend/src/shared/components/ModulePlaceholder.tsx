type Props = { title: string; description: string; areas: readonly string[] };

export function ModulePlaceholder({ title, description, areas }: Props) {
  return <section className="module-panel" aria-label={title}>
    <div className="panel-heading"><h2>{title}</h2><span className="subtle-badge">Belum tersedia</span></div>
    <div className="empty-state">
      <span className="empty-icon" aria-hidden="true">◈</span>
      <h3>Ruang untuk {title.toLowerCase()}</h3>
      <p>{description}</p>
      <span className="development-badge">Dalam pengembangan</span>
    </div>
    <div className="module-areas" aria-label="Cakupan modul">{areas.map((area) => <span key={area}>{area}</span>)}</div>
  </section>;
}
