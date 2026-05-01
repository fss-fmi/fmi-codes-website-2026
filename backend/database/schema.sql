-- ============================================================================
-- HACKATHON MANAGEMENT SYSTEM - POSTGRESQL SCHEMA
-- Version: 1.0
-- Date: March 3, 2026
-- Database: PostgreSQL 12+
-- ============================================================================
-- This schema implements a production-ready, normalized (3NF) relational
-- database design for managing hackathons with participants, teams, and mentors.
-- ============================================================================

-- ============================================================================
-- DROP EXISTING OBJECTS (Execute with caution!)
-- ============================================================================
-- Uncomment to drop and recreate from scratch
/*
DROP TRIGGER IF EXISTS trig_update_timestamp_universities ON universities CASCADE;
DROP TRIGGER IF EXISTS trig_update_timestamp_specialties ON specialties CASCADE;
DROP TRIGGER IF EXISTS trig_update_timestamp_teams ON teams CASCADE;
DROP TRIGGER IF EXISTS trig_update_timestamp_mentors ON mentors CASCADE;
DROP TRIGGER IF EXISTS trig_update_timestamp_participants ON participants CASCADE;
DROP TRIGGER IF EXISTS trig_update_timestamp_hackathon_events ON hackathon_events CASCADE;
DROP TRIGGER IF EXISTS trig_prevent_team_deletion ON teams CASCADE;
DROP TRIGGER IF EXISTS trig_update_participant_count ON participants CASCADE;

DROP FUNCTION IF EXISTS update_timestamp();
DROP FUNCTION IF EXISTS prevent_team_deletion_with_participants();
DROP FUNCTION IF EXISTS update_team_participant_count();

DROP VIEW IF EXISTS v_teams_summary;
DROP VIEW IF EXISTS v_participants_full;
DROP VIEW IF EXISTS v_mentors_assignments;

DROP TABLE IF EXISTS team_mentors;
DROP TABLE IF EXISTS participants;
DROP TABLE IF EXISTS mentors;
DROP TABLE IF EXISTS teams;
DROP TABLE IF EXISTS hackathon_events;
DROP TABLE IF EXISTS specialties;
DROP TABLE IF EXISTS universities;
*/

-- ============================================================================
-- SECTION 1: LOOKUP TABLES (Normalization)
-- ============================================================================

