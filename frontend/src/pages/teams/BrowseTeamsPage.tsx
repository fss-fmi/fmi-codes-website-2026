import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import Navbar from '@/components/layout/Navbar';
import RequireAuth from '@/components/layout/RequireAuth';
import PageHeader from '@/components/layout/PageHeader';
import GlassCard from '@/components/common/GlassCard';
import LoadingSpinner from '@/components/common/LoadingSpinner';
import api from '@/lib/api';

interface BrowseTeam {
  team_id: number;
  team_name: string;
  participant_count: number;
  applied?: boolean;
}

function BrowseTeamsContent() {
  const [applied, setApplied] = useState<Set<number>>(new Set());
  const [applyingTo, setApplyingTo] = useState<number | null>(null);
  const [toastMsg, setToastMsg] = useState('');

  const { data, isLoading } = useQuery<{ teams: BrowseTeam[] }>({
    queryKey: ['available-teams'],
    queryFn: () => api.get('/api/teams/available'),
  });

  function showToast(msg: string) {
    setToastMsg(msg);
    setTimeout(() => setToastMsg(''), 3500);
  }

  async function applyToTeam(teamId: number) {
    setApplyingTo(teamId);
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
      setApplyingTo(null);
    }
  }

  const teams = data?.teams ?? [];

  return (
    <main style={{ padding: '80px 24px 80px', maxWidth: '900px', margin: '0 auto' }}>
      <PageHeader
        eyebrow="Teams"
        title="Browse Teams"
        subtitle="Find a team looking for members and apply to join."
      />

      {isLoading && <LoadingSpinner />}

      {!isLoading && teams.length === 0 && (
        <GlassCard style={{ padding: 48, textAlign: 'center' }}>
          <div style={{ fontSize: 48, marginBottom: 16 }}>🔍</div>
          <h2 style={{ fontWeight: 700, marginBottom: 8 }}>No teams available</h2>
          <p style={{ color: 'var(--muted)' }}>
            All teams are either full or not accepting applications right now.
          </p>
        </GlassCard>
      )}

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))',
          gap: 20,
        }}
      >
        {teams.map((t) => {
          const isApplied = applied.has(t.team_id) || !!t.applied;
          const isApplying = applyingTo === t.team_id;
          const pct = Math.round((t.participant_count / 6) * 100);

          return (
            <GlassCard
              key={t.team_id}
              style={{ padding: 24 }}
            >
              <div style={{ fontWeight: 800, fontSize: 18, marginBottom: 8 }}>{t.team_name}</div>
              <div style={{ marginBottom: 16 }}>
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    marginBottom: 6,
                    fontSize: 13,
                    color: 'var(--muted)',
                  }}
                >
                  <span>{t.participant_count}/6 members</span>
                  <span>{pct}%</span>
                </div>
                <div style={{ height: 4, background: 'rgba(255,255,255,0.08)', borderRadius: 2 }}>
                  <div
                    style={{
                      height: '100%',
                      width: `${pct}%`,
                      background: 'linear-gradient(90deg, #60a5fa, #22d3ee)',
                      borderRadius: 2,
                    }}
                  />
                </div>
              </div>
              <button
                className="btn btn-primary"
                style={{
                  width: '100%',
                  opacity: isApplied ? 0.6 : 1,
                  cursor: isApplied ? 'default' : 'pointer',
                }}
                disabled={isApplied || isApplying}
                onClick={() => !isApplied && applyToTeam(t.team_id)}
              >
                {isApplying ? 'Applying...' : isApplied ? 'Applied ✓' : 'Apply to Join'}
              </button>
            </GlassCard>
          );
        })}
      </div>

      {toastMsg && (
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
          {toastMsg}
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
