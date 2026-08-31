-- ============================================================================
-- Marketing-Ops Schema for Vibemind Supabase
-- ============================================================================
-- This is the DDL that creates the `marketing` schema in supabase-db.
--
-- Heritage:
--   - Pattern from x-pathfinder-db.emails (accounts, emails, strategies, runs)
--     — proven schema for email discovery, kept as compatible substructure.
--   - Marketing-Ops additions for audiences, campaigns, templates, sends.
--
-- Data: NONE migrated from pathfinder (DSGVO-clean start).
--
-- Status: DEPLOYED to supabase-db (2026-05-26, rebuilt 2026-06-02 after
-- a vibemind-os submodule reset wiped the original DDL file. Live schema
-- is intact — this file re-codifies it. See _live_marketing_dump.sql for
-- the pg_dump reference.)
--
-- Apply with:
--   docker cp 001_marketing_schema.sql vibemind_supabase-db.1.<id>:/tmp/
--   docker exec vibemind_supabase-db.1.<id> psql -U supabase_admin -d postgres -f /tmp/001_marketing_schema.sql
--
-- Rollback:
--   docker exec vibemind_supabase-db.1.<id> psql -U supabase_admin -d postgres -c 'DROP SCHEMA marketing CASCADE'

BEGIN;

CREATE SCHEMA IF NOT EXISTS marketing;
SET search_path TO marketing, public;

-- ============================================================================
-- LEAD-LAYER (Pathfinder-Pattern: accounts + emails + discovery-strategies)
-- ============================================================================

