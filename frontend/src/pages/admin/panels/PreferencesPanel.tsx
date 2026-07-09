import { useQuery } from '@tanstack/react-query';
import Panel from '@/components/common/Panel';
import DonutChart from '@/components/admin/DonutChart';
import LoadingSpinner from '@/components/common/LoadingSpinner';
import api from '@/lib/api';
import { CHART_COLORS, type PrefStatus } from './shared';

export default function PreferencesPanel() {
  const { data, isLoading } = useQuery<PrefStatus>({
    queryKey: ['admin-pref-status'],
    queryFn: () => api.get('/api/admin/preference-status'),
  });

  if (isLoading) return <LoadingSpinner />;
  if (!data) return null;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))',
          gap: 20,
        }}
      >
        <DonutChart
          title="TEAM PREFERENCE SUBMISSIONS"
          data={[
            { name: 'Submitted', value: data.teams_submitted, color: CHART_COLORS.green },
            {
              name: 'Pending',
              value: data.teams_total - data.teams_submitted,
              color: CHART_COLORS.danger,
            },
          ].filter((d) => d.value > 0)}
        />
        <DonutChart
          title="MENTOR PREFERENCE SUBMISSIONS"
          data={[
            { name: 'Submitted', value: data.mentors_submitted, color: CHART_COLORS.teal },
            {
              name: 'Pending',
              value: data.mentors_total - data.mentors_submitted,
              color: CHART_COLORS.danger,
            },
          ].filter((d) => d.value > 0)}
        />
      </div>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))',
          gap: 20,
        }}
      >
        <Panel title={`TEAMS (${data.teams_submitted}/${data.teams_total})`}>
          {(data.teams ?? []).map((t) => (
            <div
              key={t.id}
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                padding: '8px 0',
                borderBottom: '1px solid var(--px-teal-dim)',
                fontFamily: 'var(--px-mono)',
                fontSize: '0.85rem',
                color: 'var(--px-white)',
              }}
            >
              <span>{t.name}</span>
              <span
                style={{
                  color: t.submitted ? CHART_COLORS.green : CHART_COLORS.danger,
                  fontWeight: 700,
                }}
              >
                {t.submitted ? '✓' : '—'}
              </span>
            </div>
          ))}
        </Panel>
        <Panel title={`MENTORS (${data.mentors_submitted}/${data.mentors_total})`}>
          {(data.mentors ?? []).map((m) => (
            <div
              key={m.id}
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                padding: '8px 0',
                borderBottom: '1px solid var(--px-teal-dim)',
                fontFamily: 'var(--px-mono)',
                fontSize: '0.85rem',
                color: 'var(--px-white)',
              }}
            >
              <span>{m.name}</span>
              <span
                style={{
                  color: m.submitted ? CHART_COLORS.green : CHART_COLORS.danger,
                  fontWeight: 700,
                }}
              >
                {m.submitted ? '✓' : '—'}
              </span>
            </div>
          ))}
        </Panel>
      </div>
    </div>
  );
}
