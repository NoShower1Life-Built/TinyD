ALTER TABLE tinyd_work_items
    ADD COLUMN IF NOT EXISTS lease_token UUID;

ALTER TABLE tinyd_work_items
    DROP CONSTRAINT IF EXISTS tinyd_work_items_lease_consistency;

ALTER TABLE tinyd_work_items
    ADD CONSTRAINT tinyd_work_items_lease_consistency CHECK (
        (status = 'LEASED'
            AND lease_owner IS NOT NULL
            AND lease_expires_at IS NOT NULL
            AND lease_token IS NOT NULL)
        OR (status <> 'LEASED'
            AND lease_owner IS NULL
            AND lease_expires_at IS NULL
            AND lease_token IS NULL)
    );
