-- Migration 007: Team Registration Queue System
-- Adds registration tracking and queue positioning for teams.
-- First 18 active teams become "registered"; additional active teams are queued.
-- ============================================================================

-- 1. Add registration and queue columns to teams
ALTER TABLE teams ADD COLUMN IF NOT EXISTS is_registered BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE teams ADD COLUMN IF NOT EXISTS registered_at TIMESTAMPTZ DEFAULT NULL;
ALTER TABLE teams ADD COLUMN IF NOT EXISTS queue_position INTEGER DEFAULT NULL;

-- 2. Partial indexes for fast lookups
CREATE INDEX IF NOT EXISTS idx_teams_registered ON teams(is_registered) WHERE is_registered = TRUE;
CREATE INDEX IF NOT EXISTS idx_teams_queue ON teams(queue_position) WHERE queue_position IS NOT NULL;

-- 3. Relax hackathon_events.max_teams CHECK constraint (total teams now uncapped)
ALTER TABLE hackathon_events DROP CONSTRAINT IF EXISTS hackathon_events_max_teams_check;

-- 4. Recreate v_teams_summary view to include new columns
DROP VIEW IF EXISTS v_teams_summary;
CREATE VIEW v_teams_summary AS
SELECT
    t.id,
    t.team_name,
    t.status,
    t.participant_count,
    t.is_registered,
    t.registered_at,
    t.queue_position,
    COUNT(DISTINCT tm.mentor_id) as mentor_count,
    STRING_AGG(DISTINCT m.company_name, ', ') as mentor_companies,
    h.hackathon_name,
    t.created_at,
    t.updated_at
FROM teams t
LEFT JOIN team_mentors tm ON t.id = tm.team_id AND tm.is_active = TRUE
LEFT JOIN mentors m ON tm.mentor_id = m.id
LEFT JOIN hackathon_events h ON t.hackathon_event_id = h.id
GROUP BY t.id, t.team_name, t.status, t.participant_count,
         t.is_registered, t.registered_at, t.queue_position,
         h.hackathon_name, t.created_at, t.updated_at;

-- 5. Backfill: register existing active teams (up to 18, ordered by created_at)
WITH ranked AS (
    SELECT id, ROW_NUMBER() OVER (ORDER BY created_at) AS rn
    FROM teams
    WHERE status = 'active'
)
UPDATE teams
SET is_registered = TRUE, registered_at = NOW()
WHERE id IN (SELECT id FROM ranked WHERE rn <= 18);
