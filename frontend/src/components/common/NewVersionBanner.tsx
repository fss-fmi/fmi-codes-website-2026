import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  IDLE,
  fetchServedBuild,
  nextState,
  readBuild,
  reloadPage,
  type CheckState,
} from '@/lib/buildId';

const KEY = ['build-id'];

/**
 * Offers a reload once the server settles on a build other than the one this tab runs. Mounted
 * outside the router and its error boundary, so it uses no router hooks and keeps its render
 * trivial.
 */
export default function NewVersionBanner() {
  const queryClient = useQueryClient();
  const [running] = useState(() => readBuild(document));
  const [dismissed, setDismissed] = useState<string | null>(null);

  // Each check folds into the last state (nextState), so an old pod reached mid-rollout neither
  // shows the card nor hides it; a failed fetch keeps the state too. initialData plus staleTime
  // spares a second fetch of index.html on page load.
  const { data } = useQuery({
    queryKey: KEY,
    enabled: running !== null,
    initialData: IDLE,
    staleTime: 30_000,
    refetchInterval: 30_000,
    refetchOnWindowFocus: 'always',
    queryFn: async () => {
      const state = queryClient.getQueryData<CheckState>(KEY) ?? IDLE;
      const served = await fetchServedBuild();
      return running ? nextState(state, served, running) : state;
    },
  });

  const newer = data.offer;
  const show = newer !== null && newer.id !== dismissed;

  // The live region stays mounted, so screen readers announce the text when it appears.
  return (
    <div
      role="status"
      aria-live="polite"
      style={{ position: 'fixed', left: '24px', bottom: '24px', zIndex: 1100 }}
    >
      {show && (
        <div
          style={{
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
            onClick={() => setDismissed(newer.id)}
            style={{
              minWidth: '44px',
              minHeight: '44px',
              margin: '-12px -16px 0 0',
              background: 'transparent',
              border: 'none',
              color: 'var(--px-muted-strong)',
              fontFamily: 'var(--px-font)',
              fontSize: '0.55rem',
              cursor: 'pointer',
            }}
          >
            ×
          </button>
        </div>
      )}
    </div>
  );
}
