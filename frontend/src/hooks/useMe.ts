import { useQuery, useQueryClient } from '@tanstack/react-query';
import type { User } from '@/types/auth';

export type MeData = { success: boolean; user: User } | null;

export const ME_KEY = ['me'];

let generation = 0;

/**
 * Login, logout and a 401 elsewhere call this before they write the user: a /api/auth/me
 * answer requested before then describes the old session and must not overwrite theirs.
 */
export function startNewSession() {
  generation += 1;
}

/**
 * Raw fetch, so an expected 401 here never fires api.ts's auth:unauthorized. Only a 401
 * or 404 means nobody is signed in; any other failure throws, so the last answer is kept
 * and a 429 or a 503 logs nobody out.
 */
export async function fetchMe(): Promise<MeData> {
  const res = await fetch('/api/auth/me', { credentials: 'include' });
  if (res.status === 401 || res.status === 404) return null;
  if (!res.ok) throw new Error(`/api/auth/me answered ${res.status}`);
  return (await res.json()) as { success: boolean; user: User };
}

/**
 * The signed-in user, the one source AuthContext reads too. Each mount adds an observer,
 * which refetches stale data, so a page opened after someone else changed this user's
 * team (removed them, accepted them, made them captain) shows the change.
 */
export function useMe() {
  const queryClient = useQueryClient();
  return useQuery({
    queryKey: ME_KEY,
    queryFn: async () => {
      const started = generation;
      const me = await fetchMe();
      return started === generation ? me : (queryClient.getQueryData<MeData>(ME_KEY) ?? null);
    },
  });
}
