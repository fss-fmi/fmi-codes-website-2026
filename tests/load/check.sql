-- Registration rush (#222): database consistency after the run. Every row is a problem;
-- no rows means the database is consistent. Run in the staging Postgres pod
-- (docs/testing.md, "Load test"). Read only.
--
-- The checks cover the whole database, which is right because the run starts on a staging
-- with no teams. 18 and 6 are MAX_REGISTERED_TEAMS and MAX_TEAM_MEMBERS in team_service.py.
-- participants.team_id holds one team, so the only way to sit in two teams is to captain
-- one while a member of another: the two captain checks catch that.

-- member_count is the active members, as the app counts them for team size and activation;
-- row_count is every participant on the team, as the participant_count trigger counts them.
WITH members AS (
    SELECT t.id, t.team_name, t.status, t.is_registered, t.queue_position,
           t.participant_count, t.captain_id,
           COUNT(p.id) FILTER (WHERE p.status = 'active') AS member_count,
           COUNT(p.id) AS row_count
    FROM teams t
    LEFT JOIN participants p ON p.team_id = t.id
    GROUP BY t.id
),
queue AS (
    SELECT id, team_name, queue_position,
           ROW_NUMBER() OVER (ORDER BY queue_position, id) AS expected_position
    FROM teams
    WHERE queue_position IS NOT NULL
)
SELECT 'registered teams' AS problem,
       COUNT(*) FILTER (WHERE is_registered) || ' registered, expected '
       || LEAST(18, COUNT(*) FILTER (WHERE status = 'active')) AS detail
FROM members
HAVING COUNT(*) FILTER (WHERE is_registered)
       <> LEAST(18, COUNT(*) FILTER (WHERE status = 'active'))

UNION ALL
SELECT 'queue position', team_name || ' at ' || queue_position || ', expected ' || expected_position
FROM queue
WHERE queue_position <> expected_position

UNION ALL
SELECT 'over 6 members', team_name || ' has ' || member_count
FROM members
WHERE member_count > 6

UNION ALL
SELECT 'status vs members', team_name || ' is ' || status || ' with ' || member_count || ' members'
FROM members
WHERE (status = 'active') <> (member_count >= 3)

UNION ALL
SELECT 'registered and queued', team_name
FROM members
WHERE is_registered AND queue_position IS NOT NULL

UNION ALL
SELECT 'active team neither registered nor queued', team_name
FROM members
WHERE status = 'active' AND NOT is_registered AND queue_position IS NULL

UNION ALL
SELECT 'pending team registered or queued', team_name
FROM members
WHERE status = 'pending' AND (is_registered OR queue_position IS NOT NULL)

UNION ALL
SELECT 'participant_count', team_name || ' says ' || participant_count || ', has ' || row_count
FROM members
WHERE participant_count <> row_count

UNION ALL
SELECT 'captain not in the team', m.team_name || ' captain ' || COALESCE(p.email, 'none')
FROM members m
LEFT JOIN participants p ON p.id = m.captain_id
WHERE p.id IS NULL OR p.team_id IS DISTINCT FROM m.id OR NOT p.is_captain

UNION ALL
SELECT 'captain of no team', p.email
FROM participants p
LEFT JOIN teams t ON t.captain_id = p.id
WHERE p.is_captain AND t.id IS NULL;
