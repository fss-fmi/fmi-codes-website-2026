import { useQuery, useQueryClient } from '@tanstack/react-query';
import Panel from '@/components/common/Panel';
import { useToast } from '@/components/common/useToast';
import DonutChart from '@/components/admin/DonutChart';
import LoadingSpinner from '@/components/common/LoadingSpinner';
import api from '@/lib/api';
import { CHART_COLORS, type RegStatus } from './shared';

export default function RegistrationPanel() {
  const qc = useQueryClient();
  const { showToast } = useToast();

  const { data, isLoading, isError } = useQuery<RegStatus>({
    queryKey: ['admin-reg-status'],
    queryFn: () => api.get('/api/admin/teams/registration-status'),
  });

  async function handleRegister(teamId: number) {
    try {
      const d = await api.post<{ success: boolean; error?: string }>(
        `/api/admin/teams/${teamId}/register`,
        {},
      );
      if (d.success) {
        qc.invalidateQueries({ queryKey: ['admin-reg-status'] });
        showToast({ kind: 'success', message: 'Team registered.' });
      } else showToast({ kind: 'danger', message: d.error ?? 'Error' });
    } catch {
      showToast({ kind: 'danger', message: 'Network error' });
    }
  }

  async function handleUnregister(teamId: number) {
    try {
      const d = await api.post<{ success: boolean; error?: string }>(
        `/api/admin/teams/${teamId}/unregister`,
        {},
      );
      if (d.success) {
        qc.invalidateQueries({ queryKey: ['admin-reg-status'] });
        showToast({ kind: 'success', message: 'Team unregistered.' });
      } else showToast({ kind: 'danger', message: d.error ?? 'Error' });
    } catch {
      showToast({ kind: 'danger', message: 'Network error' });
    }
  }

  if (isLoading) return <LoadingSpinner />;
  if (isError)
    return (
      <Panel title="REGISTRATION">
        <p className="px-body-sm" style={{ color: 'var(--px-danger)', margin: 0 }}>
          &gt; Failed to load registration data.
        </p>
      </Panel>
    );
  if (!data) return null;
  const { registered_count, max_registered, queue_count, registered_teams, queued_teams } = data;
  const pct = Math.round((registered_count / (max_registered || 1)) * 100);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      <Panel title="REGISTRATION PROGRESS">
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            marginBottom: 8,
            fontFamily: 'var(--px-mono)',
            fontSize: '0.9rem',
            color: 'var(--px-muted-strong)',
          }}
        >
          <span>Registered Teams</span>
          <span>
            {registered_count}/{max_registered}
          </span>
        </div>
        <div
          role="progressbar"
          aria-valuenow={registered_count}
          aria-valuemin={0}
          aria-valuemax={max_registered}
          aria-label="Teams registered progress"
          className="px-progress-track"
          style={{ height: 8 }}
        >
          <div className="px-progress-fill" style={{ transform: `scaleX(${pct / 100})` }} />
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 16 }}>
          {Array.from({ length: max_registered }, (_, i) => (
            <div
              key={i}
              aria-hidden="true"
              style={{
                width: 10,
                height: 10,
                background:
                  i < registered_count ? CHART_COLORS.green : 'var(--px-teal-dim)',
              }}
            />
          ))}
        </div>
      </Panel>

      <DonutChart
        title="SLOT ALLOCATION"
        data={[
          { name: 'Registered', value: registered_count, color: CHART_COLORS.green },
          { name: 'Queued', value: queue_count, color: CHART_COLORS.amber },
          {
            name: 'Available',
            value: Math.max(0, max_registered - registered_count - queue_count),
            color: CHART_COLORS.tealDim,
          },
        ].filter((d) => d.value > 0)}
      />

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))',
          gap: 20,
        }}
      >
        <Panel title={`REGISTERED (${registered_count})`}>
          {registered_teams.length === 0 && (
            <p className="px-body-sm" style={{ color: 'var(--px-muted-strong)', margin: 0 }}>
              &gt; No teams yet.
            </p>
          )}
          {registered_teams.map((t) => (
            <div
              key={t.id}
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                padding: '10px 0',
                borderBottom: '1px solid var(--px-teal-dim)',
                gap: '12px',
                flexWrap: 'wrap',
              }}
            >
              <span style={{ fontFamily: 'var(--px-mono)', fontSize: '0.9rem', color: 'var(--px-white)' }}>
                {t.team_name}
              </span>
              <button
                type="button"
                className="px-btn-danger"
                onClick={() => handleUnregister(t.id)}
                aria-label={`Unregister ${t.team_name}`}
                style={{ padding: '10px 16px', fontSize: '0.55rem' }}
              >
                UNREGISTER
              </button>
            </div>
          ))}
        </Panel>

        <Panel title={`QUEUE (${queue_count})`}>
          {queued_teams.length === 0 && (
            <p className="px-body-sm" style={{ color: 'var(--px-muted-strong)', margin: 0 }}>
              &gt; Queue is empty.
            </p>
          )}
          {queued_teams.map((t) => (
            <div
              key={t.id}
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                padding: '10px 0',
                borderBottom: '1px solid var(--px-teal-dim)',
                gap: '12px',
                flexWrap: 'wrap',
              }}
            >
              <span style={{ fontFamily: 'var(--px-mono)', fontSize: '0.9rem', color: 'var(--px-white)' }}>
                {t.team_name}
              </span>
              <button
                type="button"
                className="px-btn-secondary"
                onClick={() => handleRegister(t.id)}
                aria-label={`Register ${t.team_name}`}
                style={{ padding: '10px 16px', fontSize: '0.55rem' }}
              >
                REGISTER
              </button>
            </div>
          ))}
        </Panel>
      </div>
    </div>
  );
}
