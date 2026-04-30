import { useQuery } from '@tanstack/react-query';
import Navbar from '@/components/layout/Navbar';
import PageHeader from '@/components/layout/PageHeader';
import GlassCard from '@/components/common/GlassCard';
import LoadingSpinner from '@/components/common/LoadingSpinner';
import api from '@/lib/api';
import type { RankedTeam } from '@/types/ranking';

const MEDAL = ['🥇', '🥈', '🥉'];
const PODIUM_ORDER = [1, 0, 2]; // 2nd, 1st, 3rd heights

function PodiumBlock({ team, rank }: { team: RankedTeam; rank: number }) {
  const heights = ['160px', '200px', '130px'];
  const colors = [
    'linear-gradient(135deg, #a78bfa, #7c3aed)',
    'linear-gradient(135deg, #fbbf24, #f59e0b)',
    'linear-gradient(135deg, #60a5fa, #22d3ee)',
  ];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 0 }}>
      <div style={{ textAlign: 'center', marginBottom: 12 }}>
        <div style={{ fontSize: 32 }}>{MEDAL[rank]}</div>
        <div style={{ fontWeight: 800, fontSize: 16, marginTop: 4 }}>{team.team_name}</div>
        <div
          style={{
            fontSize: 22,
            fontWeight: 900,
            color: rank === 0 ? '#fbbf24' : rank === 1 ? '#a78bfa' : '#60a5fa',
            marginTop: 2,
          }}
        >
          {team.score != null ? `${team.score.toFixed(2)} pts` : '—'}
        </div>
      </div>
      <div
        style={{
          width: 120,
          height: heights[rank],
          borderRadius: '12px 12px 0 0',
          background: colors[rank],
          display: 'flex',
          alignItems: 'flex-start',
          justifyContent: 'center',
          paddingTop: 12,
          fontWeight: 900,
          fontSize: 28,
          color: 'rgba(0,0,0,0.4)',
          boxShadow: `0 8px 32px ${rank === 0 ? 'rgba(251,191,36,0.3)' : rank === 1 ? 'rgba(167,139,250,0.3)' : 'rgba(96,165,250,0.3)'}`,
        }}
      >
        {rank + 1}
      </div>
    </div>
  );
}

function RankCard({ team, maxScore }: { team: RankedTeam; maxScore: number }) {
  const rank = team.rank ?? 0;
  const score = team.score ?? 0;
  const barPct = maxScore > 0 ? (score / maxScore) * 100 : 0;
  const barColor = rank <= 6 ? '#a78bfa' : rank <= 10 ? '#22d3ee' : 'rgba(255,255,255,0.2)';

  return (
    <GlassCard style={{ padding: '16px 20px' }}>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: 10,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <span
            style={{ fontWeight: 800, fontSize: 18, color: rank <= 9 ? '#60a5fa' : 'var(--muted)' }}
          >
            #{rank}
          </span>
          <span style={{ fontWeight: 700, fontSize: 15 }}>{team.team_name}</span>
        </div>
        <span
          style={{ fontWeight: 700, color: team.score == null ? 'var(--muted)' : 'var(--text)' }}
        >
          {team.score != null ? `${score.toFixed(2)} pts` : '—'}
        </span>
      </div>
      <div style={{ height: 4, background: 'rgba(255,255,255,0.06)', borderRadius: 2 }}>
        <div
          style={{
            height: '100%',
            width: `${barPct}%`,
            background: barColor,
            borderRadius: 2,
            transition: 'width 0.8s ease',
          }}
        />
      </div>
    </GlassCard>
  );
}

export default function RankingsLivePage() {
  const { data, isLoading } = useQuery<{ success: boolean; rankings: RankedTeam[] }>({
    queryKey: ['rankings'],
    queryFn: () => api.get('/api/teams/rankings'),
    refetchInterval: 30_000,
  });

  const rankings = data?.success ? (data.rankings ?? []) : [];
  const hasScores = rankings.some((t) => t.score != null);
  const top3 = rankings.slice(0, 3);
  const rest = rankings.slice(3);
  const maxScore = rankings.reduce((m, t) => Math.max(m, t.score ?? 0), 0);

  return (
    <>
      <Navbar />
      <main style={{ padding: '80px 24px 80px', maxWidth: '860px', margin: '0 auto' }}>
        <PageHeader
          eyebrow="Live"
          title="Rankings"
          subtitle="Scores update every 30 seconds."
        />

        {isLoading && <LoadingSpinner />}

        {!isLoading && (!hasScores || rankings.length === 0) && (
          <GlassCard style={{ padding: 48, textAlign: 'center' }}>
            <div style={{ fontSize: 48, marginBottom: 16 }}>🏆</div>
            <h2 style={{ fontWeight: 700, marginBottom: 8 }}>No Scores Yet</h2>
            <p style={{ color: 'var(--muted)' }}>Scores will appear here once judging begins.</p>
          </GlassCard>
        )}

        {!isLoading && hasScores && (
          <>
            {/* Podium */}
            {top3.length >= 1 && (
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'center',
                  alignItems: 'flex-end',
                  gap: 12,
                  marginBottom: 60,
                }}
              >
                {PODIUM_ORDER.map((idx) =>
                  top3[idx] ? (
                    <PodiumBlock
                      key={idx}
                      team={top3[idx]}
                      rank={idx}
                    />
                  ) : null,
                )}
              </div>
            )}

            {/* Rest */}
            {rest.length > 0 && (
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))',
                  gap: 14,
                }}
              >
                {rest.map((team) => (
                  <RankCard
                    key={team.team_id}
                    team={team}
                    maxScore={maxScore}
                  />
                ))}
              </div>
            )}
          </>
        )}
      </main>
    </>
  );
}
