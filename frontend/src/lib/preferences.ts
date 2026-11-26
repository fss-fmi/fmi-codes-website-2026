import { useState } from 'react';
import type { QueryClient } from '@tanstack/react-query';

/** The API's 403 message while the admin has preference submission switched off. */
export const PREFERENCES_CLOSED_ERROR = 'Preference submission is closed';

/** The API's 403 message once the admin has confirmed matching. */
export const PREFERENCES_CONFIRMED_ERROR =
  'Matching is confirmed, so preferences can no longer change.';

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

/**
 * A save refused because submissions just closed or matching was just confirmed: refetch
 * what changed so the page locks now.
 */
export function refetchFlagsIfClosed(err: unknown, qc: QueryClient) {
  if (!(err instanceof Error)) return;
  if (err.message === PREFERENCES_CLOSED_ERROR) {
    qc.invalidateQueries({ queryKey: ['config'] });
  } else if (err.message === PREFERENCES_CONFIRMED_ERROR) {
    qc.invalidateQueries({ queryKey: ['config'] });
    qc.invalidateQueries({ queryKey: ['matching-status'] });
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
