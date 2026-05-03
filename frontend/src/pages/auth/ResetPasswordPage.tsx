import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import Navbar from '@/components/layout/Navbar';
import GradientText from '@/components/common/GradientText';
import api from '@/lib/api';

const inputStyle: React.CSSProperties = {
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

const focusHandlers = {
  onFocus: (e: React.FocusEvent<HTMLInputElement>) => {
    e.target.style.borderColor = '#a78bfa';
    e.target.style.boxShadow = '0 0 0 3px rgba(167,139,250,0.15)';
  },
  onBlur: (e: React.FocusEvent<HTMLInputElement>) => {
    e.target.style.borderColor = 'rgba(255,255,255,0.08)';
    e.target.style.boxShadow = 'none';
  },
};

export default function ResetPasswordPage() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token') ?? '';
  const role = searchParams.get('role') ?? '';

  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [loading, setLoading] = useState(false);

  const isInvalidLink = !token || !['participant', 'mentor'].includes(role);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError('');

    if (newPassword.length < 12) {
      setError('Password must be at least 12 characters.');
      return;
    }
    if (newPassword !== confirmPassword) {
      setError('Passwords do not match.');
      return;
    }

    setLoading(true);
    try {
      const data = await api.post<{ success: boolean; message?: string; error?: string }>(
        '/api/auth/reset-password/confirm',
        { token, new_password: newPassword, role },
      );
      if (data.success) {
        setSuccess(data.message ?? 'Password reset successfully. You can now log in.');
      } else {
        setError(data.error ?? 'Something went wrong. Please request a new reset link.');
      }
    } catch (err: unknown) {
      setError((err as Error)?.message ?? 'Network error. Please try again.');
    } finally {
      setLoading(false);
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
          <div style={{ marginBottom: '28px' }}>
            <h1
              style={{
                fontSize: '2rem',
                fontWeight: 900,
                letterSpacing: '-0.02em',
                marginBottom: '6px',
                paddingBottom: '0.15em',
              }}
            >
              <GradientText>Reset Password</GradientText>
            </h1>
            <p style={{ color: 'var(--muted)', fontSize: '15px', lineHeight: 1.5 }}>
              {isInvalidLink
                ? 'This link is invalid or has expired.'
                : 'Choose a new password for your account.'}
            </p>
          </div>

          {isInvalidLink && (
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
              This reset link is invalid or has expired. Please request a new one from the{' '}
              <Link
                to="/login"
                style={{ color: '#f472b6', textDecoration: 'underline' }}
              >
                login page
              </Link>
              .
            </div>
          )}

          {success && (
            <div
              style={{
                background: 'rgba(52,211,153,0.15)',
                border: '1px solid rgba(52,211,153,0.3)',
                color: '#34d399',
                padding: '14px',
                borderRadius: '10px',
                marginBottom: '20px',
                fontSize: '14px',
                fontWeight: 500,
              }}
            >
              {success}{' '}
              <Link
                to="/login"
                style={{ color: '#6ee7b7', textDecoration: 'underline' }}
              >
                Sign in now →
              </Link>
            </div>
          )}

          {!isInvalidLink && !success && (
            <form onSubmit={handleSubmit}>
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
                  New Password
                </label>
                <input
                  type="password"
                  required
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  placeholder="At least 12 characters"
                  style={inputStyle}
                  {...focusHandlers}
                />
              </div>

              <div style={{ marginBottom: '24px' }}>
                <label
                  style={{
                    display: 'block',
                    fontSize: '13px',
                    fontWeight: 600,
                    color: 'var(--muted)',
                    marginBottom: '8px',
                  }}
                >
                  Confirm New Password
                </label>
                <input
                  type="password"
                  required
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  placeholder="Repeat your new password"
                  style={inputStyle}
                  {...focusHandlers}
                />
              </div>

              <button
                type="submit"
                disabled={loading}
                style={{
                  width: '100%',
                  padding: '14px',
                  border: 'none',
                  cursor: loading ? 'not-allowed' : 'pointer',
                  background: 'linear-gradient(135deg, #a78bfa, #f472b6)',
                  borderRadius: '12px',
                  color: '#0b1021',
                  fontFamily: 'inherit',
                  fontSize: '15px',
                  fontWeight: 700,
                  boxShadow: '0 4px 20px rgba(167,139,250,0.3)',
                  opacity: loading ? 0.7 : 1,
                  transition: 'transform 0.2s, box-shadow 0.2s',
                }}
              >
                {loading ? 'Resetting...' : 'Set New Password'}
              </button>
            </form>
          )}

          <p
            style={{
              textAlign: 'center',
              marginTop: '24px',
              color: 'var(--muted)',
              fontSize: '14px',
            }}
          >
            <Link
              to="/login"
              style={{ color: 'var(--accent)', textDecoration: 'none', fontWeight: 600 }}
            >
              ← Back to sign in
            </Link>
          </p>
        </div>
      </main>
    </>
  );
}
