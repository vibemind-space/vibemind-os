# Forgetting Mechanism Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Wire the existing `MoltbookStore.consolidate()` into the consolidation cycle's Phase 1 so dead entries are actually deleted, add a TombstoneLog for tracking forgotten knowledge, and surface eviction stats in the dashboard.

**Architecture:** Modify `_phase_decay()` in MemoryConsolidator to call `consolidate(0.01)` after applying decay. Add a `TombstoneLog` dataclass+class in the same file. Capture dead entries before deletion to create tombstones. Persist tombstones in Phase 7. Expose eviction count in `get_stats()`.

**Tech Stack:** Python 3.11, dataclasses, deque, JSON, numpy, pytest, HTML/JS dashboard

---

### Task 1: TombstoneLog — Test + Implementation

**Files:**
- Modify: `core/memory_consolidation.py` (add classes at top, before MemoryConsolidator)
- Test: `tests/test_memory_consolidation.py`

**Step 1: Write the failing tests**

Add these tests at the END of `tests/test_memory_consolidation.py`, inside a new test class:

```python
# ═══════════════════════════════════════════════════════════════════
# TestTombstoneLog
# ═══════════════════════════════════════════════════════════════════

class TestTombstoneLog:
    """Test tombstone recording for forgotten entries."""

    def test_record_creates_tombstones(self):
        """Recording dead entries creates Tombstone objects."""
        from core.memory_consolidation import TombstoneLog
        log = TombstoneLog(max_tombstones=100)

        # Create fake dead entries
        entry = MagicMock()
        entry.id = 'dead_1'
        entry.tags = ['python', 'basics']
        entry.content = 'Python is a programming language used for many applications'
        entry.confidence = 0.3
        entry.created_at = time.time() - 7200  # 2 hours old

        log.record([entry], reason='activation_decay')
        assert len(log._tombstones) == 1

        tomb = log._tombstones[0]
        assert tomb.entry_id == 'dead_1'
        assert tomb.tags == ['python', 'basics']
        assert tomb.content_preview == 'Python is a programming language used for many applications'[:80]
        assert tomb.confidence == 0.3
        assert tomb.reason == 'activation_decay'
        assert tomb.age_hours >= 1.9  # ~2 hours

    def test_tombstone_log_cap(self):
        """Deque maxlen caps at max_tombstones."""
        from core.memory_consolidation import TombstoneLog
        log = TombstoneLog(max_tombstones=5)

        for i in range(10):
            entry = MagicMock()
            entry.id = f'dead_{i}'
            entry.tags = []
            entry.content = f'Content {i}'
            entry.confidence = 0.1
            entry.created_at = time.time()
            log.record([entry], reason='activation_decay')

        # Only last 5 should survive
        assert len(log._tombstones) == 5
        assert log._tombstones[0].entry_id == 'dead_5'
        assert log._total_forgotten == 10

    def test_recent_returns_latest(self):
        """recent(n) returns the N most recent tombstones."""
        from core.memory_consolidation import TombstoneLog
        log = TombstoneLog(max_tombstones=100)

        for i in range(8):
            entry = MagicMock()
            entry.id = f'dead_{i}'
            entry.tags = [f'topic_{i}']
            entry.content = f'Content {i}'
            entry.confidence = 0.1
            entry.created_at = time.time()
            log.record([entry], reason='activation_decay')

        recent = log.recent(3)
        assert len(recent) == 3
        assert recent[0].entry_id == 'dead_7'  # Most recent first

    def test_forgotten_concepts(self):
        """forgotten_concepts() returns all tags from tombstones."""
        from core.memory_consolidation import TombstoneLog
        log = TombstoneLog(max_tombstones=100)

        for tags in [['python', 'ml'], ['docker', 'devops'], ['python', 'web']]:
            entry = MagicMock()
            entry.id = str(id(tags))
            entry.tags = tags
            entry.content = 'Test'
            entry.confidence = 0.1
            entry.created_at = time.time()
            log.record([entry], reason='activation_decay')

        concepts = log.forgotten_concepts()
        assert concepts == {'python', 'ml', 'docker', 'devops', 'web'}

    def test_get_stats(self):
        """get_stats() returns summary dict."""
        from core.memory_consolidation import TombstoneLog
        log = TombstoneLog(max_tombstones=100)
        stats = log.get_stats()
        assert stats['total_forgotten'] == 0
        assert stats['tombstone_count'] == 0

    def test_persistence_roundtrip(self):
        """Save and load produces identical tombstone log."""
        from core.memory_consolidation import TombstoneLog
        import tempfile, os

        path = os.path.join(tempfile.mkdtemp(), 'tombstones.jsonl')
        log = TombstoneLog(max_tombstones=100, persist_path=path)

        for i in range(3):
            entry = MagicMock()
            entry.id = f'dead_{i}'
            entry.tags = [f'tag_{i}']
            entry.content = f'Content about topic {i}'
            entry.confidence = 0.2 + i * 0.1
            entry.created_at = time.time() - (i * 3600)
            log.record([entry], reason='activation_decay')

        log.save()
        assert os.path.exists(path)

        log2 = TombstoneLog(max_tombstones=100, persist_path=path)
        log2.load()
        assert len(log2._tombstones) == 3
        assert log2._total_forgotten == 3
        assert log2._tombstones[0].entry_id == 'dead_0'
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_memory_consolidation.py::TestTombstoneLog -v 2>&1 | tail -20`
Expected: FAIL with `ImportError: cannot import name 'TombstoneLog'`

