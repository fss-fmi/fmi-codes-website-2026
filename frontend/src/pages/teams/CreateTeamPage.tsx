import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
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

function CreateTeamContent() {
  const navigate = useNavigate();
  const [name, setName] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    setError('');
    setLoading(true);
    try {
      const d = await api.post<{ success: boolean; error?: string }>('/api/teams', {
        team_name: name.trim(),
      });
      if (d.success) navigate('/team');
      else setError(d.error ?? 'Failed to create team.');
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
          <GradientText>Create Team</GradientText>
        </h1>
        <p style={{ color: 'var(--muted)', marginBottom: 28, fontSize: 15 }}>
          Pick a name and share the invite code with your teammates.
        </p>

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
              Team Name
            </label>
            <input
              type="text"
              required
              placeholder="e.g. Code Wizards"
              value={name}
              onChange={(e) => setName(e.target.value)}
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
            {loading ? 'Creating...' : 'Create Team'}
          </button>
        </form>
        <p style={{ textAlign: 'center', marginTop: 24, color: 'var(--muted)', fontSize: 14 }}>
          Already in a team?{' '}
          <Link
            to="/team"
            style={{ color: 'var(--accent)', textDecoration: 'none', fontWeight: 600 }}
          >
            Go to Dashboard
          </Link>
        </p>
      </GlassCard>
    </main>
  );
}

export default function CreateTeamPage() {
  return (
    <RequireAuth allowedRole="participant">
      <Navbar />
      <CreateTeamContent />
    </RequireAuth>
  );
}
