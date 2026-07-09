-- Migration 015: per-user session revocation epoch
-- Password reset/change previously left already-issued JWTs valid until their
-- natural 3-day expiry, so resetting a compromised password did not evict an
-- attacker's live session. This adds a per-user `tokens_valid_from` timestamp:
-- token_required rejects any JWT whose `iat` predates it, and the auth flow
-- bumps it to NOW() on every password change/reset — invalidating all existing
-- sessions for that user at once (something the per-jti blocklist cannot do).

ALTER TABLE participants ADD COLUMN IF NOT EXISTS tokens_valid_from TIMESTAMPTZ DEFAULT NULL;
ALTER TABLE mentors ADD COLUMN IF NOT EXISTS tokens_valid_from TIMESTAMPTZ DEFAULT NULL;
