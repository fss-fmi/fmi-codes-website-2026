import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { fetchServedBuildId, readBuildId, reloadPage } from '@/lib/buildId';

const KEY = ['build-id'];

/**
 * Offers a reload once the server serves a build other than the one this tab runs. Mounted
 * outside the router and its error boundary, so it uses no router hooks and keeps its render
 * trivial.
 */
export default function NewVersionBanner() {
  const queryClient = useQueryClient();
  const [running] = useState(() => readBuildId(document));
  const [dismissed, setDismissed] = useState<string | null>(null);

  // data is the newest build id seen that differs from the running one. It never goes back to
  // null, so the card stays while a rollout serves old and new pods in turn; a failed fetch
  // keeps it too. initialData plus staleTime spares a second fetch of index.html on page load.
  const { data: newer } = useQuery({
    queryKey: KEY,
    enabled: running !== null,
    initialData: null,
    staleTime: 30_000,
    refetchInterval: 30_000,
    refetchOnWindowFocus: 'always',
    queryFn: async () => {
      const served = await fetchServedBuildId();
      if (served !== null && served !== running) return served;
      return queryClient.getQueryData<string | null>(KEY) ?? null;
    },
  });

  if (!newer || newer === dismissed) return null;

  return (
    <div
      role="status"
      aria-live="polite"
      style={{
        position: 'fixed',
        left: '24px',
        bottom: '24px',
        zIndex: 1100,
        maxWidth: 'min(360px, calc(100vw - 24px - 84px))',
        background: 'var(--px-bg-panel)',
        borderTop: '1px solid var(--px-teal-dim)',
        borderRight: '1px solid var(--px-teal-dim)',
        borderBottom: '1px solid var(--px-teal-dim)',
        borderLeft: '2px solid var(--px-teal)',
        padding: '16px 20px',
        color: 'var(--px-white)',
        fontFamily: 'var(--px-mono)',
        fontSize: '0.85rem',
        lineHeight: 1.5,
        display: 'flex',
        alignItems: 'flex-start',
        gap: '12px',
      }}
    >
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '12px' }}>
        <span>A new version of the site is available.</span>
        <button
          type="button"
          className="px-btn"
          onClick={reloadPage}
          style={{ alignSelf: 'flex-start', padding: '8px 14px' }}
        >
          RELOAD
        </button>
      </div>
      <button
        type="button"
        aria-label="Dismiss"
        onClick={() => setDismissed(newer)}
        style={{
          background: 'transparent',
          border: 'none',
          color: 'var(--px-muted-strong)',
          fontFamily: 'var(--px-font)',
          fontSize: '0.55rem',
          cursor: 'pointer',
          padding: '2px 6px',
        }}
      >
        ×
      </button>
    </div>
  );
}
