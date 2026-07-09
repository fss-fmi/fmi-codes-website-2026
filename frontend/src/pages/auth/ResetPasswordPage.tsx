import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import Navbar from '@/components/layout/Navbar';
import Panel from '@/components/common/Panel';
import Field from '@/components/common/Field';
import Input from '@/components/common/Input';
import Button from '@/components/common/Button';
import FormAlert from '@/components/common/FormAlert';
import { validateNewPassword } from '@/lib/validation';
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

    const validationError = validateNewPassword(newPassword, confirmPassword);
    if (validationError) {
      setError(validationError);
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
              <FormAlert kind="error">
                This reset link is invalid or has expired. Please request a new one from the{' '}
                <Link
                  to="/login"
                  style={{ color: 'var(--px-teal)', textDecoration: 'underline' }}
                >
                  login page
                </Link>
                .
              </FormAlert>
            )}

            {success && (
              <FormAlert kind="success">
                {success}{' '}
                <Link
                  to="/login"
                  style={{ color: 'var(--px-teal)', textDecoration: 'underline' }}
                >
                  Sign in now
                </Link>
              </FormAlert>
            )}

            {!isInvalidLink && !success && (
              <form onSubmit={handleSubmit} noValidate>
                {error && <FormAlert kind="error">{error}</FormAlert>}
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
