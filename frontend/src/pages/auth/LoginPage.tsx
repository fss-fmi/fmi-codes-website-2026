import { useState } from 'react';
import { Link, useNavigate, useLocation } from 'react-router-dom';
import Navbar from '@/components/layout/Navbar';
import GradientText from '@/components/common/GradientText';
import { useAuth } from '@/context/AuthContext';
import api from '@/lib/api';
import type { User } from '@/types/auth';

type Role = 'participant' | 'mentor' | 'admin';

const ROLE_DEFAULT: Record<Role, string> = {
  participant: '/team',
  mentor: '/mentorDashboard',
  admin: '/admin/matching',
};

const inputStyle = {
  width: '100%',
  padding: '14px 16px',
  background: 'rgba(255,255,255,0.03)',
  border: '1px solid rgba(255,255,255,0.08)',
  borderRadius: '12px',
  color: 'var(--text)',
  fontFamily: 'inherit',
  fontSize: '15px',
  outline: 'none',
  transition: 'border-color 0.2s, box-shadow 0.2s',
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
      setError((err as Error)?.message ?? 'Network error. Please check your connection.');
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
        setResetSuccess(data.message ?? 'Recovery email sent!');
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
        <div
          className="glass-card"
          style={{ width: '100%', maxWidth: '440px', padding: '40px 36px' }}
        >
          {/* Header */}
          <div style={{ marginBottom: '24px' }}>
            <h1
              style={{
                fontSize: '2rem',
                fontWeight: 900,
                letterSpacing: '-0.02em',
                marginBottom: '6px',
                paddingBottom: '0.15em',
              }}
            >
              <GradientText>Welcome back</GradientText>
            </h1>
            <p style={{ color: 'var(--muted)', fontSize: '15px', lineHeight: 1.5 }}>
              Sign in to your FMI&#123;Codes&#125; account
            </p>
          </div>

          {/* Role toggle */}
          <div style={{ display: 'flex', gap: '8px', marginBottom: '24px' }}>
            {(['participant', 'mentor', 'admin'] as Role[]).map((r) => (
              <button
                key={r}
                type="button"
                onClick={() => {
                  setRole(r);
                  if (r === 'admin') setShowReset(false);
                }}
                style={{
                  flex: 1,
                  padding: '10px 12px',
                  borderRadius: '10px',
                  fontFamily: 'inherit',
                  fontSize: '13px',
                  fontWeight: 600,
                  cursor: 'pointer',
                  transition: 'all 0.2s cubic-bezier(0.22,1,0.36,1)',
                  ...(role === r
                    ? {
                        background: 'linear-gradient(135deg, #60a5fa, #22d3ee)',
                        color: '#0b1021',
                        border: 'none',
                        boxShadow: '0 4px 15px rgba(96,165,250,0.25)',
                      }
                    : {
                        background: 'rgba(255,255,255,0.04)',
                        border: '1px solid rgba(255,255,255,0.08)',
                        color: 'var(--muted)',
                      }),
                }}
              >
                {r.charAt(0).toUpperCase() + r.slice(1)}
              </button>
            ))}
          </div>

          {error && (
            <div
              style={{
                background: 'rgba(239,68,68,0.15)',
                border: '1px solid rgba(239,68,68,0.3)',
                color: '#fca5a5',
                padding: '14px',
                borderRadius: '10px',
                marginBottom: '20px',
                fontSize: '14px',
                fontWeight: 500,
              }}
            >
              {error}
            </div>
          )}

          {/* Login form */}
          {!showReset && (
            <form onSubmit={handleLogin}>
              <div style={{ marginBottom: '20px' }}>
                <label
                  style={{
                    display: 'block',
                    fontSize: '13px',
                    fontWeight: 600,
                    color: 'var(--muted)',
                    marginBottom: '8px',
                  }}
                >
                  Email address
                </label>
                <input
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="name@example.com"
                  style={inputStyle}
                  onFocus={(e) => {
                    e.target.style.borderColor = '#60a5fa';
                    e.target.style.boxShadow = '0 0 0 3px rgba(96,165,250,0.15)';
                  }}
                  onBlur={(e) => {
                    e.target.style.borderColor = 'rgba(255,255,255,0.08)';
                    e.target.style.boxShadow = 'none';
                  }}
                />
              </div>
              <div style={{ marginBottom: '20px' }}>
                <label
                  style={{
                    display: 'block',
                    fontSize: '13px',
                    fontWeight: 600,
                    color: 'var(--muted)',
                    marginBottom: '8px',
                  }}
                >
                  Password
                </label>
                <input
                  type="password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  style={inputStyle}
                  onFocus={(e) => {
                    e.target.style.borderColor = '#60a5fa';
                    e.target.style.boxShadow = '0 0 0 3px rgba(96,165,250,0.15)';
                  }}
                  onBlur={(e) => {
                    e.target.style.borderColor = 'rgba(255,255,255,0.08)';
                    e.target.style.boxShadow = 'none';
                  }}
                />
              </div>
              <button
                type="submit"
                disabled={loading}
                style={{
                  width: '100%',
                  padding: '14px',
                  marginTop: '8px',
                  border: 'none',
                  cursor: loading ? 'not-allowed' : 'pointer',
                  background: 'linear-gradient(135deg, #60a5fa, #22d3ee)',
                  borderRadius: '12px',
                  color: '#0b1021',
                  fontFamily: 'inherit',
                  fontSize: '15px',
                  fontWeight: 700,
                  boxShadow: '0 4px 20px rgba(96,165,250,0.3)',
                  opacity: loading ? 0.7 : 1,
                  transition: 'transform 0.2s, box-shadow 0.2s',
                }}
              >
                {loading ? 'Authenticating...' : 'Sign In'}
              </button>
            </form>
          )}

          {/* Reset form */}
          {showReset && (
            <div
              style={{
                marginTop: '24px',
                paddingTop: '24px',
                borderTop: '1px solid rgba(255,255,255,0.08)',
                animation: 'fadeSlideUp 0.4s ease both',
              }}
            >
              <h2
                style={{
                  fontSize: '20px',
                  fontWeight: 800,
                  background: 'linear-gradient(135deg, #a78bfa, #f472b6)',
                  WebkitBackgroundClip: 'text',
                  WebkitTextFillColor: 'transparent',
                  marginBottom: '8px',
                }}
              >
                Reset Password
              </h2>
              <p
                style={{
                  fontSize: '13px',
                  color: 'var(--muted)',
                  marginBottom: '16px',
                  lineHeight: 1.6,
                }}
              >
                Enter your email to receive a recovery link.
              </p>
              {resetError && (
                <div
                  style={{
                    background: 'rgba(239,68,68,0.15)',
                    border: '1px solid rgba(239,68,68,0.3)',
                    color: '#fca5a5',
                    padding: '12px',
                    borderRadius: '10px',
                    marginBottom: '16px',
                    fontSize: '14px',
                  }}
                >
                  {resetError}
                </div>
              )}
              {resetSuccess && (
                <div
                  style={{
                    background: 'rgba(52,211,153,0.15)',
                    border: '1px solid rgba(52,211,153,0.3)',
                    color: '#34d399',
                    padding: '12px',
                    borderRadius: '10px',
                    marginBottom: '16px',
                    fontSize: '14px',
                  }}
                >
                  {resetSuccess}
                </div>
              )}
              <form onSubmit={handleReset}>
                <div style={{ marginBottom: '16px' }}>
                  <label
                    style={{
                      display: 'block',
                      fontSize: '13px',
                      fontWeight: 600,
                      color: 'var(--muted)',
                      marginBottom: '8px',
                    }}
                  >
                    Email address
                  </label>
                  <input
                    type="email"
                    required
                    value={resetEmail}
                    onChange={(e) => setResetEmail(e.target.value)}
                    placeholder="name@example.com"
                    style={inputStyle}
                    disabled={!!resetSuccess}
                  />
                </div>
                <button
                  type="submit"
                  disabled={resetLoading || !!resetSuccess}
                  style={{
                    width: '100%',
                    padding: '14px',
                    border: 'none',
                    background: 'linear-gradient(135deg, #a78bfa, #f472b6)',
                    borderRadius: '12px',
                    color: '#0b1021',
                    fontFamily: 'inherit',
                    fontSize: '15px',
                    fontWeight: 700,
                    cursor: resetLoading || resetSuccess ? 'not-allowed' : 'pointer',
                    opacity: resetLoading || !!resetSuccess ? 0.6 : 1,
                    boxShadow: '0 4px 20px rgba(167,139,250,0.3)',
                  }}
                >
                  {resetLoading ? 'Sending...' : resetSuccess ? 'Sent!' : 'Send Recovery Email'}
                </button>
              </form>
              <p style={{ textAlign: 'center', marginTop: '16px', fontSize: '13px' }}>
                <button
                  type="button"
                  onClick={() => setShowReset(false)}
                  style={{
                    background: 'none',
                    border: 'none',
                    color: 'var(--muted)',
                    cursor: 'pointer',
                    fontSize: '13px',
                  }}
                >
                  ← Back to sign in
                </button>
              </p>
            </div>
          )}

          {/* Forgot password */}
          {!showReset && role !== 'admin' && (
            <p style={{ textAlign: 'center', marginTop: '16px', fontSize: '13px' }}>
              <button
                type="button"
                onClick={() => {
                  setShowReset(true);
                  setResetEmail(email);
                }}
                style={{
                  background: 'none',
                  border: 'none',
                  color: 'var(--muted)',
                  cursor: 'pointer',
                  fontSize: '13px',
                  transition: 'color 0.2s',
                }}
                onMouseEnter={(e) => (e.currentTarget.style.color = 'var(--accent)')}
                onMouseLeave={(e) => (e.currentTarget.style.color = 'var(--muted)')}
              >
                Forgot password?
              </button>
            </p>
          )}

          <p
            style={{
              textAlign: 'center',
              marginTop: '24px',
              color: 'var(--muted)',
              fontSize: '14px',
            }}
          >
            Don't have an account?{' '}
            <Link
              to="/registration"
              style={{ color: 'var(--accent)', textDecoration: 'none', fontWeight: 600 }}
            >
              Register here
            </Link>
          </p>
        </div>
      </main>
    </>
  );
}
