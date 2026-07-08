import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import Navbar from '@/components/layout/Navbar';
import RequireAuth from '@/components/layout/RequireAuth';
import PageHeader from '@/components/layout/PageHeader';
import Panel from '@/components/common/Panel';
import NestedCard from '@/components/common/NestedCard';
import LoadingSpinner from '@/components/common/LoadingSpinner';
import Button from '@/components/common/Button';
import { useToast } from '@/components/common/useToast';
import api from '@/lib/api';

interface BrowseTeam {
  team_id: number;
  team_name: string;
  participant_count: number;
  applied?: boolean;
}

function BrowseTeamsContent() {
  const { showToast } = useToast();
  const [applied, setApplied] = useState<Set<number>>(new Set());
  const [applyingTo, setApplyingTo] = useState<number | null>(null);

  const { data, isLoading } = useQuery<{ teams: BrowseTeam[] }>({
    queryKey: ['available-teams'],
    queryFn: () => api.get('/api/teams/available'),
  });

  async function applyToTeam(teamId: number) {
    setApplyingTo(teamId);
    try {
      const d = await api.post<{ success: boolean; error?: string }>(
        `/api/teams/${teamId}/apply`,
        {},
      );
      if (d.success) {
        setApplied((prev) => new Set([...prev, teamId]));
        showToast({ kind: 'success', message: 'Application submitted.' });
      } else {
        showToast({ kind: 'danger', message: d.error ?? 'Failed to apply.' });
      }
    } catch {
      showToast({ kind: 'danger', message: 'Network error.' });
    } finally {
      setApplyingTo(null);
    }
  }

  const teams = data?.teams ?? [];

  return (
    <main style={{ padding: '80px 24px 80px', maxWidth: '960px', margin: '0 auto' }}>
      <PageHeader
        title="BROWSE TEAMS"
        description="Find a team looking for members and apply to join."
      />

      {isLoading && <LoadingSpinner />}

      {!isLoading && teams.length === 0 && (
        <Panel title="> NO TEAMS YET">
          <p className="px-body" style={{ margin: 0, color: 'var(--px-muted-strong)' }}>
            &gt; All teams are either full or not accepting applications right now. Check back after
            new teams register.
          </p>
        </Panel>
      )}

      {teams.length > 0 && (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
            gap: 20,
          }}
        >
          {teams.map((t) => {
            const isApplied = applied.has(t.team_id) || !!t.applied;
            const isApplying = applyingTo === t.team_id;
            const pct = Math.round((t.participant_count / 6) * 100);

            return (
              <NestedCard key={t.team_id}>
                <div
                  style={{
                    fontFamily: 'var(--px-font)',
                    fontSize: '0.75rem',
                    color: 'var(--px-white)',
                    textTransform: 'uppercase',
                    letterSpacing: '0.05em',
                    marginBottom: '16px',
                    lineHeight: 1.4,
                    wordBreak: 'break-word',
                  }}
                >
                  {t.team_name}
                </div>
                <div style={{ marginBottom: '16px' }}>
                  <div
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      marginBottom: '8px',
                      fontFamily: 'var(--px-mono)',
                      fontSize: '0.8rem',
                      color: 'var(--px-muted-strong)',
                    }}
                  >
                    <span>{t.participant_count}/6 members</span>
                    <span>{pct}%</span>
                  </div>
                  <div
                    role="progressbar"
                    aria-valuenow={t.participant_count}
                    aria-valuemin={0}
                    aria-valuemax={6}
                    aria-label={`${t.participant_count} of 6 members`}
                    className="px-progress-track"
                  >
                    <div className="px-progress-fill" style={{ width: `${pct}%` }} />
                  </div>
                </div>
                {isApplied ? (
                  <button
                    type="button"
                    className="px-btn-secondary"
                    aria-pressed="true"
                    aria-label="Application submitted"
                    disabled
                    style={{ width: '100%' }}
                  >
                    APPLIED
                  </button>
                ) : (
                  <Button
                    variant="primary"
                    onClick={() => applyToTeam(t.team_id)}
                    disabled={isApplying}
                    style={{ width: '100%' }}
                  >
                    {isApplying ? 'APPLYING…' : 'APPLY TO JOIN'}
                  </Button>
                )}
              </NestedCard>
            );
          })}
        </div>
      )}
    </main>
  );
}

export default function BrowseTeamsPage() {
  return (
    <RequireAuth roles={['participant']}>
      <Navbar />
      <BrowseTeamsContent />
    </RequireAuth>
  );
}
