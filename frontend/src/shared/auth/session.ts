/**
 * Penyimpanan token akses dari POST /auth/login (DIG-86).
 *
 * Token disimpan di localStorage bersama waktu kedaluwarsanya, supaya sesi bertahan
 * saat halaman di-refresh dan otomatis dianggap habis tanpa perlu bertanya ke API.
 */

const STORAGE_KEY = 'dt-puti.session';

type StoredSession = { token: string; expiresAt: number };

const clearedListeners = new Set<() => void>();

function read(): StoredSession | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const session = JSON.parse(raw) as Partial<StoredSession>;
    if (typeof session.token !== 'string' || typeof session.expiresAt !== 'number' || session.expiresAt <= Date.now()) {
      localStorage.removeItem(STORAGE_KEY);
      return null;
    }
    return { token: session.token, expiresAt: session.expiresAt };
  } catch {
    return null;
  }
}

export function getAccessToken(): string | null {
  return read()?.token ?? null;
}

/** Waktu kedaluwarsa token dalam milidetik epoch, atau null bila belum login. */
export function getSessionExpiry(): number | null {
  return read()?.expiresAt ?? null;
}

export function saveSession(token: string, expiresInSeconds: number): void {
  const session: StoredSession = { token, expiresAt: Date.now() + expiresInSeconds * 1000 };
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
  } catch {
    // Mode privat atau storage penuh: sesi tetap jalan sampai tab ditutup lewat state React.
  }
}

/** Hapus token dan beri tahu AuthProvider agar kembali ke halaman login. */
export function clearSession(): void {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch {
    // Abaikan, yang penting listener tetap dipanggil.
  }
  for (const listener of clearedListeners) listener();
}

export function onSessionCleared(listener: () => void): () => void {
  clearedListeners.add(listener);
  return () => { clearedListeners.delete(listener); };
}

// Logout di satu tab ikut mengeluarkan tab lain yang terbuka.
window.addEventListener('storage', (event) => {
  if (event.key === STORAGE_KEY && event.newValue === null) for (const listener of clearedListeners) listener();
});