CREATE TABLE IF NOT EXISTS marketing.accounts (
    handle        text PRIMARY KEY,
    display_name  text DEFAULT ''::text,
    bio           text DEFAULT ''::text,
    followers     integer DEFAULT 0,
    niche         text DEFAULT ''::text,
    source        text DEFAULT ''::text,
    created_at    timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_accounts_niche ON marketing.accounts(niche);

CREATE TABLE IF NOT EXISTS marketing.emails (
    email         text PRIMARY KEY,
    handle        text REFERENCES marketing.accounts(handle) ON DELETE CASCADE,
    confidence    real DEFAULT 0.0,
    mx_valid      boolean DEFAULT false,
    smtp_valid    smallint DEFAULT -1,
    catch_all     boolean DEFAULT false,
    strategy_id   text DEFAULT ''::text,
    domain        text DEFAULT ''::text,
    country       text DEFAULT 'XX'::text,
    created_at    timestamptz DEFAULT now(),
    -- Marketing-Ops additions: DSGVO-relevant consent + engagement tracking
    consent_given_at   timestamptz,
    consent_source     text DEFAULT '',
    unsubscribed_at    timestamptz,
    bounce_count       integer DEFAULT 0,
    last_engagement_at timestamptz
);
CREATE INDEX IF NOT EXISTS idx_emails_confidence ON marketing.emails(confidence DESC);
CREATE INDEX IF NOT EXISTS idx_emails_country    ON marketing.emails(country);
CREATE INDEX IF NOT EXISTS idx_emails_domain     ON marketing.emails(domain);
CREATE INDEX IF NOT EXISTS idx_emails_mx         ON marketing.emails(mx_valid);
CREATE INDEX IF NOT EXISTS idx_emails_smtp       ON marketing.emails(smtp_valid);
CREATE INDEX IF NOT EXISTS idx_emails_consent    ON marketing.emails(consent_given_at) WHERE consent_given_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_emails_unsub      ON marketing.emails(unsubscribed_at)  WHERE unsubscribed_at IS NOT NULL;

CREATE TABLE IF NOT EXISTS marketing.strategies (
    id              text PRIMARY KEY,
    format_pattern  text,
    domain          text,
    fitness         real DEFAULT 0.0,
    success_count   integer DEFAULT 0,
    created_at      timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS marketing.runs (
    id                  serial PRIMARY KEY,
    started_at          timestamptz,
    ended_at            timestamptz,
    accounts_processed  integer DEFAULT 0,
    emails_generated    integer DEFAULT 0,
    emails_verified     integer DEFAULT 0,
    status              text DEFAULT 'running'
);

-- ============================================================================
-- TAG-LAYER (audience-building primitives)
-- ============================================================================

CREATE TABLE IF NOT EXISTS marketing.tags (
    id          serial PRIMARY KEY,
    name        text NOT NULL UNIQUE,
    color       text DEFAULT '#888888',
    kind        text DEFAULT 'user',          -- 'system' (auto) or 'user' (manual)
    description text DEFAULT '',
    created_at  timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS marketing.email_tags (
    email   text REFERENCES marketing.emails(email) ON DELETE CASCADE,
    tag_id  integer REFERENCES marketing.tags(id) ON DELETE CASCADE,
    set_at  timestamptz DEFAULT now(),
    set_by  text DEFAULT '',
    PRIMARY KEY (email, tag_id)
);
CREATE INDEX IF NOT EXISTS idx_email_tags_tag ON marketing.email_tags(tag_id);

-- ============================================================================
-- AUDIENCE-LAYER (saved filters)
-- ============================================================================

CREATE TABLE IF NOT EXISTS marketing.audiences (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name          text NOT NULL,
    description   text DEFAULT '',
    filter_dsl    jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at    timestamptz DEFAULT now(),
    last_built_at timestamptz,
    member_count  integer DEFAULT 0
);

CREATE TABLE IF NOT EXISTS marketing.audience_members (
    audience_id  uuid REFERENCES marketing.audiences(id) ON DELETE CASCADE,
    email        text REFERENCES marketing.emails(email) ON DELETE CASCADE,
    added_at     timestamptz DEFAULT now(),
    PRIMARY KEY (audience_id, email)
);
CREATE INDEX IF NOT EXISTS idx_audience_members_email ON marketing.audience_members(email);

-- ============================================================================
-- TEMPLATE-LAYER (multi-channel content)
-- ============================================================================

CREATE TABLE IF NOT EXISTS marketing.templates (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name        text NOT NULL,
    channel     text NOT NULL,                          -- 'email','telegram','linkedin','mastodon',...
    subject     text DEFAULT '',
    body_html   text DEFAULT '',
    body_text   text DEFAULT '',
    variables   jsonb DEFAULT '[]'::jsonb,
    created_at  timestamptz DEFAULT now(),
    updated_at  timestamptz DEFAULT now(),
    created_by  text DEFAULT 'system'
);
CREATE INDEX IF NOT EXISTS idx_templates_channel ON marketing.templates(channel);

-- ============================================================================
-- CAMPAIGN-LAYER
-- ============================================================================

CREATE TABLE IF NOT EXISTS marketing.campaigns (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name            text NOT NULL,
    audience_id     uuid REFERENCES marketing.audiences(id) ON DELETE RESTRICT,
    template_id     uuid REFERENCES marketing.templates(id) ON DELETE RESTRICT,
    channel         text NOT NULL,
    status          text DEFAULT 'draft',               -- 'draft','scheduled','sending','sent','failed','cancelled'
    scheduled_at    timestamptz,
    sent_at         timestamptz,
    created_at      timestamptz DEFAULT now(),
    ab_variant_of   uuid REFERENCES marketing.campaigns(id) ON DELETE SET NULL,
    ab_split_pct    smallint DEFAULT 50 CHECK (ab_split_pct >= 0 AND ab_split_pct <= 100),
    is_loopback     boolean DEFAULT true
);
CREATE INDEX IF NOT EXISTS idx_campaigns_status     ON marketing.campaigns(status);
CREATE INDEX IF NOT EXISTS idx_campaigns_scheduled  ON marketing.campaigns(scheduled_at) WHERE status='scheduled';

-- ============================================================================
-- SEND-LAYER (per-recipient per-campaign tracking)
-- ============================================================================

CREATE TABLE IF NOT EXISTS marketing.campaign_sends (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    campaign_id   uuid NOT NULL REFERENCES marketing.campaigns(id) ON DELETE CASCADE,
    email         text NOT NULL REFERENCES marketing.emails(email) ON DELETE CASCADE,
    queued_at     timestamptz DEFAULT now(),
    sent_at       timestamptz,
    delivered_at  timestamptz,
    opened_at     timestamptz,
    clicked_at    timestamptz,
    replied_at    timestamptz,
    bounced_at    timestamptz,
    bounce_reason text,
    unsubscribed_at timestamptz,
    open_count    integer DEFAULT 0,
    click_count   integer DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_sends_campaign ON marketing.campaign_sends(campaign_id);
CREATE INDEX IF NOT EXISTS idx_sends_email    ON marketing.campaign_sends(email);
CREATE INDEX IF NOT EXISTS idx_sends_sent     ON marketing.campaign_sends(sent_at);

-- ============================================================================
-- INBOUND-LAYER (mail-sync from Mailcow IMAP)
-- ============================================================================

CREATE TABLE IF NOT EXISTS marketing.inbound_messages (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    received_at     timestamptz NOT NULL,
    mailbox         text NOT NULL,
    from_email      text,
    from_name       text,
    to_email        text,
    subject         text,
    body_text       text,
    message_id      text,
    in_reply_to     text,
    headers         jsonb,
    is_bounce       boolean DEFAULT false,
    is_autoreply    boolean DEFAULT false,
    linked_send_id  uuid REFERENCES marketing.campaign_sends(id) ON DELETE SET NULL,
    created_at      timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_inbound_received  ON marketing.inbound_messages(received_at DESC);
CREATE INDEX IF NOT EXISTS idx_inbound_from      ON marketing.inbound_messages(from_email);
CREATE INDEX IF NOT EXISTS idx_inbound_in_reply  ON marketing.inbound_messages(in_reply_to);

-- ============================================================================
-- AUDIT
-- ============================================================================

CREATE TABLE IF NOT EXISTS marketing.audit_log (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    actor        text DEFAULT 'system',
    action       text NOT NULL,
    target_table text,
    target_id    text,
    payload      jsonb,
    created_at   timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_audit_created  ON marketing.audit_log(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_actor    ON marketing.audit_log(actor);
CREATE INDEX IF NOT EXISTS idx_audit_action   ON marketing.audit_log(action);

COMMIT;

-- ============================================================================
-- Verification: 13 tables expected
--   SELECT tablename FROM pg_tables WHERE schemaname='marketing' ORDER BY tablename;
-- Expected: accounts, audience_members, audiences, audit_log, campaign_sends,
--           campaigns, email_tags, emails, inbound_messages, runs, strategies,
--           tags, templates
-- ============================================================================
