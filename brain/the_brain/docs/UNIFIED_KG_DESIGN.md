# Unified Brain Knowledge Graph — Design

Status: **Draft v1** (2026-04-12) — reviewed before implementation.

## Goal

One Qdrant-backed knowledge graph that subsumes:

- Brain's continuous thoughts (ContinuousThinkingEngine output)
- Brain's chat responses (BrainChat.send results)
- Brain's internal state snapshots (bridge activations, modulation)
- Rowboat bubbles + ideas (read from `~/.rowboat/vibemind/ideas/`)
- Space + event manifests (replacing `space_routing_head.pt` / `event_routing_head.pt`)

Single source of truth for **"what does Brain know, and what resonates with what"** — semantically AND neurologically.

## Why one collection, not many

Alternative considered: separate collections per node type (thoughts, bubbles, ideas, spaces, events).

Problems with that approach:

- Cross-type search needs multiple queries + manual merge
- Edges between types live in payloads on both sides → sync bug-prone
- Filter "give me anything similar to X" requires N queries
- Schema diverges slowly into N parallel schemas that drift

**Decision: one collection `brain-kg` with `node_type` as a keyword-indexed payload field.** Filter by `node_type` when you need it, skip the filter when you don't. Qdrant's filter + vector search is fast enough that this is the right choice.

## Collection Schema

```yaml
collection: brain-kg
vectors:
  semantic:
    size: 1024          # Qwen3-Embedding-0.6B
    distance: Cosine
    on_disk: false
  neural:
    size: 20484         # TriBE fsaverage5 vertices
    distance: Cosine
    on_disk: true       # sparse-ish, large — keep off hot RAM
payload_schema:
  node_type: keyword    # thought | response | bubble | idea | space | event | snapshot
  created_at: integer   # unix timestamp
  source: keyword       # continuous_thinking | brain_chat | rowboat_reader | etc.
  content: text
  # node-type specific fields below
payload_indexes:
  - node_type (keyword)
  - source (keyword)
  - created_at (integer, range)
  - tags (keyword, array)
  - space_hint (keyword)
  - bubble_id (keyword)
```

## Node Types and Their Payloads

### `thought`

```json
{
  "node_type": "thought",
  "thought_id": "uuid-string",
  "content": "my curiosity turns to: ...",
  "category": "explore | question | association | ...",
  "source": "continuous_thinking",
  "confidence": 0.6,
  "emotional_valence": 0.2,
  "arousal": 0.4,
  "created_at": 1776023456,
  "tags": ["topic:dopamine", "mode:idle"],
  "space_hint": "brain" | null,
  "bridge_levels_at_creation": {         // TriBE-derived snapshot
    "cortex": 0.31,
    "limbic": -0.05,
    "defense": 0.12,
    "motor": 0.02,
    "visceral": 0.08,
    "social": 0.11,
    "integration": 0.22,
    "memory": 0.15
  },
  "linked": {
    "bubbles": [],
    "ideas":   [],
    "thoughts": [],
    "responses": [],
    "spaces": [],
    "events":  []
  }
}
```

### `response`

```json
{
  "node_type": "response",
  "response_id": "uuid",
  "content": "Dopamine neurons in the VTA encode reward prediction...",
  "source": "brain_chat",
  "user_query": "how does dopamine signal reward prediction error",
  "query_id": "uuid",      // optional if query is also stored as node
  "routing_mode": "thalamic",
  "task_type": "thalamic_routed",
  "confidence": 0.75,
  "llm_model": "groq::llama-3.3-70b-versatile",
  "created_at": 1776024000,
  "thinking_time_ms": 2353,
  "tags": ["fact", "neuroscience"],
  "linked": {
    "bubbles": [], "ideas": [], "thoughts": [],
    "responses": [], "spaces": [], "events": []
  }
}
```

### `bubble`  (Rowboat)

```json
{
  "node_type": "bubble",
  "bubble_id": "bubble--abc123",
  "title": "...",
  "description": "...",
  "notes": ["...", "..."],        // top 20
  "bubble_edges": ["bubble--xyz"], // Rowboat's own bubble-bubble edges
  "source": "rowboat_reader",
  "created_at": 1776000000,
  "linked": { "thoughts": [], "ideas": [], "responses": [], ... }
}
```

### `idea`  (Rowboat)

