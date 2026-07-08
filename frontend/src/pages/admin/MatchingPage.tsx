import { useState, useEffect, useRef } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import Navbar from '@/components/layout/Navbar';
import RequireAuth from '@/components/layout/RequireAuth';
import PageHeader from '@/components/layout/PageHeader';
import Panel from '@/components/common/Panel';
import Button from '@/components/common/Button';
import ConfirmDialog from '@/components/common/ConfirmDialog';
import { useToast } from '@/components/common/useToast';
import KPICard from '@/components/admin/KPICard';
import ScoreInput from '@/components/admin/ScoreInput';
import DonutChart from '@/components/admin/DonutChart';
import HorizontalBar from '@/components/admin/HorizontalBar';
import LoadingSpinner from '@/components/common/LoadingSpinner';
import api from '@/lib/api';

interface RegStatus {
  registered_count: number;
  max_registered: number;
  queue_count: number;
  registered_teams: { id: number; team_name: string }[];
  queued_teams: { id: number; team_name: string }[];
}

interface PrefStatus {
  teams_submitted: number;
  teams_total: number;
  mentors_submitted: number;
  mentors_total: number;
  teams: { id: number; name: string; submitted: boolean }[];
  mentors: { id: number; name: string; submitted: boolean }[];
}

interface TeamScore {
  team_id: number;
  team_name: string;
  score: number | null;
}

type Tab = 'registration' | 'preferences' | 'matching' | 'scores';

const PALETTE = {
  green: 'var(--px-green)',
  amber: 'var(--px-amber)',
  danger: 'var(--px-danger)',
  teal: 'var(--px-teal)',
  tealDim: 'var(--px-teal-dim)',
};

// Recharts consumes CSS variables through getComputedStyle at render time; we resolve them once here.
const CHART_COLORS = {
  green: '#4ecdc4',
  amber: '#f9a825',
  danger: '#e05252',
  teal: '#2dd4bf',
  tealDim: 'rgba(45, 212, 191, 0.18)',
};

