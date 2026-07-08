import { useQuery } from '@tanstack/react-query';
import Navbar from '@/components/layout/Navbar';
import PageHeader from '@/components/layout/PageHeader';
import Panel from '@/components/common/Panel';
import NestedCard from '@/components/common/NestedCard';
import LoadingSpinner from '@/components/common/LoadingSpinner';
import api from '@/lib/api';
import type { RankedTeam } from '@/types/ranking';

const PODIUM_ORDER = [1, 0, 2]; // 2nd, 1st, 3rd left-to-right

function PodiumBlock({ team, rank }: { team: RankedTeam; rank: number }) {
  const heights = ['160px', '200px', '130px'];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 0, minWidth: 140 }}>
      <div style={{ textAlign: 'center', marginBottom: 12 }}>
        <div
          className="px-label"
          style={{ color: 'var(--px-teal)', marginBottom: 6 }}
        >
          RANK #{rank + 1}
        </div>
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
            fontFamily: 'var(--px-font)',
            fontSize: '0.75rem',
            color: 'var(--px-teal)',
          }}
        >
          {team.score != null ? `${team.score.toFixed(2)} PTS` : '—'}
        </div>
      </div>
      <div
        style={{
          width: 120,
          height: heights[rank],
          background: 'var(--px-bg-card)',
          border: '2px solid var(--px-teal-border)',
          borderBottom: 'none',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontFamily: 'var(--px-font)',
          fontSize: '1.5rem',
          color: 'var(--px-salmon)',
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

  return (
    <NestedCard>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: 10,
          gap: 12,
          flexWrap: 'wrap',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <span
            className="px-label"
            style={{ color: 'var(--px-teal)', fontSize: '0.7rem' }}
          >
            #{rank}
          </span>
          <span
            style={{
              fontFamily: 'var(--px-mono)',
              fontWeight: 700,
              color: 'var(--px-white)',
            }}
          >
            {team.team_name}
          </span>
        </div>
        <span
          style={{
            fontFamily: 'var(--px-mono)',
            fontWeight: 700,
            color: team.score == null ? 'var(--px-muted-strong)' : 'var(--px-white)',
          }}
        >
          {team.score != null ? `${score.toFixed(2)} pts` : '—'}
        </span>
      </div>
      <div
        role="progressbar"
        aria-valuenow={score}
        aria-valuemin={0}
        aria-valuemax={maxScore || 1}
        aria-label={`${team.team_name} score`}
        className="px-progress-track"
        style={{ height: 4 }}
      >
        <div className="px-progress-fill" style={{ width: `${barPct}%` }} />
      </div>
    </NestedCard>
  );
}

export default function RankingsLivePage() {
  const { data, isLoading } = useQuery<{ success: boolean; rankings: RankedTeam[] }>({
    queryKey: ['rankings'],
    queryFn: () => api.get('/api/teams/rankings'),
    refetchInterval: 30_000,
    refetchIntervalInBackground: false,
  });

  const rankings = data?.success ? (data.rankings ?? []) : [];
  const hasScores = rankings.some((t) => t.score != null);
  const top3 = rankings.slice(0, 3);
  const rest = rankings.slice(3);
  const maxScore = rankings.reduce((m, t) => Math.max(m, t.score ?? 0), 0);

  return (
    <>
      <Navbar />
      <main style={{ padding: '80px 24px 80px', maxWidth: '900px', margin: '0 auto' }}>
        <PageHeader
          title="RANKINGS"
          description="Live scores. Updates every 30 seconds."
        />

        {isLoading && <LoadingSpinner />}

        {!isLoading && (!hasScores || rankings.length === 0) && (
          <Panel title="> NO SCORES YET">
            <p className="px-body" style={{ color: 'var(--px-muted-strong)', margin: 0 }}>
              &gt; Scores will appear here once judging begins.
            </p>
          </Panel>
        )}

        {!isLoading && hasScores && (
          <div aria-live="polite">
            {top3.length >= 1 && (
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'center',
                  alignItems: 'flex-end',
                  gap: 12,
                  marginBottom: 60,
                  flexWrap: 'wrap',
                }}
              >
                {PODIUM_ORDER.map((idx) =>
                  top3[idx] ? <PodiumBlock key={idx} team={top3[idx]} rank={idx} /> : null,
                )}
              </div>
            )}

            {rest.length > 0 && (
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))',
                  gap: 14,
                }}
              >
                {rest.map((team) => (
                  <RankCard key={team.team_id} team={team} maxScore={maxScore} />
                ))}
              </div>
            )}
          </div>
        )}
      </main>
    </>
  );
}
