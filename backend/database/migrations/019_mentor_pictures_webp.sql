-- Migration 019: mentor photos are WebP files served by the frontend at /mentorPictures/.
-- Seeded rows still point at /static/mentorPictures/<name>.jpg|jpeg|png, which no longer exist.

UPDATE mentors
SET picture_url = '/mentorPictures/'
        || regexp_replace(substr(picture_url, 24), '\.(jpe?g|png)$', '.webp', 'i'),
    picture_filename = regexp_replace(picture_filename, '\.(jpe?g|png)$', '.webp', 'i')
WHERE picture_url LIKE '/static/mentorPictures/%';
