-- ============================================================================
-- MIGRATION 002: Auth, Captain, Join Code, and Preference Tables
-- ============================================================================
-- Adds JWT-compatible auth fields, captain system, team join codes,
-- and ranked preference tables for Gale-Shapley matching.
-- ============================================================================

-- 1. Add password_hash to participants (for individual JWT auth)
ALTER TABLE participants ADD COLUMN IF NOT EXISTS password_hash VARCHAR(255);
ALTER TABLE participants ADD COLUMN IF NOT EXISTS is_captain BOOLEAN DEFAULT FALSE;

-- 2. Add password_hash to mentors (for mentor login)
ALTER TABLE mentors ADD COLUMN IF NOT EXISTS password_hash VARCHAR(255);

-- 3. Add captain_id and join_code to teams, drop password_hash requirement
ALTER TABLE teams ADD COLUMN IF NOT EXISTS captain_id BIGINT REFERENCES participants(id) ON DELETE SET NULL;
ALTER TABLE teams ADD COLUMN IF NOT EXISTS join_code VARCHAR(20) UNIQUE;

-- Make participants.team_id nullable (participants register before joining a team)
ALTER TABLE participants ALTER COLUMN team_id DROP NOT NULL;

-- Drop the old team password_hash column if it exists (teams no longer have passwords)
-- We keep it for now to avoid breaking the migration, will clean up later
-- ALTER TABLE teams DROP COLUMN IF EXISTS password_hash;

-- 4. Create team_mentor_preferences table (captain ranks mentors)
CREATE TABLE IF NOT EXISTS team_mentor_preferences (
    team_id BIGINT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    mentor_id BIGINT NOT NULL REFERENCES mentors(id) ON DELETE CASCADE,
    rank INTEGER NOT NULL CHECK (rank BETWEEN 1 AND 3),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (team_id, mentor_id),
    UNIQUE (team_id, rank)
);

CREATE INDEX IF NOT EXISTS idx_tmp_team_id ON team_mentor_preferences(team_id);
CREATE INDEX IF NOT EXISTS idx_tmp_mentor_id ON team_mentor_preferences(mentor_id);

-- 5. Create mentor_team_preferences table (mentor ranks teams)
CREATE TABLE IF NOT EXISTS mentor_team_preferences (
    mentor_id BIGINT NOT NULL REFERENCES mentors(id) ON DELETE CASCADE,
    team_id BIGINT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    rank INTEGER NOT NULL CHECK (rank BETWEEN 1 AND 3),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (mentor_id, team_id),
    UNIQUE (mentor_id, rank)
);

CREATE INDEX IF NOT EXISTS idx_mtp_mentor_id ON mentor_team_preferences(mentor_id);
CREATE INDEX IF NOT EXISTS idx_mtp_team_id ON mentor_team_preferences(team_id);

-- 6. Fix the participant count trigger to handle NULLs from nullable team_id
CREATE OR REPLACE FUNCTION update_team_participant_count()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' AND NEW.team_id IS NOT NULL THEN
        UPDATE teams SET participant_count = participant_count + 1 WHERE id = NEW.team_id;
    ELSIF TG_OP = 'DELETE' AND OLD.team_id IS NOT NULL THEN
        UPDATE teams SET participant_count = GREATEST(participant_count - 1, 0) WHERE id = OLD.team_id;
    ELSIF TG_OP = 'UPDATE' THEN
        IF OLD.team_id IS NOT NULL AND (NEW.team_id IS NULL OR NEW.team_id != OLD.team_id) THEN
            UPDATE teams SET participant_count = GREATEST(participant_count - 1, 0) WHERE id = OLD.team_id;
        END IF;
        IF NEW.team_id IS NOT NULL AND (OLD.team_id IS NULL OR NEW.team_id != OLD.team_id) THEN
            UPDATE teams SET participant_count = participant_count + 1 WHERE id = NEW.team_id;
        END IF;
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

-- Recreate trigger to also fire on UPDATE (for team transfers / leaving)
DROP TRIGGER IF EXISTS trig_update_participant_count ON participants;
CREATE TRIGGER trig_update_participant_count
AFTER INSERT OR UPDATE OF team_id OR DELETE ON participants
FOR EACH ROW EXECUTE FUNCTION update_team_participant_count();
