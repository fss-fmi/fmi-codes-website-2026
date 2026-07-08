import { useQuery } from '@tanstack/react-query';
import api from '@/lib/api';

export interface Regulation {
  question: string;
  answer: string;
}

/**
 * Shared data hook used by all three Regulations variants.
 * The API returns rules in a fixed order; we don't sort them client-side.
 */
export function useRegulations() {
  return useQuery<Regulation[]>({
    queryKey: ['regulations'],
    queryFn: () =>
      api
        .get<{ success: boolean; regulations: Regulation[] }>('/api/regulations')
        .then((r) => r.regulations),
    staleTime: 5 * 60_000,
  });
}

/**
 * The 13 rules cluster into 5 acts. The grouping matches the natural reading
 * flow (What is it → Who / How to enter → How to work → How you compete →
 * Legal), not the API order — the API order is preserved inside each act.
 *
 * Index refers to the rule's 0-based position in the API response.
 */
export interface Chapter {
  key: string;
  num: string;
  title: string;
  ruleIndexes: number[];
}

export const CHAPTERS: Chapter[] = [
  { key: 'event', num: '01', title: 'THE EVENT', ruleIndexes: [0, 1] },
  { key: 'register', num: '02', title: 'REGISTER + TEAMS', ruleIndexes: [2, 3] },
  { key: 'work', num: '03', title: 'THE WORK', ruleIndexes: [4, 5, 6, 7] },
  { key: 'compete', num: '04', title: 'COMPETE', ruleIndexes: [8, 9, 10, 11] },
  { key: 'legal', num: '05', title: 'LEGAL', ruleIndexes: [12] },
];

/** Given a rule index, find which chapter it belongs to. */
export function chapterOf(ruleIndex: number): Chapter {
  return (
    CHAPTERS.find((c) => c.ruleIndexes.includes(ruleIndex)) ?? CHAPTERS[0]
  );
}

/**
 * Pad a rule index to a two-digit quest number, e.g. 0 → "01", 12 → "13".
 * Used by Variants B and C.
 */
export function questNumber(ruleIndex: number): string {
  return String(ruleIndex + 1).padStart(2, '0');
}
