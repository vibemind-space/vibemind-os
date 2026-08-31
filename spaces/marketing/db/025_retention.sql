-- ============================================================================
-- Marketing-Ops: retention for tracking + webhook tables
-- ============================================================================
-- High-cardinality append-only tables need bounded growth. This migration
-- creates three SQL functions that delete rows past their retention
-- window. They are SAFE to call on production (idempotent, LIMIT-batched,
-- write to audit_log so any massive purge is visible).
--
-- The functions are NOT scheduled by this migration. Operator runs them
-- via either:
--   - pg_cron extension (if installed): scheduled SELECT
--   - external cron / scheduled task: docker exec ... psql -c "SELECT ..."
--   - manual: ad-hoc psql session
--
-- Retention defaults (over-ride per call):
--   marketing.email_opens                  ->  365 days (1 year of opens)
--   marketing.email_clicks                 ->  365 days
--   marketing.webhook_events               ->   90 days
--   marketing.webhook_deliveries (delivered) -> 90 days
--   marketing.webhook_deliveries (dead)    ->  180 days (kept longer for forensics)
--
-- Each function returns the number of rows it deleted. Batched in
-- chunks of 10000 to avoid long-running locks. Caller loops the function
-- until 0 (or sets max_batches to cap).
--
-- Apply:
--   docker cp 025_retention.sql <db>:/tmp/
--   docker exec <db> psql -U supabase_admin -d postgres -f /tmp/025_retention.sql

BEGIN;

-- ─── prune_email_opens ─────────────────────────────────────────────
CREATE OR REPLACE FUNCTION marketing.prune_email_opens(
    p_keep_days int DEFAULT 365,
    p_batch     int DEFAULT 10000
) RETURNS int AS $$
DECLARE
    v_cutoff timestamptz := now() - make_interval(days => p_keep_days);
    v_count  int;
BEGIN
    WITH d AS (
        DELETE FROM marketing.email_opens
         WHERE opened_at < v_cutoff
           AND id IN (
               SELECT id FROM marketing.email_opens
                WHERE opened_at < v_cutoff
                ORDER BY opened_at
                LIMIT p_batch
           )
        RETURNING 1
    )
    SELECT COUNT(*) INTO v_count FROM d;
    IF v_count > 0 THEN
        INSERT INTO marketing.audit_log (actor, action, target_table, payload)
        VALUES ('retention', 'prune.email_opens',
                'marketing.email_opens',
                jsonb_build_object('rows', v_count, 'cutoff', v_cutoff::text));
    END IF;
    RETURN v_count;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION marketing.prune_email_opens IS
    'Delete email_opens rows older than p_keep_days (default 365). '
    'Batched at p_batch rows per call (default 10k) to bound lock time. '
    'Returns rows deleted. Loop in caller until result is 0 to fully drain.';


-- ─── prune_email_clicks ────────────────────────────────────────────
CREATE OR REPLACE FUNCTION marketing.prune_email_clicks(
    p_keep_days int DEFAULT 365,
    p_batch     int DEFAULT 10000
) RETURNS int AS $$
DECLARE
    v_cutoff timestamptz := now() - make_interval(days => p_keep_days);
    v_count  int;
BEGIN
    WITH d AS (
        DELETE FROM marketing.email_clicks
         WHERE clicked_at < v_cutoff
           AND id IN (
               SELECT id FROM marketing.email_clicks
                WHERE clicked_at < v_cutoff
                ORDER BY clicked_at
                LIMIT p_batch
           )
        RETURNING 1
    )
    SELECT COUNT(*) INTO v_count FROM d;
    IF v_count > 0 THEN
        INSERT INTO marketing.audit_log (actor, action, target_table, payload)
        VALUES ('retention', 'prune.email_clicks',
                'marketing.email_clicks',
                jsonb_build_object('rows', v_count, 'cutoff', v_cutoff::text));
    END IF;
    RETURN v_count;
END;
$$ LANGUAGE plpgsql;


-- ─── prune_webhook_events ──────────────────────────────────────────
-- Webhook events and their per-subscription deliveries cascade via FK,
-- so we delete events; deliveries follow.
CREATE OR REPLACE FUNCTION marketing.prune_webhook_events(
    p_keep_days int DEFAULT 90,
    p_batch     int DEFAULT 10000
) RETURNS int AS $$
DECLARE
    v_cutoff timestamptz := now() - make_interval(days => p_keep_days);
    v_count  int;
BEGIN
    WITH d AS (
        DELETE FROM marketing.webhook_events
         WHERE occurred_at < v_cutoff
           AND fanned_out_at IS NOT NULL   -- never delete unfanned events
           AND id IN (
               SELECT id FROM marketing.webhook_events
                WHERE occurred_at < v_cutoff
                  AND fanned_out_at IS NOT NULL
                ORDER BY occurred_at
                LIMIT p_batch
           )
        RETURNING 1
    )
    SELECT COUNT(*) INTO v_count FROM d;
    IF v_count > 0 THEN
        INSERT INTO marketing.audit_log (actor, action, target_table, payload)
        VALUES ('retention', 'prune.webhook_events',
                'marketing.webhook_events',
                jsonb_build_object('rows', v_count, 'cutoff', v_cutoff::text));
    END IF;
    RETURN v_count;
