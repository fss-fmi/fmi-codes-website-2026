import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import Navbar from '@/components/layout/Navbar';
import PageHeader from '@/components/layout/PageHeader';
import Panel from '@/components/common/Panel';
import NestedCard from '@/components/common/NestedCard';
import LoadingSpinner from '@/components/common/LoadingSpinner';
import api from '@/lib/api';
import type { RankedTeam } from '@/types/ranking';

// Left-to-right podium slots map to ranks [2nd, 1st, 3rd]. PODIUM_HEIGHTS is
// indexed by rank (0=1st, 1=2nd, 2=3rd) — values preserved from the original
// design so the visual output is unchanged.
const PODIUM_ORDER = [1, 0, 2];
const PODIUM_HEIGHTS = ['160px', '200px', '130px'];

function PodiumBlock({ team, rank }: { team: RankedTeam; rank: number }) {
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
          height: PODIUM_HEIGHTS[rank],
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
        <div className="px-progress-fill" style={{ transform: `scaleX(${barPct / 100})` }} />
      </div>
    </NestedCard>
  );
}

export default function RankingsLivePage() {
  const { data, isLoading, isError } = useQuery<{ success: boolean; rankings: RankedTeam[] }>({
    queryKey: ['rankings'],
    queryFn: () => api.get('/api/teams/rankings'),
    refetchInterval: 30_000,
    refetchIntervalInBackground: false,
  });

  const { hasScores, top3, rest, maxScore, rankingsLength } = useMemo(() => {
    const rankings = data?.success ? (data.rankings ?? []) : [];
    return {
      hasScores: rankings.some((t) => t.score != null),
      top3: rankings.slice(0, 3),
      rest: rankings.slice(3),
      maxScore: rankings.reduce((m, t) => Math.max(m, t.score ?? 0), 0),
      rankingsLength: rankings.length,
    };
  }, [data]);

  return (
    <>
      <Navbar />
      <main style={{ padding: '80px 24px 80px', maxWidth: '900px', margin: '0 auto' }}>
        <PageHeader
          title="RANKINGS"
          description="Live scores. Updates every 30 seconds."
        />

        {isLoading && <LoadingSpinner />}

        {!isLoading && isError && (
          <Panel title="> CONNECTION LOST">
            <p className="px-body" style={{ color: 'var(--px-salmon)', margin: 0 }}>
              &gt; Could not reach the scoreboard — retrying every 30 seconds…
            </p>
          </Panel>
        )}

        {!isLoading && !isError && (!hasScores || rankingsLength === 0) && (
          <Panel title="> NO SCORES YET">
            <p className="px-body" style={{ color: 'var(--px-muted-strong)', margin: 0 }}>
              &gt; Scores will appear here once judging begins.
            </p>
          </Panel>
        )}

        {!isLoading && !isError && hasScores && (
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
                  top3[idx] ? <PodiumBlock key={top3[idx].team_id} team={top3[idx]} rank={idx} /> : null,
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
