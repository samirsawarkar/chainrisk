ALTER TABLE tick_metrics ADD COLUMN IF NOT EXISTS edge_metrics JSONB DEFAULT '{}'::jsonb;
