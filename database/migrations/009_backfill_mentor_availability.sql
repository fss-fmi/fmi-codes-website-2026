-- ============================================================================
-- Migration 009: Backfill availability_text for seeded mentor rows
-- Date: March 11, 2026
-- Description:
--   Migration 008 added the availability_text column AFTER the initial mentor
--   seed was loaded, so all 8 seeded rows have NULL in that column.
--   This migration backfills the values from the seed data.
--
--   Format: comma-separated time intervals "Day HH:MM-HH:MM"
--   Safe to run multiple times (WHERE availability_text IS NULL guard).
-- ============================================================================

UPDATE mentors SET availability_text = 'Sat 10:00-14:00, Sun 11:00-15:00'
WHERE first_name = 'Alice' AND last_name = 'Johnson' AND company_name = 'Tech University'
  AND availability_text IS NULL;

UPDATE mentors SET availability_text = 'Sat 09:00-12:00, Sat 14:00-17:00'
WHERE first_name = 'Bob' AND last_name = 'Smith' AND company_name = 'Innovate Labs'
  AND availability_text IS NULL;

UPDATE mentors SET availability_text = 'Sun 10:00-16:00'
WHERE first_name = 'Carla' AND last_name = 'Nguyen' AND company_name = 'AI Research Group'
  AND availability_text IS NULL;

UPDATE mentors SET availability_text = 'Sat 11:00-13:00, Sun 13:00-17:00'
WHERE first_name = 'David' AND last_name = 'Lee' AND company_name = 'Cloud Nine Systems'
  AND availability_text IS NULL;

UPDATE mentors SET availability_text = 'Sat 09:00-17:00'
WHERE first_name = 'Elena' AND last_name = 'Garcia' AND company_name = 'Quantum Labs'
  AND availability_text IS NULL;

UPDATE mentors SET availability_text = 'Sat 10:00-12:00, Sun 10:00-12:00, Sun 14:00-16:00'
WHERE first_name = 'Farid' AND last_name = 'Hassan' AND company_name = 'DeepSight Analytics'
  AND availability_text IS NULL;

UPDATE mentors SET availability_text = 'Sat 13:00-17:00, Sun 09:00-13:00'
WHERE first_name = 'Grace' AND last_name = 'Kim' AND company_name = 'Open Data Works'
  AND availability_text IS NULL;

UPDATE mentors SET availability_text = 'Sun 11:00-15:00'
WHERE first_name = 'Henry' AND last_name = 'Brown' AND company_name = 'Northwind Robotics'
  AND availability_text IS NULL;
