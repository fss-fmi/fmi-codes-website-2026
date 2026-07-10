import { useQuery, useQueryClient } from '@tanstack/react-query';
import Panel from '@/components/common/Panel';
import { useToast } from '@/components/common/useToast';
import ScoreInput from '@/components/admin/ScoreInput';
import HorizontalBar from '@/components/admin/HorizontalBar';
import LoadingSpinner from '@/components/common/LoadingSpinner';
import api from '@/lib/api';
import type { TeamScore } from './shared';

export default function ScoresPanel() {
  const qc = useQueryClient();
  const { showToast } = useToast();

  const { data, isLoading } = useQuery<{ teams: TeamScore[] }>({
    queryKey: ['admin-scores'],
    queryFn: () => api.get('/api/admin/teams/scores'),
  });

  async function saveScore(teamId: number, score: number) {
    try {
      const d = await api.put<{ success: boolean; error?: string }>(
        `/api/admin/teams/${teamId}/score`,
        { score },
      );
      if (d.success) {
        qc.invalidateQueries({ queryKey: ['admin-scores'] });
        showToast({ kind: 'success', message: 'Score saved.' });
      } else showToast({ kind: 'danger', message: d.error ?? 'Error' });
    } catch {
      showToast({ kind: 'danger', message: 'Network error' });
    }
  }

  if (isLoading) return <LoadingSpinner />;

  const scoredTeams = [...(data?.teams ?? [])]
    .filter((t) => t.score !== null)
    .sort((a, b) => (b.score ?? 0) - (a.score ?? 0));
  const maxScore = Math.max(...scoredTeams.map((t) => t.score ?? 0), 1);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      {scoredTeams.length > 0 && (
        <Panel title="SCORE OVERVIEW">
          {scoredTeams.map((t) => (
            <HorizontalBar
              key={t.team_id}
              label={t.team_name}
              value={t.score ?? 0}
              max={maxScore}
              color="var(--px-teal)"
            />
          ))}
        </Panel>
      )}

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
          gap: 14,
        }}
      >
        {(data?.teams ?? []).map((t) => (
          <div
            key={t.team_id}
            style={{
              background: 'var(--px-bg-card)',
              border: '1px solid var(--px-teal-dim)',
              padding: '20px',
            }}
          >
            <div
              style={{
                fontFamily: 'var(--px-mono)',
                fontWeight: 700,
                marginBottom: 12,
                fontSize: '0.95rem',
                color: 'var(--px-white)',
              }}
            >
              {t.team_name}
            </div>
            <ScoreInput
              teamId={t.team_id}
              teamName={t.team_name}
              currentScore={t.score}
              onSave={saveScore}
            />
          </div>
        ))}
      </div>
    </div>
  );
}
