-- ============================================================================
-- Marketing-Ops: extended retention for Schicht 6 tables (Schicht 6.6)
-- ============================================================================
-- DSGVO-konforme retention für die Schicht-6 tables:
--   marketing.inbound_messages       — 180 days (Art. 5 Abs. 1 lit. e DSGVO)
--   marketing.reply_proposals        — 180 days for terminal status (rejected/sent),
--                                       730 days (2 years) for audit (approved/sent)
--   marketing.audience_proposals     — 365 days (existing data, longer due to
--                                       lead-generation history)
--   marketing.n8n_api_audit          — 90 days (Schicht 6.1)
--   marketing.audit_log              — 730 days (legal/audit floor)
--
-- run_retention_once_v2() runs all prune functions in batches.
-- Operator wires this to pg_cron or scheduled task (daily 03:00).
--
-- Apply:
--   docker cp 029_retention_extended.sql <db>:/tmp/
--   docker exec <db> psql -U supabase_admin -d postgres -f /tmp/029_retention_extended.sql

BEGIN;

-- ─── prune_inbound_messages ──────────────────────────────────────────
CREATE OR REPLACE FUNCTION marketing.prune_inbound_messages(
    p_keep_days int DEFAULT 180,
    p_batch     int DEFAULT 10000
) RETURNS int AS $$
DECLARE
    v_cutoff timestamptz := now() - make_interval(days => p_keep_days);
    v_count  int;
BEGIN
    WITH d AS (
        DELETE FROM marketing.inbound_messages
         WHERE received_at < v_cutoff
           AND id IN (
               SELECT id FROM marketing.inbound_messages
                WHERE received_at < v_cutoff
                ORDER BY received_at
                LIMIT p_batch
           )
        RETURNING 1
    ) SELECT COUNT(*) INTO v_count FROM d;
    IF v_count > 0 THEN
        INSERT INTO marketing.audit_log (actor, action, target_table, payload)
        VALUES ('retention', 'prune.inbound_messages',
                'marketing.inbound_messages',
                jsonb_build_object('rows', v_count, 'cutoff', v_cutoff::text));
    END IF;
    RETURN v_count;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION marketing.prune_inbound_messages IS
    'Delete inbound_messages older than p_keep_days (default 180). '
    'CASCADE deletes reply_proposals linked to them. Batched at p_batch. '
    'DSGVO Art. 5 Abs. 1 lit. e: data minimization + storage limitation.';

-- ─── prune_reply_proposals (different windows for sent vs rest) ──────
CREATE OR REPLACE FUNCTION marketing.prune_reply_proposals(
    p_keep_days_terminal int DEFAULT 180,   -- rejected, abandoned-draft
    p_keep_days_audit    int DEFAULT 730,   -- sent (2 years audit trail)
    p_batch              int DEFAULT 10000
) RETURNS int AS $$
DECLARE
    v_cutoff_terminal timestamptz := now() - make_interval(days => p_keep_days_terminal);
    v_cutoff_audit    timestamptz := now() - make_interval(days => p_keep_days_audit);
    v_count           int;
BEGIN
    WITH d AS (
        DELETE FROM marketing.reply_proposals
         WHERE id IN (
            SELECT id FROM marketing.reply_proposals
             WHERE (status = 'rejected' AND created_at < v_cutoff_terminal)
                OR (status = 'draft' AND updated_at < v_cutoff_terminal)
                OR (status IN ('sent', 'approved') AND created_at < v_cutoff_audit)
             ORDER BY created_at
             LIMIT p_batch
         )
        RETURNING 1
    ) SELECT COUNT(*) INTO v_count FROM d;
    IF v_count > 0 THEN
        INSERT INTO marketing.audit_log (actor, action, target_table, payload)
        VALUES ('retention', 'prune.reply_proposals',
                'marketing.reply_proposals',
                jsonb_build_object('rows', v_count,
                                   'terminal_cutoff', v_cutoff_terminal::text,
                                   'audit_cutoff', v_cutoff_audit::text));
    END IF;
    RETURN v_count;
END;
$$ LANGUAGE plpgsql;

-- ─── prune_audit_log (very long retention) ───────────────────────────
CREATE OR REPLACE FUNCTION marketing.prune_audit_log(
    p_keep_days int DEFAULT 730,
    p_batch     int DEFAULT 10000
) RETURNS int AS $$
DECLARE
    v_cutoff timestamptz := now() - make_interval(days => p_keep_days);
    v_count  int;
BEGIN
    WITH d AS (
        DELETE FROM marketing.audit_log
         WHERE created_at < v_cutoff
           AND actor != 'retention'        -- never delete retention's own audit
           AND id IN (
               SELECT id FROM marketing.audit_log
                WHERE created_at < v_cutoff
                  AND actor != 'retention'
                ORDER BY created_at
                LIMIT p_batch
           )
        RETURNING 1
    ) SELECT COUNT(*) INTO v_count FROM d;
    IF v_count > 0 THEN
        INSERT INTO marketing.audit_log (actor, action, target_table, payload)
        VALUES ('retention', 'prune.audit_log',
                'marketing.audit_log',
                jsonb_build_object('rows', v_count, 'cutoff', v_cutoff::text));
    END IF;
    RETURN v_count;
