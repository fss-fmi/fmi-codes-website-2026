import { useState } from 'react';
import { Link } from 'react-router-dom';
import Navbar from '@/components/layout/Navbar';
import RequireAuth from '@/components/layout/RequireAuth';
import GlassCard from '@/components/common/GlassCard';
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

function JoinTeamContent() {
  const [code, setCode] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!code.trim()) return;
    setError('');
    setLoading(true);
    try {
      const d = await api.post<{ success: boolean; error?: string }>('/api/teams/join', {
        join_code: code.trim(),
      });
      if (d.success) setSuccess(true);
      else setError(d.error ?? 'Failed to join team.');
    } catch {
      setError('Network error. Please try again.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <main
      style={{
        minHeight: '80vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '60px 24px',
      }}
    >
      <GlassCard style={{ width: '100%', maxWidth: 440, padding: '40px 36px' }}>
        <h1
          style={{
            fontSize: '2rem',
            fontWeight: 900,
            letterSpacing: '-0.02em',
            marginBottom: '8px',
          }}
        >
          <GradientText>Join a Team</GradientText>
        </h1>
        <p style={{ color: 'var(--muted)', marginBottom: 28, fontSize: 15 }}>
          Enter the invite code you received from your team captain.
        </p>

        {success ? (
          <div style={{ textAlign: 'center' }}>
            <div style={{ fontSize: 48, marginBottom: 16 }}>🎉</div>
            <div
              style={{
                background: 'rgba(52,211,153,0.15)',
                border: '1px solid rgba(52,211,153,0.3)',
                color: '#34d399',
                padding: '14px',
                borderRadius: '10px',
                marginBottom: 24,
                fontSize: 15,
                fontWeight: 600,
              }}
            >
              You successfully joined the team!
            </div>
            <Link
              to="/team"
              className="btn btn-primary"
              style={{ textDecoration: 'none' }}
            >
              Go to Team Dashboard
            </Link>
          </div>
        ) : (
          <>
            {error && (
              <div
                style={{
                  background: 'rgba(239,68,68,0.15)',
                  border: '1px solid rgba(239,68,68,0.3)',
                  color: '#fca5a5',
                  padding: '12px 14px',
                  borderRadius: '10px',
                  marginBottom: 20,
                  fontSize: 14,
                }}
              >
                {error}
              </div>
            )}
            <form onSubmit={handleSubmit}>
              <div style={{ marginBottom: 20 }}>
                <label
                  style={{
                    display: 'block',
                    fontSize: 13,
                    fontWeight: 600,
                    color: 'var(--muted)',
                    marginBottom: 8,
                  }}
                >
                  Invite Code
                </label>
                <input
                  type="text"
                  required
                  placeholder="Enter invite code"
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                  style={{
                    ...inputStyle,
                    textTransform: 'uppercase',
                    letterSpacing: '0.1em',
                    textAlign: 'center',
                    fontSize: 20,
                  }}
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
                  border: 'none',
                  cursor: loading ? 'not-allowed' : 'pointer',
                  background: 'linear-gradient(135deg, #60a5fa, #22d3ee)',
                  borderRadius: '12px',
                  color: '#0b1021',
                  fontFamily: 'inherit',
                  fontSize: 15,
                  fontWeight: 700,
                  opacity: loading ? 0.7 : 1,
                  boxShadow: '0 4px 20px rgba(96,165,250,0.3)',
                }}
              >
                {loading ? 'Joining...' : 'Join Team'}
              </button>
            </form>
            <p style={{ textAlign: 'center', marginTop: 24, color: 'var(--muted)', fontSize: 14 }}>
              Don't have a code?{' '}
              <Link
                to="/createTeam"
                style={{ color: 'var(--accent)', textDecoration: 'none', fontWeight: 600 }}
              >
                Create your own team
              </Link>
            </p>
          </>
        )}
      </GlassCard>
    </main>
  );
}

export default function JoinTeamPage() {
  return (
    <RequireAuth allowedRole="participant">
      <Navbar />
      <JoinTeamContent />
    </RequireAuth>
  );
}
