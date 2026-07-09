import { useState } from 'react';
import { Link, useNavigate, useLocation } from 'react-router-dom';
import Navbar from '@/components/layout/Navbar';
import Panel from '@/components/common/Panel';
import Field from '@/components/common/Field';
import Input from '@/components/common/Input';
import Button from '@/components/common/Button';
import { useAuth } from '@/context/AuthContext';
import api from '@/lib/api';
import type { User } from '@/types/auth';

type Role = 'participant' | 'mentor' | 'admin';

const ROLE_DEFAULT: Record<Role, string> = {
  participant: '/team',
  mentor: '/mentorDashboard',
  admin: '/admin/matching',
};

const ROLE_LABEL: Record<Role, string> = {
  participant: 'PARTICIPANT',
  mentor: 'MENTOR',
  admin: 'ADMIN',
};

export default function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { login } = useAuth();

  const [role, setRole] = useState<Role>('participant');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const [showReset, setShowReset] = useState(false);
  const [resetEmail, setResetEmail] = useState('');
  const [resetError, setResetError] = useState('');
  const [resetSuccess, setResetSuccess] = useState('');
  const [resetLoading, setResetLoading] = useState(false);

  async function handleLogin(e: React.FormEvent) {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const data = await api.post<{
        success: boolean;
        role: Role;
        user_id: number;
        user: User;
        error?: string;
      }>('/api/auth/login', { email, password, role });
      if (data.success) {
        login(data.role, data.user_id, data.user);
        const from =
          (location.state as { from?: { pathname: string } } | null)?.from?.pathname ??
          ROLE_DEFAULT[data.role];
        navigate(from, { replace: true });
      } else {
        setError(data.error ?? 'Invalid credentials. Please try again.');
      }
    } catch (err: unknown) {
      console.error('Login failed:', err);
      setError('Something went wrong. Please try again.');
    } finally {
      setLoading(false);
    }
  }

  async function handleReset(e: React.FormEvent) {
    e.preventDefault();
    setResetError('');
    setResetSuccess('');
    if (!resetEmail.trim()) {
      setResetError('Please enter your email address.');
      return;
    }
    setResetLoading(true);
    try {
      const data = await api.post<{ success: boolean; message?: string; error?: string }>(
        '/api/auth/reset-password',
        { email: resetEmail, role },
      );
      if (data.success) {
        setResetSuccess(data.message ?? 'Recovery email sent.');
      } else {
        setResetError(data.error ?? 'Something went wrong.');
      }
    } catch {
      setResetError('Network error. Please try again.');
    } finally {
      setResetLoading(false);
    }
  }

  return (
    <>
      <Navbar />
      <main
        style={{
          minHeight: '80vh',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '60px 24px',
        }}
      >
        <div style={{ width: '100%', maxWidth: '460px' }}>
          <Panel title={showReset ? 'RESET PASSWORD' : 'LOGIN'}>
            {!showReset ? (
              <p className="px-body-sm" style={{ margin: '0 0 24px 0', color: 'var(--px-muted-strong)' }}>
                Sign in to your FMI&#123;Codes&#125; account.
              </p>
            ) : (
              <p className="px-body-sm" style={{ margin: '0 0 24px 0', color: 'var(--px-muted-strong)' }}>
                Enter your email to receive a recovery link.
              </p>
            )}

            {!showReset && (
              <div
                role="group"
                aria-label="Sign in role"
                style={{ display: 'flex', gap: '8px', marginBottom: '24px', flexWrap: 'wrap' }}
              >
                {(['participant', 'mentor', 'admin'] as Role[]).map((r) => (
                  <button
                    key={r}
                    type="button"
                    className="px-btn-secondary"
                    aria-pressed={role === r}
                    onClick={() => {
                      setRole(r);
                      if (r === 'admin') setShowReset(false);
                    }}
                    style={{ flex: '1 1 100px', minWidth: '100px' }}
                  >
                    {ROLE_LABEL[r]}
                  </button>
                ))}
              </div>
            )}

            {error && !showReset && (
              <div
                role="alert"
                style={{
                  background: 'var(--px-bg-panel)',
                  border: '1px solid var(--px-danger)',
                  borderLeft: '2px solid var(--px-danger)',
                  color: 'var(--px-danger)',
                  fontFamily: 'var(--px-mono)',
                  fontSize: '0.85rem',
                  padding: '12px 14px',
                  marginBottom: '20px',
                }}
              >
                {error}
              </div>
            )}

            {!showReset && (
              <form onSubmit={handleLogin} noValidate>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
                  <Field id="login-email" label="EMAIL" required>
                    <Input
                      type="email"
                      required
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      placeholder="name@example.com"
                      autoComplete="email"
                    />
                  </Field>
                  <Field id="login-password" label="PASSWORD" required>
                    <Input
                      type="password"
                      required
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      placeholder="••••••••"
                      autoComplete="current-password"
                    />
                  </Field>
                  <Button
                    type="submit"
                    variant="primary"
                    disabled={loading}
                    style={{ width: '100%', marginTop: '4px' }}
                  >
                    {loading ? 'AUTHENTICATING…' : 'SIGN IN'}
                  </Button>
                </div>
              </form>
            )}

            {showReset && (
              <div style={{ animation: 'fadeSlideUp 0.4s ease both' }}>
                {resetError && (
                  <div
                    role="alert"
                    style={{
                      background: 'var(--px-bg-panel)',
                      border: '1px solid var(--px-danger)',
                      borderLeft: '2px solid var(--px-danger)',
                      color: 'var(--px-danger)',
                      fontFamily: 'var(--px-mono)',
                      fontSize: '0.85rem',
                      padding: '12px 14px',
                      marginBottom: '16px',
                    }}
                  >
                    {resetError}
                  </div>
                )}
                {resetSuccess && (
                  <div
                    role="status"
                    style={{
                      background: 'var(--px-bg-panel)',
                      border: '1px solid var(--px-green)',
                      borderLeft: '2px solid var(--px-green)',
                      color: 'var(--px-green)',
                      fontFamily: 'var(--px-mono)',
                      fontSize: '0.85rem',
                      padding: '12px 14px',
                      marginBottom: '16px',
                    }}
                  >
                    {resetSuccess}
                  </div>
                )}
                <form onSubmit={handleReset} noValidate>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                    <Field id="reset-email" label="EMAIL" required>
                      <Input
                        type="email"
                        required
                        value={resetEmail}
                        onChange={(e) => setResetEmail(e.target.value)}
                        placeholder="name@example.com"
                        disabled={!!resetSuccess}
                        autoComplete="email"
                      />
                    </Field>
                    <Button
                      type="submit"
                      variant="primary"
                      disabled={resetLoading || !!resetSuccess}
                      style={{ width: '100%' }}
                    >
                      {resetLoading ? 'SENDING…' : resetSuccess ? 'SENT' : 'SEND RECOVERY EMAIL'}
                    </Button>
                  </div>
                </form>
                <div style={{ textAlign: 'center', marginTop: '16px' }}>
                  <button
                    type="button"
                    onClick={() => setShowReset(false)}
                    className="px-btn-ghost"
                  >
                    BACK TO SIGN IN
                  </button>
                </div>
              </div>
            )}

            {!showReset && role !== 'admin' && (
              <div style={{ textAlign: 'center', marginTop: '16px' }}>
                <button
                  type="button"
                  onClick={() => {
                    setShowReset(true);
                    setResetEmail(email);
                  }}
                  className="px-btn-ghost"
                >
                  FORGOT PASSWORD?
                </button>
              </div>
            )}

            <p
              className="px-body-sm"
              style={{
                textAlign: 'center',
                marginTop: '24px',
                color: 'var(--px-muted-strong)',
              }}
            >
              No account?{' '}
              <Link
                to="/registration"
                style={{
                  color: 'var(--px-teal)',
                  textDecoration: 'underline',
                  textUnderlineOffset: '4px',
                  fontFamily: 'var(--px-mono)',
                }}
              >
                Register here
              </Link>
            </p>
          </Panel>
        </div>
      </main>
    </>
  );
}
