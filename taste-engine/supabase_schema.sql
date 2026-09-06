-- Run this in your Supabase SQL Editor to create the tables for the Taste Engine.

-- 1. Create the ratings table
CREATE TABLE ratings (
    site_id TEXT PRIMARY KEY,
    mu FLOAT NOT NULL DEFAULT 25.0,
    sigma FLOAT NOT NULL DEFAULT 8.333,
    wins INTEGER NOT NULL DEFAULT 0,
    losses INTEGER NOT NULL DEFAULT 0,
    comparisons INTEGER NOT NULL DEFAULT 0,
    vector jsonb  -- Store the 768-d embedding vector as a JSON array
);

-- 2. Create the match history table
CREATE TABLE match_history (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    winner_id TEXT REFERENCES ratings(site_id),
    loser_id TEXT REFERENCES ratings(site_id),
    is_draw BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now())
);

-- 3. Enable RLS (Row Level Security) - For a simple prototype, we'll allow anon reads/writes.
-- IMPORTANT: In production, you'd want to lock this down.
ALTER TABLE ratings ENABLE ROW LEVEL SECURITY;
ALTER TABLE match_history ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Allow anonymous read access to ratings" ON ratings FOR SELECT USING (true);
CREATE POLICY "Allow anonymous update access to ratings" ON ratings FOR UPDATE USING (true);
CREATE POLICY "Allow anonymous insert access to ratings" ON ratings FOR INSERT WITH CHECK (true);

CREATE POLICY "Allow anonymous read access to match_history" ON match_history FOR SELECT USING (true);
CREATE POLICY "Allow anonymous insert access to match_history" ON match_history FOR INSERT WITH CHECK (true);