-- Universities lookup table
CREATE TABLE IF NOT EXISTS universities (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL UNIQUE,
    country VARCHAR(100),
    city VARCHAR(100),
    is_seed BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_universities_name ON universities(name);
CREATE INDEX IF NOT EXISTS idx_universities_country ON universities(country);
CREATE INDEX IF NOT EXISTS idx_universities_is_seed ON universities(is_seed);

-- Specialties lookup table
CREATE TABLE IF NOT EXISTS specialties (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL UNIQUE,
    description TEXT,
    is_seed BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_specialties_name ON specialties(name);
CREATE INDEX IF NOT EXISTS idx_specialties_is_seed ON specialties(is_seed);

-- ============================================================================
-- SECTION 2: CORE ENTITY TABLES
-- ============================================================================

-- Hackathon Events table (supports multiple hackathons)
CREATE TABLE IF NOT EXISTS hackathon_events (
    id BIGSERIAL PRIMARY KEY,
    hackathon_name VARCHAR(255) NOT NULL UNIQUE,
    description TEXT,
    max_teams INTEGER NOT NULL DEFAULT 18,
    max_participants INTEGER NOT NULL DEFAULT 108,
    start_date TIMESTAMP WITH TIME ZONE NOT NULL,
    end_date TIMESTAMP WITH TIME ZONE NOT NULL,
    status VARCHAR(20) DEFAULT 'pending'
        CHECK (status IN ('pending', 'onboarding', 'active', 'completed', 'cancelled')),
    location VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT check_event_dates CHECK (end_date > start_date)
);

CREATE INDEX IF NOT EXISTS idx_hackathon_events_name ON hackathon_events(hackathon_name);
CREATE INDEX IF NOT EXISTS idx_hackathon_events_status ON hackathon_events(status);
CREATE INDEX IF NOT EXISTS idx_hackathon_events_dates ON hackathon_events(start_date, end_date);

-- Teams table
CREATE TABLE IF NOT EXISTS teams (
    id BIGSERIAL PRIMARY KEY,
    team_name VARCHAR(100) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    join_code VARCHAR(20) UNIQUE,
    status VARCHAR(20) DEFAULT 'pending'
        CHECK (status IN ('pending', 'active', 'completed', 'disqualified')),
    participant_count INTEGER DEFAULT 0 CHECK (participant_count >= 0),
    is_registered BOOLEAN NOT NULL DEFAULT FALSE,
    registered_at TIMESTAMP WITH TIME ZONE DEFAULT NULL,
    queue_position INTEGER DEFAULT NULL,
    score DOUBLE PRECISION DEFAULT NULL,
    score_updated_at TIMESTAMP WITH TIME ZONE DEFAULT NULL,
    hackathon_event_id BIGINT REFERENCES hackathon_events(id) ON DELETE CASCADE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_teams_team_name ON teams(team_name);
CREATE INDEX IF NOT EXISTS idx_teams_status ON teams(status);
CREATE INDEX IF NOT EXISTS idx_teams_hackathon ON teams(hackathon_event_id);
CREATE INDEX IF NOT EXISTS idx_teams_created_at ON teams(created_at);
CREATE INDEX IF NOT EXISTS idx_teams_registered ON teams(is_registered) WHERE is_registered = TRUE;
CREATE INDEX IF NOT EXISTS idx_teams_queue ON teams(queue_position) WHERE queue_position IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_teams_score ON teams (score DESC NULLS LAST) WHERE score IS NOT NULL;

-- Mentors table
CREATE TABLE IF NOT EXISTS mentors (
    id BIGSERIAL PRIMARY KEY,
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE,
    phone_number VARCHAR(20) NOT NULL,
    company_name VARCHAR(255) NOT NULL,
    picture_url VARCHAR(500),
    picture_filename VARCHAR(255),
    bio TEXT,
    technologies TEXT[] DEFAULT '{}',
    availability_text TEXT DEFAULT NULL,
    password_hash VARCHAR(255),
    password_reset_requested_at TIMESTAMPTZ DEFAULT NULL,
    status VARCHAR(20) DEFAULT 'active'
        CHECK (status IN ('active', 'inactive', 'archived')),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uidx_mentors_identity UNIQUE (first_name, last_name, company_name)
);

CREATE INDEX IF NOT EXISTS idx_mentors_email ON mentors(email);
CREATE INDEX IF NOT EXISTS idx_mentors_status ON mentors(status);
CREATE INDEX IF NOT EXISTS idx_mentors_lastname ON mentors(last_name);
CREATE INDEX IF NOT EXISTS idx_mentors_created_at ON mentors(created_at);
CREATE INDEX IF NOT EXISTS idx_mentors_technologies ON mentors USING GIN (technologies);
CREATE INDEX IF NOT EXISTS idx_mentors_reset_requested_at ON mentors (password_reset_requested_at)
    WHERE password_reset_requested_at IS NOT NULL;

-- Participants table
CREATE TABLE IF NOT EXISTS participants (
    id BIGSERIAL PRIMARY KEY,
    team_id BIGINT REFERENCES teams(id) ON DELETE RESTRICT ON UPDATE CASCADE,
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE,
    phone_number VARCHAR(20) NOT NULL,
    faculty_number VARCHAR(20) NOT NULL UNIQUE,
    course VARCHAR(30) NOT NULL CHECK (course IN (
        'Bachelor 1st Year', 'Bachelor 2nd Year', 'Bachelor 3rd Year', 'Bachelor 4th Year',
        'Masters 1st Year', 'Masters 2nd Year', 'Masters 3rd Year', 'Masters 4th Year', 'Masters 5th Year', 'Masters 6th Year'
    )),
    specialty_id BIGINT NOT NULL REFERENCES specialties(id) ON DELETE RESTRICT,
    university_id BIGINT NOT NULL REFERENCES universities(id) ON DELETE RESTRICT,
    password_hash VARCHAR(255),
    password_reset_requested_at TIMESTAMPTZ DEFAULT NULL,
    is_captain BOOLEAN DEFAULT FALSE,
    status VARCHAR(20) DEFAULT 'active'
        CHECK (status IN ('active', 'inactive', 'removed')),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Comprehensive indexes for participant queries
CREATE INDEX IF NOT EXISTS idx_participants_email ON participants(email);
CREATE INDEX IF NOT EXISTS idx_participants_team_id ON participants(team_id);
CREATE INDEX IF NOT EXISTS idx_participants_faculty_number ON participants(faculty_number);
CREATE INDEX IF NOT EXISTS idx_participants_course ON participants(course);
CREATE INDEX IF NOT EXISTS idx_participants_specialty_id ON participants(specialty_id);
CREATE INDEX IF NOT EXISTS idx_participants_university_id ON participants(university_id);
CREATE INDEX IF NOT EXISTS idx_participants_status ON participants(status);
CREATE INDEX IF NOT EXISTS idx_participants_created_at ON participants(created_at);
CREATE INDEX IF NOT EXISTS idx_participants_reset_requested_at ON participants (password_reset_requested_at)
    WHERE password_reset_requested_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_participants_team_course ON participants(team_id, course);

-- Add captain_id to teams (references participants — defined after participants to avoid circular FK)
ALTER TABLE teams ADD COLUMN IF NOT EXISTS captain_id BIGINT REFERENCES participants(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_teams_captain_id ON teams(captain_id);
CREATE INDEX IF NOT EXISTS idx_teams_join_code ON teams(join_code);

-- ============================================================================
-- SECTION 3: JUNCTION TABLES (Many-to-Many Relationships)
-- ============================================================================

-- Team-Mentors association table (N:M relationship)
CREATE TABLE IF NOT EXISTS team_mentors (
    team_id BIGINT NOT NULL REFERENCES teams(id) ON DELETE CASCADE ON UPDATE CASCADE,
    mentor_id BIGINT NOT NULL REFERENCES mentors(id) ON DELETE CASCADE ON UPDATE CASCADE,
    assigned_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE,
    notes TEXT,
    PRIMARY KEY (team_id, mentor_id)
);

-- Indexes for efficient lookups
CREATE INDEX IF NOT EXISTS idx_team_mentors_mentor_id ON team_mentors(mentor_id);
CREATE INDEX IF NOT EXISTS idx_team_mentors_assigned_at ON team_mentors(assigned_at);
CREATE INDEX IF NOT EXISTS idx_team_mentors_is_active ON team_mentors(is_active);
CREATE INDEX IF NOT EXISTS idx_team_mentors_active_teams ON team_mentors(team_id) WHERE is_active = TRUE;

-- Team-Mentor preferences (captain ranks mentors for Gale-Shapley matching)
CREATE TABLE IF NOT EXISTS team_mentor_preferences (
    team_id BIGINT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    mentor_id BIGINT NOT NULL REFERENCES mentors(id) ON DELETE CASCADE,
    rank INTEGER NOT NULL CHECK (rank BETWEEN 1 AND 3),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (team_id, mentor_id),
    UNIQUE (team_id, rank)
);

CREATE INDEX IF NOT EXISTS idx_tmp_team_id ON team_mentor_preferences(team_id);
CREATE INDEX IF NOT EXISTS idx_tmp_mentor_id ON team_mentor_preferences(mentor_id);

-- Mentor-Team preferences (mentor ranks teams for Gale-Shapley matching)
CREATE TABLE IF NOT EXISTS mentor_team_preferences (
    mentor_id BIGINT NOT NULL REFERENCES mentors(id) ON DELETE CASCADE,
    team_id BIGINT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    rank INTEGER NOT NULL CHECK (rank BETWEEN 1 AND 3),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (mentor_id, team_id),
    UNIQUE (mentor_id, rank)
);

CREATE INDEX IF NOT EXISTS idx_mtp_mentor_id ON mentor_team_preferences(mentor_id);
CREATE INDEX IF NOT EXISTS idx_mtp_team_id ON mentor_team_preferences(team_id);

-- Team Join Requests (participants apply to teams; captains accept/decline)
CREATE TABLE IF NOT EXISTS team_join_requests (
    id BIGSERIAL PRIMARY KEY,
    participant_id BIGINT NOT NULL REFERENCES participants(id) ON DELETE CASCADE,
    team_id BIGINT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    status VARCHAR(20) NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'accepted', 'declined', 'invalidated', 'cancelled')),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (participant_id, team_id)
);

CREATE INDEX IF NOT EXISTS idx_tjr_team_pending
    ON team_join_requests (team_id) WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS idx_tjr_participant_pending
    ON team_join_requests (participant_id) WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS idx_tjr_participant_id ON team_join_requests (participant_id);
CREATE INDEX IF NOT EXISTS idx_tjr_team_id ON team_join_requests (team_id);
CREATE INDEX IF NOT EXISTS idx_tjr_status ON team_join_requests (status);

-- ============================================================================
-- SECTION 4: TRIGGER FUNCTIONS FOR DATA INTEGRITY
-- ============================================================================

-- Function: Auto-update timestamp on any table update
CREATE OR REPLACE FUNCTION update_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Function: Prevent deletion of teams with active participants
CREATE OR REPLACE FUNCTION prevent_team_deletion_with_participants()
RETURNS TRIGGER AS $$
BEGIN
    IF (SELECT COUNT(*) FROM participants WHERE team_id = OLD.id AND status = 'active') > 0 THEN
        RAISE EXCEPTION 'Cannot delete team with active participants. Remove all participants first.';
    END IF;
    RETURN OLD;
END;
$$ LANGUAGE plpgsql;

-- Function: Update team participant count on participant insert/update/delete
CREATE OR REPLACE FUNCTION update_team_participant_count()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' AND NEW.team_id IS NOT NULL THEN
        UPDATE teams SET participant_count = participant_count + 1 WHERE id = NEW.team_id;
    ELSIF TG_OP = 'DELETE' AND OLD.team_id IS NOT NULL THEN
        UPDATE teams SET participant_count = GREATEST(participant_count - 1, 0) WHERE id = OLD.team_id;
    ELSIF TG_OP = 'UPDATE' THEN
        IF OLD.team_id IS NOT NULL AND (NEW.team_id IS NULL OR NEW.team_id != OLD.team_id) THEN
            UPDATE teams SET participant_count = GREATEST(participant_count - 1, 0) WHERE id = OLD.team_id;
        END IF;
        IF NEW.team_id IS NOT NULL AND (OLD.team_id IS NULL OR NEW.team_id != OLD.team_id) THEN
            UPDATE teams SET participant_count = participant_count + 1 WHERE id = NEW.team_id;
        END IF;
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- SECTION 5: APPLY TRIGGERS
-- ============================================================================

-- Auto-update timestamps
CREATE TRIGGER trig_update_timestamp_universities
BEFORE UPDATE ON universities
FOR EACH ROW EXECUTE FUNCTION update_timestamp();

CREATE TRIGGER trig_update_timestamp_specialties
BEFORE UPDATE ON specialties
FOR EACH ROW EXECUTE FUNCTION update_timestamp();

CREATE TRIGGER trig_update_timestamp_hackathon_events
BEFORE UPDATE ON hackathon_events
FOR EACH ROW EXECUTE FUNCTION update_timestamp();

CREATE TRIGGER trig_update_timestamp_teams
BEFORE UPDATE ON teams
FOR EACH ROW EXECUTE FUNCTION update_timestamp();

CREATE TRIGGER trig_update_timestamp_mentors
BEFORE UPDATE ON mentors
FOR EACH ROW EXECUTE FUNCTION update_timestamp();

CREATE TRIGGER trig_update_timestamp_participants
BEFORE UPDATE ON participants
FOR EACH ROW EXECUTE FUNCTION update_timestamp();

-- Data integrity triggers
CREATE TRIGGER trig_prevent_team_deletion
BEFORE DELETE ON teams
FOR EACH ROW EXECUTE FUNCTION prevent_team_deletion_with_participants();

CREATE TRIGGER trig_update_participant_count
AFTER INSERT OR UPDATE OF team_id OR DELETE ON participants
FOR EACH ROW EXECUTE FUNCTION update_team_participant_count();

CREATE TRIGGER trig_update_timestamp_team_join_requests
BEFORE UPDATE ON team_join_requests
FOR EACH ROW EXECUTE FUNCTION update_timestamp();

-- Matching confirmation state (single-row table, admin-controlled)
CREATE TABLE IF NOT EXISTS matching_state (
    id           INTEGER PRIMARY KEY DEFAULT 1,
    is_confirmed BOOLEAN     NOT NULL DEFAULT FALSE,
    confirmed_at TIMESTAMPTZ DEFAULT NULL,
    CONSTRAINT single_row CHECK (id = 1)
);
INSERT INTO matching_state (id, is_confirmed)
VALUES (1, FALSE)
ON CONFLICT (id) DO NOTHING;

-- ============================================================================
-- SECTION 6: VIEWS FOR REPORTING
-- ============================================================================

-- View: Teams with participant and mentor counts
CREATE OR REPLACE VIEW v_teams_summary AS
SELECT
    t.id,
    t.team_name,
    t.status,
    t.participant_count,
    t.is_registered,
    t.registered_at,
    t.queue_position,
    COUNT(DISTINCT tm.mentor_id) as mentor_count,
    STRING_AGG(DISTINCT m.company_name, ', ') as mentor_companies,
    h.hackathon_name,
    t.created_at,
    t.updated_at
FROM teams t
LEFT JOIN team_mentors tm ON t.id = tm.team_id AND tm.is_active = TRUE
LEFT JOIN mentors m ON tm.mentor_id = m.id
LEFT JOIN hackathon_events h ON t.hackathon_event_id = h.id
GROUP BY t.id, t.team_name, t.status, t.participant_count,
         t.is_registered, t.registered_at, t.queue_position,
         h.hackathon_name, t.created_at, t.updated_at;

-- View: Participants with full details
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

-- View: Mentors with assignment details
CREATE OR REPLACE VIEW v_mentors_assignments AS
SELECT
    m.id,
    m.first_name,
    m.last_name,
    m.email,
    m.phone_number,
    m.company_name,
    m.status,
    COUNT(DISTINCT CASE WHEN tm.is_active = TRUE THEN tm.team_id END) as active_team_count,
    COUNT(DISTINCT tm.team_id) as total_team_assignments,
    STRING_AGG(DISTINCT t.team_name, ', ' ORDER BY t.team_name) FILTER (WHERE tm.is_active = TRUE) as active_teams,
    m.created_at,
    m.updated_at
FROM mentors m
LEFT JOIN team_mentors tm ON m.id = tm.mentor_id
LEFT JOIN teams t ON tm.team_id = t.id
GROUP BY m.id, m.first_name, m.last_name, m.email, m.phone_number, m.company_name, m.status, m.created_at, m.updated_at;

-- View: Teams with participants breakdown by course
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

-- ============================================================================
-- SECTION 7: SEED DATA (Sample/Test Data)
-- ============================================================================

-- Universities seed data
INSERT INTO universities (name, country, city, is_seed) VALUES
    ('Sofia University "St. Kliment Ohridski"', 'Bulgaria', 'Sofia', TRUE),
    ('Technical University of Sofia', 'Bulgaria', 'Sofia', TRUE),
    ('University of Plovdiv "Paisii Hilendarski"', 'Bulgaria', 'Plovdiv', TRUE),
    ('Vasil Levski Military Academy', 'Bulgaria', 'Sofia', TRUE),
    ('American University in Bulgaria', 'Bulgaria', 'Blagoevgrad', TRUE),
    ('New Bulgarian University', 'Bulgaria', 'Sofia', TRUE)
ON CONFLICT (name) DO NOTHING;

-- Specialties seed data
INSERT INTO specialties (name, description, is_seed) VALUES
    ('Web Development', 'Frontend, Backend, Full-Stack development', TRUE),
    ('AI/Machine Learning', 'Machine Learning, Deep Learning, NLP, Computer Vision', TRUE),
    ('DevOps/Cloud', 'Cloud Architecture, Containerization, CI/CD, Infrastructure', TRUE),
    ('Mobile Development', 'iOS, Android, Flutter, React Native', TRUE),
    ('Data Science', 'Data Analysis, Data Engineering, Business Analytics', TRUE),
    ('Cybersecurity', 'Security, Penetration Testing, Secure Development', TRUE),
    ('Blockchain/Web3', 'Smart Contracts, Cryptocurrencies, Distributed Systems', TRUE),
    ('Software Engineering', 'Engineering and Designing Systems', TRUE)
ON CONFLICT (name) DO NOTHING;

-- Sample hackathon event
INSERT INTO hackathon_events (
    hackathon_name,
    description,
    max_teams,
    max_participants,
    start_date,
    end_date,
    status,
    location
) VALUES (
    'FMI Hackathon 2026',
    'Annual hackathon organized by Faculty of Mathematics and Informatics',
    18,
    108,
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP + INTERVAL '2 days',
    'active',
    'Sofia University, Sofia, Bulgaria'
)
ON CONFLICT (hackathon_name) DO NOTHING;

-- ============================================================================
-- SECTION 8: DATA QUALITY CHECKS
-- ============================================================================

-- Function to check and report data consistency issues
CREATE OR REPLACE FUNCTION check_data_consistency()
RETURNS TABLE (issue_type TEXT, issue_description TEXT, affected_records INTEGER) AS $$
BEGIN
    -- Check teams with no participants
    RETURN QUERY
    SELECT
        'Data Quality Issue'::TEXT,
        'Teams with less than 3 participants (minimum required)'::TEXT,
        COUNT(*)::INTEGER
    FROM (
        SELECT t.id, COUNT(p.id) as pcount
        FROM teams t
        LEFT JOIN participants p ON t.id = p.team_id
        GROUP BY t.id
        HAVING COUNT(p.id) < 3
    ) sub;

    -- Check teams with more than 6 participants
    RETURN QUERY
    SELECT
        'Data Quality Issue'::TEXT,
        'Teams with more than 6 participants (maximum allowed)'::TEXT,
        COUNT(*)::INTEGER
    FROM (
        SELECT t.id, COUNT(p.id) as pcount
        FROM teams t
        LEFT JOIN participants p ON t.id = p.team_id
        GROUP BY t.id
        HAVING COUNT(p.id) > 6
    ) sub;

    -- Check mentors not assigned to any team
    RETURN QUERY
    SELECT
        'Data Quality Issue'::TEXT,
        'Active mentors with no team assignments'::TEXT,
        COUNT(*)::INTEGER
    FROM mentors m
    WHERE m.status = 'active'
    AND NOT EXISTS (SELECT 1 FROM team_mentors tm WHERE tm.mentor_id = m.id AND tm.is_active = TRUE);
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- DOCUMENTATION AND USAGE EXAMPLES
-- ============================================================================

/*
USAGE EXAMPLES:
================

1. Get all participants for a team:
   SELECT * FROM v_participants_full WHERE team_id = 1;

2. Get teams summary with mentor counts:
   SELECT * FROM v_teams_summary WHERE status = 'active';

3. Get mentors and their assignments:
   SELECT * FROM v_mentors_assignments WHERE status = 'active';

4. Check data consistency:
   SELECT * FROM check_data_consistency();

5. Add a new participant:
   INSERT INTO participants (team_id, first_name, last_name, email, phone_number,
                            faculty_number, course, specialty_id, university_id)
   VALUES (1, 'John', 'Doe', 'john@example.com', '+359881234567',
           'FAK123456', 2, 1, 1);

6. Assign a mentor to a team:
   INSERT INTO team_mentors (team_id, mentor_id, is_active)
   VALUES (1, 1, TRUE);

7. Get teams with participant breakdown by course:
   SELECT * FROM v_teams_participant_breakdown;

8. Find participants by university:
   SELECT * FROM v_participants_full WHERE university = 'Sofia University "St. Kliment Ohridski"';

9. Count participants by specialty:
   SELECT specialty, COUNT(*) as count FROM v_participants_full GROUP BY specialty;

10. Get active teams with < 6 participants:
    SELECT t.id, t.team_name, t.participant_count
    FROM teams t
    WHERE t.status = 'active' AND t.participant_count < 6;
*/

-- ============================================================================
-- END OF SCHEMA
-- ============================================================================
