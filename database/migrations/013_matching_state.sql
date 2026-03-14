-- Migration 013: Matching confirmation state
-- Tracks whether the admin has confirmed the current matching results as final.
-- Teams and mentors see preferences until confirmed; after confirmation they see
-- their actual algorithm-assigned mentors/teams.

CREATE TABLE IF NOT EXISTS matching_state (
    id         INTEGER PRIMARY KEY DEFAULT 1,
    is_confirmed  BOOLEAN     NOT NULL DEFAULT FALSE,
    confirmed_at  TIMESTAMPTZ DEFAULT NULL,
    CONSTRAINT single_row CHECK (id = 1)
);

-- Seed the single row if it doesn't exist yet
INSERT INTO matching_state (id, is_confirmed)
VALUES (1, FALSE)
ON CONFLICT (id) DO NOTHING;