**Step 3: Write minimal implementation**

Add these classes in `core/memory_consolidation.py` AFTER the imports (line 34) and BEFORE the `MemoryConsolidator` class (line 37):

```python
from dataclasses import dataclass, field
import json

@dataclass
class Tombstone:
    """Record of a forgotten knowledge entry."""
    entry_id: str
    tags: List[str]
    content_preview: str       # First 80 chars
    confidence: float
    reason: str                # 'activation_decay' | 'curation_prune' | 'lru_eviction'
    died_at: float
    age_hours: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            'entry_id': self.entry_id,
            'tags': self.tags,
            'content_preview': self.content_preview,
            'confidence': round(self.confidence, 4),
            'reason': self.reason,
            'died_at': self.died_at,
            'age_hours': round(self.age_hours, 2),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'Tombstone':
        return cls(**d)


class TombstoneLog:
    """Lightweight log of deleted knowledge entries.

    Keeps a bounded deque of Tombstone records for tracking what the
    brain has forgotten. Enables concept death detection and
    'forgotten knowledge' awareness.
    """

    def __init__(self, max_tombstones: int = 1000,
                 persist_path: Optional[str] = None):
        from collections import deque
        self._tombstones: deque = deque(maxlen=max_tombstones)
        self._persist_path = persist_path
        self._total_forgotten: int = 0

    def record(self, entries: list, reason: str) -> None:
        """Create tombstones for a batch of dead entries."""
        now = time.time()
        for entry in entries:
            created = getattr(entry, 'created_at', now)
            tomb = Tombstone(
                entry_id=getattr(entry, 'id', 'unknown'),
                tags=list(getattr(entry, 'tags', [])),
                content_preview=str(getattr(entry, 'content', ''))[:80],
                confidence=float(getattr(entry, 'confidence', 0.0)),
                reason=reason,
                died_at=now,
                age_hours=round((now - created) / 3600, 2),
            )
            self._tombstones.append(tomb)
            self._total_forgotten += 1

    def recent(self, n: int = 20) -> List['Tombstone']:
        """Return the N most recent tombstones (newest first)."""
        items = list(self._tombstones)
        items.reverse()
        return items[:n]

    def forgotten_concepts(self) -> set:
        """Return all tags from all tombstones."""
        concepts = set()
        for t in self._tombstones:
            concepts.update(t.tags)
        return concepts

    def get_stats(self) -> Dict[str, Any]:
        """Summary statistics."""
        return {
            'total_forgotten': self._total_forgotten,
            'tombstone_count': len(self._tombstones),
        }

    def save(self) -> None:
        """Persist tombstones to JSONL file."""
        if not self._persist_path:
            return
        os.makedirs(os.path.dirname(self._persist_path), exist_ok=True)
        with open(self._persist_path, 'w') as f:
            # First line: metadata
            json.dump({'total_forgotten': self._total_forgotten}, f)
            f.write('\n')
            for tomb in self._tombstones:
                json.dump(tomb.to_dict(), f)
                f.write('\n')

    def load(self) -> None:
        """Load tombstones from JSONL file."""
        if not self._persist_path or not os.path.exists(self._persist_path):
            return
        try:
            with open(self._persist_path, 'r') as f:
                lines = f.readlines()
            if not lines:
                return
            # First line is metadata
            meta = json.loads(lines[0])
            self._total_forgotten = meta.get('total_forgotten', 0)
            for line in lines[1:]:
                line = line.strip()
                if line:
                    self._tombstones.append(Tombstone.from_dict(json.loads(line)))
        except Exception as e:
            logger.warning("Failed to load tombstones: %s", e)
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_memory_consolidation.py::TestTombstoneLog -v 2>&1 | tail -20`
Expected: 6 PASSED

