import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import Navbar from '@/components/layout/Navbar';
import PageHeader from '@/components/layout/PageHeader';
import GlassCard from '@/components/common/GlassCard';
import SVGProgressRing from '@/components/common/SVGProgressRing';
import LoadingSpinner from '@/components/common/LoadingSpinner';
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
  const [applying, setApplying] = useState<number | null>(null);
  const [applied, setApplied] = useState<Set<number>>(new Set());
  const [toast, setToast] = useState('');

  const { data, isLoading } = useQuery<RegisteredTeamsResponse>({
    queryKey: ['registered-teams'],
    queryFn: () => api.get('/api/teams/registered'),
  });

  function showToast(msg: string) {
    setToast(msg);
    setTimeout(() => setToast(''), 3500);
  }

  async function applyToTeam(teamId: number) {
    setApplying(teamId);
    try {
      const d = await api.post<{ success: boolean; error?: string }>(
        `/api/teams/${teamId}/apply`,
        {},
      );
      if (d.success) {
        setApplied((prev) => new Set([...prev, teamId]));
        showToast('Application submitted!');
      } else {
        showToast(d.error ?? 'Failed to apply.');
      }
    } catch {
      showToast('Network error.');
    } finally {
      setApplying(null);
    }
  }

  const teams = data?.teams ?? [];
  const maxRegistered = data?.max_registered ?? 18;
  const canApply = data?.can_apply ?? false;

  return (
    <>
      <Navbar />
      <main style={{ padding: '80px 24px 80px', maxWidth: '860px', margin: '0 auto' }}>
        <PageHeader
          eyebrow="Teams"
          title="Registered Teams"
          subtitle="Teams that have confirmed their participation."
        />

        {/* Progress ring */}
        {!isLoading && (
          <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 48 }}>
            <GlassCard
              style={{
                padding: 40,
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                gap: 12,
              }}
            >
              <SVGProgressRing
                value={teams.length}
                max={maxRegistered}
                size={140}
                stroke={10}
              />
              <div style={{ textAlign: 'center' }}>
                <div
                  style={{
                    fontSize: 13,
                    color: 'var(--muted)',
                    textTransform: 'uppercase',
                    letterSpacing: '0.08em',
                  }}
                >
                  Teams Registered
                </div>
                <div style={{ fontSize: 28, fontWeight: 900, marginTop: 2 }}>
                  {teams.length}{' '}
                  <span style={{ color: 'var(--muted)', fontWeight: 400, fontSize: 18 }}>
                    of {maxRegistered}
                  </span>
                </div>
              </div>
            </GlassCard>
          </div>
        )}

        {isLoading && <LoadingSpinner />}

        {!isLoading && teams.length === 0 && (
          <GlassCard style={{ padding: 48, textAlign: 'center' }}>
            <div style={{ fontSize: 48, marginBottom: 16 }}>🏆</div>
            <h2 style={{ fontWeight: 700, marginBottom: 8 }}>No teams registered yet</h2>
            <p style={{ color: 'var(--muted)' }}>
              Be the first — create a team and get 3 members to lock in your spot!
            </p>
          </GlassCard>
        )}

        {/* Timeline */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          {teams.map((team, i) => {
            const isFull = team.is_full || team.participant_count >= 6;
            const isApplied = applied.has(team.team_id) || team.already_applied;
            const isApplying = applying === team.team_id;

            return (
              <GlassCard
                key={team.team_id}
                style={{ padding: '20px 24px', display: 'flex', alignItems: 'center', gap: 20 }}
              >
                {/* Rank */}
                <div
                  style={{
                    width: 36,
                    height: 36,
                    borderRadius: '50%',
                    flexShrink: 0,
                    background:
                      'linear-gradient(135deg, rgba(96,165,250,0.2), rgba(167,139,250,0.2))',
                    border: '1px solid rgba(96,165,250,0.3)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontWeight: 800,
                    fontSize: 14,
                    color: '#60a5fa',
                  }}
                >
                  {i + 1}
                </div>

                <div style={{ flex: 1 }}>
                  <div style={{ fontWeight: 800, fontSize: 16, marginBottom: 4 }}>
                    {team.team_name}
                  </div>
                  <div style={{ display: 'flex', gap: 12, fontSize: 12, color: 'var(--muted)' }}>
                    <span>👥 {team.participant_count}/6 members</span>
                    <span>🕒 {relativeTime(team.registered_at)}</span>
                  </div>
                </div>

                {/* Member dots */}
                <div style={{ display: 'flex', gap: 4 }}>
                  {Array.from({ length: 6 }, (_, j) => (
                    <div
                      key={j}
                      style={{
                        width: 10,
                        height: 10,
                        borderRadius: '50%',
                        background:
                          j < team.participant_count
                            ? 'linear-gradient(135deg, #60a5fa, #22d3ee)'
                            : 'rgba(255,255,255,0.1)',
                        border:
                          j < team.participant_count ? 'none' : '1px solid rgba(255,255,255,0.15)',
                      }}
                    />
                  ))}
                </div>

                {/* Apply button (only for eligible participants) */}
                {canApply && (
                  <button
                    disabled={isFull || !!isApplied || isApplying}
                    onClick={() => !isFull && !isApplied && applyToTeam(team.team_id)}
                    style={
                      {
                        padding: '8px 16px',
                        border: 'none',
                        borderRadius: 8,
                        fontFamily: 'inherit',
                        fontSize: 13,
                        fontWeight: 600,
                        cursor: isFull || isApplied ? 'default' : 'pointer',
                        background: isFull
                          ? 'rgba(255,255,255,0.05)'
                          : isApplied
                            ? 'rgba(52,211,153,0.15)'
                            : 'linear-gradient(135deg, #60a5fa, #22d3ee)',
                        color: isFull ? 'var(--muted)' : isApplied ? '#34d399' : '#0b1021',
                        border: isApplied ? '1px solid rgba(52,211,153,0.3)' : 'none',
                        opacity: isFull ? 0.5 : 1,
                      } as React.CSSProperties
                    }
                  >
                    {isFull ? 'Full' : isApplied ? 'Applied ✓' : isApplying ? '...' : 'Apply'}
                  </button>
                )}
              </GlassCard>
            );
          })}
        </div>
      </main>

      {toast && (
        <div
          style={{
            position: 'fixed',
            bottom: 24,
            right: 24,
            zIndex: 9999,
            padding: '12px 20px',
            borderRadius: 12,
            background: 'rgba(52,211,153,0.15)',
            border: '1px solid rgba(52,211,153,0.3)',
            color: '#34d399',
            fontWeight: 600,
            fontSize: 14,
          }}
        >
          {toast}
        </div>
      )}
    </>
  );
}
