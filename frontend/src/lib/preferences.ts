import { useState } from 'react';
import type { QueryClient } from '@tanstack/react-query';

/** The API's 403 message while the admin has preference submission switched off. */
export const PREFERENCES_CLOSED_ERROR = 'Preference submission is closed';

/**
 * Where a ranking page stands before matching is confirmed. While submissions
 * are closed a saved ranking is shown read-only, even mid-edit, and a missing
 * one shows the closed notice.
 */
export function rankingStep(
  hasSaved: boolean,
  editing: boolean,
  open: boolean,
  uiStep: 'select' | 'rank',
): 'select' | 'rank' | 'done' | 'closed' {
  if (hasSaved && (!editing || !open)) return 'done';
  return open ? uiStep : 'closed';
}

/** A save refused because submissions just closed: refetch the flags so the page locks now. */
export function refetchFlagsIfClosed(err: unknown, qc: QueryClient) {
  if (err instanceof Error && err.message === PREFERENCES_CLOSED_ERROR) {
    qc.invalidateQueries({ queryKey: ['config'] });
  }
}

/**
 * Calls onClose when submissions close and onReopen when they open again, so a
 * half-done edit isn't resumed with stale picks. Runs during render, React's
 * pattern for adjusting state when a prop changes.
 */
export function useOnPreferencesSwitch(open: boolean, onClose: () => void, onReopen: () => void) {
  const [seen, setSeen] = useState(open);
  if (seen !== open) {
    setSeen(open);
    if (open) onReopen();
    else onClose();
  }
}
