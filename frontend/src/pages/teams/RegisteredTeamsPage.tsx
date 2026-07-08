import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import Navbar from '@/components/layout/Navbar';
import PageHeader from '@/components/layout/PageHeader';
import Panel from '@/components/common/Panel';
import NestedCard from '@/components/common/NestedCard';
import SVGProgressRing from '@/components/common/SVGProgressRing';
import LoadingSpinner from '@/components/common/LoadingSpinner';
import Button from '@/components/common/Button';
import { useToast } from '@/components/common/useToast';
import api from '@/lib/api';

interface RegTeam {
  team_id: number;
  team_name: string;
  participant_count: number;
  registered_at: string;
  is_full?: boolean;
  already_applied?: boolean;
}

interface RegisteredTeamsResponse {
  teams: RegTeam[];
  can_apply: boolean;
  max_registered: number;
}

function relativeTime(dateStr: string) {
  const diff = Math.floor((Date.now() - new Date(dateStr).getTime()) / 1000);
  if (diff < 60) return 'just now';
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

export default function RegisteredTeamsPage() {
  const { showToast } = useToast();
  const [applying, setApplying] = useState<number | null>(null);
  const [applied, setApplied] = useState<Set<number>>(new Set());

  const { data, isLoading } = useQuery<RegisteredTeamsResponse>({
    queryKey: ['registered-teams'],
    queryFn: () => api.get('/api/teams/registered'),
  });

  async function applyToTeam(teamId: number) {
    setApplying(teamId);
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
      setApplying(null);
    }
  }

  const teams = data?.teams ?? [];
  const maxRegistered = data?.max_registered ?? 18;
  const canApply = data?.can_apply ?? false;
  const progressValue = teams.length / (maxRegistered || 1);

  return (
    <>
      <Navbar />
      <main style={{ padding: '80px 24px 80px', maxWidth: '900px', margin: '0 auto' }}>
        <PageHeader
          title="REGISTERED TEAMS"
          description="First 18 teams to hit 3 members auto-register for the event."
        />

        {!isLoading && (
          <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 40 }}>
            <Panel>
              <div
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  gap: 16,
                }}
              >
                <div
                  role="progressbar"
                  aria-valuenow={teams.length}
                  aria-valuemin={0}
                  aria-valuemax={maxRegistered}
                  aria-label={`${teams.length} of ${maxRegistered} teams registered`}
                >
                  <SVGProgressRing
                    value={progressValue}
                    size={140}
                    strokeWidth={10}
                    strokeColor="#2dd4bf"
                    trackColor="rgba(45, 212, 191, 0.18)"
                  />
                </div>
                <div style={{ textAlign: 'center' }}>
                  <div className="px-label" style={{ marginBottom: 6 }}>
                    TEAMS REGISTERED
                  </div>
                  <div
                    style={{
                      fontFamily: 'var(--px-font)',
                      fontSize: '1.25rem',
                      color: 'var(--px-salmon)',
                    }}
                  >
                    {teams.length}
                    <span style={{ color: 'var(--px-muted-strong)', marginLeft: 8 }}>
                      / {maxRegistered}
                    </span>
                  </div>
                </div>
              </div>
            </Panel>
          </div>
        )}

        {isLoading && <LoadingSpinner />}

        {!isLoading && teams.length === 0 && (
          <Panel title="> NO TEAMS REGISTERED YET">
            <p className="px-body" style={{ margin: 0, color: 'var(--px-muted-strong)' }}>
              &gt; Be the first — create a team and get 3 members to lock in your spot.
            </p>
          </Panel>
        )}

        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          {teams.map((team, i) => {
            const isFull = team.is_full || team.participant_count >= 6;
            const isApplied = applied.has(team.team_id) || team.already_applied;
            const isApplying = applying === team.team_id;

            return (
              <NestedCard key={team.team_id}>
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 20,
                    flexWrap: 'wrap',
                  }}
                >
                  <span
                    className="px-label"
                    style={{
                      color: 'var(--px-teal)',
                      minWidth: 40,
                      textAlign: 'center',
                    }}
                  >
                    #{i + 1}
                  </span>

                  <div style={{ flex: 1, minWidth: '180px' }}>
                    <div
                      style={{
                        fontFamily: 'var(--px-mono)',
                        fontWeight: 700,
                        fontSize: '0.95rem',
                        color: 'var(--px-white)',
                        marginBottom: 4,
                      }}
                    >
                      {team.team_name}
                    </div>
                    <div
                      style={{
                        display: 'flex',
                        gap: 12,
                        fontFamily: 'var(--px-mono)',
                        fontSize: '0.8rem',
                        color: 'var(--px-muted-strong)',
                        flexWrap: 'wrap',
                      }}
                    >
                      <span>{team.participant_count}/6 members</span>
                      <span>{relativeTime(team.registered_at)}</span>
                    </div>
                  </div>

                  <div style={{ display: 'flex', gap: 4 }} aria-hidden="true">
                    {Array.from({ length: 6 }, (_, j) => (
                      <div
                        key={j}
                        style={{
                          width: 8,
                          height: 8,
                          background:
                            j < team.participant_count ? 'var(--px-teal)' : 'transparent',
                          border: '1px solid var(--px-teal-dim)',
                        }}
                      />
                    ))}
                  </div>

                  {canApply && (
                    <>
                      {isApplied ? (
                        <button
                          type="button"
                          className="px-btn-secondary"
                          aria-pressed="true"
                          aria-label="Application submitted"
                          disabled
                        >
                          APPLIED
                        </button>
                      ) : isFull ? (
                        <button
                          type="button"
                          className="px-btn-secondary"
                          disabled
                        >
                          FULL
                        </button>
                      ) : (
                        <Button
                          variant="primary"
                          onClick={() => applyToTeam(team.team_id)}
                          disabled={isApplying}
                        >
                          {isApplying ? '…' : 'APPLY'}
                        </Button>
                      )}
                    </>
                  )}
                </div>
              </NestedCard>
            );
          })}
        </div>
      </main>
    </>
  );
}