**Step 5: Run all existing tests to verify no regressions**

Run: `python -m pytest tests/test_memory_consolidation.py tests/test_socialization_metrics.py -v 2>&1 | tail -10`
Expected: 92 passed (86 existing + 6 new)

**Step 6: Commit**

```bash
git add core/memory_consolidation.py tests/test_memory_consolidation.py
git commit -m "feat: add TombstoneLog for tracking forgotten knowledge entries"
```

---

### Task 2: Wire consolidate() into _phase_decay — Test + Implementation

**Files:**
- Modify: `core/memory_consolidation.py:45-146` (MemoryConsolidator.__init__ + _phase_decay)
- Test: `tests/test_memory_consolidation.py`

**Step 1: Write the failing tests**

Add to the existing `TestMemoryConsolidator` class in `tests/test_memory_consolidation.py`:

```python
    def test_phase_decay_evicts_dead_entries(self):
        """Phase DECAY actually removes entries with activation < 0.01."""
        store = _make_mock_moltbook(n_entries=5)

        # Make 2 entries "dead" (activation < 0.01)
        dead_entry_0 = store._entries['entry_0']
        dead_entry_0.compute_activation = MagicMock(return_value=0.005)  # Below 0.01
        dead_entry_0.tags = ['python']
        dead_entry_0.content = 'Dead content about Python'
        dead_entry_0.confidence = 0.1
        dead_entry_0.created_at = time.time() - 86400

        dead_entry_1 = store._entries['entry_1']
        dead_entry_1.compute_activation = MagicMock(return_value=0.003)  # Below 0.01
        dead_entry_1.tags = ['docker']
        dead_entry_1.content = 'Dead content about Docker'
        dead_entry_1.confidence = 0.05
        dead_entry_1.created_at = time.time() - 172800

        # Other entries are alive
        for eid in ['entry_2', 'entry_3', 'entry_4']:
            store._entries[eid].compute_activation = MagicMock(return_value=0.5)

        # Mock consolidate to actually remove the dead entries
        def fake_consolidate(activation_threshold=0.01):
            removed = 0
            dead_ids = []
            for eid, entry in list(store._entries.items()):
                if entry.compute_activation() < activation_threshold:
                    dead_ids.append(eid)
            for eid in dead_ids:
                del store._entries[eid]
                removed += 1
            return {'removed': removed, 'merged': 0}

        store.consolidate = MagicMock(side_effect=fake_consolidate)

        mc = MemoryConsolidator(moltbook_store=store)
        result = mc._phase_decay()

        # consolidate was called
        store.consolidate.assert_called_once_with(activation_threshold=0.01)
        # Eviction count reported
        assert result.get('evicted', 0) == 2
        # Only 3 entries remain
        assert len(store._entries) == 3
        # Tombstones recorded
        assert mc._tombstone_log._total_forgotten == 2

    def test_phase_decay_preserves_active_entries(self):
        """Phase DECAY does not remove entries with high activation."""
        store = _make_mock_moltbook(n_entries=3)

        # All entries are alive
        for eid in store._entries:
            store._entries[eid].compute_activation = MagicMock(return_value=0.8)

        store.consolidate = MagicMock(return_value={'removed': 0, 'merged': 0})

        mc = MemoryConsolidator(moltbook_store=store)
        result = mc._phase_decay()

        store.consolidate.assert_called_once_with(activation_threshold=0.01)
        assert result.get('evicted', 0) == 0
        assert len(store._entries) == 3
        assert mc._tombstone_log._total_forgotten == 0
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_memory_consolidation.py::TestMemoryConsolidator::test_phase_decay_evicts_dead_entries tests/test_memory_consolidation.py::TestMemoryConsolidator::test_phase_decay_preserves_active_entries -v 2>&1 | tail -10`
Expected: FAIL — `mc` has no `_tombstone_log` attribute

