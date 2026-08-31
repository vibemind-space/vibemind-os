# Radial Attention Network — Design Document

**Date:** 2026-02-25
**Status:** Approved
**Module:** `core/radial_attention.py`, `core/hebbian_plasticity.py`, `core/radial_sleep_trainer.py`

## Motivation

Tahlamus has 43 brain modules, a 7-phase consolidation cycle, and socialization metrics — but all of it runs on **handwritten heuristics with random or fixed weights**. No module actually **learns** from experience. The CorticalColumn has 6 layers of random weights that never adapt. The routing is explicit, not learned.

This design adds a **learning core** — a Radial Attention Network that:
1. Processes signals through concentric rings of increasing abstraction
2. Learns in real-time via Hebbian plasticity (fast, biological)
3. Consolidates via backpropagation during DreamMode (slow, mathematical)
4. Uses Predictive Coding (only prediction errors propagate, not raw signals)
5. Implements Dual Process theory (System 1 fast intuition + System 2 slow deliberation)

## Core Thesis

> "One brain = one neuron. Many neurons form intelligence."

Each Tahlamus instance is a single neuron. The KlotskiCTM provides the consciousness trace, KuroGraph mines successful activation patterns, and the Radial Attention Network learns which paths through the abstraction layers lead to good outcomes. Scale comes from the network of instances (Phase 2), not from parameter count.

## Architecture

### Radial Ring Structure

```
          ┌─────────────────────────┐
          │    Ring 5: Meta (ACC)   │  "What do I know about this?"
          │  ┌───────────────────┐  │
          │  │Ring 4: Abstract   │  │  "What strategy?"
          │  │  (DLPFC + DMN)    │  │
          │  │  ┌─────────────┐  │  │
          │  │  │ Ring 3: Sem │  │  │  "Which concept?"
          │  │  │ (LAN + MTL) │  │  │
          │  │  │  ┌───────┐  │  │  │
          │  │  │  │Ring 2 │  │  │  │  "What does it mean?"
          │  │  │  │OFC+INS│  │  │  │
          │  │  │  │ ┌───┐ │  │  │  │
          │  │  │  │ │ T │ │  │  │  │  T = Thalamus (center)
          │  │  │  │ └───┘ │  │  │  │
          │  │  │  └───────┘  │  │  │
          │  │  └─────────────┘  │  │
          │  └───────────────────┘  │
          └─────────────────────────┘
```

### Ring Specifications

| Ring | Name | CTM Modules | Dim | Heads | Params | Purpose |
|------|------|-------------|-----|-------|--------|---------|
| Center | Thalamic Encoder | — | 384→128 | — | ~50K | Encode input to seed |
| 1 | Sensory | VIS+AUD+SOM | 64 | 4 | ~0.8M | Raw pattern detection |
| 2 | Pattern | OFC+INS | 128 | 4 | ~2.5M | Value + internal state |
| 3 | Semantic | LAN+MTL | 256 | 8 | ~8M | Language + memory |
| 4 | Abstract | DLPFC+DMN | 256 | 8 | ~8M | Planning + default mode |
| 5 | Meta | ACC | 128 | 4 | ~2.5M | Conflict monitoring |
| — | Projections + Gates | — | — | — | ~3.2M | Top-down + precision |
| **Total** | | | | | **~25M** | |

### RingLayer Architecture

Each ring implements:

```python
class RingLayer(nn.Module):
    def forward(self, bottom_up, top_down_prediction=None):
        # 1. Self-Attention over input
        attended = self.self_attention(bottom_up)

        # 2. Predictive Coding: only ERROR propagates
        if top_down_prediction is not None:
            error = attended - top_down_prediction
            precision = self.precision_gate(error)
            signal = error * precision
        else:
            signal = attended

        # 3. Feedforward transform
        output = self.ffn(signal)

        # 4. Residual + LayerNorm
        return self.norm(output + signal)
```

Key insight: **Only prediction errors flow between rings.** If a ring correctly predicts what the next ring will see, nothing propagates — the brain is "unsurprised." Only surprises (errors) flow upward and drive learning.

## Dual Process — System 1 + System 2

