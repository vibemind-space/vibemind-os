# Tahlamus Brain System - Repository Structure

## Quick Navigation

- **[Core System](#core-system)** - 200+ brain modules and cognitive systems
- **[Web Server](#web-server)** - Unified FastAPI server with dashboards
- **[Production](#production)** - Production services and deployment
- **[Tests](#tests)** - 1981+ tests across 69 files
- **[Configuration](#configuration)** - Settings and environment

---

## Core System

### `core/` - Brain Modules (200+ files)

#### Neuroscience Modules (43 total, Phases C-F)

**Phase C — Original 9 modules:**
`cerebellum_module.py`, `prefrontal_cortex.py`, `hypothalamus_drives.py`, `default_mode_network.py`, `insular_cortex.py`, `superior_colliculus.py`, `entorhinal_cortex.py`, `nucleus_accumbens.py`, `anterior_cingulate.py`

**Phase D — Tier 1 (6 modules):**
`amygdala_complex.py`, `ventral_tegmental_area.py`, `locus_coeruleus.py`, `raphe_nuclei.py`, `lateral_habenula.py`, `periaqueductal_gray.py`

**Phase E — Tier 2 (9 modules):**
`claustrum.py`, `reticular_formation.py`, `basal_forebrain.py`, `septal_nuclei.py`, `inferior_olive.py`, `mammillary_bodies.py`, `bed_nucleus_stria_terminalis.py`, `parabrachial_nucleus.py`, `orbitofrontal_cortex.py`

**Phase F — Tier 3 (14 modules):**
`substantia_nigra.py`, `zona_incerta.py`, `red_nucleus.py`, `tuberomammillary_nucleus.py`, `pedunculopontine_nucleus.py`, `ventral_pallidum.py`, `nucleus_tractus_solitarius.py`, `olfactory_system.py`, `fusiform_gyrus.py`, `temporoparietal_junction.py`, `posterior_parietal_cortex.py`, `cortical_column.py`, `pineal_gland.py`, `corpus_callosum.py`

#### Radial Attention Network
- `radial_attention.py` - 5-ring network (Sensory→Pattern→Semantic→Abstract→Meta) + DualProcessRouter
- `modulation_context.py` - 29 hooks → 4 composite factors (attention, precision, FFN, threshold)
- `hebbian_plasticity.py` - Live attention bias updates
- `experience_buffer.py` - FIFO replay buffer for sleep training
- `radial_sleep_trainer.py` - 4-loss backprop during DreamMode
- `predictive_coding.py` - Prediction error + precision weighting
- `seed_encoder.py` - Thalamic 384→128 seed compression
- `sensory_preprocessor.py` - Input preprocessing for rings

#### 10 Bridges (each has State dataclass + Bridge class)
`neuromodulation_bridge.py`, `cortex_bridge.py`, `limbic_bridge.py`, `sleep_wake_bridge.py`, `motor_bridge.py`, `defense_bridge.py`, `memory_bridge.py`, `integration_bridge.py`, `visceral_bridge.py`, `social_perception_bridge.py`

Supporting: `inter_bridge_coupling.py`, `cortical_feedback.py`, `hook_coefficients.py`

#### V2 Systems (8 phases, 100 tasks)
- `agent_loop.py` - Agent FSM (IDLE/THINKING/ACTING/STOPPED)
- `sensor_systems.py` - 11 sensor/fusion modules
- `action_systems.py` - 7 action/approval modules
- `goal_management.py` - Goal hierarchy + conflict resolution
- `motivation_drives.py` - Curiosity, competence, homeostatic drives
- `safety_regulation.py` - Autonomy budget, safety governor
- `proactive_behavior.py` - Proactive task generation
- `language_center.py` - Brain language center
- `personality.py` - Personality model, emotional expression
- `dialogue_manager.py` - Conversation management
- `experience_learning.py` - Experience replay, transfer learning
- `skill_library.py` - Skill composition and refinement
- `world_model.py` - Causal + predictive world model
- `meta_cognition.py` - Self-awareness, knowledge gap detection
- `social_learning.py` - Learning from demonstration
- `self_model.py` - Autobiographic memory, value system
- `emotional_memory.py` - Emotional memory, mood, stress
- `user_relationship.py` - User model, trust, collaboration
- `resilience.py` - Graceful degradation, self-healing
- `ecosystem_intelligence.py` - Orchestrator, synergy, evolution

#### Core Routing
- `thalamo_pc_adaptive.py` - 10-modality thalamic routing with Hebbian learning
- `task_feature_router.py` - Layer 1: Feature extraction
- `conversation_path_planner.py` - Layer 2: Graph-based planning
- `decision_router.py` - Layer 3: Multi-target routing
- `hierarchical_planner.py` - Integration of all layers

#### LLM Integration
- `multi_llm_router.py` - Routes to GPT-4o, DeepSeek R1, Claude 3.5, Gemini Flash
- `brain_chat.py` - ContinuousThinkingEngine (500-thought buffer, evolutionary selection)
- `moltbook.py` - SemanticIndex (384-dim embeddings, sentence-transformers)

---

## Web Server

### `web/` - Unified FastAPI Server

- `brain_server.py` - **Main server** (port 5000): initializes all brain components, serves all dashboards
- `__init__.py` - Package init

**Routers:**
- `routers/radial.py` - SSE stream for bridges/rings/modulation at 2Hz
- `routers/cortex.py` - Cortex/thought endpoints
- `routers/introspection.py` - Brain introspection API
- `routers/oscillator.py` - Multi-band oscillator endpoints
- `routers/swarm.py` - Swarm agent endpoints
- `routers/training.py` - Training endpoints
- `routers/legacy_compat.py` - Backward-compatible endpoints

**Streams:**
- `streams/chat.py` - WebSocket chat: GPT-4o + semantic thought matching + brain state context
- `streams/consciousness.py` - Consciousness metrics stream

**Middleware:**
- `middleware/thalamic_gate.py` - Request routing through thalamic gate

**Templates:**
- `templates/unified_brain_dashboard.html` - SVG brain visualization + chat (`/brain`)
- `templates/brain_dashboard.html` - Classic dashboard (`/`)
- `templates/radial_dashboard.html` - Radial network dashboard (`/radial`)
- `templates/cognitive_loop_viz.html` - Cognitive loop SVG
- `templates/oscillator_dashboard.html` - Oscillator visualization

**Legacy (reference only):**
- `legacy/` - Old standalone servers (replaced by unified brain_server.py)

---

## Production

### `production/`
- `production_planner.py` - Production routing + dream cycle
- `unified_brain_service.py` - Legacy unified service
- `api_server.py` - Legacy REST API
- `brain_heartbeat.py` - Autonomous monitoring
- `adaptive_router.py` - Adaptive routing layer
- `layer4_endpoints.py` - Layer 4 temporal endpoints

---

## Tests

### `tests/` - 1981+ tests, 0 failures

- `test_core.py` - Core routing tests
- `test_phase7_modules.py` - Phase C neuroscience modules (219 tests)
- `test_phase_d_modules.py` - Phase D modules (99 tests)
- `test_phase_e_modules.py` - Phase E modules (103 tests)
- `test_phase_f_modules.py` - Phase F modules (84 tests)
- `test_neuromodulation_bridge.py` - Neuromod bridge (25 tests)
- `test_cortex_bridge.py` - Cortex bridge (25 tests)
- `test_limbic_bridge.py` - Limbic bridge (28 tests)
- `test_modulation_context.py` - ModulationContext (18 tests)
- `test_agent_loop.py`, `test_goal_management.py`, etc. - V2 systems
- `tests/agi/` - AGI-specific module tests
- `tests/integration/` - Integration tests
- `tests/scripts/` - Test scripts and utilities

---

## Configuration

- `configs/default.yaml` - All configuration (radial, bridges, hooks, modulation, etc.)
- `.env` - Environment variables (API keys)
- `.gitignore` - Excludes binary models, checkpoints, training data
- `Dockerfile` + `docker-compose.yml` - Docker deployment
- `requirements.txt` - Python dependencies

---

## Other Directories

- `demos/` - Demo scripts (Klotski solver, training, evolutionary optimization)
- `scripts/` - Utility scripts (cleanup, recalibration, validation)
- `training/` - Training pipeline (losses, data generators, trainers)
- `learning_engine/` - Learning engine modules
- `integrations/` - JAX/Mamba experimental integrations
- `memory_api/` - Memory storage client
- `docs/` - All documentation
