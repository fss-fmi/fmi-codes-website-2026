-- Migration 014: password_reset_tokens table
-- C4: Replaces the old plaintext-password-in-email reset flow with a
--     secure token-link flow.  The raw token is never stored — only a
--     SHA-256 hex hash is kept so a DB breach can't be used to reset passwords.

CREATE TABLE IF NOT EXISTS password_reset_tokens (
    id         SERIAL PRIMARY KEY,
    user_id    INTEGER      NOT NULL,
    role       VARCHAR(20)  NOT NULL CHECK (role IN ('participant', 'mentor')),
    token_hash VARCHAR(64)  NOT NULL UNIQUE,  -- SHA-256 hex digest, 64 chars
    expires_at TIMESTAMPTZ  NOT NULL,
    used_at    TIMESTAMPTZ,
    created_at TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- Fast lookup by hash on the confirm endpoint (only for unused tokens)
CREATE INDEX IF NOT EXISTS idx_prt_token_hash
    ON password_reset_tokens (token_hash)
    WHERE used_at IS NULL;

-- Periodic cleanup by expiry (used by a future maintenance job)
CREATE INDEX IF NOT EXISTS idx_prt_expires_unused
    ON password_reset_tokens (expires_at)
    WHERE used_at IS NULL;
