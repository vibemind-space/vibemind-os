# Thalamic Rewiring Design
> Date: 2026-02-22
> Status: APPROVED
> Approach: Rewire existing Python brain so ThalamoPC6 becomes THE single input gate

## Problem Statement

The Brain currently has 3 disconnected entry points:

1. **BrainChat.send()** — text goes through `_route_through_thalamus()` which uses
   TaskFeatureRouter -> ConversationPathPlanner -> DecisionRouter (3-layer routing).
   ThalamoPC6's thalamic math is never invoked.

2. **Unified Brain `/predict`** — the HierarchicalPlanner pipeline.
   Also bypasses ThalamoPC6.

3. **CognitiveLoop** — has its own PERCEIVE phase (SuperiorColliculus saliency).
   Bypasses ThalamoPC6 too.

Meanwhile, the learning engine (`learning_engine/klotski/neurosymbolic/`) has exactly
the right components — KotlinGraph (episodic memory), KuroGraph (pattern mining),
CTMLayer (continuous thought), NeuroSymbolicBrain (4-layer processing) — but they are
hardcoded for Klotski puzzles and disconnected from the main brain.

**The gap:** ThalamoPC6 has real thalamic math (TRN inhibition, prediction errors,
Kuramoto coupling, softmax gating) but nothing actually sends input through it.

## Target Architecture

```
ALL INPUT
  |-- Chat text (user messages)
  |-- Sensor data (SystemVitals, FileSystem, Process, Git...)
  |-- Agent events (actions, outcomes, errors)
  |-- Self-knowledge (memories, reflections, emotions)
  +-- External API (webhooks, triggers)
        |
        v
+----------------------------------------------+
|          ThalamoPC6 (Thalamic Gate)           |
|  6 modalities -> softmax gating -> routes    |
|  TRN lateral inhibition + prediction errors  |
|  Kuramoto phase coupling                     |
+------+----------+-----------+----------------+
       |          |           |
  +----v---+ +---v---+ +----v---+
  | Area A | | Area B| | Area N |  <- MoltBook Communities
  |(always | |(always| |(always |    (parallel cortical columns)
  | active)| |active)| |active) |
  +----+---+ +---+---+ +----+---+
       |          |           |
       v          v           v
  +--------------------------------------+
  |  KotlinGraph (episodic memory)       |  <- shared, records all events
  |  KuroGraph (pattern mining)          |  <- extracts strategies over time
  +--------------------------------------+
       |
       v  activation levels read by...
  +--------------------------------------+
  |     Response Agent                   |
  |  CTMLayer (continuous thought)       |
  |  -> LLM (natural language)           |
  +--------------------------------------+
       |
       v
    OUTPUT
```

## Design Decisions

1. **Single thalamic gate for everything** — ALL input types (chat, sensors, agent
   events, API calls) funnel through ThalamoPC6. No bypass paths.

2. **Communities as brain areas** — MoltBook communities work in parallel constantly.
   A response agent reads activations to form responses.

3. **KuroGraph = custom DAG computation graph** — Not Kuramoto-based, despite the
   name similarity. A pattern mining graph built on KotlinGraph.

4. **Stay Python** — All implementation in Python. The Kotlin references in voice
   conversation were aspirational, not for implementation.

5. **No deletions** — Everything existing stays as fallback. The 3-layer router
   becomes a fallback, not primary path.

## Modality Mapping

| ThalamoPC6 Modality | Brain Input               | Example                          |
|---------------------|---------------------------|----------------------------------|
| `vision`            | Structured data           | File contents, JSON, code, API   |
| `audio`             | Natural language text     | User messages, log entries       |
| `touch`             | System sensors            | CPU, memory, disk, processes     |
| `taste`             | Internal state            | Emotions, drives, motivation     |
| `vestibular`        | Spatial/temporal context  | Time, location, session state    |
| `threat`            | Anomalies & urgency       | Errors, safety flags, interrupts |

## Implementation Phases

### Phase 1: Generalize the Learning Engine (~3 files)

**Goal:** Make KotlinGraph, KuroGraph, and DualGraphManager domain-agnostic.

Currently under `learning_engine/klotski/neurosymbolic/memory/` storing `np.ndarray`
board states with `int` actions. Generalize to any hashable state + named actions.

| Source File | Target File | Changes |
|---|---|---|
| `learning_engine/.../memory/kotlingraph.py` | `core/kotlin_graph.py` | States: ndarray -> Dict[str,Any], Actions: int -> str, Keep NetworkX MultiDiGraph |
| `learning_engine/.../memory/kurograph.py` | `core/kuro_graph.py` | Same type generalization, n-gram mining stays generic |
| `learning_engine/.../memory/dual_graph_manager.py` | `core/dual_graph.py` | Same coordinator, expose record_event() and suggest_action() |

**What stays the same:** All graph algorithms, episode tracking, n-gram mining,
pattern scoring. This is a port, not a rewrite.

### Phase 2: Wire ThalamoPC6 as THE Input Gate (~2 files)

**Goal:** Every input type flows through ThalamoPC6's existing math.

**New file: `core/thalamic_adapter.py`** (~150 lines)
- `encode_input(input_type, data) -> Dict[modality, vector]`
- Calls `ThalamoPC6.step(inputs)` to get gated outputs + routing weights
- Returns which "areas" (communities) to activate most strongly

