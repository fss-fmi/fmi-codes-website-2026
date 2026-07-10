export interface RegStatus {
  registered_count: number;
  max_registered: number;
  queue_count: number;
  registered_teams: { id: number; team_name: string }[];
  queued_teams: { id: number; team_name: string }[];
}

export interface PrefStatus {
  teams_submitted: number;
  teams_total: number;
  mentors_submitted: number;
  mentors_total: number;
  teams: { id: number; name: string; submitted: boolean }[];
  mentors: { id: number; name: string; submitted: boolean }[];
}

export interface TeamScore {
  team_id: number;
  team_name: string;
  score: number | null;
}

export type Tab = 'registration' | 'preferences' | 'matching' | 'scores';

/**
 * Single source of truth for the admin chart/status palette. Chart libraries
 * need concrete color values, so these are hardcoded hex rather than CSS vars.
 * They MUST stay in sync with the theme tokens in index.css
 * (--px-green, --px-amber, --px-danger, --px-teal, --px-teal-dim).
 */
export const CHART_COLORS = {
  green: '#4ecdc4',
  amber: '#f9a825',
  danger: '#e05252',
  teal: '#2dd4bf',
  tealDim: 'rgba(45, 212, 191, 0.18)',
};
