-- ============================================================================
-- Migration 006: Password reset cooldown column
-- ============================================================================
-- Adds a `password_reset_requested_at` column to both participants and mentors.
--
-- Purpose:
--   Used as an atomic per-user "claim slot" by the POST /api/auth/reset-password
--   endpoint to serialize concurrent reset requests without any application-level
--   locks and without holding a DB connection during the SMTP send.
--
-- Semantics:
--   NULL        — no reset in progress; a new reset may proceed
--   <timestamp> — a reset was claimed at this time; another is blocked until
--                 either (a) the endpoint clears it on completion/failure, or
--                 (b) 60 seconds elapse and it auto-expires in the WHERE clause
--
-- Safe to run multiple times (IF NOT EXISTS / ADD COLUMN IF NOT EXISTS).
-- ============================================================================

ALTER TABLE participants
    ADD COLUMN IF NOT EXISTS password_reset_requested_at TIMESTAMPTZ DEFAULT NULL;

ALTER TABLE mentors
    ADD COLUMN IF NOT EXISTS password_reset_requested_at TIMESTAMPTZ DEFAULT NULL;

-- Index so the WHERE clause in the claim UPDATE is fast on large tables
CREATE INDEX IF NOT EXISTS idx_participants_reset_requested_at
    ON participants (password_reset_requested_at)
    WHERE password_reset_requested_at IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_mentors_reset_requested_at
    ON mentors (password_reset_requested_at)
    WHERE password_reset_requested_at IS NOT NULL;
