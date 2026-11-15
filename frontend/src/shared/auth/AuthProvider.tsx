import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { ApiError } from '../api/client';
import { fetchMe, login, type AuthUser } from './api';
import { clearSession, getAccessToken, getSessionExpiry, onSessionCleared, saveSession } from './session';

type AuthState =
  | { status: 'checking'; user: null }
  | { status: 'authenticated'; user: AuthUser }
  | { status: 'anonymous'; user: null };

type AuthContextValue = AuthState & {
  signIn: (username: string, password: string) => Promise<void>;
  signOut: () => void;
};

const AuthContext = createContext<AuthContextValue | null>(null);

const ANONYMOUS: AuthState = { status: 'anonymous', user: null };

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>(() => (getAccessToken() ? { status: 'checking', user: null } : ANONYMOUS));

  // Token lama di localStorage dicek dulu ke /auth/me sebelum aplikasi dibuka.
  useEffect(() => {
    if (!getAccessToken()) return;
    const controller = new AbortController();
    fetchMe(controller.signal)
      .then((user) => setState({ status: 'authenticated', user }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        // 401 sudah menghapus token lewat client.ts. Error lain (API mati) cukup minta login ulang.
        if (!(error instanceof ApiError && error.status === 401)) setState(ANONYMOUS);
      });
    return () => controller.abort();
  }, []);

  useEffect(() => onSessionCleared(() => setState(ANONYMOUS)), []);

  // Keluarkan pengguna tepat saat token kedaluwarsa, tanpa menunggu request berikutnya gagal.
  useEffect(() => {
    if (state.status !== 'authenticated') return;
    const expiresAt = getSessionExpiry();
    if (expiresAt === null) return;
    const timer = window.setTimeout(clearSession, Math.max(0, expiresAt - Date.now()));
    return () => window.clearTimeout(timer);
  }, [state.status]);

  const signIn = useCallback(async (username: string, password: string) => {
    const response = await login(username, password);
    saveSession(response.access_token, response.expires_in);
    setState({ status: 'authenticated', user: response.user });
  }, []);

  const value = useMemo<AuthContextValue>(() => ({ ...state, signIn, signOut: clearSession }), [state, signIn]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth harus dipakai di dalam <AuthProvider>');
  return context;
}
