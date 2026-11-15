import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { ApiError } from '../api/client';
import { fetchMe, login, type AuthUser } from './api';
import { clearSession, getAccessToken, getSessionExpiry, onSessionCleared, saveSession } from './session';

type AuthState =
  | { status: 'checking'; user: null }
  | { status: 'authenticated'; user: AuthUser }
  // Token masih tersimpan tapi /auth/me gagal bukan karena 401 (API mati). Sesi tidak dihapus.
  | { status: 'offline'; user: null }
  | { status: 'anonymous'; user: null };

type AuthContextValue = AuthState & {
  signIn: (username: string, password: string) => Promise<void>;
  signOut: () => void;
  /** Cek ulang token ke /auth/me, dipakai tombol "Coba lagi" saat offline. */
  retry: () => void;
};

const AuthContext = createContext<AuthContextValue | null>(null);

const ANONYMOUS: AuthState = { status: 'anonymous', user: null };
const CHECKING: AuthState = { status: 'checking', user: null };

// Batas setTimeout di browser (sekitar 24,8 hari). Delay lebih besar langsung dijalankan.
const MAX_TIMEOUT_MS = 2 ** 31 - 1;

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>(() => (getAccessToken() ? CHECKING : ANONYMOUS));
  const [attempt, setAttempt] = useState(0);

  // Token lama di localStorage dicek dulu ke /auth/me sebelum aplikasi dibuka.
  useEffect(() => {
    if (!getAccessToken()) {
      setState(ANONYMOUS);
      return;
    }
    const controller = new AbortController();
    fetchMe(controller.signal)
      .then((user) => setState({ status: 'authenticated', user }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        // 401 sudah menghapus token lewat client.ts (listener di bawah mengubah state).
        if (error instanceof ApiError && error.status === 401) return;
        setState(getAccessToken() ? { status: 'offline', user: null } : ANONYMOUS);
      });
    return () => controller.abort();
  }, [attempt]);

  useEffect(() => onSessionCleared(() => setState(ANONYMOUS)), []);

  // Keluarkan pengguna tepat saat token kedaluwarsa, tanpa menunggu request berikutnya gagal.
  useEffect(() => {
    if (state.status !== 'authenticated') return;
    let timer: number | undefined;
    const schedule = () => {
      const expiresAt = getSessionExpiry();
      if (expiresAt === null) return clearSession();
      const remaining = expiresAt - Date.now();
      if (remaining <= 0) return clearSession();
      timer = window.setTimeout(schedule, Math.min(remaining, MAX_TIMEOUT_MS));
    };
    schedule();
    return () => window.clearTimeout(timer);
  }, [state.status]);

  const signIn = useCallback(async (username: string, password: string) => {
    const response = await login(username, password);
    saveSession(response.access_token, response.expires_in);
    setState({ status: 'authenticated', user: response.user });
  }, []);

  const retry = useCallback(() => {
    setState(CHECKING);
    setAttempt((current) => current + 1);
  }, []);

  const value = useMemo<AuthContextValue>(() => ({ ...state, signIn, signOut: clearSession, retry }), [state, signIn, retry]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth harus dipakai di dalam <AuthProvider>');
  return context;
}
