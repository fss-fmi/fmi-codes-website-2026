import { useState } from 'react';
import Navbar from '@/components/layout/Navbar';
import PageHeader from '@/components/layout/PageHeader';
import Panel from '@/components/common/Panel';
import LoadingSpinner from '@/components/common/LoadingSpinner';
import RequireAuth from '@/components/layout/RequireAuth';
import Field from '@/components/common/Field';
import Input from '@/components/common/Input';
import Button from '@/components/common/Button';
import FormAlert from '@/components/common/FormAlert';
import { useAuth } from '@/context/AuthContext';
import api from '@/lib/api';
import { validateNewPassword } from '@/lib/validation';

function InfoCell({ label, value }: { label: string; value?: string | number | null }) {
  if (value === null || value === undefined || value === '') return null;
  return (
    <div
      style={{
        background: 'var(--px-bg-card)',
        border: '1px solid var(--px-teal-dim)',
        padding: '14px 16px',
      }}
    >
      <div className="px-label" style={{ marginBottom: '8px' }}>
        {label}
      </div>
      <div
        style={{
          fontFamily: 'var(--px-mono)',
          fontSize: '0.9rem',
          fontWeight: 500,
          color: 'var(--px-white)',
        }}
      >
        {value}
      </div>
    </div>
  );
}

function ProfileContent() {
  const { user, role } = useAuth();
  const [curPw, setCurPw] = useState('');
  const [newPw, setNewPw] = useState('');
  const [confPw, setConfPw] = useState('');
  const [pwError, setPwError] = useState('');
  const [pwSuccess, setPwSuccess] = useState('');
  const [pwLoading, setPwLoading] = useState(false);

  if (!user) return <LoadingSpinner fullPage />;

  const name =
    user.first_name && user.last_name
      ? `${user.first_name} ${user.last_name}`
      : role === 'admin'
        ? 'Admin'
        : 'User';

  const initials = name
    .split(' ')
    .filter(Boolean)
    .map((w) => w[0])
    .join('')
    .toUpperCase()
    .slice(0, 2);

  async function handlePasswordChange(e: React.FormEvent) {
    e.preventDefault();
    setPwError('');
    setPwSuccess('');
    const validationError = validateNewPassword(newPw, confPw);
    if (validationError) {
      setPwError(validationError);
      return;
    }
    setPwLoading(true);
    try {
      const data = await api.patch<{ success: boolean; error?: string }>(
        '/api/auth/change-password',
        { current_password: curPw, new_password: newPw },
      );
      if (data.success) {
        setPwSuccess('Password updated successfully.');
        setCurPw('');
        setNewPw('');
        setConfPw('');
      } else {
        setPwError(data.error ?? 'Failed to update password.');
      }
    } catch (err: unknown) {
      setPwError((err as Error)?.message ?? 'Network error. Please try again.');
    } finally {
      setPwLoading(false);
    }
  }

  return (
    <main style={{ padding: '80px 24px 80px', maxWidth: '760px', margin: '0 auto' }}>
      <PageHeader title="PROFILE" />

      <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
        <Panel title="ACCOUNT">
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '20px',
              marginBottom: '20px',
              flexWrap: 'wrap',
            }}
          >
            <div
              aria-hidden="true"
              style={{
                width: '64px',
                height: '64px',
                background: 'var(--px-bg-elevated)',
                border: '2px solid var(--px-teal-border)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontFamily: 'var(--px-font)',
                fontSize: '1rem',
                color: 'var(--px-teal)',
              }}
            >
              {initials}
            </div>
            <div style={{ flex: 1, minWidth: '200px' }}>
              <div
                style={{
                  fontFamily: 'var(--px-font)',
                  fontSize: '0.75rem',
                  color: 'var(--px-white)',
                  textTransform: 'uppercase',
                  letterSpacing: '0.05em',
                  marginBottom: '8px',
                }}
              >
                {name}
              </div>
              <span className="px-status-chip">{role?.toUpperCase()}</span>
            </div>
          </div>
        </Panel>

        <Panel title="PROFILE INFO">
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
              gap: '12px',
            }}
          >
            {user.email && (
              <div style={{ gridColumn: '1 / -1' }}>
                <InfoCell label="EMAIL" value={user.email} />
              </div>
            )}
            {role === 'participant' && (
              <>
                <InfoCell label="UNIVERSITY" value={user.university} />
                <InfoCell label="SPECIALTY" value={user.specialty} />
                <InfoCell label="COURSE" value={user.course} />
                <InfoCell label="FACULTY NUMBER" value={user.faculty_number} />
                <InfoCell label="PHONE" value={user.phone_number} />
                {user.team_name && (
                  <>
                    <InfoCell label="TEAM" value={user.team_name} />
                    <InfoCell label="JOIN CODE" value={user.join_code ?? undefined} />
                  </>
                )}
              </>
            )}
            {role === 'mentor' && (
              <>
                <InfoCell label="COMPANY" value={user.company_name} />
                <InfoCell label="PHONE" value={user.phone_number} />
                {user.bio && (
                  <div style={{ gridColumn: '1 / -1' }}>
                    <InfoCell label="BIO" value={user.bio} />
                  </div>
                )}
              </>
            )}
          </div>
        </Panel>

        <Panel title="CHANGE PASSWORD">
          {pwError && (
            <FormAlert kind="error" style={{ marginBottom: '16px' }}>
              {pwError}
            </FormAlert>
          )}
          {pwSuccess && (
            <FormAlert kind="success" style={{ marginBottom: '16px' }}>
              {pwSuccess}
            </FormAlert>
          )}
          <form onSubmit={handlePasswordChange} noValidate>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              <Field id="curPw" label="CURRENT PASSWORD" required>
                <Input
                  type="password"
                  required
                  autoComplete="current-password"
                  placeholder="Enter current password"
                  value={curPw}
                  onChange={(e) => setCurPw(e.target.value)}
                />
              </Field>
              <Field
                id="newPw"
                label="NEW PASSWORD"
                required
                hint="Minimum 12 characters."
              >
                <Input
                  type="password"
                  required
                  autoComplete="new-password"
                  placeholder="Min 12 characters"
                  value={newPw}
                  onChange={(e) => setNewPw(e.target.value)}
                />
              </Field>
              <Field id="confPw" label="CONFIRM NEW PASSWORD" required>
                <Input
                  type="password"
                  required
                  autoComplete="new-password"
                  placeholder="Repeat new password"
                  value={confPw}
                  onChange={(e) => setConfPw(e.target.value)}
                />
              </Field>
              <Button type="submit" variant="primary" disabled={pwLoading}>
                {pwLoading ? 'UPDATING…' : 'UPDATE PASSWORD'}
              </Button>
            </div>
          </form>
        </Panel>
      </div>
    </main>
  );
}

export default function ProfilePage() {
  return (
    <RequireAuth>
      <Navbar />
      <ProfileContent />
    </RequireAuth>
  );
}