function RegistrationPanel() {
  const qc = useQueryClient();
  const { showToast } = useToast();

  const { data, isLoading } = useQuery<RegStatus>({
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
          <div className="px-progress-fill" style={{ width: `${pct}%` }} />
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

function PreferencesPanel() {
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
                  color: t.submitted ? PALETTE.green : PALETTE.danger,
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
                  color: m.submitted ? PALETTE.green : PALETTE.danger,
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

interface DialogState {
  open: boolean;
  title: string;
  description?: string;
  onConfirm: () => void;
}

const CLOSED_DIALOG: DialogState = {
  open: false,
  title: '',
  onConfirm: () => {},
};

function MatchingPanel() {
  const qc = useQueryClient();
  const { showToast } = useToast();
  const [running, setRunning] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [exportData, setExportData] = useState<string | null>(null);
  const [dialog, setDialog] = useState<DialogState>(CLOSED_DIALOG);

  const { data } = useQuery<{
    state: string;
    assignments?: { team_name: string; mentor_name: string }[];
  }>({
    queryKey: ['matching-status'],
    queryFn: () => api.get('/api/matching-status'),
  });

  const { data: results, refetch: refetchResults } = useQuery<{
    success: boolean;
    results: { team_name: string; mentor_name: string }[];
  }>({
    queryKey: ['matching-results'],
    queryFn: () => api.get('/api/admin/matching-results'),
    enabled: false,
  });

  async function doRunMatching() {
    setDialog(CLOSED_DIALOG);
    setRunning(true);
    try {
      const d = await api.post<{ success: boolean; error?: string }>('/api/admin/run-matching', {});
      if (d.success) {
        qc.invalidateQueries({ queryKey: ['matching-status'] });
        refetchResults();
        showToast({ kind: 'success', message: 'Matching complete.' });
      } else showToast({ kind: 'danger', message: d.error ?? 'Error' });
    } catch {
      showToast({ kind: 'danger', message: 'Network error' });
    } finally {
      setRunning(false);
    }
  }

  async function doConfirmMatching() {
    setDialog(CLOSED_DIALOG);
    setConfirming(true);
    try {
      const d = await api.post<{ success: boolean; error?: string }>(
        '/api/admin/confirm-matching',
        {},
      );
      if (d.success) {
        qc.invalidateQueries({ queryKey: ['matching-status'] });
        showToast({ kind: 'success', message: 'Matching confirmed.' });
      } else showToast({ kind: 'danger', message: d.error ?? 'Error' });
    } catch {
      showToast({ kind: 'danger', message: 'Network error' });
    } finally {
      setConfirming(false);
    }
  }

  function askRun() {
    setDialog({
      open: true,
      title: 'RUN MATCHING',
      description: 'Run the matching algorithm? This will overwrite any previous results.',
      onConfirm: doRunMatching,
    });
  }

  function askConfirm() {
    setDialog({
      open: true,
      title: 'CONFIRM MATCHING',
      description: 'Confirm and publish matching results? This cannot be undone.',
      onConfirm: doConfirmMatching,
    });
  }

  async function fetchExport() {
    try {
      const d = await api.get<{ success: boolean; export: string }>('/api/admin/matching-export');
      if (d.success) setExportData(d.export);
    } catch {
      showToast({ kind: 'danger', message: 'Export failed' });
    }
  }

  const state = data?.state ?? 'pending';
  const assignments = results?.results ?? data?.assignments ?? [];

  const stateLabel =
    state === 'confirmed'
      ? 'CONFIRMED'
      : state === 'complete'
        ? 'RAN — NOT CONFIRMED'
        : 'PENDING';

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <Panel>
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            gap: 16,
            flexWrap: 'wrap',
          }}
        >
          <div>
            <div className="px-label" style={{ marginBottom: 8 }}>
              MATCHING STATE
            </div>
            <div
              style={{
                fontFamily: 'var(--px-font)',
                fontSize: '1rem',
                color: 'var(--px-salmon)',
              }}
            >
              {stateLabel}
            </div>
          </div>
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
            <Button
              variant="primary"
              onClick={askRun}
              disabled={running}
            >
              {running ? 'RUNNING…' : 'RUN MATCHING'}
            </Button>
            <button
              type="button"
              className="px-btn-secondary"
              onClick={askConfirm}
              disabled={confirming || state === 'confirmed'}
            >
              {confirming ? 'CONFIRMING…' : 'CONFIRM'}
            </button>
            <button type="button" className="px-btn-ghost" onClick={fetchExport}>
              EXPORT
            </button>
          </div>
        </div>
      </Panel>

      {assignments.length > 0 && (
        <Panel title={`RESULTS (${assignments.length} PAIRS)`}>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
              gap: 10,
            }}
          >
            {assignments.map((a, i) => (
              <div
                key={i}
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  padding: '10px 14px',
                  background: 'var(--px-bg-card)',
                  border: '1px solid var(--px-teal-dim)',
                  fontFamily: 'var(--px-mono)',
                  fontSize: '0.85rem',
                  color: 'var(--px-white)',
                  gap: 12,
                }}
              >
                <span style={{ fontWeight: 700 }}>{a.team_name}</span>
                <span style={{ color: 'var(--px-teal)' }}>→ {a.mentor_name}</span>
              </div>
            ))}
          </div>
        </Panel>
      )}

      {exportData && (
        <Panel>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 12, alignItems: 'center' }}>
            <h3 className="px-prompt-heading" style={{ margin: 0 }}>EXPORT DATA</h3>
            <button
              type="button"
              onClick={() => setExportData(null)}
              aria-label="Close export"
              style={{
                border: 'none',
                background: 'transparent',
                color: 'var(--px-muted-strong)',
                cursor: 'pointer',
                fontFamily: 'var(--px-font)',
                fontSize: '0.75rem',
              }}
            >
              ×
            </button>
          </div>
          <pre
            style={{
              background: 'var(--px-bg)',
              padding: 16,
              fontFamily: 'var(--px-mono)',
              fontSize: '0.75rem',
              overflowX: 'auto',
              color: 'var(--px-white)',
              maxHeight: 300,
              border: '1px solid var(--px-teal-dim)',
            }}
          >
            {exportData}
          </pre>
          <button
            type="button"
            onClick={() => navigator.clipboard.writeText(exportData)}
            className="px-btn-secondary"
            style={{ marginTop: 12 }}
          >
            COPY TO CLIPBOARD
          </button>
        </Panel>
      )}

      <ConfirmDialog
        open={dialog.open}
        title={dialog.title}
        description={dialog.description}
        onConfirm={dialog.onConfirm}
        onCancel={() => setDialog(CLOSED_DIALOG)}
      />
    </div>
  );
}