**Step 3: Implement — Wire tombstone log + consolidate into _phase_decay**

In `core/memory_consolidation.py`, modify `MemoryConsolidator.__init__()`:

After line 96 (`self._evo_path = ...`), add:

```python
        # Tombstone log for tracking forgotten entries
        self._tombstone_log = TombstoneLog(
            max_tombstones=1000,
            persist_path='data/moltbook/tombstones.jsonl',
        )
```

Modify `_phase_decay()` (lines 130-146) to:

```python
    def _phase_decay(self) -> Dict[str, int]:
        """Apply Ebbinghaus forgetting curve + evict dead entries.

        1. apply_decay() — compute activation for all entries
        2. Identify dead entries (activation < 0.01)
        3. Record tombstones for dead entries
        4. consolidate() — remove dead entries from store
        """
        if not self._decay:
            return {'decayed': 0, 'below_threshold': 0, 'evicted': 0}

        try:
            result = self._decay.apply_decay()
            self._total_decayed += result.get('decayed', 0)

            # Collect dead entries BEFORE deletion (for tombstones)
            dead_entries = [
                e for e in list(self._moltbook._entries.values())
                if e.compute_activation() < 0.01
            ]

            # Record tombstones
            if dead_entries:
                self._tombstone_log.record(dead_entries, 'activation_decay')

            # Actually evict dead entries
            eviction = self._moltbook.consolidate(activation_threshold=0.01)
            result['evicted'] = eviction.get('removed', 0)

            if result['evicted'] > 0:
                logger.info(
                    "Phase DECAY evicted %d entries (%d tombstones total)",
                    result['evicted'], self._tombstone_log._total_forgotten,
                )

            return result
        except Exception as e:
            logger.warning("Phase DECAY failed: %s", e)
            return {'decayed': 0, 'below_threshold': 0, 'evicted': 0}
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_memory_consolidation.py::TestMemoryConsolidator::test_phase_decay_evicts_dead_entries tests/test_memory_consolidation.py::TestMemoryConsolidator::test_phase_decay_preserves_active_entries -v 2>&1 | tail -10`
Expected: 2 PASSED

**Step 5: Run ALL tests**

Run: `python -m pytest tests/test_memory_consolidation.py tests/test_socialization_metrics.py -v 2>&1 | tail -10`
Expected: 94 passed (86 + 6 tombstone + 2 eviction)

**Step 6: Commit**

```bash
git add core/memory_consolidation.py tests/test_memory_consolidation.py
git commit -m "feat: wire consolidate() into Phase 1 DECAY to evict dead entries

Entries with activation < 0.01 (~16 days of no access) are now actually
removed during consolidation cycles. Tombstones are recorded before
deletion to track what was forgotten."
```

