-- Migration 016: email verification on registration (issue #4)
-- Existing participants are grandfathered as verified; new ones start unverified.
-- Enforcement is off until REQUIRE_EMAIL_VERIFICATION=true.

-- Email verification. Added with DEFAULT TRUE so participants who registered
-- before verification existed are grandfathered as verified, then the default
-- flips so every new registration starts unverified. Safe to re-run.
ALTER TABLE participants ADD COLUMN IF NOT EXISTS email_verified BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE participants ALTER COLUMN email_verified SET DEFAULT FALSE;

-- Email verification tokens. Like password_reset_tokens, only the SHA-256
-- hex hash of the emailed token is stored.
CREATE TABLE IF NOT EXISTS email_verification_tokens (
    id             SERIAL      PRIMARY KEY,
    participant_id BIGINT      NOT NULL REFERENCES participants(id) ON DELETE CASCADE,
    token_hash     VARCHAR(64) NOT NULL UNIQUE,
    expires_at     TIMESTAMPTZ NOT NULL,
    used_at        TIMESTAMPTZ,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_evt_participant_unused
    ON email_verification_tokens (participant_id)
    WHERE used_at IS NULL;
