-- Add scene_video_url column to images table for per-scene video persistence
ALTER TABLE images ADD COLUMN IF NOT EXISTS scene_video_url TEXT;
