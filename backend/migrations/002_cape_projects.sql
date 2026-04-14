CREATE TABLE IF NOT EXISTS cape_projects (
    project_id            VARCHAR(64) PRIMARY KEY,
    project_name          TEXT NOT NULL,
    scenario_file_name    TEXT DEFAULT '',
    system_config         JSONB NOT NULL,
    scenario_events       JSONB NOT NULL,
    latest_status         VARCHAR(24) DEFAULT 'draft',
    latest_decision       JSONB DEFAULT '{}'::jsonb,
    latest_metrics        JSONB DEFAULT '{}'::jsonb,
    latest_visual_summary JSONB DEFAULT '{}'::jsonb,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_run_at           TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_cape_projects_updated_at
    ON cape_projects(updated_at DESC);