```
STIMULUS arrives
       │
       ├──→ FAST PATH (System 1, <5ms)
       │    MoltbookGraph.spreading_activation(seed)
       │    → immediate associations from knowledge graph
       │    → "intuition" / gut feeling
       │
       ├──→ SLOW PATH (System 2, ~100ms)
       │    RadialAttentionNetwork.forward(seed)
       │    → Ring 1 → Ring 2 → Ring 3 → Ring 4 → Ring 5
       │    → deep analysis with Predictive Coding
       │
       └──→ ACC (Ring 5) decides:
            conflict = |system1_result - system2_result|
            if conflict < threshold:
                return system1_result   # Fast path sufficient
            else:
                return system2_result   # Deep analysis needed
```

## Training

### A. Hebbian Live (during waking)

Every activation updates attention biases — no gradients needed:

```python
# Correlation-based Hebbian update
correlation = pre_activation.T @ post_activation
ring.attention_bias += η * correlation        # η = 0.001
ring.attention_bias *= (1 - λ)                # λ = 0.0001 decay
ring.attention_bias = clamp(bias, -2.0, 2.0)  # Prevent explosion
```

**Effect:** After many activations, each ring develops preferred attention patterns. Ring 3 (Semantic) learns which concepts co-occur. This is **short-term plasticity** — fast but shallow.

### B. Backprop Sleep Training (during DreamMode)

Full gradient-based training on collected experiences:

**Experience Buffer** collects during day:
- `input_embedding`: What came in
- `ring_activations`: What happened in each ring
- `ctm_trajectory`: KlotskiCTM consciousness trace
- `kuro_reward`: KuroGraph pattern success score
- `outcome`: Success or failure

**4-Loss Training** during sleep:

```
Loss = PC_loss + Trajectory_loss + 0.1 * Reward_loss + 0.5 * EWC_loss

PC_loss:          Ring i should predict Ring i+1's activation
Trajectory_loss:  Ring activations should match CTM consciousness trace
Reward_loss:      Paths that led to good outcomes are reinforced
EWC_loss:         Elastic Weight Consolidation prevents catastrophic forgetting
```

**Budget:** ~10 min training on RTX 3060, ~1000 experiences per day, batch 32 × 30 epochs.

### C. Training Cycle

```
         ┌──────────────────────────────────────┐
         │            AWAKE (Day)                │
         │                                       │
         │  Stimulus → RadialAttention → Result  │
         │      │                          │     │
         │      ↓                          ↓     │
         │  Hebbian Update         Experience    │
         │  (bias adjusted         Buffer        │
         │   immediately)          (collected)   │
         └──────────────┬───────────────────────┘
                        │ every 6h / when idle
                        ↓
         ┌──────────────────────────────────────┐
         │          SLEEP (DreamMode)            │
         │                                       │
         │  1. Sample from Experience Buffer     │
         │  2. Backprop with 4 losses            │
         │  3. Update EWC Fisher matrix          │
         │  4. Hebbian bias → seed new attention │
         │  5. KuroGraph mines new patterns      │
         └──────────────────────────────────────┘
```

## Integration with Existing Architecture

### Data Flow

```
User Input → BrainChat → Routing → LLM → Response
                 │                   ↑
                 ↓                   │
            Thalamus-Core ──────────┘
                 │         (radial output augments
                 ↓          LLM context)
         RadialAttention
         Ring 1→2→3→4→5
                 │
                 ├── System 1: MoltbookGraph (immediate)
                 └── System 2: Ring activations (100ms)

Background: CognitiveLoop → 9 Phases → ConsolidationCycle
                                            │
                                            ↓
                                  RadialSleepTrainer
                                  (trains in DreamMode)
```

### Connection Points

