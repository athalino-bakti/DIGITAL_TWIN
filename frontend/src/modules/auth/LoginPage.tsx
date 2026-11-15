import { useState, type FormEvent } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { ApiError } from '../../shared/api/client';
import { useAuth } from '../../shared/auth/AuthProvider';
import { Icon } from '../../shared/components/Icon';
import { ServiceStatus } from '../../shared/components/ServiceStatus';

type Errors = { username?: string; password?: string; form?: string };

/** Hanya terima path internal, supaya state "from" tidak bisa dipakai untuk redirect keluar aplikasi. */
function safeRedirect(state: unknown): string {
  const from = (state as { from?: unknown } | null)?.from;
  return typeof from === 'string' && from.startsWith('/') && !from.startsWith('//') && !from.startsWith('/login') ? from : '/';
}

export function LoginPage() {
  const { status, signIn } = useAuth();
  const location = useLocation();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [errors, setErrors] = useState<Errors>({});
  const [submitting, setSubmitting] = useState(false);

  if (status === 'authenticated') return <Navigate to={safeRedirect(location.state)} replace />;

  async function submit(event: FormEvent) {
    event.preventDefault();
    const found: Errors = {};
    if (!username.trim()) found.username = 'Username wajib diisi';
    if (!password) found.password = 'Password wajib diisi';
    setErrors(found);
    if (Object.keys(found).length) return;

    setSubmitting(true);
    try {
      await signIn(username, password);
      // Setelah status berubah, <Navigate> di atas yang memindahkan halaman.
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        setErrors({ form: 'Username atau password salah' });
        setPassword('');
      } else if (error instanceof ApiError) {
        const fields = error.fieldErrors();
        setErrors({ username: fields.username, password: fields.password, form: fields.username || fields.password ? undefined : error.message });
      } else {
        setErrors({ form: 'API belum terhubung. Periksa koneksi lalu coba lagi.' });
      }
      setSubmitting(false);
    }
  }

  const describe = (key: 'username' | 'password') => ({
    'aria-invalid': errors[key] ? true : undefined,
    'aria-describedby': errors[key] ? `login-${key}-error` : undefined,
  });

  return (
    <div className="auth-shell">
      <main className="auth-card" aria-labelledby="login-title">
        <div className="auth-brand">
          <span className="brand-mark"><Icon name="folder-open-dot" /></span>
          <span className="brand-text"><strong>Digital Twin PuTI</strong><small>Simulasi proyek</small></span>
        </div>
        <h1 id="login-title">Masuk</h1>
        <p className="auth-subtitle">Gunakan akun yang dibuatkan admin tim.</p>
        <form className="form-grid" onSubmit={submit} noValidate>
          {errors.form && <div className="form-alert" role="alert">{errors.form}</div>}
          <label className="field" htmlFor="login-username">
            <span>Username</span>
            <input
              id="login-username"
              name="username"
              autoComplete="username"
              autoCapitalize="none"
              spellCheck={false}
              autoFocus
              maxLength={50}
              value={username}
              disabled={submitting}
              onChange={(event) => { setUsername(event.target.value); setErrors((current) => ({ ...current, username: undefined, form: undefined })); }}
              {...describe('username')}
            />
            {errors.username && <span className="field-error" id="login-username-error">{errors.username}</span>}
          </label>
          <label className="field" htmlFor="login-password">
            <span>Password</span>
            <input
              id="login-password"
              name="password"
              type="password"
              autoComplete="current-password"
              maxLength={256}
              value={password}
              disabled={submitting}
              onChange={(event) => { setPassword(event.target.value); setErrors((current) => ({ ...current, password: undefined, form: undefined })); }}
              {...describe('password')}
            />
            {errors.password && <span className="field-error" id="login-password-error">{errors.password}</span>}
          </label>
          <button type="submit" className="button" disabled={submitting}>{submitting ? 'Memproses…' : 'Masuk'}</button>
        </form>
      </main>
      <ServiceStatus />
    </div>
  );
}