---

### Task 3: Persist Tombstones in Phase 7 + Expose Stats

**Files:**
- Modify: `core/memory_consolidation.py:410-546` (_phase_persist + get_stats)
- Test: `tests/test_memory_consolidation.py`

**Step 1: Write the failing test**

Add to `TestMemoryConsolidator` class:

```python
    def test_eviction_stats_in_get_stats(self):
        """get_stats() includes tombstone/eviction data."""
        store = _make_mock_moltbook()
        store.consolidate = MagicMock(return_value={'removed': 0, 'merged': 0})
        mc = MemoryConsolidator(moltbook_store=store)

        stats = mc.get_stats()
        assert 'total_evicted' in stats
        assert 'tombstone_count' in stats
        assert stats['total_evicted'] == 0
        assert stats['tombstone_count'] == 0
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_memory_consolidation.py::TestMemoryConsolidator::test_eviction_stats_in_get_stats -v 2>&1 | tail -10`
Expected: FAIL — `total_evicted` not in stats dict

**Step 3: Implement stats + persist**

In `core/memory_consolidation.py`, modify `_phase_persist()` (line ~410). Add tombstone persistence AFTER evolution save:

```python
        # Tombstones
        try:
            self._tombstone_log.save()
        except Exception as e:
            logger.warning("Persist tombstones failed: %s", e)
```

Modify `get_stats()` (line ~532). Add these keys to the returned dict:

```python
            'total_evicted': self._tombstone_log._total_forgotten,
            'tombstone_count': len(self._tombstone_log._tombstones),
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_memory_consolidation.py::TestMemoryConsolidator::test_eviction_stats_in_get_stats -v 2>&1 | tail -10`
Expected: PASS

**Step 5: Run ALL tests**

Run: `python -m pytest tests/test_memory_consolidation.py tests/test_socialization_metrics.py -v 2>&1 | tail -10`
Expected: 95 passed

**Step 6: Commit**

```bash
git add core/memory_consolidation.py tests/test_memory_consolidation.py
git commit -m "feat: persist tombstones in Phase 7, expose eviction stats"
```

---

### Task 4: Dashboard — Show Eviction Count in Learning Status

**Files:**
- Modify: `web/templates/moltbook_dashboard.html:1332-1342` (summary text section)

**Step 1: Add eviction info to the summary text**

In `moltbook_dashboard.html`, find the summary text construction (~line 1333). After the existing `parts.push(...)` calls, add:

```javascript
    // Show forgotten entries count (from consolidation stats, not socialization)
    const evicted = statsData.consolidation_evicted || 0;
    if (evicted > 0) parts.push(evicted + ' forgotten');
```

**Step 2: Verify the API provides eviction data**

The `/api/knowledge/socialization` endpoint already returns `consolidation_stats` from `MemoryConsolidator.get_stats()`. We may need to ensure the `total_evicted` field flows through. Check `web/routers/knowledge.py` to see if consolidation stats are included.

If not already included, add `consolidation_evicted` to the API response in `web/routers/knowledge.py`:

```python
    # In get_socialization_stats():
    consolidation = getattr(request.app.state, 'memory_consolidator', None)
    consolidation_stats = consolidation.get_stats() if consolidation else {}

    return {
        'metrics': soc.get_stats(),
        'consolidation_evicted': consolidation_stats.get('total_evicted', 0),
    }
```

**Step 3: Live test in browser**

Start server, navigate to `/ui/moltbook`, check Socialization tab. If entries have been evicted, the summary should show "N forgotten".

**Step 4: Commit**

```bash
git add web/templates/moltbook_dashboard.html web/routers/knowledge.py
git commit -m "feat: show forgotten entry count in Socialization dashboard"
```

---

### Task 5: Integration Test — Concept Death After Eviction

**Files:**
- Test: `tests/test_memory_consolidation.py`

**Step 1: Write the integration test**

This test verifies the end-to-end flow: entries die → concept death rate becomes non-zero.

