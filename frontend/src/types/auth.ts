export type Role = 'participant' | 'mentor' | 'admin';

export interface User {
  id?: number;
  role: Role;
  first_name?: string;
  last_name?: string;
  email?: string;
  phone_number?: string;
  faculty_number?: string;
  course?: string;
  specialty?: string;
  university?: string;
  team_id?: number | null;
  team_name?: string | null;
  join_code?: string | null;
  is_captain?: boolean;
  status?: string;
  email_verified?: boolean;
  // mentor fields
  company_name?: string;
  bio?: string;
}
