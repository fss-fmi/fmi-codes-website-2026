import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import Navbar from '@/components/layout/Navbar';
import RequireAuth from '@/components/layout/RequireAuth';
import Panel from '@/components/common/Panel';
import Field from '@/components/common/Field';
import Input from '@/components/common/Input';
import Button from '@/components/common/Button';
import { useAuth } from '@/context/AuthContext';
import api from '@/lib/api';

function JoinTeamContent() {
  const navigate = useNavigate();
  const { refreshUser } = useAuth();
  const queryClient = useQueryClient();
  const [code, setCode] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!code.trim()) return;
    setError('');
    setLoading(true);
    try {
      const d = await api.post<{ success: boolean; error?: string }>('/api/teams/join', {
        join_code: code.trim(),
      });
      if (d.success) {
        await refreshUser();
        queryClient.invalidateQueries({ queryKey: ['me'] });
        navigate('/team', { replace: true });
      } else setError(d.error ?? 'Failed to join team.');
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
      <div style={{ width: '100%', maxWidth: 480 }}>
        <Panel title="JOIN A TEAM">
          <p
            className="px-body-sm"
            style={{ margin: '0 0 24px 0', color: 'var(--px-muted-strong)' }}
          >
            Enter the invite code you received from your team captain.
          </p>

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
          <form onSubmit={handleSubmit} noValidate>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
              <Field id="inviteCode" label="INVITE CODE" required>
                <Input
                  type="text"
                  required
                  placeholder="Enter invite code"
                  value={code}
                  onChange={(e) => setCode(e.target.value.toUpperCase())}
                  style={{
                    letterSpacing: '0.15em',
                    textAlign: 'center',
                    fontSize: '1.1rem',
                  }}
                  autoCapitalize="characters"
                  spellCheck={false}
                />
              </Field>
              <Button type="submit" variant="primary" disabled={loading} style={{ width: '100%' }}>
                {loading ? 'JOINING…' : 'JOIN TEAM'}
              </Button>
            </div>
          </form>
          <p
            className="px-body-sm"
            style={{ textAlign: 'center', marginTop: 24, color: 'var(--px-muted-strong)' }}
          >
            No code?{' '}
            <Link
              to="/createTeam"
              style={{
                color: 'var(--px-teal)',
                textDecoration: 'underline',
                textUnderlineOffset: '4px',
                fontFamily: 'var(--px-mono)',
              }}
            >
              Create your own team
            </Link>
          </p>
        </Panel>
      </div>
    </main>
  );
}

export default function JoinTeamPage() {
  return (
    <RequireAuth roles={['participant']}>
      <Navbar />
      <JoinTeamContent />
    </RequireAuth>
  );
}
