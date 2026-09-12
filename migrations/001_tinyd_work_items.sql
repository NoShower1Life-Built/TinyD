CREATE TABLE IF NOT EXISTS tinyd_work_items (
    work_id UUID PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    aggregate_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('PENDING', 'LEASED', 'COMPLETED', 'FAILED')),
    attempt_count BIGINT NOT NULL DEFAULT 0
        CHECK (attempt_count >= 0),
    available_at TIMESTAMPTZ NOT NULL,
    lease_owner TEXT,
    lease_expires_at TIMESTAMPTZ,
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    CONSTRAINT tinyd_work_items_event_unique UNIQUE (tenant_id, event_id),
    CONSTRAINT tinyd_work_items_lease_consistency CHECK (
        (status = 'LEASED' AND lease_owner IS NOT NULL AND lease_expires_at IS NOT NULL)
        OR (status <> 'LEASED')
    ),
    CONSTRAINT tinyd_work_items_completed_consistency CHECK (
        (status = 'COMPLETED' AND completed_at IS NOT NULL)
        OR (status <> 'COMPLETED')
    )
);

CREATE INDEX IF NOT EXISTS tinyd_work_items_claim_idx
    ON tinyd_work_items (available_at, work_id)
    WHERE status = 'PENDING';

CREATE INDEX IF NOT EXISTS tinyd_work_items_lease_idx
    ON tinyd_work_items (lease_expires_at, work_id)
    WHERE status = 'LEASED';
