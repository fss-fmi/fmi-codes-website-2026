import type { QueryClient } from '@tanstack/react-query';
import { ApiError } from './errors';

/** The API's 403 text for a team change once matching is confirmed, shown as the lock note too. */
export const TEAMS_LOCKED =
  'Teams are locked while the event runs. For any changes, contact the organizers.';

/** A team change refused because matching was just confirmed: refetch the flags so the page locks now. */
export function refetchConfigIfLocked(err: unknown, qc: QueryClient) {
  if (err instanceof ApiError && err.status === 403 && err.message === TEAMS_LOCKED) {
    qc.invalidateQueries({ queryKey: ['config'] });
  }
}
