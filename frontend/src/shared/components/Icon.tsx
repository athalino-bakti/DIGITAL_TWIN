/* Ikon lucide dari Figma (lihat src/assets/icons). Dirender sebagai mask CSS
   supaya warnanya ikut currentColor. */
export type IconName =
  | 'layout-dashboard' | 'list-checks' | 'sliders-horizontal' | 'chart-column'
  | 'folder-open-dot' | 'calendar-days' | 'chevron-down' | 'user';

type Props = { name: IconName; size?: 'sm' | 'lg' };

export function Icon({ name, size }: Props) {
  return <span className={`icon icon-${name}${size ? ` icon-${size}` : ''}`} aria-hidden="true" />;
}
