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
    // Sync once in case the value changed between render and mount.
    setIsMobile(mql.matches);
    return () => mql.removeEventListener('change', onChange);
  }, []);

  return isMobile;
}
