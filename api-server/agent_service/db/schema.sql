-- Neon (Postgres) schema for the Market Research Agent API layer
-- gen_random_uuid() is built into PostgreSQL 13+ (Neon runs 14-17), so no extension is needed.

CREATE TABLE IF NOT EXISTS tenants (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT NOT NULL,
    clerk_org_id TEXT UNIQUE,
    plan_tier   TEXT NOT NULL DEFAULT 'free' CHECK (plan_tier IN ('free','pro','enterprise')),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS workflow_runs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    user_id         TEXT,
    ticker          TEXT NOT NULL,
    quarter         TEXT,
    query           TEXT NOT NULL,
    workflow_type   TEXT NOT NULL,
    priority        TEXT NOT NULL DEFAULT 'normal',
    status          TEXT NOT NULL DEFAULT 'queued'
                    CHECK (status IN ('queued','running','completed','failed','cancelled')),
    current_step    TEXT,
    progress_pct    INTEGER NOT NULL DEFAULT 0 CHECK (progress_pct BETWEEN 0 AND 100),
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at    TIMESTAMPTZ,
    report_jsonb    JSONB,
    trace_log_jsonb JSONB NOT NULL DEFAULT '[]'::jsonb
);

CREATE TABLE IF NOT EXISTS citations (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id      UUID NOT NULL REFERENCES workflow_runs(id) ON DELETE CASCADE,
    source_url  TEXT,
    source_type TEXT,
    metric_name TEXT,
    value       TEXT,
    period      TEXT,
    confidence  DOUBLE PRECISION CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
    raw_snippet TEXT
);

CREATE TABLE IF NOT EXISTS workflow_schedules (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    inngest_schedule_id TEXT,
    ticker              TEXT NOT NULL,
    workflow_type       TEXT NOT NULL,
    cron_expr           TEXT NOT NULL,
    query               TEXT,
    active              BOOLEAN NOT NULL DEFAULT TRUE,
    last_run_at         TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_runs_tenant_id   ON workflow_runs (tenant_id);
CREATE INDEX IF NOT EXISTS idx_runs_ticker      ON workflow_runs (ticker);
CREATE INDEX IF NOT EXISTS idx_runs_status      ON workflow_runs (status);
CREATE INDEX IF NOT EXISTS idx_runs_started_at  ON workflow_runs (started_at DESC);
CREATE INDEX IF NOT EXISTS idx_runs_tenant_started ON workflow_runs (tenant_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_citations_run_id ON citations (run_id);
CREATE INDEX IF NOT EXISTS idx_schedules_tenant ON workflow_schedules (tenant_id);
CREATE INDEX IF NOT EXISTS idx_schedules_active ON workflow_schedules (active);

-- Upgrade path for databases created from the first version of this schema (safe to re-run):
ALTER TABLE workflow_runs      ADD COLUMN IF NOT EXISTS quarter     TEXT;
ALTER TABLE workflow_schedules ADD COLUMN IF NOT EXISTS query       TEXT;
ALTER TABLE workflow_schedules ADD COLUMN IF NOT EXISTS last_run_at TIMESTAMPTZ;