```json
{
  "node_type": "idea",
  "idea_id": "idea--xyz789",
  "bubble_id": "bubble--abc123",
  "title": "...",
  "content": "...",
  "tags": ["..."],
  "source": "rowboat_reader",
  "created_at": 1776000000,
  "linked": { "thoughts": [], "bubbles": [], ... }
}
```

### `space`  (replaces space_routing_head.pt)

```json
{
  "node_type": "space",
  "space_id": "brain",                  // one of the 13 vibemind spaces
  "title": "Brain",
  "description": "Cognitive engine with bridges and thoughts",
  "source": "manifest",
  "created_at": 1776000000,
  "activation_strength": 0.0,           // bumped on successful route
  "linked": { "thoughts": [], "events": [], ... }
}
```

### `event`  (replaces event_routing_head.pt)

```json
{
  "node_type": "event",
  "event_id": "user_asks_question",
  "title": "...",
  "trigger_description": "...",
  "typical_response_strategy": "...",
  "source": "manifest",
  "created_at": 1776000000,
  "activation_strength": 0.0,
  "linked": { "thoughts": [], "responses": [], ... }
}
```

### `snapshot`  (Brain-state, optional)

Periodic snapshots of Brain's internal state (bridge activations, modulation factors, consciousness level). Lets us retrieve "what was Brain thinking/feeling around the time of thought X" by temporal proximity.

```json
{
  "node_type": "snapshot",
  "snapshot_id": "uuid",
  "created_at": 1776024000,
  "bridges": { "cortex": 0.78, "limbic": -0.09, ... },
  "modulation": { "attention_gain": 0.87, ... },
  "consciousness_level": 0.42,
  "cte_mode": "idle"
}
```

## Edge Model

Edges live in `payload.linked.*` arrays on **both** nodes (bidirectional). This trades a bit of write cost for cheap reads — you never have to query a join table.

**Edge types by source:**

| Creator | When | Writes on Side A | Writes on Side B |
|---|---|---|---|
| QdrantKG.upsert_thought | new thought | thought.linked.bubbles/ideas (top-k similar) | bubble.linked.thoughts / idea.linked.thoughts (append) |
| QdrantKG.upsert_response | new chat response | response.linked.ideas/bubbles/thoughts | mirror appends |
| Routing hit (I.1) | chat routed to space X | response.linked.spaces += [space_X] | space.linked.responses += [response_id] |
| Event trigger (I.1) | event Y fires | response.linked.events += [event_Y] | event.linked.responses |
| Rowboat bubble edge | bubble manifest has edge[] to another bubble | bubble.bubble_edges (direct) | — |

**Edge weight:** stored implicitly via `activation_strength` on the target node, bumped per hit. Not a separate edge-weight map (simpler).

**Max fan-out:** each `linked.*` array is capped at 50 to prevent hot nodes from blowing up payloads (`existing[-50:]` pattern).

## Similarity-Based Edge Creation

When a new thought T with vectors (v_sem, v_neu) arrives:

```
Phase 1: semantic-space edges
  search(collection=brain-kg, vector=v_sem, limit=20,
         filter={must_not: {node_type: thought}},
         score_threshold=0.55)
  → top-k ≈ bubbles/ideas/responses/spaces/events that semantically resonate

Phase 2: neural-space edges
  search(collection=brain-kg, vector=v_neu, limit=20,
         filter={must_not: {node_type: thought}},
         score_threshold=0.40)
  → top-k that neurologically resonate (TriBE activation similarity)

Phase 3: merge + deduplicate
  edges = set_union(semantic_hits, neural_hits)
  tag each edge with `matched_by`: "semantic" | "neural" | "both"

Phase 4: materialize bidirectionally
  upsert T with linked.* filled
  for each target: set_payload appending T to its linked.thoughts
```

## Routing Replacement (Phase I)

Current: `space_routing_head.pt` (trained MLP, 384-dim → 13 space scores)
New: query `brain-kg` for `node_type=space`, return weighted top-k.

```python
def route_to_space(query_text: str) -> dict:
    v_sem = qwen_embed(query_text)
    v_neu = tribe_predict(query_text)       # may be None (best-effort)
    sem_hits = search(v_sem, filter={node_type: "space"}, limit=3)
    if v_neu is not None:
        neu_hits = search(v_neu, filter={node_type: "space"}, limit=3)
    else:
        neu_hits = []
    # Hybrid score: 0.7 semantic + 0.3 neural, fallback semantic-only
    return weighted_merge(sem_hits, neu_hits, w=[0.7, 0.3])
```

Same pattern for events (`filter={node_type: "event"}`).

