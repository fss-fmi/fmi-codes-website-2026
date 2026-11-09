-- Migration 018: a Masters degree has only a 1st and a 2nd year.
-- Fails if a participant already has Masters 3rd to 6th Year, so no stored
-- year is rewritten by guesswork.

ALTER TABLE participants DROP CONSTRAINT IF EXISTS participants_course_check;
ALTER TABLE participants ADD CONSTRAINT participants_course_check CHECK (course IN (
    'Bachelor 1st Year', 'Bachelor 2nd Year', 'Bachelor 3rd Year', 'Bachelor 4th Year',
    'Masters 1st Year', 'Masters 2nd Year'
));
