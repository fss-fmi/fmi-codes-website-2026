import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import Navbar from '@/components/layout/Navbar';
import RequireAuth from '@/components/layout/RequireAuth';
import Panel from '@/components/common/Panel';
import Field from '@/components/common/Field';
import Input from '@/components/common/Input';
import Button from '@/components/common/Button';
import { useAuth } from '@/context/AuthContext';
import api from '@/lib/api';

function CreateTeamContent() {
  const navigate = useNavigate();
  const { refreshUser } = useAuth();
  const queryClient = useQueryClient();
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
      if (d.success) {
        await refreshUser();
        queryClient.invalidateQueries({ queryKey: ['me'] });
        navigate('/team', { replace: true });
      } else setError(d.error ?? 'Failed to create team.');
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
        <Panel title="CREATE TEAM">
          <p
            className="px-body-sm"
            style={{ margin: '0 0 24px 0', color: 'var(--px-muted-strong)' }}
          >
            Pick a name and share the invite code with your teammates.
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
              <Field id="teamName" label="TEAM NAME" required>
                <Input
                  type="text"
                  required
                  maxLength={50}
                  placeholder="e.g. Code Wizards"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                />
              </Field>
              <Button type="submit" variant="primary" disabled={loading} style={{ width: '100%' }}>
                {loading ? 'CREATING…' : 'CREATE TEAM'}
              </Button>
            </div>
          </form>
          <p
            className="px-body-sm"
            style={{ textAlign: 'center', marginTop: 24, color: 'var(--px-muted-strong)' }}
          >
            Already in a team?{' '}
            <Link
              to="/team"
              style={{
                color: 'var(--px-teal)',
                textDecoration: 'underline',
                textUnderlineOffset: '4px',
                fontFamily: 'var(--px-mono)',
              }}
            >
              Go to Dashboard
            </Link>
          </p>
        </Panel>
      </div>
    </main>
  );
}

export default function CreateTeamPage() {
  return (
    <RequireAuth roles={['participant']}>
      <Navbar />
      <CreateTeamContent />
    </RequireAuth>
  );
}
