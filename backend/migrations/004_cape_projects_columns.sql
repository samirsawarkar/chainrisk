-- Idempotent column alignment for cape_projects (older DBs created before all columns existed).
ALTER TABLE cape_projects ADD COLUMN IF NOT EXISTS last_run_at TIMESTAMPTZ;
ALTER TABLE cape_projects ADD COLUMN IF NOT EXISTS latest_decision JSONB DEFAULT '{}'::jsonb;
ALTER TABLE cape_projects ADD COLUMN IF NOT EXISTS latest_metrics JSONB DEFAULT '{}'::jsonb;
ALTER TABLE cape_projects ADD COLUMN IF NOT EXISTS latest_visual_summary JSONB DEFAULT '{}'::jsonb;
ALTER TABLE cape_projects ADD COLUMN IF NOT EXISTS latest_report JSONB DEFAULT '{}'::jsonb;
ALTER TABLE cape_projects ADD COLUMN IF NOT EXISTS chat_history JSONB DEFAULT '[]'::jsonb;
