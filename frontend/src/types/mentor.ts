export interface Mentor {
  mentor_id: number;
  name: string;
  first_name?: string;
  last_name?: string;
  email?: string;
  company_name?: string;
  bio?: string;
  picture_filename?: string;
  technologies?: string[];
  availability_text?: string;
}

export interface Preference {
  mentor_id: number;
  rank: 1 | 2 | 3;
}
