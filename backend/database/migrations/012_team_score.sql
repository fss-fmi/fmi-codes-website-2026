-- Migration 012: Add score column to teams table for ranking
-- Idempotent: safe to run multiple times

BEGIN;

-- Add the score column (floating point for granular ranking)
ALTER TABLE teams ADD COLUMN IF NOT EXISTS score DOUBLE PRECISION DEFAULT NULL;

-- Track when score was last updated
ALTER TABLE teams ADD COLUMN IF NOT EXISTS score_updated_at TIMESTAMP WITH TIME ZONE DEFAULT NULL;

-- Partial index for fast ORDER BY score DESC lookups (skips NULL rows)
CREATE INDEX IF NOT EXISTS idx_teams_score ON teams (score DESC NULLS LAST) WHERE score IS NOT NULL;

COMMIT;
