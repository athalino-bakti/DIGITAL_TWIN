// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { clearSession, getAccessToken, getSessionExpiry, onSessionCleared, saveSession } from './session';

const KEY = 'dt-puti.session';

describe('session', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-11-15T09:00:00Z'));
  });
  afterEach(() => vi.useRealTimers());

  it('menyimpan token beserta waktu kedaluwarsa', () => {
    saveSession('abc', 3600);
    expect(getAccessToken()).toBe('abc');
    expect(getSessionExpiry()).toBe(Date.now() + 3_600_000);
  });

  it('token kedaluwarsa dianggap tidak ada dan dihapus dari storage', () => {
    saveSession('abc', 60);
    vi.advanceTimersByTime(60_000);
    expect(getAccessToken()).toBeNull();
    expect(localStorage.getItem(KEY)).toBeNull();
  });

  it.each(['bukan json', '{"token":1,"expiresAt":0}', '{"token":"abc"}'])('isi storage rusak diabaikan: %s', (raw) => {
    localStorage.setItem(KEY, raw);
    expect(getAccessToken()).toBeNull();
  });

  it('clearSession menghapus token dan memanggil listener', () => {
    const listener = vi.fn();
    const unsubscribe = onSessionCleared(listener);
    saveSession('abc', 3600);
    clearSession();
    expect(getAccessToken()).toBeNull();
    expect(listener).toHaveBeenCalledOnce();
    unsubscribe();
    clearSession();
    expect(listener).toHaveBeenCalledOnce();
  });

  it('logout di tab lain (event storage) ikut mengeluarkan tab ini', () => {
    const listener = vi.fn();
    const unsubscribe = onSessionCleared(listener);
    window.dispatchEvent(new StorageEvent('storage', { key: KEY, newValue: null }));
    window.dispatchEvent(new StorageEvent('storage', { key: 'kunci-lain', newValue: null }));
    expect(listener).toHaveBeenCalledOnce();
    unsubscribe();
  });
});
