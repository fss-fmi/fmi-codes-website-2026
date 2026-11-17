-- Migration 020: preferences_open feature flag (issue #239)
-- While it is off, teams and mentors can't submit or change their rankings.
-- Seeded false: ranking opens at a time the admin announces, like registration.

ALTER TABLE feature_flags DROP CONSTRAINT IF EXISTS feature_flags_name_check;
ALTER TABLE feature_flags ADD CONSTRAINT feature_flags_name_check CHECK (name IN (
    'registration_open', 'rankings_live', 'mentors_stay_tuned', 'preferences_open'
));

INSERT INTO feature_flags (name, enabled)
VALUES ('preferences_open', FALSE)
ON CONFLICT (name) DO NOTHING;
