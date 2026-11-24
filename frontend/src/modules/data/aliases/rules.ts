import type { IdentitySource, ResourceAlias, UnmappedIdentity } from './api';

type Named = { resource_id: string; resource_name: string };

const words = (value: string) => value.normalize('NFKD').replace(/[̀-ͯ]/g, '').toLowerCase().split(/[^a-z0-9]+/).filter(Boolean);

/**
 * Usulan anggota untuk identitas yang belum terpetakan, hanya sebagai isian awal pilihan.
 * Backend sengaja tidak mencocokkan secara kabur (DIG-111), jadi usulan ini tetap harus
 * dikonfirmasi admin. Aturannya: nama tampilan sama persis dengan nama anggota (abaikan huruf
 * besar, aksen, dan tanda baca), atau semua kata nama tampilan adalah awal kata nama anggota dan
 * hanya satu anggota yang cocok. Username tanpa spasi dicocokkan dengan nama anggota yang
 * digabung ("sari.puspita" ke "Sari Puspita").
 */
export function suggestResource(identity: Pick<UnmappedIdentity, 'display_name' | 'username'>, resources: readonly Named[]): string | null {
  const shown = words(identity.display_name ?? '');
  if (shown.length) {
    const exact = resources.filter((r) => words(r.resource_name).join(' ') === shown.join(' '));
    if (exact.length === 1) return exact[0].resource_id;
    const prefix = resources.filter((r) => {
      const name = words(r.resource_name);
      return shown.every((word, i) => name[i]?.startsWith(word));
    });
    if (prefix.length === 1) return prefix[0].resource_id;
  }
  const user = words(identity.username ?? '').join('');
  if (user.length >= 3) {
    const joined = resources.filter((r) => words(r.resource_name).join('') === user);
    if (joined.length === 1) return joined[0].resource_id;
  }
  return null;
}

/** Label identitas: nama tampilan, lalu username, lalu alias mentah. */
export function identityLabel(identity: Pick<UnmappedIdentity, 'display_name' | 'username' | 'alias'>): string {
  return identity.display_name ?? (identity.username ? `@${identity.username}` : identity.alias);
}

/** Validasi sisi klien yang sama dengan alias_key di backend, supaya error muncul sebelum kirim. */
export function aliasError(source: IdentitySource, alias: string): string | null {
  const value = alias.trim();
  if (!value) return 'Alias wajib diisi';
  if (value.length > 200) return 'Alias paling panjang 200 karakter';
  if (source === 'trello' && !/^[0-9a-f]{24}$/i.test(value)) return 'Id member Trello harus 24 karakter heksadesimal';
  if (source === 'teamgit' && !/^[^\s@]+@[^\s@]+$/.test(value)) return 'Isi dengan email author commit';
  return null;
}

/** Jumlah alias per anggota, untuk menandai anggota yang belum punya alias di sebuah sumber. */
export function aliasCount(aliases: readonly ResourceAlias[]): Map<string, number> {
  const count = new Map<string, number>();
  for (const alias of aliases) count.set(alias.resource_id, (count.get(alias.resource_id) ?? 0) + 1);
  return count;
}
