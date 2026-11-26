import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import Panel from '@/components/common/Panel';
import Button from '@/components/common/Button';
import ConfirmDialog from '@/components/common/ConfirmDialog';
import { useToast } from '@/components/common/useToast';
import { useConfig } from '@/context/ConfigContext';
import { useConfirmAction } from '@/hooks/useConfirmAction';
import api from '@/lib/api';
import { errorMessage } from '@/lib/errors';

interface MatchingExport {
  teams: { team_name: string; mentors: { mentor_name: string; company_name: string }[] }[];
  total_assignments: number;
  violations: string[];
  generated_at: string;
}

function plural(n: number, word: string) {
  return `${n} ${word}${n === 1 ? '' : 's'}`;
}

function formatExport(d: MatchingExport): string {
  // generated_at is the server's UTC isoformat(). Slicing it keeps the text the
  // same in every time zone; Date parsing of its 6-digit fraction varies by engine.
  const lines = [
    `MATCHING EXPORT  ${d.generated_at.slice(0, 16).replace('T', ' ')} UTC`,
    `${plural(d.total_assignments, 'assignment')}, ${plural(d.teams.length, 'team')}`,
    '',
  ];
  if (d.teams.length === 0) lines.push('No assignments.');
  for (const t of d.teams) {
    const mentors = t.mentors.map((m) =>
      m.company_name ? `${m.mentor_name} (${m.company_name})` : m.mentor_name,
    );
    lines.push(`${t.team_name}: ${mentors.join(', ')}`);
  }
  lines.push('');
  if (d.violations.length === 0) lines.push('Violations: none');
  else lines.push('Violations:', ...d.violations.map((v) => `- ${v}`));
  return lines.join('\n');
}

export default function MatchingPanel() {
  const qc = useQueryClient();
  const { PREFERENCES_OPEN } = useConfig();
  const { showToast } = useToast();
  const { confirm, dialogProps } = useConfirmAction();
  const [running, setRunning] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [exportData, setExportData] = useState<string | null>(null);

  const { data } = useQuery<{ success: boolean; confirmed: boolean }>({
    queryKey: ['matching-status'],
    queryFn: () => api.get('/api/matching-status'),
  });

  const { data: results, refetch: refetchResults } = useQuery<{
    success: boolean;
    results: { team_name: string; mentor_name: string }[];
  }>({
    queryKey: ['matching-results'],
    queryFn: () => api.get('/api/admin/matching-results'),
  });

  async function doRunMatching() {
    setRunning(true);
    try {
      const d = await api.post<{ warnings?: string[] }>('/api/admin/run-matching', {});
      setExportData(null);
      // A run clears any confirmation, which lifts the freeze /api/config reports.
      qc.invalidateQueries({ queryKey: ['matching-status'] });
      qc.invalidateQueries({ queryKey: ['config'] });
      refetchResults();
      if (d.warnings?.length) {
        showToast({ kind: 'warning', message: `Matching warnings: ${d.warnings.join('; ')}` });
      }
    } finally {
      setRunning(false);
    }
  }

  async function doConfirmMatching() {
    setConfirming(true);
    try {
      await api.post('/api/admin/confirm-matching', {});
      qc.invalidateQueries({ queryKey: ['matching-status'] });
      qc.invalidateQueries({ queryKey: ['config'] });
      refetchResults();
    } finally {
      setConfirming(false);
    }
  }

  async function askRun() {
    // The polled flags can be 30 s old, a scheduled close may have just fired and
    // another admin tab may have confirmed. Plain requests, not fetchQuery, which
    // would join a request already in flight from before the click. A failed read
    // keeps the cached value.
    const [flags, status] = await Promise.allSettled([
      api.get<{ PREFERENCES_OPEN: boolean }>('/api/config'),
      api.get<{ success: boolean; confirmed: boolean }>('/api/matching-status'),
    ]);
    // Refetch rather than setQueryData: an older request still in flight would
    // land after a set and overwrite it, while invalidating cancels it.
    qc.invalidateQueries({ queryKey: ['config'] });
    qc.invalidateQueries({ queryKey: ['matching-status'] });
    const open = flags.status === 'fulfilled' ? flags.value.PREFERENCES_OPEN : PREFERENCES_OPEN;
    const published =
      status.status === 'fulfilled' ? status.value.confirmed : (data?.confirmed ?? false);
    confirm({
      title: 'RUN MATCHING',
      description: [
        'Run the matching algorithm? This will overwrite any previous results, including mentor changes made in the TEAMS tab.',
        published &&
          'The current results are published; this run hides them and reopens team changes until you confirm again.',
        open && 'Preference submissions are still open, so rankings can change after this run.',
      ]
        .filter(Boolean)
        .join(' '),
      action: doRunMatching,
      successMessage: 'Matching complete.',
    });
  }

  function askConfirm() {
    confirm({
      title: 'CONFIRM MATCHING',
      description:
        'Publish the matching results? Teams and mentors will see their assignments. Running matching again hides them until you confirm again.',
      dangerous: true,
      action: doConfirmMatching,
      successMessage: 'Matching confirmed.',
    });
  }

  async function fetchExport() {
    try {
      const d = await api.get<MatchingExport>('/api/admin/matching-export');
      setExportData(formatExport(d));
    } catch (err: unknown) {
      showToast({ kind: 'danger', message: errorMessage(err) });
    }
  }

  async function copyExport() {
    if (!exportData) return;
    try {
      if (!navigator.clipboard) throw new Error('Clipboard unavailable');
      await navigator.clipboard.writeText(exportData);
      showToast({ kind: 'success', message: 'Copied to clipboard.' });
    } catch {
      showToast({ kind: 'danger', message: 'Could not copy to clipboard.' });
    }
  }

  const assignments = results?.results ?? [];
  const confirmed = data?.confirmed ?? false;
  const hasRun = assignments.length > 0;

  const stateLabel = confirmed ? 'CONFIRMED' : hasRun ? 'RAN — NOT CONFIRMED' : 'PENDING';

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
            <div
              className="px-label"
              style={{ marginBottom: 8 }}
            >
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
              disabled={confirming || confirmed || !hasRun}
            >
              {confirming ? 'CONFIRMING…' : 'CONFIRM'}
            </button>
            <button
              type="button"
              className="px-btn-ghost"
              onClick={fetchExport}
            >
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
            {assignments.map((a) => (
              <div
                key={`${a.team_name}-${a.mentor_name}`}
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
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              marginBottom: 12,
              alignItems: 'center',
            }}
          >
            <h3
              className="px-prompt-heading"
              style={{ margin: 0 }}
            >
              EXPORT DATA
            </h3>
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
            onClick={copyExport}
            className="px-btn-secondary"
            style={{ marginTop: 12 }}
          >
            COPY TO CLIPBOARD
          </button>
        </Panel>
      )}

      <ConfirmDialog {...dialogProps} />
    </div>
  );
}
