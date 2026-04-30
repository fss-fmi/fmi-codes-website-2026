export interface Team {
  team_id: number;
  team_name: string;
  join_code?: string;
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
  name: string;
  company_name?: string;
  picture_filename?: string;
}

export interface JoinRequest {
  id: number;
  participant_id: number;
  participant_name: string;
  participant_email?: string;
  created_at: string;
  status: 'pending' | 'accepted' | 'declined' | 'invalidated' | 'cancelled';
}

export interface Application {
  id: number;
  team_id: number;
  team_name: string;
  status: 'pending' | 'accepted' | 'declined' | 'invalidated' | 'cancelled';
  created_at: string;
}