END;
$$ LANGUAGE plpgsql;


-- ─── prune_webhook_deliveries ──────────────────────────────────────
-- Deliveries that survived (FK NOT CASCADE because event deleted first
-- via prune_webhook_events). This function handles the orphans that
-- never had an event-prune (e.g., subscriptions deleted while events
-- remained but cascade was on subscription side).
--
-- ALSO: dead deliveries kept longer for forensics.
CREATE OR REPLACE FUNCTION marketing.prune_webhook_deliveries(
    p_delivered_keep_days int DEFAULT 90,
    p_dead_keep_days      int DEFAULT 180,
    p_batch               int DEFAULT 10000
) RETURNS int AS $$
DECLARE
    v_cutoff_delivered timestamptz := now() - make_interval(days => p_delivered_keep_days);
    v_cutoff_dead      timestamptz := now() - make_interval(days => p_dead_keep_days);
    v_count            int;
BEGIN
    WITH d AS (
        DELETE FROM marketing.webhook_deliveries
         WHERE id IN (
            SELECT id FROM marketing.webhook_deliveries
             WHERE (delivered_at IS NOT NULL AND delivered_at < v_cutoff_delivered
                    AND dead = false)
                OR (dead = true              AND attempted_at < v_cutoff_dead)
             ORDER BY attempted_at
             LIMIT p_batch
         )
        RETURNING 1
    )
    SELECT COUNT(*) INTO v_count FROM d;
    IF v_count > 0 THEN
        INSERT INTO marketing.audit_log (actor, action, target_table, payload)
        VALUES ('retention', 'prune.webhook_deliveries',
                'marketing.webhook_deliveries',
                jsonb_build_object('rows', v_count,
                                   'delivered_cutoff', v_cutoff_delivered::text,
                                   'dead_cutoff', v_cutoff_dead::text));
    END IF;
    RETURN v_count;
END;
$$ LANGUAGE plpgsql;


-- ─── Convenience: run_retention_once() ────────────────────────────
-- Single call that drains all four functions to completion.
-- Designed to be called from a scheduled task (taskschd / pg_cron):
--   SELECT marketing.run_retention_once();
-- Returns a jsonb summary of what was deleted.
CREATE OR REPLACE FUNCTION marketing.run_retention_once()
RETURNS jsonb AS $$
DECLARE
    v_opens_total       int := 0;
    v_clicks_total      int := 0;
    v_events_total      int := 0;
    v_deliveries_total  int := 0;
    v_batch_n           int;
    v_max_batches       int := 100;   -- safety: stop after 1M rows / function
    v_i                 int;
BEGIN
    v_i := 0;
    LOOP
        v_i := v_i + 1;
        v_batch_n := marketing.prune_email_opens(365, 10000);
        v_opens_total := v_opens_total + v_batch_n;
        EXIT WHEN v_batch_n = 0 OR v_i >= v_max_batches;
    END LOOP;

    v_i := 0;
    LOOP
        v_i := v_i + 1;
        v_batch_n := marketing.prune_email_clicks(365, 10000);
        v_clicks_total := v_clicks_total + v_batch_n;
        EXIT WHEN v_batch_n = 0 OR v_i >= v_max_batches;
    END LOOP;

    v_i := 0;
    LOOP
        v_i := v_i + 1;
        v_batch_n := marketing.prune_webhook_events(90, 10000);
        v_events_total := v_events_total + v_batch_n;
        EXIT WHEN v_batch_n = 0 OR v_i >= v_max_batches;
    END LOOP;

    v_i := 0;
    LOOP
        v_i := v_i + 1;
        v_batch_n := marketing.prune_webhook_deliveries(90, 180, 10000);
        v_deliveries_total := v_deliveries_total + v_batch_n;
        EXIT WHEN v_batch_n = 0 OR v_i >= v_max_batches;
    END LOOP;

    RETURN jsonb_build_object(
        'email_opens',         v_opens_total,
        'email_clicks',        v_clicks_total,
        'webhook_events',      v_events_total,
        'webhook_deliveries',  v_deliveries_total,
        'completed_at',        now()::text
    );
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION marketing.run_retention_once IS
    'One-shot retention drain. Calls all four prune_* functions in '
    'batches until each reports 0 deleted (or 100 batches = 1M rows per '
    'function as safety stop). Returns jsonb summary. Designed for a '
    'daily scheduled task / pg_cron job.';


INSERT INTO marketing.audit_log (actor, action, target_table, payload)
VALUES (
    'migration:025',
    'retention.functions_created',
    'marketing.run_retention_once',
    jsonb_build_object(
        'functions', jsonb_build_array(
            'marketing.prune_email_opens',
            'marketing.prune_email_clicks',
            'marketing.prune_webhook_events',
            'marketing.prune_webhook_deliveries',
            'marketing.run_retention_once'
        ),
        'note',
        'No scheduling. Operator wires this to pg_cron or scheduled task. '
        'Defaults: opens/clicks=365d, events=90d, deliveries delivered=90d / dead=180d.'
    )
);

COMMIT;
