export interface AdminTeam {
  id: number;
  team_name: string;
  status?: string;
  participant_count?: number;
  queue_position?: number | null;
}

export interface RegStatus {
  registered_count: number;
  max_registered: number;
  queue_count: number;
  registered_teams: AdminTeam[];
  queued_teams: AdminTeam[];
  unregistered_teams: AdminTeam[];
  pending_teams?: AdminTeam[];
}

export interface PrefStatus {
  teams_submitted: number;
  teams_total: number;
  mentors_submitted: number;
  mentors_total: number;
  teams: { id: number; team_name: string; submitted: boolean }[];
  mentors: {
    id: number;
    name: string;
    submitted: boolean;
    /** Picks that are still registered active teams; only these reach matching. */
    picks_counting?: number;
    picks_saved?: number;
  }[];
}

export interface TeamScore {
  team_id: number;
  team_name: string;
  score: number | null;
}

export type FlagName =
  | 'registration_open'
  | 'preferences_open'
  | 'rankings_live'
  | 'mentors_stay_tuned';

export interface FeatureFlag {
  name: FlagName;
  enabled: boolean;
  updated_at: string;
  scheduled_value: boolean | null;
  scheduled_at: string | null;
}

export type Tab = 'site' | 'registration' | 'teams' | 'preferences' | 'matching' | 'scores';

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
