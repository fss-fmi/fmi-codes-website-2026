import { useEffect, useState } from 'react';

/**
 * True while the viewport matches the arcade design system's mobile
 * breakpoint (max-width: 768px). Follows a `MediaQueryList` so it
 * updates when the user rotates their device or resizes the window.
 *
 * Server-safe: returns `false` on the first render if `window` is
 * missing, which matches the desktop default. The client hydrates to
 * the correct value on mount.
 */
export function useIsMobile(): boolean {
  const [isMobile, setIsMobile] = useState(() => {
    if (typeof window === 'undefined') return false;
    return window.matchMedia('(max-width: 768px)').matches;
  });

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const mql = window.matchMedia('(max-width: 768px)');
    const onChange = (e: MediaQueryListEvent) => setIsMobile(e.matches);
    mql.addEventListener('change', onChange);
    // Reconcile once in case the value changed between render and mount —
    // guarded so we only re-render when it actually differs. This mount-time
    // sync is the intended pattern for a live MediaQueryList, so the
    // set-state-in-effect rule is intentionally suppressed here.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setIsMobile((prev) => (prev === mql.matches ? prev : mql.matches));
    return () => mql.removeEventListener('change', onChange);
  }, []);

  return isMobile;
}
