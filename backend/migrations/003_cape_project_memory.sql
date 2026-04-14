ALTER TABLE cape_projects
    ADD COLUMN IF NOT EXISTS latest_report JSONB DEFAULT '{}'::jsonb;

ALTER TABLE cape_projects
    ADD COLUMN IF NOT EXISTS chat_history JSONB DEFAULT '[]'::jsonb;
