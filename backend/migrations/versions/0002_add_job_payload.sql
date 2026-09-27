-- Migration 0002: Add payload column to background_jobs table
ALTER TABLE background_jobs ADD COLUMN payload TEXT;
