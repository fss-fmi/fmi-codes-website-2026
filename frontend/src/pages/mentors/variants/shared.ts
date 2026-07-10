import { useQuery } from '@tanstack/react-query';
import api from '@/lib/api';
import type { Mentor } from '@/types/mentor';

/**
 * Shared data hook used by all three Mentors variants.
 */
export function useMentors(enabled = true) {
  return useQuery<Mentor[]>({
    queryKey: ['mentors'],
    queryFn: () =>
      api
        .get<{ success: boolean; mentors: Mentor[] }>('/api/mentors')
        .then((r) => r.mentors),
    staleTime: 5 * 60_000,
    enabled,
  });
}

/**
 * Group mentors by company_name (preserves API order within each company).
 * Companies that don't share a name stay one-per-group. Returns entries in
 * the order the companies first appeared in the API response.
 */
export function groupByCompany(mentors: Mentor[]): Array<{
  company: string;
  mentors: Mentor[];
}> {
  const order: string[] = [];
  const buckets = new Map<string, Mentor[]>();
  for (const m of mentors) {
    const company = m.company_name?.trim() || 'INDEPENDENT';
    if (!buckets.has(company)) {
      order.push(company);
      buckets.set(company, []);
    }
    buckets.get(company)!.push(m);
  }
  return order.map((company) => ({ company, mentors: buckets.get(company)! }));
}

/**
 * Pad a mentor's 1-based position to two digits (M.01 … M.20).
 */
export function mentorNumber(index: number): string {
  return String(index + 1).padStart(2, '0');
}

/**
 * Resolve a mentor's picture source. Prefers inline base64 picture_data, then
 * picture_url (absolute /static paths are used as-is, bare filenames are
 * prefixed), then picture_filename. Falls back to null so the caller can
 * render initials. Accepts any object carrying a subset of the picture fields
 * so both the Mentor shape and the selected-mentors shape can use it.
 */
export function pictureFor(mentor: {
  picture_data?: string | null;
  picture_url?: string | null;
  picture_filename?: string | null;
}): string | null {
  if (mentor.picture_data) {
    return `data:image/png;base64,${mentor.picture_data}`;
  }
  if (mentor.picture_url) {
    return mentor.picture_url.startsWith('/')
      ? mentor.picture_url
      : `/static/mentorPictures/${mentor.picture_url}`;
  }
  if (mentor.picture_filename) {
    return `/static/mentorPictures/${mentor.picture_filename}`;
  }
  return null;
}

/**
 * Classify an availability string into a semantic status. The API uses a
 * few different phrasings; we pattern-match the most common ones.
 */
export type AvailabilityStatus = 'full' | 'partial' | 'limited' | 'unknown';

export function availabilityStatus(text?: string | null): AvailabilityStatus {
  if (!text) return 'unknown';
  const t = text.toLowerCase();
  const hasSat = /sat/.test(t);
  const hasSun = /sun/.test(t);
  const shortSat = /sat 13:00 - 16:00/.test(t);
  if (hasSat && hasSun && !shortSat) return 'full';
  if (hasSat && hasSun && shortSat) return 'partial';
  if (hasSat && !hasSun) return 'limited';
  return 'unknown';
}

/**
 * Semantic dot colors for each availability status, shared by every consumer
 * that renders an availability indicator.
 */
export const AVAILABILITY_COLORS: Record<AvailabilityStatus, string> = {
  full: 'var(--px-green)',
  partial: 'var(--px-amber)',
  limited: 'var(--px-salmon)',
  unknown: 'var(--px-muted)',
};

/**
 * Cap technologies at N and return {shown, more} for a "+3 more" ellipsis.
 */
export function capTechs(techs: string[] | undefined, cap = 8): {
  shown: string[];
  more: number;
} {
  const list = Array.isArray(techs) ? techs.filter(Boolean) : [];
  if (list.length <= cap) return { shown: list, more: 0 };
  return { shown: list.slice(0, cap), more: list.length - cap };
}
