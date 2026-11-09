-- Migration 017: feature flags in the database (issue #201)
-- REGISTRATION_OPEN, RANKINGS_LIVE and MENTORS_STAY_TUNED were env vars read at
-- startup; the admin now switches or schedules them from Mission Control.
-- Seeded false, matching every environment's ConfigMap before this migration.

CREATE TABLE IF NOT EXISTS feature_flags (
    name            TEXT PRIMARY KEY
                    CHECK (name IN ('registration_open', 'rankings_live', 'mentors_stay_tuned')),
    enabled         BOOLEAN     NOT NULL DEFAULT FALSE,
    scheduled_value BOOLEAN,
    scheduled_at    TIMESTAMPTZ,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK ((scheduled_value IS NULL) = (scheduled_at IS NULL))
);

INSERT INTO feature_flags (name, enabled)
VALUES ('registration_open', FALSE),
       ('rankings_live', FALSE),
       ('mentors_stay_tuned', FALSE)
ON CONFLICT (name) DO NOTHING;