| Existing Module | Direction | Radial Component |
|----------------|-----------|------------------|
| `cognitive_loop.py` perceive | → | Ring 1 input |
| `cognitive_loop.py` appraise | → | Ring 2 input |
| `cognitive_loop.py` attend | ↔ | Ring 3 influences attention |
| `cognitive_loop.py` reason | ← | Ring 4 output |
| `cognitive_loop.py` reflect | ↔ | Ring 5 meta signal |
| `moltbook_retrieval.py` | ← | System 1 Fast Path |
| `dream_mode.py` | → | RadialSleepTrainer starts here |
| `klotski_ctm.py` | → | consciousness_trajectory = training signal |
| `kuro_graph.py` | → | pattern_score = reward signal |
| `brain_chat.py` | ← | Radial output extends LLM context |
| `anterior_cingulate.py` | ↔ | ACC = Ring 5 conflict monitor |

### New Files

```
core/
├── radial_attention.py        # RadialAttentionNetwork, RingLayer
├── hebbian_plasticity.py      # HebbianAttentionUpdate
├── radial_sleep_trainer.py    # Backprop in DreamMode
├── experience_buffer.py       # Replay buffer for experiences

tests/
├── test_radial_attention.py   # Ring architecture + forward pass
├── test_hebbian.py            # Hebbian update tests
├── test_radial_training.py    # Sleep training tests
```

### Non-Changes

All 43 neuroscience modules, routing layers, Moltbook, Consolidation, Socialization, and ForumAgent remain untouched. The Radial Network is **additive** — if it fails, everything works as before.

## Test Plan (~15 tests)

### Architecture Tests
- `test_ring_dimensions` — Input/output dimensions per ring
- `test_forward_pass_shape` — Seed in → 5 ring outputs out
- `test_predictive_coding_error` — error = bottom_up - top_down
- `test_precision_gating` — High variance → low precision
- `test_residual_connections` — Output contains input component

### Dual Process Tests
- `test_system1_fast_path` — Spreading activation < 5ms
- `test_system2_slow_path` — Ring forward < 200ms on CPU
- `test_acc_conflict_high` — High conflict → System 2 wins
- `test_acc_conflict_low` — Low conflict → System 1 sufficient

### Hebbian Tests
- `test_hebbian_strengthens` — Correlated neurons → bias increases
- `test_hebbian_decay` — Inactive connections → bias decreases
- `test_hebbian_clamp` — Bias stays in [-2, 2]

### Sleep Training Tests
- `test_experience_buffer_fifo` — Buffer fill + overflow
- `test_backprop_loss_decreases` — Loss drops over epochs
- `test_ewc_prevents_forgetting` — Old tasks preserved after new training

## Intelligence Impact

| Capability | Before | After |
|------------|--------|-------|
| Fluid Reasoning (Gf) | ⚠️ Pattern matching | ✅ Learned abstractions in Ring 3-4 |
| Self-Monitoring | ⚠️ Shallow | ✅ Ring 5 (ACC) with learned precision |
| Learning & Adaptation | ⚠️ No model update | ✅ Hebbian live + Backprop sleep |
| Creative Synthesis | ⚠️ Only mutation | ✅ Ring 4 (DMN) generates in default mode |

## What Still Requires Phase 2

- **Causal understanding** — Rings learn correlations, not causation
- **True creativity** — Diffusion sampling for generation outside training distribution
- **Grounding** — Connection to physical reality via BRIDGE tasks
- **Deep Theory of Mind** — Multi-agent experience from neuron-to-neuron communication
- **Multi-neuron network** — Federated learning between Tahlamus instances

## Hardware Requirements

- **Inference:** ~100MB VRAM, <200ms per forward pass
- **Sleep Training:** ~2GB VRAM, ~10 min per training cycle
- **Minimum:** Gaming GPU (RTX 3060, 8GB VRAM)
- **Recommended:** RTX 3060-4070, 8-12GB VRAM

## Parameter Budget

| Component | Parameters |
|-----------|-----------|
| Thalamic Encoder | ~50K |
| Ring 1 (Sensory) | ~0.8M |
| Ring 2 (Pattern) | ~2.5M |
| Ring 3 (Semantic) | ~8M |
| Ring 4 (Abstract) | ~8M |
| Ring 5 (Meta) | ~2.5M |
| Top-Down Projections | ~1.5M |
| Precision Gates | ~0.5M |
| Hebbian Bias Buffers | ~1.2M |
| **Total** | **~25M** |
