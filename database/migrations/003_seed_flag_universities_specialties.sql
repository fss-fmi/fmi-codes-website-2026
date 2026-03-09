-- ============================================================================
-- MIGRATION 003: Add is_seed flag to universities and specialties
-- Date: March 9, 2026
-- Purpose: Distinguish curated seed data from user-submitted "Other" entries.
--          Only seed entries (is_seed = TRUE) are shown in public dropdowns.
-- ============================================================================

-- Add is_seed column to universities
ALTER TABLE universities ADD COLUMN IF NOT EXISTS is_seed BOOLEAN NOT NULL DEFAULT FALSE;

-- Add is_seed column to specialties
ALTER TABLE specialties ADD COLUMN IF NOT EXISTS is_seed BOOLEAN NOT NULL DEFAULT FALSE;

-- Mark any existing rows as seed data
UPDATE universities SET is_seed = TRUE WHERE is_seed = FALSE;
UPDATE specialties SET is_seed = TRUE WHERE is_seed = FALSE;

-- Index for efficient filtering on the flag
CREATE INDEX IF NOT EXISTS idx_universities_is_seed ON universities(is_seed);
CREATE INDEX IF NOT EXISTS idx_specialties_is_seed ON specialties(is_seed);
