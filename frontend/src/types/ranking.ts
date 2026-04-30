export interface RankedTeam {
  team_id: number;
  team_name: string;
  score: number;
  rank: number;
  score_updated_at?: string | null;
}