END;
$$ LANGUAGE plpgsql;

-- ─── run_retention_once_v2 — drains everything in one call ───────────
CREATE OR REPLACE FUNCTION marketing.run_retention_once_v2()
RETURNS jsonb AS $$
DECLARE
    v_opens        int := 0;
    v_clicks       int := 0;
    v_events       int := 0;
    v_deliveries   int := 0;
    v_n8n          int := 0;
    v_inbound      int := 0;
    v_reply_props  int := 0;
    v_audit        int := 0;
    v_batch_n      int;
    v_max_batches  int := 100;
    v_i            int;
BEGIN
    -- Existing prunes from Schicht 5.x
    v_i := 0;
    LOOP
        v_i := v_i + 1;
        v_batch_n := marketing.prune_email_opens(365, 10000);
        v_opens := v_opens + v_batch_n;
        EXIT WHEN v_batch_n = 0 OR v_i >= v_max_batches;
    END LOOP;

    v_i := 0;
    LOOP
        v_i := v_i + 1;
        v_batch_n := marketing.prune_email_clicks(365, 10000);
        v_clicks := v_clicks + v_batch_n;
        EXIT WHEN v_batch_n = 0 OR v_i >= v_max_batches;
    END LOOP;

    v_i := 0;
    LOOP
        v_i := v_i + 1;
        v_batch_n := marketing.prune_webhook_events(90, 10000);
        v_events := v_events + v_batch_n;
        EXIT WHEN v_batch_n = 0 OR v_i >= v_max_batches;
    END LOOP;

    v_i := 0;
    LOOP
        v_i := v_i + 1;
        v_batch_n := marketing.prune_webhook_deliveries(90, 180, 10000);
        v_deliveries := v_deliveries + v_batch_n;
        EXIT WHEN v_batch_n = 0 OR v_i >= v_max_batches;
    END LOOP;

    -- Schicht 6.1
    v_i := 0;
    LOOP
        v_i := v_i + 1;
        v_batch_n := marketing.prune_n8n_audit(90, 10000);
        v_n8n := v_n8n + v_batch_n;
        EXIT WHEN v_batch_n = 0 OR v_i >= v_max_batches;
    END LOOP;

    -- Schicht 6.6 (this migration)
    v_i := 0;
    LOOP
        v_i := v_i + 1;
        v_batch_n := marketing.prune_inbound_messages(180, 10000);
        v_inbound := v_inbound + v_batch_n;
        EXIT WHEN v_batch_n = 0 OR v_i >= v_max_batches;
    END LOOP;

    v_i := 0;
    LOOP
        v_i := v_i + 1;
        v_batch_n := marketing.prune_reply_proposals(180, 730, 10000);
        v_reply_props := v_reply_props + v_batch_n;
        EXIT WHEN v_batch_n = 0 OR v_i >= v_max_batches;
    END LOOP;

    v_i := 0;
    LOOP
        v_i := v_i + 1;
        v_batch_n := marketing.prune_audit_log(730, 10000);
        v_audit := v_audit + v_batch_n;
        EXIT WHEN v_batch_n = 0 OR v_i >= v_max_batches;
    END LOOP;

    RETURN jsonb_build_object(
        'email_opens',         v_opens,
        'email_clicks',        v_clicks,
        'webhook_events',      v_events,
        'webhook_deliveries',  v_deliveries,
        'n8n_api_audit',       v_n8n,
        'inbound_messages',    v_inbound,
        'reply_proposals',     v_reply_props,
        'audit_log',           v_audit,
        'completed_at',        now()::text
    );
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION marketing.run_retention_once_v2 IS
    'Extended one-shot retention drain. Includes Schicht 6 tables. '
    'Operator wires to pg_cron (daily 03:00) or scheduled task. '
    'Returns jsonb summary of rows deleted per table.';

-- Audit
INSERT INTO marketing.audit_log (actor, action, target_table, payload)
VALUES (
    'migration:029',
    'retention.extended_v2',
    'marketing.run_retention_once_v2',
    jsonb_build_object(
        'functions_added', jsonb_build_array(
            'marketing.prune_inbound_messages',
            'marketing.prune_reply_proposals',
            'marketing.prune_audit_log',
            'marketing.run_retention_once_v2'
        ),
        'dsgvo_basis', 'Art. 5 Abs. 1 lit. e (Speicherbegrenzung) + '
                       'Art. 17 Abs. 1 lit. a (Recht auf Vergessenwerden)',
        'retention_windows', jsonb_build_object(
            'inbound_messages', '180 days',
            'reply_proposals.rejected', '180 days',
            'reply_proposals.sent', '730 days',
            'n8n_api_audit', '90 days',
            'audit_log', '730 days'
        )
    )
);

COMMIT;
