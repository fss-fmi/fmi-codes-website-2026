import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import Panel from '@/components/common/Panel';
import Button from '@/components/common/Button';
import ConfirmDialog from '@/components/common/ConfirmDialog';
import { useToast } from '@/components/common/useToast';
import { useConfirmAction } from '@/hooks/useConfirmAction';
import api from '@/lib/api';

export default function MatchingPanel() {
  const qc = useQueryClient();
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
      let d: { success: boolean; error?: string };
      try {
        d = await api.post('/api/admin/run-matching', {});
      } catch {
        throw new Error('Network error');
      }
      if (d.success) {
        qc.invalidateQueries({ queryKey: ['matching-status'] });
        refetchResults();
      } else {
        throw new Error(d.error ?? 'Error');
      }
    } finally {
      setRunning(false);
    }
  }

  async function doConfirmMatching() {
    setConfirming(true);
    try {
      let d: { success: boolean; error?: string };
      try {
        d = await api.post('/api/admin/confirm-matching', {});
      } catch {
        throw new Error('Network error');
      }
      if (d.success) {
        qc.invalidateQueries({ queryKey: ['matching-status'] });
        refetchResults();
      } else {
        throw new Error(d.error ?? 'Error');
      }
    } finally {
      setConfirming(false);
    }
  }

  function askRun() {
    confirm({
      title: 'RUN MATCHING',
      description: 'Run the matching algorithm? This will overwrite any previous results.',
      action: doRunMatching,
      successMessage: 'Matching complete.',
    });
  }

  function askConfirm() {
    confirm({
      title: 'CONFIRM MATCHING',
      description: 'Confirm and publish matching results? This cannot be undone.',
      dangerous: true,
      action: doConfirmMatching,
      successMessage: 'Matching confirmed.',
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
              disabled={confirming || confirmed || !hasRun}
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
