import { useQuery } from '@tanstack/react-query';
import type { User } from '@/types/auth';

export type MeData = { success: boolean; user: User } | null;

export const ME_KEY = ['me'];

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
  return useQuery({ queryKey: ME_KEY, queryFn: fetchMe });
}