Add to `TestTombstoneLog` class:

```python
    def test_concept_death_rate_after_eviction(self):
        """After evicting entries, concept death rate should become non-zero.

        This is an integration test verifying the pipeline:
        entries exist → socialization measures concepts → entries die →
        socialization re-measures → death_rate > 0
        """
        from core.socialization_metrics import SocializationMetrics
        from core.moltbook import MoltbookStore

        # Create a real MoltbookStore with entries
        store = MoltbookStore(config={'max_entries': 1000, 'embedding_dim': 8})

        # Add entries with distinct topics
        topics = [
            ("Python is great for data science and machine learning", ['python', 'ml']),
            ("Docker containers simplify deployment pipelines", ['docker', 'devops']),
            ("React hooks enable functional component state", ['react', 'frontend']),
            ("Kubernetes orchestrates container workloads at scale", ['k8s', 'devops']),
            ("Neural networks learn hierarchical representations", ['ml', 'neural']),
        ]
        entry_ids = []
        for content, tags in topics:
            e = store.add_entry(content=content, tags=tags, confidence=0.5)
            entry_ids.append(e.id)

        # Create SocializationMetrics and measure
        soc = SocializationMetrics(moltbook=store)
        soc.compute_all()  # First cycle — establishes baseline concepts

        # Now kill 2 entries by removing them (simulating consolidate())
        for eid in entry_ids[:2]:  # Kill python+ml and docker+devops entries
            store._remove_entry(eid)

        # Measure again — should detect concept deaths
        result = soc.compute_all()
        death_rate = result.get('concept_death_rate', 0.0)

        # At least some concepts from the dead entries should be gone
        assert death_rate > 0, f"Expected concept deaths after eviction, got {death_rate}"
```

**Step 2: Run test to verify it passes**

Run: `python -m pytest tests/test_memory_consolidation.py::TestTombstoneLog::test_concept_death_rate_after_eviction -v 2>&1 | tail -10`
Expected: PASS (this is a green-path integration test)

**Step 3: Run ALL tests**

Run: `python -m pytest tests/test_memory_consolidation.py tests/test_socialization_metrics.py -v 2>&1 | tail -10`
Expected: 96 passed

**Step 4: Commit**

```bash
git add tests/test_memory_consolidation.py
git commit -m "test: integration test verifying concept death after entry eviction"
```

---

### Task 6: Config + Final Verification

**Files:**
- Modify: `configs/default.yaml` (add tombstone_path setting)

**Step 1: Add config entry**

In `configs/default.yaml`, in the `moltbook:` section (after `markov_path`), add:

```yaml
  tombstone_path: "data/moltbook/tombstones.jsonl"
  eviction_threshold: 0.01    # Activation below this = forgotten
```

**Step 2: Wire config into MemoryConsolidator**

If the MemoryConsolidator reads from yaml config, update the tombstone path to use the config value. Otherwise skip — the hardcoded `data/moltbook/tombstones.jsonl` path is fine for now.

**Step 3: Run full test suite**

Run: `python -m pytest tests/test_memory_consolidation.py tests/test_socialization_metrics.py -v 2>&1 | tail -15`
Expected: 96 passed, 0 failed

**Step 4: Final commit**

```bash
git add configs/default.yaml
git commit -m "config: add tombstone_path and eviction_threshold settings"
```

---

## Summary

| Task | Tests Added | Files Modified |
|------|-------------|----------------|
| 1. TombstoneLog | 6 | memory_consolidation.py, test_memory_consolidation.py |
| 2. Wire consolidate() | 2 | memory_consolidation.py, test_memory_consolidation.py |
| 3. Persist + Stats | 1 | memory_consolidation.py, test_memory_consolidation.py |
| 4. Dashboard | 0 | moltbook_dashboard.html, knowledge.py |
| 5. Integration test | 1 | test_memory_consolidation.py |
| 6. Config | 0 | default.yaml |

**Total: 10 new tests, 5 files modified, 6 commits**
