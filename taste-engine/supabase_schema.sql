-- DEPRECATED: the v1 schema. Do not run it: it opens every table to anonymous reads and
-- writes. v2 uses supabase/migrations/0001_v2_voting.sql. Kept only until the v1 cleanup.

-- Run this in your Supabase SQL Editor to create the tables for the Taste Engine.

-- 1. Create the ratings table
CREATE TABLE IF NOT EXISTS ratings (
    site_id TEXT PRIMARY KEY,
    mu FLOAT NOT NULL DEFAULT 25.0,
    sigma FLOAT NOT NULL DEFAULT 8.333,
    wins INTEGER NOT NULL DEFAULT 0,
    losses INTEGER NOT NULL DEFAULT 0,
    comparisons INTEGER NOT NULL DEFAULT 0,
    vector jsonb  -- Store the 768-d embedding vector as a JSON array
);

-- 2. Create the match history table
CREATE TABLE IF NOT EXISTS match_history (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    winner_id TEXT REFERENCES ratings(site_id),
    loser_id TEXT REFERENCES ratings(site_id),
    is_draw BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now())
);

-- 3. Add voter_id and reasoning to match_history (v2 migration)
ALTER TABLE match_history ADD COLUMN IF NOT EXISTS voter_id TEXT;
ALTER TABLE match_history ADD COLUMN IF NOT EXISTS reasoning TEXT;

-- 4. Create voters table (v2)
CREATE TABLE IF NOT EXISTS voters (
    voter_id TEXT PRIMARY KEY,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()),
    total_votes INTEGER DEFAULT 0,
    agreement_rate FLOAT DEFAULT 0.0
);

-- 5. Enable RLS (Row Level Security) - For a simple prototype, we'll allow anon reads/writes.
-- IMPORTANT: In production, you'd want to lock this down.
ALTER TABLE ratings ENABLE ROW LEVEL SECURITY;
ALTER TABLE match_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE voters ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Allow anonymous read access to ratings" ON ratings FOR SELECT USING (true);
CREATE POLICY "Allow anonymous update access to ratings" ON ratings FOR UPDATE USING (true);
CREATE POLICY "Allow anonymous insert access to ratings" ON ratings FOR INSERT WITH CHECK (true);

CREATE POLICY "Allow anonymous read access to match_history" ON match_history FOR SELECT USING (true);
CREATE POLICY "Allow anonymous insert access to match_history" ON match_history FOR INSERT WITH CHECK (true);

CREATE POLICY "Allow anonymous read access to voters" ON voters FOR SELECT USING (true);
CREATE POLICY "Allow anonymous insert access to voters" ON voters FOR INSERT WITH CHECK (true);
CREATE POLICY "Allow anonymous update access to voters" ON voters FOR UPDATE USING (true);
