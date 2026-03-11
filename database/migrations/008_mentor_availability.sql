-- Migration 008: Mentor Availability Text
-- Adds a free-text availability column to mentors for display purposes.
-- Format: comma-separated time intervals, e.g. "Sat 10:00–13:00, Sun 11:00–16:00"
-- ============================================================================

ALTER TABLE mentors ADD COLUMN IF NOT EXISTS availability_text TEXT DEFAULT NULL;
