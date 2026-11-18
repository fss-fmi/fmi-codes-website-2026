-- Registration rush (#222): delete every @loadtest.invalid account and the teams they are
-- in, in one transaction. Run in the staging Postgres pod with ON_ERROR_STOP
-- (docs/testing.md, "Load test"). It refuses, changing nothing, when a team it would delete
-- has a real member or when another team holds a queue position its deletes would leave
-- with a gap.

BEGIN;

-- The lock every registration-state change takes, so no join or create interleaves.
SELECT pg_advisory_xact_lock(1);

CREATE TEMP TABLE load_participants ON COMMIT DROP AS
    SELECT id, team_id FROM participants WHERE email LIKE '%@loadtest.invalid';

CREATE TEMP TABLE load_teams ON COMMIT DROP AS
    SELECT DISTINCT team_id AS id FROM load_participants WHERE team_id IS NOT NULL;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM participants p JOIN load_teams t ON t.id = p.team_id
        WHERE p.email NOT LIKE '%@loadtest.invalid'
    ) THEN
        RAISE EXCEPTION 'a load test team has a member outside @loadtest.invalid; nothing deleted';
    END IF;
    IF EXISTS (
        SELECT 1 FROM teams
        WHERE queue_position IS NOT NULL AND id NOT IN (SELECT id FROM load_teams)
    ) THEN
        RAISE EXCEPTION 'another team is queued and would keep a gapped position; nothing deleted';
    END IF;
END
$$;

-- Teams go first, emptied by an UPDATE: deleting a member whose captain was deleted
-- earlier in the same statement fires the participant_count trigger on a team whose
-- captain_id still points at the gone row, before ON DELETE SET NULL has cleared it.
UPDATE participants SET team_id = NULL, is_captain = FALSE
WHERE id IN (SELECT id FROM load_participants);

-- Join requests, preferences and assignments cascade.
DELETE FROM teams WHERE id IN (SELECT id FROM load_teams);

-- No foreign key on this table; verification tokens cascade.
DELETE FROM password_reset_tokens
WHERE role = 'participant' AND user_id IN (SELECT id FROM load_participants);

DELETE FROM participants WHERE id IN (SELECT id FROM load_participants);

SELECT (SELECT COUNT(*) FROM load_participants) AS participants_deleted,
       (SELECT COUNT(*) FROM load_teams) AS teams_deleted;

COMMIT;
