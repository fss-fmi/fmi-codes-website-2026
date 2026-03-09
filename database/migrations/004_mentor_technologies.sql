-- ============================================================================
-- MIGRATION 004: Add technologies array to mentors
-- Date: March 9, 2026
-- Description: Adds a TEXT[] column for mentor technology tags
-- ============================================================================

ALTER TABLE mentors ADD COLUMN IF NOT EXISTS technologies TEXT[] DEFAULT '{}';

CREATE INDEX IF NOT EXISTS idx_mentors_technologies ON mentors USING GIN (technologies);
