-- Migration 011: Team Join Requests
-- Allows teamless participants to apply to teams with available slots.
-- Captains accept/decline; accepting auto-invalidates other pending requests.

CREATE TABLE IF NOT EXISTS team_join_requests (
    id BIGSERIAL PRIMARY KEY,
    participant_id BIGINT NOT NULL REFERENCES participants(id) ON DELETE CASCADE,
    team_id BIGINT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    status VARCHAR(20) NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'accepted', 'declined', 'invalidated', 'cancelled')),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (participant_id, team_id)
);

-- Fast lookups for pending requests per team (captain view)
CREATE INDEX IF NOT EXISTS idx_tjr_team_pending
    ON team_join_requests (team_id) WHERE status = 'pending';

-- Fast lookups for pending requests per participant (my-applications view)
CREATE INDEX IF NOT EXISTS idx_tjr_participant_pending
    ON team_join_requests (participant_id) WHERE status = 'pending';

-- General indexes for broader queries
CREATE INDEX IF NOT EXISTS idx_tjr_participant_id ON team_join_requests (participant_id);
CREATE INDEX IF NOT EXISTS idx_tjr_team_id ON team_join_requests (team_id);
CREATE INDEX IF NOT EXISTS idx_tjr_status ON team_join_requests (status);

-- Auto-update updated_at on row changes
CREATE TRIGGER trig_update_timestamp_team_join_requests
BEFORE UPDATE ON team_join_requests
FOR EACH ROW EXECUTE FUNCTION update_timestamp();