Every time a route is **confirmed** (response succeeds, user does not correct), we bump `activation_strength` on the chosen space/event. That's the learning signal — no gradient descent, just usage-weighted priors that bubble up in future queries.

## Read-Side API

MCP tools exposed via `brain-core` proxy:

- `kg_search(query: str, kind: str = "any", limit: int = 10, hybrid: bool = true)` — text → top-k, optionally hybrid (semantic+neural)
- `kg_related(node_id: str, depth: int = 1)` — return `linked.*` of one node (with optional 1-hop expansion)
- `kg_stats()` — collection sizes per node_type, edge-build counts, last-write times
- `kg_by_time(node_type, since_ts, until_ts)` — temporal slice (useful for "what was Brain thinking last hour")

## Write-Side Integration Points

| Event | Hook | Writes |
|---|---|---|
| CTE produces thought | `_on_thought_callbacks` in ContinuousThinkingEngine | `thought` + edges |
| BrainChat emits response | end of `brain_chat.send()` | `response` + edges |
| Rowboat reader ingests bubbles/ideas at Brain-start | `brain_server.py` startup | bulk `bubble` + `idea` upserts |
| Space/event manifests discovery | Brain-start | bulk `space` + `event` upserts |
| Consolidation tick (every 30s) | MemoryConsolidator.queue_brain_event | optional `snapshot` write |

## Sparse/Dense Consideration for TriBE Vector

TriBE output is 20484 floats. Stored as dense → 80 KB per point → 8 MB per 100 points. With `on_disk: true` in Qdrant this is fine up to ~100k nodes.

For >1M nodes we'd want sparse encoding (threshold-prune vertices with |activation| < eps). For v1 we stay dense — simpler.

## Performance Budget

Per thought ingestion (approx, CPU):

| Step | Target | Actual (worst case) |
|---|---|---|
| Qwen embed (1024d) | 100 ms | 200 ms |
| TriBE predict (20484d) | 3-5 s | 8 s (with TTS) |
| Qdrant search (×2 vectors) | 30 ms | 100 ms |
| Qdrant upsert + payload updates | 50 ms | 200 ms |
| **Total synchronous hot-path** | — | **— DO NOT DO THIS** |

**Conclusion:** everything except the Qwen embed must run async. CTE thread just hands a `ThoughtDoc` to a queue, worker thread does the heavy lifting. TriBE can be optional per-thought (sampled, e.g. every 3rd thought) to stay under daily compute budget.

## Existing Moltbook Handling

MoltbookStore persists entries to `data/moltbook/store.jsonl` with 384-dim SBERT embeddings. We leave this intact — Brain-internal ANN queries keep using it.

For KG we re-embed Moltbook entries with Qwen at startup **once**. Re-embedding ~300 entries with Qwen-0.6B costs ~30 s one-time. After that, the JSONL acts as the canonical text store and KG points reference moltbook entries via `moltbook_id` in payload.

## Open Questions

1. **TriBE every thought, or sampled?** Cost 3-5 s/thought. With CTE at 5 s tick, each thought costs one full tick. Need to sample (maybe every 3rd thought, or only responses) to stay real-time.

2. **sleep_wake and neuromod bridges** don't have good cortical correlates in TriBE. Keep heuristic, or add subcortical-proxy ROIs from a different source?

3. **Rowboat bubble sync strategy.** Full re-read at startup, or watch the `~/.rowboat/vibemind/ideas/` directory for changes? v1: startup-only.

4. **Duplicate detection.** If the same thought text comes twice, should we collapse to one point (deterministic UUID from hash) or allow duplicates (nondeterministic)? v1: hash-based id → collapses.

5. **Multi-user / multi-tenant.** Brain is single-user today. Future: `user_id` payload field + filter.

## Out of Scope for v1

- Graph visualization UI (use Rowboat's if they render the shared collection)
- Cross-instance sync (federated KGs)
- Fine-grained edge weights beyond `activation_strength`
- GNN training on the graph (would be Phase J)

## Review Checklist before Implementation

- [ ] Dimensions confirmed: Qwen-0.6B = 1024, TriBE = 20484
- [ ] Sample-rate policy for TriBE decided (default: only on user-facing responses, not CTE idle thoughts)
- [ ] Collection created with both vectors + 4 payload indexes
- [ ] `moltbook_id` cross-reference added to thought payload
- [ ] Write-queue worker thread bounded (max queue 1000, drop on overflow)
