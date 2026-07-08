import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import Navbar from '@/components/layout/Navbar';
import Panel from '@/components/common/Panel';
import Field from '@/components/common/Field';
import Input from '@/components/common/Input';
import Button from '@/components/common/Button';
import api from '@/lib/api';

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
        <div style={{ width: '100%', maxWidth: '460px' }}>
          <Panel title="RESET PASSWORD">
            <p
              className="px-body-sm"
              style={{ margin: '0 0 24px 0', color: 'var(--px-muted-strong)' }}
            >
              {isInvalidLink
                ? 'This link is invalid or has expired.'
                : 'Choose a new password for your account.'}
            </p>

            {isInvalidLink && (
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
                This reset link is invalid or has expired. Please request a new one from the{' '}
                <Link
                  to="/login"
                  style={{ color: 'var(--px-teal)', textDecoration: 'underline' }}
                >
                  login page
                </Link>
                .
              </div>
            )}

            {success && (
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
                  marginBottom: '20px',
                }}
              >
                {success}{' '}
                <Link
                  to="/login"
                  style={{ color: 'var(--px-teal)', textDecoration: 'underline' }}
                >
                  Sign in now
                </Link>
              </div>
            )}

            {!isInvalidLink && !success && (
              <form onSubmit={handleSubmit} noValidate>
                {error && (
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
                <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
                  <Field id="new-password" label="NEW PASSWORD" required>
                    <Input
                      type="password"
                      required
                      value={newPassword}
                      onChange={(e) => setNewPassword(e.target.value)}
                      placeholder="At least 12 characters"
                      autoComplete="new-password"
                    />
                  </Field>
                  <Field id="confirm-password" label="CONFIRM PASSWORD" required>
                    <Input
                      type="password"
                      required
                      value={confirmPassword}
                      onChange={(e) => setConfirmPassword(e.target.value)}
                      placeholder="Repeat your new password"
                      autoComplete="new-password"
                    />
                  </Field>
                  <Button
                    type="submit"
                    variant="primary"
                    disabled={loading}
                    style={{ width: '100%' }}
                  >
                    {loading ? 'RESETTING…' : 'SET NEW PASSWORD'}
                  </Button>
                </div>
              </form>
            )}

            <p
              className="px-body-sm"
              style={{
                textAlign: 'center',
                marginTop: '24px',
                color: 'var(--px-muted-strong)',
              }}
            >
              <Link
                to="/login"
                style={{
                  color: 'var(--px-teal)',
                  textDecoration: 'underline',
                  textUnderlineOffset: '4px',
                  fontFamily: 'var(--px-mono)',
                }}
              >
                Back to sign in
              </Link>
            </p>
          </Panel>
        </div>
      </main>
    </>
  );
}
