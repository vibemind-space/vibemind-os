-- ============================================================================
-- Marketing-Ops: n8n_api_audit — track every n8n-API-call (Schicht 6.1)
-- ============================================================================
-- Privacy-first audit log of n8n API-key calls.
--
-- What we LOG:
--   - which route was called
--   - which HTTP method
--   - response status code
--   - payload byte-count (for anomaly-detection: sudden 10MB POST = alarm)
--   - workflow-hint from X-N8N-Workflow header (which n8n flow made the call)
--   - timestamp
--
-- What we NEVER LOG:
--   - the api-key (would defeat its purpose if leaked via audit)
--   - the actual payload (PII concern: from_email, draft body, ...)
--   - response body
--   - n8n's IP/user-agent (no value, just metadata bloat)
--
-- Retention: 90 days (matches webhook_deliveries default in Schicht 5.3).
-- prune_n8n_audit() function for the scheduled-task cron.
--
-- Apply:
--   docker cp 028_n8n_api_audit.sql <db>:/tmp/
--   docker exec <db> psql -U supabase_admin -d postgres \
--     -f /tmp/028_n8n_api_audit.sql

BEGIN;

-- ─── n8n_api_audit table ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS marketing.n8n_api_audit (
    id              uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    occurred_at     timestamptz NOT NULL DEFAULT now(),
    route           text        NOT NULL,
    method          text        NOT NULL,
    response_status int,
    payload_bytes   int,
    workflow_hint   text,
    -- Indexed columns for cheap filtering
    CONSTRAINT n8n_audit_method_known CHECK (method IN ('GET','POST','PUT','PATCH','DELETE'))
);

COMMENT ON TABLE marketing.n8n_api_audit IS
    'Append-only audit log of n8n-API-key calls. NEVER stores the api_key, '
    'payload, or response body (PII concerns). Used for anomaly-detection '
    '(sudden traffic spikes, unexpected routes called, 4xx-rate). Retention '
    '90 days via prune_n8n_audit().';

COMMENT ON COLUMN marketing.n8n_api_audit.workflow_hint IS
    'Value of X-N8N-Workflow header, identifies which n8n flow made the call. '
    'Example: "inbound-classifier-v1", "reply-enrichment-v2". Free-text, '
    'truncated at 200 chars. NULL if header absent.';

-- ─── Indexes ──────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_n8n_api_audit_recent
    ON marketing.n8n_api_audit (occurred_at DESC);

CREATE INDEX IF NOT EXISTS idx_n8n_api_audit_route
    ON marketing.n8n_api_audit (route, occurred_at DESC);

CREATE INDEX IF NOT EXISTS idx_n8n_api_audit_failures
    ON marketing.n8n_api_audit (occurred_at DESC)
    WHERE response_status >= 400;

-- ─── Retention function ──────────────────────────────────────────────
CREATE OR REPLACE FUNCTION marketing.prune_n8n_audit(
    p_keep_days int DEFAULT 90,
    p_batch     int DEFAULT 10000
) RETURNS int AS $$
DECLARE
    v_cutoff timestamptz := now() - make_interval(days => p_keep_days);
    v_count  int;
BEGIN
    WITH d AS (
        DELETE FROM marketing.n8n_api_audit
         WHERE occurred_at < v_cutoff
           AND id IN (
               SELECT id FROM marketing.n8n_api_audit
                WHERE occurred_at < v_cutoff
                ORDER BY occurred_at
                LIMIT p_batch
           )
        RETURNING 1
    ) SELECT COUNT(*) INTO v_count FROM d;
    IF v_count > 0 THEN
        INSERT INTO marketing.audit_log (actor, action, target_table, payload)
        VALUES ('retention', 'prune.n8n_api_audit',
                'marketing.n8n_api_audit',
                jsonb_build_object('rows', v_count, 'cutoff', v_cutoff::text));
    END IF;
    RETURN v_count;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION marketing.prune_n8n_audit IS
    'Delete n8n_api_audit rows older than p_keep_days (default 90). '
    'Batched at p_batch (default 10000). Returns rows deleted. Loop until 0.';

-- ─── Anomaly-detection helper view ────────────────────────────────────
-- "n8n traffic last hour by route + status" — for dashboards.
CREATE OR REPLACE VIEW marketing.v_n8n_traffic_hourly AS
SELECT
    date_trunc('hour', occurred_at) AS hour,
    route,
    method,
    COUNT(*)                                            AS total_calls,
    COUNT(*) FILTER (WHERE response_status BETWEEN 200 AND 299) AS ok_calls,
    COUNT(*) FILTER (WHERE response_status BETWEEN 400 AND 499) AS client_errors,
    COUNT(*) FILTER (WHERE response_status >= 500)              AS server_errors,
    AVG(payload_bytes)::int                             AS avg_payload_bytes,
    MAX(payload_bytes)                                  AS max_payload_bytes
FROM marketing.n8n_api_audit
WHERE occurred_at > now() - interval '7 days'
GROUP BY date_trunc('hour', occurred_at), route, method
ORDER BY hour DESC, total_calls DESC;

COMMENT ON VIEW marketing.v_n8n_traffic_hourly IS
    'Hourly n8n-API traffic for the last 7 days. Use for anomaly-detection '
    '(unexpected route called, sudden traffic spike, 4xx-rate climbing).';

-- ─── Audit row ─────────────────────────────────────────────────────────
INSERT INTO marketing.audit_log (actor, action, target_table, payload)
VALUES (
    'migration:028',
    'n8n_api_audit.table_created',
    'marketing.n8n_api_audit',
    jsonb_build_object(
        'note',
        'Privacy-first audit for n8n-API calls. Never stores api_key, payload, '
        'or response body. 90d retention via prune_n8n_audit(). View '
        'v_n8n_traffic_hourly for anomaly-detection dashboards.',
        'function', 'marketing.prune_n8n_audit(keep_days=90)'
    )
);

COMMIT;
