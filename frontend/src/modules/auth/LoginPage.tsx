import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { ApiError, isApiUnreachable } from '../../shared/api/client';
import { useAuth } from '../../shared/auth/AuthProvider';
import { safeRedirect } from '../../shared/auth/redirect';
import { Icon } from '../../shared/components/Icon';
import { ServiceStatus } from '../../shared/components/ServiceStatus';

type Field = 'username' | 'password';
type Errors = { username?: string; password?: string; form?: string };

export function LoginPage() {
  const { status, signIn } = useAuth();
  const location = useLocation();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [errors, setErrors] = useState<Errors>({});
  const [submitting, setSubmitting] = useState(false);
  // Input di-disable saat submit, jadi fokus dikembalikan setelah input aktif lagi.
  const [focusField, setFocusField] = useState<Field | null>(null);
  const inputs = { username: useRef<HTMLInputElement>(null), password: useRef<HTMLInputElement>(null) };

  useEffect(() => {
    if (submitting || !focusField) return;
    inputs[focusField].current?.focus();
    setFocusField(null);
  });

  if (status === 'authenticated') return <Navigate to={safeRedirect(location.state)} replace />;

  async function submit(event: FormEvent) {
    event.preventDefault();
    const found: Errors = {};
    if (!username.trim()) found.username = 'Username wajib diisi';
    if (!password) found.password = 'Password wajib diisi';
    setErrors(found);
    if (found.username || found.password) {
      setFocusField(found.username ? 'username' : 'password');
      return;
    }

    setSubmitting(true);
    try {
      await signIn(username, password);
      // Setelah status berubah, <Navigate> di atas yang memindahkan halaman.
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        setErrors({ form: 'Username atau password salah' });
        setPassword('');
        setFocusField('password');
      } else if (isApiUnreachable(error) || !(error instanceof ApiError)) {
        setErrors({ form: 'API belum terhubung. Periksa koneksi lalu coba lagi.' });
        setFocusField('password');
      } else {
        const fields = error.fieldErrors();
        setErrors({ username: fields.username, password: fields.password, form: fields.username || fields.password ? undefined : error.message });
        setFocusField(fields.username ? 'username' : 'password');
      }
      setSubmitting(false);
    }
  }

  const describe = (key: Field) => ({
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
              ref={inputs.username}
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
              ref={inputs.password}
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
