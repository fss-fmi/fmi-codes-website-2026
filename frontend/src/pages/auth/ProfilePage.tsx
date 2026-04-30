import { useState } from 'react';
import Navbar from '@/components/layout/Navbar';
import PageHeader from '@/components/layout/PageHeader';
import GlassCard from '@/components/common/GlassCard';
import LoadingSpinner from '@/components/common/LoadingSpinner';
import RequireAuth from '@/components/layout/RequireAuth';
import { useAuth } from '@/context/AuthContext';
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

function Field({ label, value }: { label: string; value?: string | number | null }) {
  if (!value) return null;
  return (
    <div
      style={{
        background: 'rgba(255,255,255,0.03)',
        borderRadius: '12px',
        padding: '16px 20px',
        border: '1px solid rgba(255,255,255,0.06)',
      }}
    >
      <div
        style={{
          fontSize: '12px',
          fontWeight: 600,
          color: 'var(--muted)',
          textTransform: 'uppercase',
          letterSpacing: '0.08em',
          marginBottom: '6px',
        }}
      >
        {label}
      </div>
      <div style={{ fontSize: '15px', fontWeight: 500 }}>{value}</div>
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
    .map((w) => w[0])
    .join('')
    .toUpperCase()
    .slice(0, 2);

  async function handlePasswordChange(e: React.FormEvent) {
    e.preventDefault();
    setPwError('');
    setPwSuccess('');
    if (newPw.length < 6) {
      setPwError('New password must be at least 6 characters.');
      return;
    }
    if (newPw !== confPw) {
      setPwError('New passwords do not match.');
      return;
    }
    setPwLoading(true);
    try {
      const data = await api.patch<{ success: boolean; error?: string }>(
        '/api/auth/change-password',
        { current_password: curPw, new_password: newPw },
      );
      if (data.success) {
        setPwSuccess('Password updated successfully!');
        setCurPw('');
        setNewPw('');
        setConfPw('');
      } else {
        setPwError(data.error ?? 'Failed to update password.');
      }
    } catch {
      setPwError('Network error. Please try again.');
    } finally {
      setPwLoading(false);
    }
  }

  const focusHandlers = {
    onFocus: (e: React.FocusEvent<HTMLInputElement>) => {
      e.target.style.borderColor = '#60a5fa';
      e.target.style.boxShadow = '0 0 0 3px rgba(96,165,250,0.15)';
    },
    onBlur: (e: React.FocusEvent<HTMLInputElement>) => {
      e.target.style.borderColor = 'rgba(255,255,255,0.08)';
      e.target.style.boxShadow = 'none';
    },
  };

  return (
    <main style={{ padding: '80px 24px 80px', maxWidth: '680px', margin: '0 auto' }}>
      <PageHeader
        eyebrow="Account"
        title="Your Profile"
      />

      {/* Avatar + name */}
      <GlassCard
        style={{
          padding: '32px',
          marginBottom: '24px',
          display: 'flex',
          alignItems: 'center',
          gap: '20px',
        }}
      >
        <div
          style={{
            width: '64px',
            height: '64px',
            borderRadius: '50%',
            flexShrink: 0,
            background: 'linear-gradient(135deg, #60a5fa, #a78bfa)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: '22px',
            fontWeight: 700,
            color: '#0b1021',
          }}
        >
          {initials}
        </div>
        <div>
          <div style={{ fontSize: '20px', fontWeight: 700 }}>{name}</div>
          <div
            style={{
              marginTop: '4px',
              display: 'inline-block',
              padding: '3px 10px',
              borderRadius: '20px',
              background: 'rgba(96,165,250,0.15)',
              border: '1px solid rgba(96,165,250,0.3)',
              color: '#60a5fa',
              fontSize: '12px',
              fontWeight: 600,
              textTransform: 'capitalize',
            }}
          >
            {role}
          </div>
        </div>
      </GlassCard>

      {/* Info grid */}
      <GlassCard style={{ padding: '24px', marginBottom: '24px' }}>
        <h2 style={{ fontSize: '16px', fontWeight: 700, marginBottom: '16px' }}>
          Profile Information
        </h2>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
          {user.email && (
            <div
              style={{
                gridColumn: '1 / -1',
                background: 'rgba(255,255,255,0.03)',
                borderRadius: '12px',
                padding: '16px 20px',
                border: '1px solid rgba(255,255,255,0.06)',
              }}
            >
              <div
                style={{
                  fontSize: '12px',
                  fontWeight: 600,
                  color: 'var(--muted)',
                  textTransform: 'uppercase',
                  letterSpacing: '0.08em',
                  marginBottom: '6px',
                }}
              >
                Email
              </div>
              <div style={{ fontSize: '15px', fontWeight: 500 }}>{user.email}</div>
            </div>
          )}
          {role === 'participant' && (
            <>
              <Field
                label="University"
                value={user.university}
              />
              <Field
                label="Specialty"
                value={user.specialty}
              />
              <Field
                label="Course"
                value={user.course}
              />
              <Field
                label="Faculty Number"
                value={user.faculty_number}
              />
              <Field
                label="Phone"
                value={user.phone_number}
              />
              {user.team_name && (
                <>
                  <Field
                    label="Team"
                    value={user.team_name}
                  />
                  <Field
                    label="Join Code"
                    value={user.join_code ?? undefined}
                  />
                </>
              )}
            </>
          )}
          {role === 'mentor' && (
            <>
              <Field
                label="Company"
                value={user.company_name}
              />
              <Field
                label="Phone"
                value={user.phone_number}
              />
              {user.bio && (
                <div style={{ gridColumn: '1 / -1' }}>
                  <Field
                    label="Bio"
                    value={user.bio}
                  />
                </div>
              )}
            </>
          )}
        </div>
      </GlassCard>

      {/* Change password */}
      <GlassCard style={{ padding: '24px' }}>
        <h2 style={{ fontSize: '16px', fontWeight: 700, marginBottom: '16px' }}>Change Password</h2>
        {pwError && (
          <div
            style={{
              background: 'rgba(239,68,68,0.15)',
              border: '1px solid rgba(239,68,68,0.3)',
              color: '#fca5a5',
              padding: '12px 14px',
              borderRadius: '10px',
              marginBottom: '16px',
              fontSize: '14px',
            }}
          >
            {pwError}
          </div>
        )}
        {pwSuccess && (
          <div
            style={{
              background: 'rgba(52,211,153,0.15)',
              border: '1px solid rgba(52,211,153,0.3)',
              color: '#34d399',
              padding: '12px 14px',
              borderRadius: '10px',
              marginBottom: '16px',
              fontSize: '14px',
            }}
          >
            {pwSuccess}
          </div>
        )}
        <form onSubmit={handlePasswordChange}>
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
              Current Password
            </label>
            <input
              type="password"
              required
              autoComplete="current-password"
              placeholder="Enter current password"
              value={curPw}
              onChange={(e) => setCurPw(e.target.value)}
              style={inputStyle}
              {...focusHandlers}
            />
          </div>
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
              New Password
            </label>
            <input
              type="password"
              required
              autoComplete="new-password"
              placeholder="Min 6 characters"
              value={newPw}
              onChange={(e) => setNewPw(e.target.value)}
              style={inputStyle}
              {...focusHandlers}
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
              Confirm New Password
            </label>
            <input
              type="password"
              required
              autoComplete="new-password"
              placeholder="Repeat new password"
              value={confPw}
              onChange={(e) => setConfPw(e.target.value)}
              style={inputStyle}
              {...focusHandlers}
            />
          </div>
          <button
            type="submit"
            disabled={pwLoading}
            style={{
              padding: '12px 24px',
              border: 'none',
              cursor: pwLoading ? 'not-allowed' : 'pointer',
              background: 'linear-gradient(135deg, #60a5fa, #22d3ee)',
              borderRadius: '12px',
              color: '#0b1021',
              fontFamily: 'inherit',
              fontSize: '14px',
              fontWeight: 700,
              opacity: pwLoading ? 0.7 : 1,
            }}
          >
            {pwLoading ? 'Updating...' : 'Update Password'}
          </button>
        </form>
      </GlassCard>
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
