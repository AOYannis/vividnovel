-- GraphBun Phase 2 — Initial Schema
-- Run this in Supabase SQL Editor (Dashboard > SQL Editor > New Query)

-- 1. Game Sessions
CREATE TABLE game_sessions (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id               UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  player                JSONB NOT NULL,
  setting               TEXT NOT NULL,
  cast_config           JSONB NOT NULL,
  custom_setting_text   TEXT DEFAULT '',
  system_prompt_override TEXT DEFAULT '',
  sequence_number       INT DEFAULT 0,
  conversation_history  JSONB DEFAULT '[]'::jsonb,
  consistency_state     JSONB DEFAULT '{}'::jsonb,
  total_costs           JSONB DEFAULT '{"grok_input_tokens":0,"grok_output_tokens":0,"grok_cost":0,"image_cost":0,"total":0}'::jsonb,
  style_loras           JSONB DEFAULT '[]'::jsonb,
  extra_loras           JSONB DEFAULT '[]'::jsonb,
  video_settings        JSONB DEFAULT '{"draft":true,"audio":true,"duration":5,"resolution":"720p"}'::jsonb,
  status                TEXT DEFAULT 'active' CHECK (status IN ('active', 'completed', 'abandoned')),
  created_at            TIMESTAMPTZ DEFAULT now(),
  updated_at            TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_game_sessions_user ON game_sessions(user_id);
CREATE INDEX idx_game_sessions_updated ON game_sessions(updated_at DESC);

-- 2. Sequences
CREATE TABLE sequences (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id        UUID NOT NULL REFERENCES game_sessions(id) ON DELETE CASCADE,
  sequence_number   INT NOT NULL,
  narration_segments TEXT[] DEFAULT ARRAY[]::TEXT[],
  choices_offered   JSONB DEFAULT '[]'::jsonb,
  choice_made       JSONB,
  costs             JSONB,
  created_at        TIMESTAMPTZ DEFAULT now(),
  UNIQUE(session_id, sequence_number)
);

CREATE INDEX idx_sequences_session ON sequences(session_id);

-- 3. Images
CREATE TABLE images (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  sequence_id     UUID NOT NULL REFERENCES sequences(id) ON DELETE CASCADE,
  image_index     INT NOT NULL,
  url             TEXT,
  prompt          TEXT,
  actors_present  TEXT[] DEFAULT ARRAY[]::TEXT[],
  cost            NUMERIC DEFAULT 0,
  seed            BIGINT,
  generation_time NUMERIC,
  gen_settings    JSONB,
  created_at      TIMESTAMPTZ DEFAULT now(),
  UNIQUE(sequence_id, image_index)
);

CREATE INDEX idx_images_sequence ON images(sequence_id);

-- 4. Videos
CREATE TABLE videos (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  sequence_id     UUID NOT NULL REFERENCES sequences(id) ON DELETE CASCADE,
  url             TEXT,
  prompt          TEXT,
  cost            NUMERIC DEFAULT 0,
  generation_time NUMERIC,
  created_at      TIMESTAMPTZ DEFAULT now(),
  UNIQUE(sequence_id)
);

-- Auto-update updated_at
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER game_sessions_updated_at
  BEFORE UPDATE ON game_sessions
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ═══ Row Level Security ═══

ALTER TABLE game_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE sequences ENABLE ROW LEVEL SECURITY;
ALTER TABLE images ENABLE ROW LEVEL SECURITY;
ALTER TABLE videos ENABLE ROW LEVEL SECURITY;

-- game_sessions: users CRUD their own
CREATE POLICY "own_sessions_select" ON game_sessions FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "own_sessions_insert" ON game_sessions FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "own_sessions_update" ON game_sessions FOR UPDATE USING (auth.uid() = user_id);
CREATE POLICY "own_sessions_delete" ON game_sessions FOR DELETE USING (auth.uid() = user_id);

-- sequences: via parent session
CREATE POLICY "own_sequences_select" ON sequences FOR SELECT
  USING (EXISTS (SELECT 1 FROM game_sessions gs WHERE gs.id = session_id AND gs.user_id = auth.uid()));
CREATE POLICY "own_sequences_insert" ON sequences FOR INSERT
  WITH CHECK (EXISTS (SELECT 1 FROM game_sessions gs WHERE gs.id = session_id AND gs.user_id = auth.uid()));

-- images: via sequence -> session
CREATE POLICY "own_images_select" ON images FOR SELECT
  USING (EXISTS (SELECT 1 FROM sequences s JOIN game_sessions gs ON gs.id = s.session_id WHERE s.id = sequence_id AND gs.user_id = auth.uid()));
CREATE POLICY "own_images_insert" ON images FOR INSERT
  WITH CHECK (EXISTS (SELECT 1 FROM sequences s JOIN game_sessions gs ON gs.id = s.session_id WHERE s.id = sequence_id AND gs.user_id = auth.uid()));

-- videos: via sequence -> session
CREATE POLICY "own_videos_select" ON videos FOR SELECT
  USING (EXISTS (SELECT 1 FROM sequences s JOIN game_sessions gs ON gs.id = s.session_id WHERE s.id = sequence_id AND gs.user_id = auth.uid()));
CREATE POLICY "own_videos_insert" ON videos FOR INSERT
  WITH CHECK (EXISTS (SELECT 1 FROM sequences s JOIN game_sessions gs ON gs.id = s.session_id WHERE s.id = sequence_id AND gs.user_id = auth.uid()));
