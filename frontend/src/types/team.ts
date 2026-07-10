export interface Team {
  id?: number;
  team_id?: number;
  team_name: string;
  join_code?: string;
  status?: string;
  captain_id?: number;
  is_active?: boolean;
  is_registered?: boolean;
  queue_position?: number | null;
  registered_at?: string | null;
  participant_count?: number;
  score?: number | null;
  score_updated_at?: string | null;
  members?: Member[];
  mentors?: TeamMentor[];
}

export interface Member {
  id: number;
  first_name: string;
  last_name: string;
  email: string;
  specialty?: string;
  university?: string;
  is_captain: boolean;
}

export interface TeamMentor {
  mentor_id: number;
  mentor_name?: string;
  company_name?: string;
  picture_filename?: string;
}

export interface JoinRequest {
  request_id: number;
  participant_id: number;
  first_name: string;
  last_name: string;
  email?: string;
  specialty?: string;
  university?: string;
  created_at: string;
  status?: 'pending';
}

export interface Application {
  request_id: number;
  team_id: number;
  team_name: string;
  status: 'pending' | 'accepted' | 'declined' | 'invalidated' | 'cancelled';
  participant_count?: number;
  created_at: string;
}
