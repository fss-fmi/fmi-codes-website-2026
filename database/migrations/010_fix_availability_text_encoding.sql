-- ============================================================================
-- Migration 010: Fix mojibake in mentor availability_text
-- Date: March 11, 2026
--
-- Root cause:
--   The en-dash (U+2013) was stored as its Win1252 mojibake equivalent
--   (U+00E2 + U+20AC + U+201C) because psql connected with client_encoding=WIN1252
--   while the SQL source file was UTF-8. PostgreSQL faithfully converted those
--   three Win1252 glyphs to UTF-8, producing a corrupted 3-character sequence
--   instead of the single–character en-dash.
--
-- Fix strategy:
--   Use chr() — a server-side function — so the replacement is fully
--   encoding-independent regardless of which client runs this migration.
--
--   Mojibake: chr(226) || chr(8364) || chr(8220)
--             =  U+00E2   U+20AC      U+201C   (â  €  ")
--   Correct:  chr(8211) = U+2013 (–)
--
-- Safe to run multiple times (REPLACE on a clean string is a no-op).
-- ============================================================================

UPDATE mentors
SET availability_text = REPLACE(
    availability_text,
    chr(226) || chr(8364) || chr(8220),
    chr(8211)
)
WHERE availability_text IS NOT NULL
  AND availability_text LIKE '%' || chr(226) || '%';
