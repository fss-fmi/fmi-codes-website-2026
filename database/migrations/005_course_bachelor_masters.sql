-- ============================================================================
-- MIGRATION 005: Change course from INTEGER to VARCHAR (Bachelor/Masters)
-- ============================================================================
-- Converts the course column from an integer (1-4) to a descriptive string
-- supporting Bachelor 1-4 and Masters 1-6.
-- ============================================================================

-- 1. Drop the existing CHECK constraint on course
ALTER TABLE participants DROP CONSTRAINT IF EXISTS participants_course_check;

-- 2. Drop all views that depend on the course column
DROP VIEW IF EXISTS v_participants_full;
DROP VIEW IF EXISTS v_teams_participant_breakdown;

-- 3. Convert existing integer values to Bachelor labels
ALTER TABLE participants ALTER COLUMN course TYPE VARCHAR(30) USING
    CASE course::int
        WHEN 1 THEN 'Bachelor 1st Year'
        WHEN 2 THEN 'Bachelor 2nd Year'
        WHEN 3 THEN 'Bachelor 3rd Year'
        WHEN 4 THEN 'Bachelor 4th Year'
    END;

-- 4. Add new CHECK constraint with all valid course values
ALTER TABLE participants ADD CONSTRAINT participants_course_check
    CHECK (course IN (
        'Bachelor 1st Year', 'Bachelor 2nd Year', 'Bachelor 3rd Year', 'Bachelor 4th Year',
        'Masters 1st Year', 'Masters 2nd Year', 'Masters 3rd Year', 'Masters 4th Year', 'Masters 5th Year', 'Masters 6th Year'
    ));

-- 5. Recreate v_participants_full
CREATE OR REPLACE VIEW v_participants_full AS
SELECT
    p.id,
    p.first_name,
    p.last_name,
    p.email,
    p.phone_number,
    p.faculty_number,
    p.course,
    s.name as specialty,
    u.name as university,
    u.country as university_country,
    u.city as university_city,
    t.team_name,
    t.id as team_id,
    p.status,
    p.created_at,
    p.updated_at
FROM participants p
LEFT JOIN specialties s ON p.specialty_id = s.id
LEFT JOIN universities u ON p.university_id = u.id
LEFT JOIN teams t ON p.team_id = t.id;

-- 6. Recreate v_teams_participant_breakdown with string course values
CREATE OR REPLACE VIEW v_teams_participant_breakdown AS
SELECT
    t.id as team_id,
    t.team_name,
    COUNT(*) as total_participants,
    COUNT(CASE WHEN p.course LIKE 'Bachelor%' THEN 1 END) as bachelor_count,
    COUNT(CASE WHEN p.course LIKE 'Masters%' THEN 1 END) as masters_count,
    STRING_AGG(DISTINCT p.course, ', ' ORDER BY p.course) as courses,
    STRING_AGG(DISTINCT u.name, ', ') as universities,
    t.status,
    t.created_at
FROM teams t
LEFT JOIN participants p ON t.id = p.team_id
LEFT JOIN universities u ON p.university_id = u.id
GROUP BY t.id, t.team_name, t.status, t.created_at;
