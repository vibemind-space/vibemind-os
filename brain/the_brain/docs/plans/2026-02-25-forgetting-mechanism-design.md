# Forgetting Mechanism Design

**Date**: 2026-02-25
**Status**: Approved
**Approach**: A — Wire existing deletion machinery + tombstone log

## Problem

The brain accumulates knowledge but never forgets. Three socialization metrics are broken:
- **Concept death rate**: Always 0 — no entries ever deleted
- **Net progress**: Negative — low-confidence noise entries cause random drift
- **Drift consistency**: ~0 — centroid wanders incoherently due to noise

Root cause: `MoltbookStore.consolidate()` (which deletes dead entries) exists but is never called during the 7-phase consolidation cycle. Phase 1 (`_phase_decay`) only *counts* below-threshold entries without removing them.

## Design

### 1. Wire `consolidate()` into Phase 1 (DECAY)

**File**: `core/memory_consolidation.py` — `_phase_decay()`

After the existing `apply_decay()` call, invoke `self._moltbook.consolidate(activation_threshold=0.01)` to actually remove dead entries.

**Activation threshold**: 0.01 means an entry must be essentially forgotten to be deleted. An entry with `relevance=0.5`, `decay_rate=0.001`, `accessed_count=0` reaches 0.01 after ~391 hours (~16 days) of no access. Emotional entries (with valence) take even longer due to the 30% slower decay multiplier.

**Safety**: Only entries that have been completely forgotten are removed. Any entry that has been accessed even once in the past two weeks survives.

The existing `MoltbookStore.consolidate()` handles:
- Removal from `_entries` dict
- Removal from `SemanticIndex` (embedding matrix)
- Removal from `_tag_index`
- Increment of `_total_evicted` counter

We need to capture the dead entries *before* deletion to create tombstones.

### 2. Tombstone Log

**New classes in `core/memory_consolidation.py`**:

```
@dataclass Tombstone:
    entry_id: str
    tags: List[str]           # Topic tags from dead entry
    content_preview: str      # First 80 chars of content
    confidence: float         # Confidence at time of death
    reason: str               # 'activation_decay' | 'curation_prune' | 'lru_eviction'
    died_at: float            # Timestamp
    age_hours: float          # Entry age at death

class TombstoneLog:
    _tombstones: deque(maxlen=1000)
    _persist_path: str        # data/moltbook/tombstones.jsonl
    _total_forgotten: int

    record(entries, reason)   # Add tombstones for deleted entries
    recent(n=20)              # Get most recent tombstones
    forgotten_concepts()      # Tags from all tombstones (Set[str])
    get_stats()               # Summary dict
    save() / load()           # JSONL persistence
```

**Cap**: 1000 tombstones in-memory (deque maxlen). Oldest tombstones silently dropped.
**Persistence**: Saved alongside moltbook data in `data/moltbook/tombstones.jsonl`.

### 3. Integration with Consolidation Cycle

Modified Phase 1 flow:
```
Phase 1: DECAY
  1. apply_decay() — compute activation for all entries (existing)
  2. Identify dead entries (activation < 0.01)
  3. Record tombstones for dead entries (NEW)
  4. consolidate(0.01) — remove dead entries from store (NEW)
  5. Return stats including eviction count (NEW)
```

TombstoneLog is initialized in MemoryConsolidator.__init__() and saved in Phase 7 (PERSIST).

### 4. Stats Integration

`MemoryConsolidator.get_stats()` already returns cycle counts. Add:
- `total_evicted`: Running count of entries removed across all cycles
- `tombstone_count`: Current tombstone log size
- `last_eviction_count`: Entries removed in most recent cycle

Dashboard learning status line includes eviction info when non-zero:
"N entries forgotten" appended to status text.

### 5. Modification to MoltbookStore.consolidate()

The existing `consolidate()` method deletes entries but doesn't return WHICH entries were deleted. We need to either:
- (a) Return the list of deleted entry objects, or
- (b) Collect dead entries before calling consolidate()

**Choice**: (b) — Collect dead entries before deletion. This avoids changing the MoltbookStore API.

```python
# In _phase_decay():
dead_entries = [
    e for e in self._moltbook._entries.values()
    if e.compute_activation() < 0.01
]
if dead_entries:
    self._tombstone_log.record(dead_entries, 'activation_decay')
eviction = self._moltbook.consolidate(activation_threshold=0.01)
```

## Metrics Impact

All three weak metrics improve naturally without code changes:

- **Concept death rate > 0**: Deleted entries remove content → vocabulary shrinks → deaths detected
- **Net progress improves**: Noise entries removed → cleaner centroid → directional drift
- **Drift consistency improves**: Higher-quality entries → more coherent drift vectors

## Files Modified

| File | Change |
|------|--------|
| `core/memory_consolidation.py` | Add TombstoneLog class, wire consolidate() into _phase_decay(), add tombstone persistence to Phase 7, update get_stats() |
| `core/moltbook.py` | No changes needed — consolidate() and _remove_entry() already work |
| `core/socialization_metrics.py` | No changes needed — concept death tracking already correct |
| `web/templates/moltbook_dashboard.html` | Add eviction count to learning status line |
| `configs/default.yaml` | Add `tombstone_path` and `eviction_threshold` settings |

## Testing

7 new tests in `tests/test_memory_consolidation.py`:

1. `test_phase_decay_evicts_dead_entries` — Aged entries removed
2. `test_phase_decay_preserves_active_entries` — Fresh entries survive
3. `test_tombstone_recorded_on_eviction` — Tombstone has correct fields
4. `test_tombstone_log_cap` — 1000 entry cap respected
5. `test_tombstone_persistence` — Save/load roundtrip
6. `test_concept_death_rate_after_eviction` — Death rate > 0 after eviction
7. `test_eviction_stats_in_get_stats` — Stats include eviction count

Total: 86 existing + 7 new = 93 tests.
