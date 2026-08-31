-- Phase 11.U.K — Realtime DELETE payloads were missing from_node_id/to_node_id
-- because Postgres only ships the PK in `old` unless REPLICA IDENTITY is FULL.
-- Without this, supabase-realtime.js falls through and the renderer can't
-- locate which edge/node to remove from the canvas.

ALTER TABLE canvas_edges  REPLICA IDENTITY FULL;
ALTER TABLE canvas_nodes  REPLICA IDENTITY FULL;
ALTER TABLE ideas         REPLICA IDENTITY FULL;
