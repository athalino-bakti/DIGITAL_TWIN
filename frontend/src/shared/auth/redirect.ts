/**
 * Tujuan setelah login diambil dari state "from" yang diisi RequireAuth.
 *
 * Hanya path di origin aplikasi yang diterima. Backslash dan karakter kontrol (tab, baris baru)
 * langsung ditolak karena browser menormalkannya: "/\contoh.com" dan "/<tab>/contoh.com"
 * dibaca sebagai "//contoh.com", yaitu origin lain.
 */
const UNSAFE_CHARACTERS = /[\\\u0000-\u001f\u007f]/;

export function safeRedirect(state: unknown, origin: string = window.location.origin): string {
  const from = (state as { from?: unknown } | null)?.from;
  if (typeof from !== 'string' || !from.startsWith('/') || UNSAFE_CHARACTERS.test(from)) return '/';
  let url: URL;
  try {
    url = new URL(from, origin);
  } catch {
    return '/';
  }
  if (url.origin !== origin || url.pathname === '/login' || url.pathname.startsWith('/login/')) return '/';
  return `${url.pathname}${url.search}${url.hash}`;
}