**Change: `core/brain_chat.py`**
- Replace `_route_through_thalamus()` (3-layer router) with ThalamoPC6 adapter
- 3-layer router becomes fallback for backward compatibility
- CognitiveLoop's PERCEIVE phase feeds through adapter too

### Phase 3: MoltBook Communities as Cortical Areas (~2 files)

**Goal:** Each MoltBook community is an always-on parallel processor.

**New file: `core/cortical_area.py`** (~200 lines)
```python
class CorticalArea:
    """One brain area = one MoltBook community + one CorticalColumn"""
    name: str                      # e.g., "language", "reasoning", "memory"
    column: CanonicalMicrocircuit  # 6-layer processing (existing)
    activation: float = 0.0       # Current activation (read by response agent)
    specialty_modules: List        # Which neuroscience modules this area uses
    dual_graph: DualGraph          # Shared episodic + pattern memory
```

Each community:
- Has its own CorticalColumn (existing 6-layer canonical microcircuit)
- Receives thalamic input weighted by ThalamoPC6 gates
- Maintains activation level (float 0-1)
- Writes thoughts to shared KotlinGraph
- Runs continuously via CTE ticks

### Phase 4: Response Agent with CTM (~1 file)

**Goal:** A response agent reads community activations and generates output.

**New file: `core/response_agent.py`** (~200 lines)

The response agent:
1. Reads activation levels from all cortical areas
2. Selects top-K most activated areas
3. Collects their recent thoughts (from KotlinGraph)
4. Runs through CTMLayer (50-100 ticks) for deliberation
5. Passes refined thought to LLM for natural language generation

Replaces BrainChat's direct TalkerModule calls:
```
ThalamoPC6 gates -> Areas activate -> Response Agent reads -> CTM deliberates -> LLM speaks
```

### Phase 5: Integrate with Existing 43 Modules (~1 file change)

**Goal:** 43 neuroscience modules wire into cortical areas as specialty processors.

Default area assignments (configurable):
- **Language area:** LanguageCenter, PersonalityModel, DialogueManager
- **Executive area:** PrefrontalCortex, ACC, AnteriorCingulateCortex
- **Memory area:** EntorhinalCortex, MammillaryBodies, BasalForebrain
- **Emotional area:** AmygdalaComplex, NucleusAccumbens, InsularCortex
- **Motor/Action area:** Cerebellum, ActionPlanner, SkillLibrary
- **Default Mode area:** DMN, SelfModel, AutobiographicMemory
- **Reward/Motivation area:** VTA, LateralHabenula, VentralPallidum
- **Arousal/Vigilance area:** LocusCoeruleus, ReticularFormation, BNST
- **Sensory Integration area:** SuperiorColliculus, Claustrum, FusiformGyrus
- **Social/Theory of Mind area:** TPJ, CollaborativeLearning, UserRelationship

CognitiveLoop becomes the tick cycle for processing within each area.

## File Summary

| New/Changed File | Est. Lines | Purpose |
|---|---|---|
| `core/kotlin_graph.py` | ~300 | Domain-agnostic episodic memory graph |
| `core/kuro_graph.py` | ~350 | Domain-agnostic pattern mining |
| `core/dual_graph.py` | ~150 | Unified graph manager |
| `core/thalamic_adapter.py` | ~150 | Input encoding -> ThalamoPC6 modalities |
| `core/cortical_area.py` | ~200 | CorticalColumn + community + activation |
| `core/response_agent.py` | ~200 | Reads activations -> CTM -> LLM output |
| `core/brain_chat.py` | ~50 changes | Rewire send() to use ThalamoPC6 |
| `production/production_planner.py` | ~30 changes | Wire new components |
| Tests (multiple files) | ~400 | Tests for all new components |

**Total new code:** ~1,800 lines
**Deletions:** 0 (everything existing stays as fallback)

## What We Keep vs Change vs Add

| Component | Status | Notes |
|---|---|---|
| ThalamoPC6 | **Keep as-is** | Already has the right math |
| CorticalColumn | **Keep as-is** | Already has 6-layer microcircuit |
| CognitiveLoop | **Keep, rewire** | Becomes per-area processing cycle |
| KotlinGraph | **Port to core/** | Generalize from Klotski |
| KuroGraph | **Port to core/** | Same generalization |
| DualGraphManager | **Port to core/** | Same |
| CTMLayer | **Extract to core/** | Use for response agent deliberation |
| 43 neuroscience modules | **Keep all** | Assign to cortical areas |
| BrainChat.send() | **Rewire** | Route through ThalamoPC6 |
| 3-layer router | **Keep as fallback** | Demote from primary |
| MicroAgentPool | **Keep** | Already approved, continues |
| MoltBook communities | **Upgrade** | Each becomes a CorticalArea |

## Dependencies

- NumPy (existing)
- NetworkX (existing, used by KotlinGraph)
- No new external dependencies required

## Risk Mitigation

1. **Backward compatibility:** 3-layer router stays as fallback. If ThalamoPC6
   path fails, system degrades to existing routing.

2. **Incremental rollout:** Each phase can be tested independently. Phase 1 is
   pure refactoring (port files). Phase 2 adds an adapter. Phase 3-4 are new
   classes. Phase 5 is wiring.

3. **No breaking changes:** All existing tests continue to pass. New functionality
   is additive. Feature flags can control which path is active.