function ScoresPanel() {
  const qc = useQueryClient();
  const { showToast } = useToast();

  const { data, isLoading } = useQuery<{ teams: TeamScore[] }>({
    queryKey: ['admin-scores'],
    queryFn: () => api.get('/api/admin/teams/scores'),
  });

  async function saveScore(teamId: number, score: number) {
    try {
      const d = await api.post<{ success: boolean; error?: string }>(
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

function MatchingContent() {
  const [tab, setTab] = useState<Tab>('registration');
  const [clock, setClock] = useState(() =>
    new Date().toLocaleTimeString('en-GB', { hour12: false }),
  );
  const clockRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    clockRef.current = setInterval(
      () => setClock(new Date().toLocaleTimeString('en-GB', { hour12: false })),
      1000,
    );
    return () => {
      if (clockRef.current) clearInterval(clockRef.current);
    };
  }, []);

  const { data: regData } = useQuery<RegStatus>({
    queryKey: ['admin-reg-status'],
    queryFn: () => api.get('/api/admin/teams/registration-status'),
  });

  const { data: prefData } = useQuery<PrefStatus>({
    queryKey: ['admin-pref-status'],
    queryFn: () => api.get('/api/admin/preference-status'),
  });

  const { data: matchData } = useQuery<{ state: string; assignment_count?: number }>({
    queryKey: ['matching-status'],
    queryFn: () => api.get('/api/matching-status'),
  });

  const tabs: { key: Tab; label: string; badge?: string | number }[] = [
    {
      key: 'registration',
      label: 'REGISTRATION',
      badge: regData ? `${regData.registered_count}/${regData.max_registered}` : undefined,
    },
    {
      key: 'preferences',
      label: 'PREFERENCES',
      badge: prefData ? `${prefData.teams_submitted}` : undefined,
    },
    { key: 'matching', label: 'MATCHING', badge: matchData?.state?.toUpperCase() },
    { key: 'scores', label: 'SCORES' },
  ];

  return (
    <main style={{ padding: '80px 24px 80px', maxWidth: '1100px', margin: '0 auto' }}>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
          marginBottom: 32,
          gap: 20,
          flexWrap: 'wrap',
        }}
      >
        <PageHeader title="MISSION CONTROL" />
        <div
          style={{
            fontFamily: 'var(--px-font)',
            fontSize: '1.2rem',
            color: 'var(--px-teal)',
            letterSpacing: '0.08em',
            paddingTop: 48,
          }}
          aria-label="Current time"
        >
          {clock}
        </div>
      </div>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
          gap: 16,
          marginBottom: 32,
        }}
      >
        <KPICard
          label="REGISTERED TEAMS"
          value={regData ? `${regData.registered_count}/${regData.max_registered}` : '—'}
          unit="slots"
        />
        <KPICard
          label="IN QUEUE"
          value={regData ? regData.queue_count : '—'}
          unit="waiting"
        />
        <KPICard
          label="TEAMS W/ PREFS"
          value={prefData ? `${prefData.teams_submitted}/${prefData.teams_total}` : '—'}
        />
        <KPICard
          label="MENTORS W/ PREFS"
          value={prefData ? `${prefData.mentors_submitted}/${prefData.mentors_total}` : '—'}
        />
        <KPICard label="MATCHING STATE" value={matchData?.state?.toUpperCase() ?? '—'} />
      </div>

      <div
        role="tablist"
        style={{
          display: 'flex',
          gap: 8,
          marginBottom: 24,
          borderBottom: '2px solid var(--px-teal-border)',
          paddingBottom: 0,
          flexWrap: 'wrap',
        }}
      >
        {tabs.map((t) => (
          <button
            key={t.key}
            type="button"
            role="tab"
            aria-selected={tab === t.key}
            onClick={() => setTab(t.key)}
            style={{
              padding: '12px 18px',
              border: 'none',
              cursor: 'pointer',
              fontFamily: 'var(--px-font)',
              fontSize: '0.6rem',
              letterSpacing: '0.06em',
              textTransform: 'uppercase',
              background: 'transparent',
              color: tab === t.key ? 'var(--px-teal)' : 'var(--px-muted-strong)',
              borderBottom:
                tab === t.key ? '2px solid var(--px-teal)' : '2px solid transparent',
              marginBottom: -2,
              transition: 'color 0.2s',
            }}
          >
            &gt; {t.label}
            {t.badge !== undefined && (
              <span
                style={{
                  marginLeft: 8,
                  padding: '2px 8px',
                  background: 'var(--px-bg-elevated)',
                  color: 'var(--px-teal)',
                  fontFamily: 'var(--px-mono)',
                  fontSize: '0.65rem',
                  fontWeight: 700,
                }}
              >
                {t.badge}
              </span>
            )}
          </button>
        ))}
      </div>

      {tab === 'registration' && <RegistrationPanel />}
      {tab === 'preferences' && <PreferencesPanel />}
      {tab === 'matching' && <MatchingPanel />}
      {tab === 'scores' && <ScoresPanel />}
    </main>
  );
}

export default function MatchingPage() {
  return (
    <RequireAuth roles={['admin']}>
      <Navbar />
      <MatchingContent />
    </RequireAuth>
  );
}
