-- ============================================================================
-- Marketing-Ops: sync columns on marketing.accounts
-- ============================================================================
-- Adds the columns needed for bi-directional sync (per Phase 4/5 in the
-- master plan):
--
--   sync_id        : stable UUID, survives handle renames, used as the
--                    canonical reference in markdown frontmatter
--   last_synced_at : timestamp of last successful DB->FS render, lets the
--                    worker skip up-to-date rows on full re-render
--
-- Backfills sync_id for all existing rows (14.742 from pathx-import).
--
-- Apply:
--   docker cp 006_sync_columns.sql <supabase-db>:/tmp/
--   docker exec <supabase-db> psql -U supabase_admin -d postgres -f /tmp/006_sync_columns.sql

BEGIN;

ALTER TABLE marketing.accounts
    ADD COLUMN IF NOT EXISTS sync_id        uuid        DEFAULT gen_random_uuid(),
    ADD COLUMN IF NOT EXISTS last_synced_at timestamptz;

-- Backfill: every existing row gets a UUID. The DEFAULT only fires for NEW
-- rows; existing rows (added by the pathx-import) need an explicit UPDATE.
UPDATE marketing.accounts SET sync_id = gen_random_uuid() WHERE sync_id IS NULL;

-- After backfill, enforce NOT NULL + UNIQUE to make sync_id a stable second-key.
ALTER TABLE marketing.accounts
    ALTER COLUMN sync_id SET NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_accounts_sync_id ON marketing.accounts(sync_id);

COMMENT ON COLUMN marketing.accounts.sync_id IS
    'Stable UUID survives handle renames. Referenced in markdown frontmatter '
    'as sync_id. Used by sync worker for deduplication and loop-detection.';

COMMENT ON COLUMN marketing.accounts.last_synced_at IS
    'Timestamp of the last successful DB->FS markdown render. NULL means '
    'this row has never been rendered to the knowledge vault. Updated by '
    'the sync worker after each successful write.';

-- Audit
INSERT INTO marketing.audit_log (actor, action, target_table, payload)
VALUES (
    'migration:006',
    'schema.add_columns',
    'marketing.accounts',
    jsonb_build_object(
        'columns_added', jsonb_build_object(
            'sync_id', 'uuid NOT NULL UNIQUE DEFAULT gen_random_uuid()',
            'last_synced_at', 'timestamptz NULLABLE'
        ),
        'backfill_count', (SELECT COUNT(*) FROM marketing.accounts WHERE sync_id IS NOT NULL),
        'purpose', 'bi-directional sync to ~/.rowboat/knowledge/Marketing/People/'
    )
);

COMMIT;

-- Verify:
--   SELECT COUNT(*) FROM marketing.accounts WHERE sync_id IS NULL; -- expect 0
--   SELECT handle, sync_id FROM marketing.accounts LIMIT 3;
