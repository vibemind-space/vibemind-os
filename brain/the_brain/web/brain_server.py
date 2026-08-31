"""
The Brain Nervous System — Unified FastAPI Server.

Replaces the old Flask micro-service sprawl with a single ASGI app.
All core module imports are lazy (inside _init_production_modules) so the
server can start — and be tested — without heavyweight dependencies.
"""

from __future__ import annotations

import asyncio
import os
import time
from collections import deque
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_WEB_DIR = Path(__file__).resolve().parent
_TEMPLATE_DIR = _WEB_DIR / "templates"
_STATIC_DIR = _WEB_DIR / "static"
_PROJECT_ROOT = _WEB_DIR.parent

# Load .env from project root (API keys, config flags)
try:
    from dotenv import load_dotenv
    load_dotenv(_PROJECT_ROOT / ".env")
except ImportError:
    pass

# Jinja2 templates — shared across routers via app.state.templates
templates = Jinja2Templates(directory=str(_TEMPLATE_DIR))

# ---------------------------------------------------------------------------
# Boot timestamp (set once at import time so uptime is always relative)
# ---------------------------------------------------------------------------
_BOOT_TIME: float = time.time()


# ---------------------------------------------------------------------------
# State initialisation helpers
# ---------------------------------------------------------------------------

def _init_brain_state(state: Any, testing: bool = False) -> None:
    """Attach every expected attribute to *state* so later code can always
    read ``request.app.state.<attr>`` without AttributeError."""

    # Single brain / chat instances
    state.brain_chat = None
    state.continuous_thinking = None
    state.thought_radial_bridge = None
    state.thought_jury = None
    state.outcome_tracker = None

    # Moltbook
    state.moltbook_store = None
    state.moltbook_graph = None
    state.moltbook_agents: dict = {}

    # Oscillator / temporal
    state.oscillator = None
    state.checkpoint_manager = None

    # Routing / monitoring
    state.meta_router = None
    state.brain_monitor = None
    state.strategy_lib = None
    state.live_monitor = None
    state.path_planner = None
    state.llm_router = None
    state.frequency_controller = None

    # Swarm
    state.swarm_orchestrator = None
    state.swarm_logs: list = []

    # Shared mutable containers
    state.oscillator_history: list = []
    state.chat_history: list = []
    state.training_state: dict = {
        "klotski": {
            "status": "idle",
            "epoch": 0,
            "loss": 0.0,
            "agents": {},
        },
        "evolutionary": {
            "status": "idle",
            "generation": 0,
            "best_fitness": 0.0,
            "positions": [],
            "metrics": {},
            "messages": deque(maxlen=100),
        },
    }

    # Agent loop (set by ProductionPlanner or externally)
    state.agent_loop = None

    # Thalamic rewiring
    state.thalamic_adapter = None
    state.cortical_areas: list = []
    state.kotlin_graph = None
    state.dual_graph = None
    state.response_agent = None
    state.memory_consolidator = None
    state.diary_drain = None
    state.socialization_metrics = None

    state._rowboat_data = None
    state._cached_clusters = None
    state._cached_thought_clusters = None

    state.testing = testing


def _loops_enabled() -> bool:
    """Master-Gate für die CPU-gebundenen Hintergrund-Loops (Contention-Fix
    2026-06-08). Default an (=heutiges Single-Process-Verhalten). brain-core
    (HTTP) setzt BRAIN_BACKGROUND_LOOPS=0 → die Loop-OBJEKTE werden weiter
    konstruiert (state.* bleibt gefüllt, Routen funktionieren), nur ihr
    .start()-Thread wird übersprungen. Der separate brain-loops-Worker-Prozess
    setzt =1 und fährt die Loops in eigenem Prozess/GIL → der async HTTP-Server
    verhungert nicht mehr. Muster wie is_learner()-Gating der Writer-Threads."""
    return os.environ.get("BRAIN_BACKGROUND_LOOPS", "1") not in ("0", "false", "False")


def _init_production_modules(state: Any) -> None:  # pragma: no cover
    """Best-effort lazy loading of every production module.

    Each import is individually wrapped so one broken dependency can never
    prevent the rest of the system from starting.
    """

    # --- MoltbookStore (must be first — downstream modules depend on it) ---
    try:
        from core.moltbook import MoltbookStore
        state.moltbook_store = MoltbookStore()
        dim = state.moltbook_store.semantic_index._dim
        mode = "sentence-transformers" if state.moltbook_store.semantic_index._use_transformer else "hash"
        print(f"  [OK] MoltbookStore (embeddings={dim}d, mode={mode})")
        # Load persisted knowledge from disk
        try:
            loaded = state.moltbook_store.load_from_disk()
            if loaded > 0:
                print(f"  [OK] Loaded {loaded} persisted knowledge entries")
        except Exception as e2:
            print(f"  [WARN] Knowledge load failed: {e2}")
    except Exception as e:
        print(f"  [WARN] MoltbookStore failed: {e}")

    # --- MetaRouter ---
    try:
        from core.meta_router import MetaRouter
        state.meta_router = MetaRouter()
    except Exception:
        pass

    # --- BrainActivityMonitor ---
    try:
        from core.brain_monitor import BrainActivityMonitor
        state.brain_monitor = BrainActivityMonitor()
    except Exception:
        pass

    # --- StrategyLibrary ---
    try:
        from core.strategy_library import StrategyLibrary
        state.strategy_lib = StrategyLibrary()
    except Exception:
        pass

    # --- LiveBrainMonitor ---
    try:
        from core.live_brain_monitor import LiveBrainMonitor
        state.live_monitor = LiveBrainMonitor()
    except Exception:
        pass

    # --- ConversationPathPlanner ---
    try:
        from core.conversation_path_planner import ConversationPathPlanner
        state.path_planner = ConversationPathPlanner()
    except Exception:
        pass

    # --- MultiLLMRouter ---
    try:
        from core.multi_llm_router import MultiLLMRouter
        state.llm_router = MultiLLMRouter()
    except Exception:
        pass

    # --- BrainFrequencyController ---
    try:
        from core.brain_frequency_controller import BrainFrequencyController
        state.frequency_controller = BrainFrequencyController()
    except Exception:
        pass

    # --- CheckpointManager ---
    try:
        from core.oscillator_checkpoint import CheckpointManager
        state.checkpoint_manager = CheckpointManager()
    except Exception:
        pass

    # --- SwarmOrchestrator ---
    try:
        from production.brain_swarm_orchestrator import BrainSwarmOrchestrator
        state.swarm_orchestrator = BrainSwarmOrchestrator()
    except Exception:
        pass

    # --- BrainChat + ContinuousThinkingEngine ---
    try:
        from core.brain_chat import (
            BrainChat, ContinuousThinkingEngine, MicroAgentPool,
        )

        # ContinuousThinkingEngine: brain ALWAYS thinks — aber das interval_ms war
        # hartkodiert 5000ms. Der radial_tick (radiales Netz + ~13 Qdrant-Collection-
        # Queries pro Tick) ist CPU-gebunden, haelt den GIL → bei 5s effektiv
        # dauer-Last → der async HTTP-Server (Single-Process) verhungert (root-caused
        # 2026-06-08: auch mit BRAIN_ROLE=inference/Writer aus blieb CPU 100%).
        # Env-konfigurierbar, Default 30000ms (Brain denkt weiter, nur seltener →
        # HTTP atmet). BRAIN_THINK_INTERVAL_MS=0 schaltet das Ticking ganz ab.
        moltbook_store = state.moltbook_store  # may be None
        _think_ms = int(os.environ.get("BRAIN_THINK_INTERVAL_MS", "30000"))
        cte = ContinuousThinkingEngine(
            moltbook=moltbook_store,
            interval_ms=_think_ms,
        )
        state.continuous_thinking = cte

        # Routing layers (best-effort)
        l1_router = l2_planner = l3_router = None
        try:
            from core.task_feature_router import TaskFeatureRouter
            l1_router = TaskFeatureRouter()
        except Exception:
            pass
        try:
            from core.conversation_path_planner import ConversationPathPlanner
            l2_planner = ConversationPathPlanner()
        except Exception:
            pass
        try:
            from core.decision_router import DecisionRouter
            l3_router = DecisionRouter()
        except Exception:
            pass

        # InternalMonologue
        internal_monologue = None
        try:
            from core.moltbook_thinker import InternalMonologue
            internal_monologue = InternalMonologue(moltbook=moltbook_store)
        except Exception:
            pass

        # TalkerModule
        talker = None
        try:
            from core.moltbook_talker import TalkerModule
            talker = TalkerModule()
        except Exception:
            pass

        # KnowledgeAugmentor
        knowledge_augmentor = None
        try:
            from core.moltbook_pipeline import InputAnalyzer, ThinkingBudget, KnowledgeAugmentor
            knowledge_augmentor = KnowledgeAugmentor(moltbook=moltbook_store)
        except Exception:
            pass

        # InputAnalyzer + ThinkingBudget
        input_analyzer = None
        thinking_budget = None
        try:
            from core.moltbook_pipeline import InputAnalyzer, ThinkingBudget
            input_analyzer = InputAnalyzer()
            thinking_budget = ThinkingBudget()
        except Exception:
            pass

        # BrainChat: THE central chat entry point
        state.brain_chat = BrainChat(
            task_feature_router=l1_router,
            conversation_path_planner=l2_planner,
            decision_router=l3_router,
            continuous_thinking=cte,
            internal_monologue=internal_monologue,
            knowledge_augmentor=knowledge_augmentor,
            talker=talker,
            moltbook=moltbook_store,
            input_analyzer=input_analyzer,
            thinking_budget=thinking_budget,
        )
        print("  [OK] BrainChat + ContinuousThinkingEngine")

        # MicroAgentPool: LLM-powered knowledge refinement
        pool = None
        try:
            pool = MicroAgentPool(llm_router=state.llm_router)
            state.brain_chat.set_micro_agent_pool(pool)
            state.micro_agent_pool = pool
            n_agents = len(pool._agents) if hasattr(pool, '_agents') else '?'
            has_router = pool._router is not None
            print(f"  [OK] MicroAgentPool ({n_agents} agents, router={'YES' if has_router else 'NO'})")
        except Exception as e:
            state.micro_agent_pool = None
            state.micro_agent_pool_error = str(e)
            import traceback
            print(f"  [FAIL] MicroAgentPool init: {e}")
            traceback.print_exc()

        # QdrantKG: unified knowledge graph (semantic-only for now).
        # Best-effort — if Qdrant is unreachable, Brain still runs.
        state.qdrant_kg = None
        try:
            from core.qdrant_kg import QdrantKG, COLLECTIONS
            kg = QdrantKG()
            kg.ensure_collections()
            kg.start()
            # Wire CTE callback so every new thought flows into the graph
            cte.on_thought(kg.make_thought_callback())
            # Wire BrainChat so every response is upserted + edge-linked
            state.brain_chat.set_qdrant_kg(kg)
            state.qdrant_kg = kg
            coll_names = ", ".join(COLLECTIONS.values())
            print(f"  [OK] QdrantKG connected (5 cognitive collections: {coll_names}; CTE->KG + BrainChat->KG wired)")

            # MCMP graph gardener: random walks + decay + prune on brain-episodic
            # and brain-semantic. Keeps the graph self-curating.
            try:
                from core.mcmp_gardener import MCMPGardener
                gardener = MCMPGardener(kg)
                state.mcmp_gardener = gardener
                if _loops_enabled():
                    gardener.start()
                    print("  [OK] MCMP gardener started (pheromone walks on episodic+semantic)")
                else:
                    print("  [SKIP] MCMP gardener (BRAIN_BACKGROUND_LOOPS=0)")
            except Exception as e:
                state.mcmp_gardener = None
                print(f"  [WARN] MCMP gardener failed to start: {e}")

            # Phase 8.B: DecisionGraph — Neo4j-backed persistent
            # cluster/plan/dispatch history for the Cytoscape UI.
            state.decision_graph = None
            try:
                from core.decision_graph import DecisionGraph
                dg = DecisionGraph()
                state.decision_graph = dg
                if dg.is_connected():
                    print(f"  [OK] DecisionGraph connected (Neo4j {dg.stats().get('uri','?')})")
                else:
                    print(f"  [WARN] DecisionGraph disconnected: {dg._connect_error}")
            except Exception as e:
                state.decision_graph_error = str(e)
                print(f"  [WARN] DecisionGraph init failed: {e}")

            # Phase 9.0.4: ToolCallApprovalGate — risk-tagging + post-hoc
            # approval tracker for sensitive MCP tool-calls. Named uniquely
            # to avoid collision with AgentLoop's older `ApprovalGate`.
            state.approval_gate = None
            try:
                from core.approval_gate import ToolCallApprovalGate
                state.approval_gate = ToolCallApprovalGate(decision_graph=state.decision_graph)
                print("  [OK] ToolCallApprovalGate ready (high-risk tool-calls flagged)")
            except Exception as e:
                state.approval_gate_error = str(e)
                print(f"  [WARN] ToolCallApprovalGate init failed: {e}")

            # Phase 8.1: ClusterEngine — per-cluster activation aggregator
            # over thought-evolution UMAP+DBSCAN. Drives Self-Steerer (8.3)
            # and Galaxy UI (8.2).
            state.cluster_engine = None
            try:
                from core.cluster_engine import ClusterEngine
                ce = ClusterEngine(
                    brain_chat=state.brain_chat,
                    kg=kg,
                    decision_graph=state.decision_graph,
                )
                state.cluster_engine = ce
                if _loops_enabled():
                    ce.start()
                    print("  [OK] ClusterEngine started (cluster activation, 60s tick)")
                else:
                    print("  [SKIP] ClusterEngine (BRAIN_BACKGROUND_LOOPS=0)")
            except Exception as e:
                state.cluster_engine_error = str(e)
                print(f"  [WARN] ClusterEngine failed to start: {e}")

            # Phase 8.3: SelfSteerer — autonomous capability dispatch when
            # cluster activations cross threshold. Closes the loop:
            # cluster activation → execute → result back as thought.
            state.self_steerer = None
            try:
                if state.cluster_engine is not None:
                    from core.self_steerer import SelfSteerer
                    ss = SelfSteerer(
                        cluster_engine=state.cluster_engine,
                        capability_router=getattr(state, "capability_router", None),
                        brain_chat=state.brain_chat,
                        decision_graph=state.decision_graph,
                    )
                    state.self_steerer = ss
                    if _loops_enabled():
                        ss.start()
                        print(
                            f"  [OK] SelfSteerer started "
                            f"({ss.stats_dict()['mappings_loaded']} cluster->capability mappings, "
                            f"30s tick)"
                        )
                    else:
                        print("  [SKIP] SelfSteerer (BRAIN_BACKGROUND_LOOPS=0)")
            except Exception as e:
                state.self_steerer_error = str(e)
                print(f"  [WARN] SelfSteerer failed to start: {e}")
        except Exception as e:
            state.qdrant_kg = None
            state.qdrant_kg_error = str(e)
            print(f"  [WARN] QdrantKG unavailable: {e}")

        # SubagentDispatcher: Phase E. Brain dispatches subtasks to Claude/Groq.
        state.subagent_dispatcher = None
        try:
            from core.subagent_dispatcher import SubagentDispatcher
            state.subagent_dispatcher = SubagentDispatcher(state.llm_router)
            n_router = "YES" if state.llm_router else "NO"
            print(f"  [OK] SubagentDispatcher ready (router={n_router}, tools=claude_subagent, groq_subagent)")
        except Exception as e:
            state.subagent_dispatcher_error = str(e)
            print(f"  [WARN] SubagentDispatcher unavailable: {e}")

        # ── Phase C4: Tier boundary ──────────────────────────────────────
        # The 6 periodic engines below WRITE to Qdrant / disk on a timer
        # (Consolidation, Snapshot, DiscourseAggregator, MirofishKGSync,
        # SelfAwarenessWatcher, DiscourseMemoryConsolidator). Only one
        # instance may own these writes or N replicas corrupt shared state.
        # config.is_learner() is True for mono (default → unchanged) and
        # learner; False only for inference replicas. The engine OBJECTS are
        # still constructed (so app.state.* stays populated and the rest of
        # the code keeps working) — only their .start() background thread is
        # gated, i.e. an inference replica simply never writes.
        try:
            from core import config as _cfg
            _tier_writers_enabled = _cfg.is_learner()
            _role = _cfg.brain_role()
        except Exception:
            _tier_writers_enabled = True   # fail-safe = legacy behaviour
            _role = "mono"
        if not _tier_writers_enabled:
            print(f"  [TIER] BRAIN_ROLE={_role} — periodic writer threads "
                  f"(consolidation/snapshot/discourse/mirofish/self-aware) "
                  f"DISABLED (inference replica: read-only).")

        # ConsolidationEngine: Phase L. Episodic -> Semantic.
        state.consolidation_engine = None
        try:
            from core.consolidation_engine import ConsolidationEngine
            ce = ConsolidationEngine(kg, state.subagent_dispatcher)
            if _tier_writers_enabled:
                ce.start()
            state.consolidation_engine = ce
            _st = "started" if _tier_writers_enabled else "constructed (writer disabled: inference)"
            print(f"  [OK] ConsolidationEngine {_st} (DBSCAN + groq_subagent synth, every 5min)")
        except Exception as e:
            state.consolidation_engine_error = str(e)
            print(f"  [WARN] ConsolidationEngine unavailable: {e}")

        # SnapshotEngine: Phase M. Periodic Brain self-state -> brain-state.
        state.snapshot_engine = None
        try:
            from core.snapshot_engine import SnapshotEngine
            import requests as _rq
            _base = "http://127.0.0.1:5000"

            def _bridges_provider():
                try:
                    return _rq.get(f"{_base}/api/bridges", timeout=2).json()
                except Exception:
                    return {}

            def _state_provider():
                try:
                    return _rq.get(f"{_base}/api/brain/state", timeout=2).json()
                except Exception:
                    return {}

            def _modulation_provider():
                try:
                    return _rq.get(f"{_base}/api/modulation", timeout=2).json()
                except Exception:
                    return {}

            se = SnapshotEngine(
                kg,
                bridges_provider=_bridges_provider,
                state_provider=_state_provider,
                modulation_provider=_modulation_provider,
            )
            if _tier_writers_enabled:
                se.start()
            state.snapshot_engine = se
            _st = "started" if _tier_writers_enabled else "constructed (writer disabled: inference)"
            print(f"  [OK] SnapshotEngine {_st} (every 5min -> brain-state)")
        except Exception as e:
            state.snapshot_engine_error = str(e)
            print(f"  [WARN] SnapshotEngine unavailable: {e}")

        # Standalone MinibookClient (when agent_loop isn't used).
        state.minibook_client = None
        try:
            from core.minibook_client import MinibookClient
            import yaml as _yaml
            _cfg_path = Path(__file__).resolve().parent.parent / "configs" / "default.yaml"
            _mb_cfg = {}
            try:
                with open(_cfg_path, "r", encoding="utf-8") as _f:
                    _full = _yaml.safe_load(_f) or {}
                _mb_cfg = (_full.get("minibook") or {})
            except Exception:
                pass
            if _mb_cfg.get("enabled", True):
                mb_client = MinibookClient(
                    base_url=_mb_cfg.get("base_url", "http://127.0.0.1:3480"),
                    api_key=_mb_cfg.get("api_key", ""),
                    agent_name=_mb_cfg.get("agent_name", "Brain"),
                )
                state.minibook_client = mb_client
                print(f"  [OK] MinibookClient ready ({_mb_cfg.get('base_url')})")
        except Exception as e:
            state.minibook_client_error = str(e)
            print(f"  [WARN] MinibookClient unavailable: {e}")

        # IdeasClient: Phase O.1. Brain <-> Ideas-Space HTTP wrapper.
        state.ideas_client = None
        try:
            from core.ideas_client import IdeasClient
            ic = IdeasClient()
            h = ic.health()
            state.ideas_client = ic
            if ic.is_online:
                print(f"  [OK] IdeasClient ready ({ic.base_url}, "
                      f"{h.get('idea_count', '?')} ideas)")
            else:
                print(f"  [WARN] IdeasClient initialised but offline ({ic.base_url})")
            # Q.5 — wire into BrainChat for reward routing
            if state.brain_chat is not None and hasattr(state.brain_chat, "set_ideas_client"):
                state.brain_chat.set_ideas_client(ic)
        except Exception as e:
            state.ideas_client_error = str(e)
            print(f"  [WARN] IdeasClient unavailable: {e}")

        # DiscourseEngine: Phase R.3 + R+.1 (three-mode). Idle-loop +
        # intent-mode (sync) + response-tick (background-loop).
        state.discourse_engine = None
        try:
            from core.discourse_engine import DiscourseEngine
            de = DiscourseEngine(kg, dispatcher=state.subagent_dispatcher)
            state.discourse_engine = de
            if _loops_enabled():
                de.start()
            else:
                print("  [SKIP] DiscourseEngine loop (BRAIN_BACKGROUND_LOOPS=0)")
            # R+.2 wire into BrainChat for response-queue (post-hoc agent
            # assessment of every Brain response).
            if state.brain_chat is not None and hasattr(state.brain_chat, "set_discourse_engine"):
                state.brain_chat.set_discourse_engine(de)
            print("  [OK] DiscourseEngine started "
                  "(idle 30s + response queue + intent on-demand)")
        except Exception as e:
            state.discourse_engine_error = str(e)
            print(f"  [WARN] DiscourseEngine unavailable: {e}")

        # DiscourseAggregator: Phase R.4. Every 3h — condense tweets into
        # Topic/Finding/Decision nodes via groq_subagent.
        state.discourse_aggregator = None
        try:
            from core.discourse_aggregator import DiscourseAggregator
            agg = DiscourseAggregator(
                kg=kg,
                dispatcher=state.subagent_dispatcher,
                cte=state.continuous_thinking,
            )
            if _tier_writers_enabled:
                agg.start()
            state.discourse_aggregator = agg
            _st = "started" if _tier_writers_enabled else "constructed (writer disabled: inference)"
            print(f"  [OK] DiscourseAggregator {_st} (every 3h, groq+md+kg)")
        except Exception as e:
            state.discourse_aggregator_error = str(e)
            print(f"  [WARN] DiscourseAggregator unavailable: {e}")

        # MirofishKGSync: Phase R.6. Mirror Mirofish Neo4j into Brain's
        # `mirofish-kg` Qdrant collection every 5min, read-only.
        state.mirofish_kg_sync = None
        try:
            from core.mirofish_kg_sync import MirofishKGSync
            mfs = MirofishKGSync(kg)
            if _tier_writers_enabled:
                mfs.start()
            state.mirofish_kg_sync = mfs
            _st = "started" if _tier_writers_enabled else "constructed (writer disabled: inference)"
            print(f"  [OK] MirofishKGSync {_st} (Neo4j -> mirofish-kg, 5min)")
        except Exception as e:
            state.mirofish_kg_sync_error = str(e)
            print(f"  [WARN] MirofishKGSync unavailable: {e}")

        # Phase S.3: FungusClient — semantic code-search backend for the
        # DiscourseEngine query-round resolver. Lazy-loads the persistent
        # FAISS index built by build_vibemind_index.py. Defaults to CPU.
        state.fungus_client = None
        try:
            from core.fungus_client import FungusClient
            fc = FungusClient()
            state.fungus_client = fc
            if fc.is_online:
                # Wire into DiscourseEngine if it's running
                de = getattr(state, "discourse_engine", None)
                if de is not None and hasattr(de, "set_fungus_client"):
                    de.set_fungus_client(fc)
                print(f"  [OK] FungusClient online ({fc.stats_dict().get('doc_count')} docs)")
            else:
                print(f"  [WARN] FungusClient offline: {fc.error}")
        except Exception as e:
            state.fungus_client_error = str(e)
            print(f"  [WARN] FungusClient init failed: {e}")

        # Phase 1: CapabilityRouter — narrows intent dispatches from broadcast
        # to a focused agent subset based on data/capabilities.yaml. Falls
        # back to broadcast on no-match (existing behaviour preserved).
        state.capability_router = None
        try:
            from core.capability_router import CapabilityRouter
            from pathlib import Path as _P
            _brain_dir = _P(__file__).resolve().parent.parent
            cap_path = _brain_dir / "data" / "capabilities.yaml"
            cr = CapabilityRouter(cap_path)
            state.capability_router = cr
            # Phase 8.3 — inject router into SelfSteerer (init order: SelfSteerer
            # is built before CapabilityRouter, so we backfill here).
            ss = getattr(state, "self_steerer", None)
            if ss is not None and hasattr(ss, "set_capability_router"):
                ss.set_capability_router(cr)
            if cr.stats_dict().get("registry_size", 0) > 0:
                de = getattr(state, "discourse_engine", None)
                if de is not None and hasattr(de, "set_capability_router"):
                    de.set_capability_router(cr)
                # Phase 2 — wire FungusClient embedder for semantic fallback.
                # Reuses the already-loaded sentence-transformer (no second
                # 1.2 GB model loaded). Falls back to regex-only if fungus
                # is offline.
                fc = getattr(state, "fungus_client", None)
                if fc is not None and getattr(fc, "is_online", False):
                    try:
                        cr.set_embedder(fc)
                    except Exception as embed_err:
                        print(f"  [WARN] CapabilityRouter semantic wiring failed: {embed_err}")
                # Phase 1.5 — validate execution_targets at startup so
                # registry-rot (typo'd module path, missing function) is
                # visible immediately, not on first user-triggered call.
                try:
                    # Phase 11.U.E — use multi-kind build_executor so
                    # `supabase:`, `http:`, `openfang:` etc. don't get
                    # flagged as broken (the legacy check only handled
                    # `direct:`).
                    from core.capability_targets import build_executor
                    direct_caps = [
                        c for c in cr.list_capabilities()
                        if c.get("has_execution_target")
                    ]
                    bad = []
                    for c in direct_caps:
                        cap_meta = next(
                            (e for e in cr._capabilities if e.capability == c["capability"]),
                            None,
                        )
                        if cap_meta and cap_meta.execution_target:
                            try:
                                exe = build_executor(cap_meta.execution_target)
                                # is_resolvable only meaningful for direct:
                                # — remote kinds return True unconditionally
                                if not exe.is_resolvable():
                                    bad.append(
                                        f"{c['capability']} -> {cap_meta.execution_target}"
                                    )
                            except Exception as exe_err:
                                bad.append(f"{c['capability']}: {exe_err}")
                    if bad:
                        print(
                            f"  [WARN] {len(bad)} unresolvable execution_target(s): "
                            + "; ".join(bad)
                        )
                    else:
                        direct_n = len(direct_caps)
                        print(
                            f"  [OK] CapabilityRouter loaded "
                            f"({cr.stats_dict()['registry_size']} capabilities, "
                            f"{direct_n} direct-execution)"
                        )
                except Exception as exe_err:
                    print(
                        f"  [OK] CapabilityRouter loaded "
                        f"({cr.stats_dict()['registry_size']} capabilities); "
                        f"could not validate executors: {exe_err}"
                    )
            else:
                print(
                    f"  [WARN] CapabilityRouter loaded with 0 capabilities "
                    f"(check {cap_path})"
                )
        except Exception as e:
            state.capability_router_error = str(e)
            print(f"  [WARN] CapabilityRouter init failed: {e}")

        # Phase 3: CapabilityValidator — post-execution sanity check for
        # direct-execution capabilities. Wired into DiscourseEngine; runs
        # only when a capability has a `validator` block in YAML.
        state.capability_validator = None
        try:
            from core.capability_validator import CapabilityValidator
            cv = CapabilityValidator()
            state.capability_validator = cv
            de = getattr(state, "discourse_engine", None)
            if de is not None and hasattr(de, "set_validator"):
                de.set_validator(cv)
            print("  [OK] CapabilityValidator wired (rule + agent kinds available)")
        except Exception as e:
            state.capability_validator_error = str(e)
            print(f"  [WARN] CapabilityValidator init failed: {e}")

        # Phase 6: Multi-hop Plan Executor — advisor + planner + executor +
        # synthesizer. Wired into BrainChat so connective intents become
        # multi-hop DAGs instead of single-hop routes.
        state.multihop_advisor = None
        state.multihop_planner = None
        state.plan_executor = None
        state.final_synthesizer = None
        try:
            from core.multihop_advisor import MultiHopAdvisor
            from core.planner_llm import PlannerLLM
            from core.plan_executor import PlanExecutor
            from core.final_synthesizer import FinalSynthesizer
            adv = MultiHopAdvisor()
            pl = PlannerLLM(
                dispatcher=getattr(state, "subagent_dispatcher", None),
                capability_router=getattr(state, "capability_router", None),
            )
            pe = PlanExecutor(
                capability_router=getattr(state, "capability_router", None),
                validator=getattr(state, "capability_validator", None),
                dispatcher=getattr(state, "subagent_dispatcher", None),
                kg=getattr(state, "qdrant_kg", None),
            )
            # Phase 6.14.2 — wire DiscourseEngine for plan-time pause/resume
            de_for_plan = getattr(state, "discourse_engine", None)
            if de_for_plan is not None and hasattr(pe, "attach_discourse_engine"):
                pe.attach_discourse_engine(de_for_plan)
            # Phase 7.5 — wire CTE so plan completions/rewards seed the thought stream
            cte_for_events = getattr(state, "continuous_thinking", None)
            if cte_for_events is not None:
                if hasattr(pe, "attach_continuous_thinking"):
                    pe.attach_continuous_thinking(cte_for_events)
                if de_for_plan is not None and hasattr(cte_for_events, "set_discourse_engine_ref"):
                    cte_for_events.set_discourse_engine_ref(de_for_plan)
            # Phase 8.B — wire DecisionGraph so plans/hops are persisted in Neo4j
            dg_for_plan = getattr(state, "decision_graph", None)
            if dg_for_plan is not None and hasattr(pe, "attach_decision_graph"):
                pe.attach_decision_graph(dg_for_plan)
            syn = FinalSynthesizer(dispatcher=getattr(state, "subagent_dispatcher", None))
            state.multihop_advisor = adv
            state.multihop_planner = pl
            state.plan_executor = pe
            state.final_synthesizer = syn
            # Wire into BrainChat so /api/brain/chat goes through it
            bc = getattr(state, "brain_chat", None)
            if bc is not None and hasattr(bc, "set_multihop"):
                bc.set_multihop(advisor=adv, planner=pl, executor=pe, synthesizer=syn)
            print("  [OK] MultiHopExecutor wired (advisor + planner + executor + synth)")
        except Exception as e:
            state.multihop_error = str(e)
            print(f"  [WARN] MultiHopExecutor init failed: {e}")

        # Phase 5: CapabilityCurator — telemetry recorder + cluster-based
        # suggestion generator over no-match intents. Wired into
        # DiscourseEngine so every routing decision is logged.
        state.capability_curator = None
        try:
            from core.capability_curator import CapabilityCurator
            from pathlib import Path as _P2
            _brain_dir2 = _P2(__file__).resolve().parent.parent
            cap_path2 = _brain_dir2 / "data" / "capabilities.yaml"
            cur = CapabilityCurator(
                registry_path=cap_path2,
                embedder=getattr(state, "fungus_client", None),
                capability_router=getattr(state, "capability_router", None),
            )
            state.capability_curator = cur
            de2 = getattr(state, "discourse_engine", None)
            if de2 is not None and hasattr(de2, "set_curator"):
                de2.set_curator(cur)
            # Phase 7.5 — wire CTE so cluster suggestions seed thought stream
            cte_for_curator = getattr(state, "continuous_thinking", None)
            if cte_for_curator is not None and hasattr(cur, "attach_continuous_thinking"):
                cur.attach_continuous_thinking(cte_for_curator)
            cur_stats = cur.stats_dict()
            print(
                f"  [OK] CapabilityCurator wired "
                f"(loaded {cur_stats['intents_logged']} historical intents, "
                f"{cur_stats['no_match_logged']} no-matches)"
            )
        except Exception as e:
            state.capability_curator_error = str(e)
            print(f"  [WARN] CapabilityCurator init failed: {e}")

        # Phase S.4: SelfAwarenessWatcher — periodic re-seed of architecture
        # substrate when source files change.
        state.self_awareness_watcher = None
        try:
            from core.self_awareness_watcher import SelfAwarenessWatcher
            saw = SelfAwarenessWatcher(kg)
            if _tier_writers_enabled:
                saw.start()
            state.self_awareness_watcher = saw
            _st = "started" if _tier_writers_enabled else "constructed (writer disabled: inference)"
            print(f"  [OK] SelfAwarenessWatcher {_st} (1h tick, hash-based reseed)")
        except Exception as e:
            state.self_awareness_watcher_error = str(e)
            print(f"  [WARN] SelfAwarenessWatcher unavailable: {e}")

        # Phase S.5: DiscourseMemoryConsolidator — cross-session theme
        # detection over aggregated-kg topics. 6h tick, DBSCAN-cluster +
        # groq_subagent synthesis into meta_topic nodes.
        state.discourse_memory_consolidator = None
        try:
            from core.discourse_memory_consolidator import DiscourseMemoryConsolidator
            dmc = DiscourseMemoryConsolidator(kg, dispatcher=state.subagent_dispatcher)
            if _tier_writers_enabled:
                dmc.start()
            state.discourse_memory_consolidator = dmc
            # Wire into BrainChat so self-queries can recall historical memory.
            if state.brain_chat is not None and hasattr(
                state.brain_chat, "set_discourse_memory_consolidator"
            ):
                state.brain_chat.set_discourse_memory_consolidator(dmc)
            _st = "started" if _tier_writers_enabled else "constructed (writer disabled: inference)"
            print(f"  [OK] DiscourseMemoryConsolidator {_st} (6h tick, cross-session meta_topics)")
        except Exception as e:
            state.discourse_memory_consolidator_error = str(e)
            print(f"  [WARN] DiscourseMemoryConsolidator unavailable: {e}")

        # AutoDispatcher: Phase F.4. BrainChat -> Minibook on @mentions.
        state.auto_dispatcher = None
        try:
            from core.auto_dispatcher import AutoDispatcher

            def _mb_provider():
                # Prefer standalone client; fall back to agent_loop's client.
                mb = getattr(state, "minibook_client", None)
                if mb is not None:
                    return mb
                al = getattr(state, "agent_loop", None)
                if al is None:
                    return None
                return getattr(al, "minibook_client", None)

            def _ideas_provider():
                return getattr(state, "ideas_client", None)

            ad = AutoDispatcher(
                minibook_client_provider=_mb_provider,
                ideas_client_provider=_ideas_provider,
            )
            if state.brain_chat is not None:
                state.brain_chat.set_auto_dispatcher(ad)
            state.auto_dispatcher = ad
            print(
                "  [OK] AutoDispatcher wired "
                "(@vibemind_ideas -> local Ideas HTTP, others -> Minibook)"
            )
        except Exception as e:
            state.auto_dispatcher_error = str(e)
            print(f"  [WARN] AutoDispatcher unavailable: {e}")

        # ThoughtEvolutionEngine: evolutionary thought refinement
        try:
            from core.brain_chat import ThoughtEvolutionEngine
            sem_idx = moltbook_store.semantic_index if moltbook_store else None
            evo_engine = ThoughtEvolutionEngine(
                micro_agent_pool=pool,
                semantic_index=sem_idx,
            )
            state.brain_chat.set_evolution_engine(evo_engine)
            print(f"  [OK] ThoughtEvolutionEngine (pool={'YES' if pool else 'NO'}, embeddings={'YES' if sem_idx else 'NO'})")
            # Load persisted evolution state
            try:
                count = evo_engine.load_state('data/moltbook/evolution_state.json')
                if count > 0:
                    print(f"  [OK] Loaded {count} evolved thoughts from disk")
            except Exception:
                pass
        except Exception as e:
            print(f"  [WARN] ThoughtEvolutionEngine failed: {e}")

        # KnowledgeSynthesizer: module-driven reasoning
        try:
            from core.brain_chat import KnowledgeSynthesizer
            from core.default_mode_network import DefaultModeNetwork
            from core.orbitofrontal_cortex import OrbitofrontalCortex
            from core.anterior_cingulate import AnteriorCingulateCortex
            from core.prefrontal_cortex import PrefrontalCortex
            ks = KnowledgeSynthesizer(
                dmn=DefaultModeNetwork(),
                ofc=OrbitofrontalCortex(),
                acc=AnteriorCingulateCortex(),
                pfc=PrefrontalCortex(),
            )
            state.brain_chat.set_knowledge_synthesizer(ks)
            print("  [OK] KnowledgeSynthesizer (DMN+OFC+ACC+PFC)")
        except Exception:
            pass

        # Moltbook Agents: Evaluation, Curation, Research, Feedback
        try:
            from core.moltbook_agents import (
                MoltbookFeeder, EvaluationAgent, CurationAgent,
                ResearchAgent, FeedbackAgent,
            )
            feeder = MoltbookFeeder(
                moltbook=moltbook_store,
                agent_name="brain_server",
            )
            state.moltbook_feeder = feeder

            state.evaluation_agent = EvaluationAgent(
                moltbook=moltbook_store,
                semantic_index=moltbook_store.semantic_index if moltbook_store else None,
            )
            state.curation_agent = CurationAgent(
                moltbook=moltbook_store,
                semantic_index=moltbook_store.semantic_index if moltbook_store else None,
            )
            state.research_agent = ResearchAgent(
                feeder=feeder,
            )
            state.feedback_agent = FeedbackAgent(
                moltbook=moltbook_store,
            )

            # Wire agents to BrainChat for access
            if state.brain_chat:
                state.brain_chat._research_agent = state.research_agent
                state.brain_chat._feedback_agent = state.feedback_agent
                state.brain_chat._moltbook_feeder = feeder

            # Populate moltbook_agents dict for knowledge router endpoints
            state.moltbook_agents = {
                "feeder": feeder,
                "evaluator": state.evaluation_agent,
                "curator": state.curation_agent,
                "researcher": state.research_agent,
                "feedback": state.feedback_agent,
            }

            agents_ok = []
            for name in ['evaluation_agent', 'curation_agent', 'research_agent', 'feedback_agent']:
                if getattr(state, name, None) is not None:
                    agents_ok.append(name.replace('_agent', ''))
            print(f"  [OK] Moltbook Agents: {', '.join(agents_ok)}")
        except Exception as e:
            print(f"  [WARN] Moltbook Agents failed: {e}")

        # Start continuous thinking (Phase 11.U.E — env-gated for load tests;
        # 2026-06-08 zusätzlich BRAIN_BACKGROUND_LOOPS-Master-Gate → im HTTP-Prozess
        # aus, im brain-loops-Worker an).
        if (os.environ.get("CONTINUOUS_THINKING_ENABLED", "1").lower() in ("1", "true", "yes")
                and _loops_enabled()):
            cte.start()
            print("  [OK] ContinuousThinking STARTED")
        elif not _loops_enabled():
            print("  [SKIP] ContinuousThinking (BRAIN_BACKGROUND_LOOPS=0)")
        else:
            print("  [SKIP] ContinuousThinking disabled via CONTINUOUS_THINKING_ENABLED=0")

    except Exception as e:
        print(f"  [--] BrainChat setup failed: {e}")

    # --- Thalamic Rewiring Components ---
    try:
        from core.thalamic_adapter import ThalamicAdapter
        from core.cortical_area import CorticalArea, CorticalAreaConfig
        from core.response_agent import ResponseAgent, ResponseAgentConfig
        from core.dual_graph import DualGraph
        from core.kotlin_graph import KotlinGraph

        # Create thalamic adapter (wraps ThalamoPC6)
        state.thalamic_adapter = ThalamicAdapter()

        # Create cortical areas (6 default areas)
        area_configs = [
            CorticalAreaConfig(name="language", specialty=["language_center", "dialogue_manager"]),
            CorticalAreaConfig(name="executive", specialty=["prefrontal_cortex", "anterior_cingulate"]),
            CorticalAreaConfig(name="memory", specialty=["entorhinal_cortex", "basal_forebrain"]),
            CorticalAreaConfig(name="emotional", specialty=["amygdala_complex", "insular_cortex"]),
            CorticalAreaConfig(name="motor", specialty=["cerebellum", "action_planner"]),
            CorticalAreaConfig(name="default_mode", specialty=["default_mode_network", "self_model"]),
        ]
        state.cortical_areas = [CorticalArea(c) for c in area_configs]

        # Create shared memory
        state.kotlin_graph = KotlinGraph()
        state.dual_graph = DualGraph(
            save_dir='data/moltbook',
            # Phase 1 — keep auto-mine off the hot path: the default (10) mined
            # the FULL event history synchronously inside plan_executor's finally
            # (under the ingest write lock) every 10th episode, growing with
            # uptime. 200 keeps mining alive at 1/20th the cadence; force_mine()
            # covers on-demand needs. This DualGraph is used ONLY by the multihop
            # diary (the cortical ResponseAgent writes to the separate
            # state.kotlin_graph instance), so the cadence change affects nothing
            # else.
            auto_mine_interval=200,
        )
        # Load persisted episodic memory
        try:
            if state.dual_graph.load('memory'):
                kg_stats = state.dual_graph.kotlingraph.get_statistics()
                print(f"  [OK] Loaded episodic memory ({kg_stats['total_events']} events, {kg_stats['total_episodes']} episodes)")
        except Exception as e:
            print(f"  [WARN] Episodic memory load failed: {e}")

        # Phase 1 — the executor no longer holds a dual_graph reference: it
        # enqueues each executed plan into the shared diary queue instead
        # (core/multihop_kotlin_adapter.py::enqueue_plan). state.dual_graph
        # is still needed here — the DiaryDrain below (loop-process only)
        # is the sole writer into it.

        # Create response agent
        state.response_agent = ResponseAgent(ResponseAgentConfig(top_k=3))
        state.response_agent.memory = state.kotlin_graph

        # Wire ThalamicAdapter to BrainChat if available
        if state.brain_chat is not None:
            state.brain_chat._thalamic_adapter = state.thalamic_adapter
            print("  [OK] Thalamic Rewiring (adapter + 6 areas + DualGraph)")

    except Exception:
        pass

    # --- MetaKnowledgeGraph (emergent knowledge pipeline) ---
    try:
        from core.meta_knowledge_graph import MetaKnowledgeGraph
        moltbook_store = getattr(state, 'moltbook_store', None)
        sem_idx = moltbook_store.semantic_index if moltbook_store and hasattr(moltbook_store, 'semantic_index') else None
        state.meta_knowledge_graph = MetaKnowledgeGraph(semantic_index=sem_idx)
        print("  [OK] MetaKnowledgeGraph (emergent knowledge pipeline)")
    except Exception as e:
        state.meta_knowledge_graph = None
        print(f"  [WARN] MetaKnowledgeGraph failed: {e}")

    # --- MemoryConsolidator (30s sleep cycle) ---
    try:
        from core.memory_consolidation import MemoryConsolidator
        evo_eng = None
        if hasattr(state, 'brain_chat') and state.brain_chat:
            evo_eng = getattr(state.brain_chat, '_evolution_engine', None)
        consolidator = MemoryConsolidator(
            moltbook_store=getattr(state, 'moltbook_store', None),
            dual_graph=getattr(state, 'dual_graph', None),
            evolution_engine=evo_eng,
            micro_agent_pool=getattr(state.brain_chat, '_micro_agent_pool', None) if state.brain_chat else None,
            meta_knowledge_graph=getattr(state, 'meta_knowledge_graph', None),
            klotski_ctm=getattr(state, 'klotski_ctm', None),
            knowledge_synthesizer=getattr(state.brain_chat, '_knowledge_synthesizer', None) if state.brain_chat else None,
            continuous_thinking_engine=getattr(state, 'continuous_thinking', None),
            # Intervall env-konfigurierbar; Default 300s (5 min) statt vormals
            # hartkodiert 30s. Bei 30s lief der 7-Phasen-Zyklus (inkl. dual_graph
            # n-gram-Mining + qdrant-scroll über alle Collections, ~6s @188% CPU)
            # quasi dauernd → starvte den async HTTP-Layer, multihop-Requests
            # timeouteten (root-caused 2026-06-08). 300s = HTTP atmet.
            interval_s=float(os.environ.get("BRAIN_CONSOLIDATION_INTERVAL_S", "300")),
        )
        state.memory_consolidator = consolidator
        if state.brain_chat:
            state.brain_chat.set_memory_consolidator(consolidator)
        if _loops_enabled():
            consolidator.start()
            print("  [OK] MemoryConsolidator (interval=%ss, meta-graph=%s)" %
                  (os.environ.get("BRAIN_CONSOLIDATION_INTERVAL_S", "300"),
                   'YES' if getattr(state, 'meta_knowledge_graph', None) else 'NO'))
        else:
            print("  [SKIP] MemoryConsolidator (BRAIN_BACKGROUND_LOOPS=0)")
    except Exception as e:
        print(f"  [WARN] MemoryConsolidator failed: {e}")

    # --- Tagebuch-Drain (Queue -> dual_graph). NUR im Loop-Prozess:
    # brain-core (BRAIN_BACKGROUND_LOOPS=0) haengt nur an die Queue an; hier
    # (brain-loops / nativ) wird sie drainiert und danach persistiert.
    state.diary_drain = None
    try:
        from core.multihop_diary_drain import DiaryDrain
        if _loops_enabled() and getattr(state, "dual_graph", None) is not None:
            state.diary_drain = DiaryDrain(state.dual_graph)
            state.diary_drain.start()
            print("  [OK] DiaryDrain gestartet (multihop queue -> dual_graph)")
        else:
            print("  [SKIP] DiaryDrain (BRAIN_BACKGROUND_LOOPS=0 -> nur enqueue)")
    except Exception as e:
        print(f"  [WARN] DiaryDrain unavailable: {e}")

    # --- SocializationMetrics (6 learning metrics from Moltbook paper) ---
    try:
        from core.socialization_metrics import SocializationMetrics
        soc_metrics = SocializationMetrics(
            moltbook_store=getattr(state, 'moltbook_store', None),
        )
        state.socialization_metrics = soc_metrics
        consolidator_ref = getattr(state, 'memory_consolidator', None)
        if consolidator_ref:
            consolidator_ref.set_socialization_metrics(soc_metrics)
        print("  [OK] SocializationMetrics (6 learning metrics)")
    except Exception as e:
        print(f"  [WARN] SocializationMetrics failed: {e}")

    # --- AgentLoop + RadialAttentionNetwork (from ProductionPlanner) ---
    try:
        # NOTE: do NOT `import os` here — Python's scope rules then treat `os`
        # as a local in the WHOLE _init_production_modules function, and the
        # earlier reference at line ~958 (`os.environ.get("CONTINUOUS_THINKING_ENABLED")`)
        # raises "cannot access local variable 'os' where it is not associated
        # with a value", which silently swallows the entire BrainChat setup block
        # (its except handler reports "BrainChat setup failed: ..."). The
        # module-level import on line 12 is what we use. Phase 11.U.K (2026-06-02).
        os.environ.setdefault('ENABLE_AGENT_LOOP', 'true')
        from production.production_planner import ProductionPlanner
        planner = ProductionPlanner(session_log_dir="production/session_logs")
        state.agent_loop = planner.agent_loop
        radial = getattr(planner.agent_loop, "radial_network", None)
        has_radial = radial is not None
        has_seed = getattr(planner.agent_loop, "seed_encoder", None) is not None
        has_buf = getattr(planner.agent_loop, "experience_buffer", None) is not None
        print(f"  [OK] AgentLoop (radial={'YES' if has_radial else 'NO'}, "
              f"seed={'YES' if has_seed else 'NO'}, "
              f"buffer={'YES' if has_buf else 'NO'})")

        # Connect AgentLoop to ContinuousThinkingEngine so every think tick
        # fires a radial forward pass (bridges alive, dashboard populated).
        cte = state.continuous_thinking
        if cte is not None and has_radial and has_seed:
            cte.set_agent_loop(planner.agent_loop)
            print("  [OK] ContinuousThinking -> AgentLoop.radial_tick CONNECTED")

            # Wire ThoughtRadialBridge: thoughts flow through rings
            try:
                from core.thought_radial_bridge import ThoughtRadialBridge
                thought_bridge = ThoughtRadialBridge()
                thought_bridge.set_agent_loop(planner.agent_loop)
                cte.set_thought_radial_bridge(thought_bridge)
                state.thought_radial_bridge = thought_bridge
                # Give agent_loop a ref for reward-weighted Hebbian updates
                planner.agent_loop._thought_radial_bridge_ref = thought_bridge
                print("  [OK] ThoughtRadialBridge wired: CTE <-> RadialNetwork")
            except Exception as e:
                print(f"  [WARN] ThoughtRadialBridge init failed: {e}")

            # ThoughtJury: autonomous thought evaluation (5 judges + DeepReview)
            try:
                from core.thought_jury import ThoughtJury
                sem_idx = state.moltbook_store.semantic_index if state.moltbook_store else None
                brain_chat = state.brain_chat
                pool = brain_chat._micro_agent_pool if brain_chat else None
                thought_jury = ThoughtJury(
                    semantic_index=sem_idx,
                    micro_agent_pool=pool,
                    deep_review_interval=50,
                )
                cte.set_thought_jury(thought_jury)
                state.thought_jury = thought_jury
                print("  [OK] ThoughtJury wired (5 judges + DeepReview)")
            except Exception as e:
                print(f"  [WARN] ThoughtJury init failed: {e}")

            # OutcomeRewardTracker: outcome-based reward signals
            try:
                from core.outcome_reward import OutcomeRewardTracker
                outcome_tracker = OutcomeRewardTracker(
                    bridge=thought_bridge,
                    cte=cte,
                    moltbook_store=state.moltbook_store,
                    meta_graph=getattr(state, 'meta_knowledge_graph', None),
                )
                state.outcome_tracker = outcome_tracker
                if state.brain_chat:
                    state.brain_chat._outcome_tracker = outcome_tracker
                cte._outcome_tracker = outcome_tracker
                if state.memory_consolidator:
                    state.memory_consolidator._outcome_tracker = outcome_tracker
                print("  [OK] OutcomeRewardTracker wired (4 signals)")
            except Exception as e:
                print(f"  [WARN] OutcomeRewardTracker init failed: {e}")

            # SpaceRoutingHead: learned space centroids for intent routing
            try:
                from pathlib import Path as _Path
                from core.space_routing_head import SpaceRoutingHead
                from core import config as _cfg
                routing_head = SpaceRoutingHead()
                # Checkpoint path is identity-namespaced (Phase C). With the
                # default identity this is byte-identical to the legacy
                # "data/brain_checkpoints" so existing .pt files keep loading.
                _space_ckpt_dir = _Path(_cfg.checkpoint_dir("brain_checkpoints"))
                _space_ckpt_dir.mkdir(parents=True, exist_ok=True)
                _space_ckpt_path = str(_space_ckpt_dir / "space_routing_head.pt")
                state.space_routing_head_ckpt = _space_ckpt_path

                if not routing_head.load(_space_ckpt_path):
                    # Fresh seed from the event_type → space mapping
                    seeded = routing_head.seed_from_event_map(planner.agent_loop)
                    print(f"  [OK] SpaceRoutingHead wired ({len(routing_head.space_names)} spaces, "
                          f"freshly seeded from {seeded} events)")
                else:
                    print(f"  [OK] SpaceRoutingHead wired ({len(routing_head.space_names)} spaces, "
                          f"loaded from {_space_ckpt_path})")
                state.space_routing_head = routing_head
            except Exception as e:
                state.space_routing_head = None
                state.space_routing_head_ckpt = None
                print(f"  [WARN] SpaceRoutingHead init failed: {e}")

            # EventRoutingHead: learned event_type centroids for intent classification
            # (the stage *before* SpaceRoutingHead — text → event_type → space).
            # Embeddings come from sentence-transformers (MiniLM, 384-dim) — the
            # Brain's native SeedEncoder was tested first but proved too weak
            # for 123-way classification.
            try:
                from pathlib import Path as _Path
                import torch as _torch
                from core.event_routing_head import EventRoutingHead

                # Lazy-load multilingual SBERT once and cache on app.state.
                # paraphrase-multilingual-MiniLM-L12-v2 keeps DE and EN
                # greetings in the same cluster (cf. all-MiniLM-L6-v2 which
                # is English-only and put 'hallo' far from 'hello').
                sbert = None
                try:
                    from sentence_transformers import SentenceTransformer
                    sbert = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
                    print(f"  [OK] SBERT loaded (dim={sbert.get_sentence_embedding_dimension()})")
                except Exception as sb_err:
                    print(f"  [WARN] SBERT load failed: {sb_err}")
                state.sbert_encoder = sbert

                event_head = EventRoutingHead(embed_dim=384)
                # Identity-namespaced checkpoint path (Phase C); legacy-
                # identical under the default identity.
                from core import config as _cfg
                _ckpt_dir = _Path(_cfg.checkpoint_dir("brain_checkpoints"))
                _ckpt_dir.mkdir(parents=True, exist_ok=True)
                _ckpt_path = str(_ckpt_dir / "event_routing_head.pt")
                state.event_routing_head_ckpt = _ckpt_path

                if not event_head.load(_ckpt_path):
                    if sbert is not None:
                        def _embed_fn(text: str):
                            vec = sbert.encode([text[:200]], convert_to_numpy=True)
                            return _torch.tensor(vec, dtype=_torch.float32)
                        seeded_e = event_head.seed(_embed_fn, lr=0.20)
                        print(f"  [OK] EventRoutingHead wired ({len(event_head.event_names)} events, "
                              f"seeded {seeded_e} phrases via SBERT)")
                    else:
                        print(f"  [WARN] EventRoutingHead built but no SBERT — head is random!")
                else:
                    print(f"  [OK] EventRoutingHead wired ({len(event_head.event_names)} events, "
                          f"loaded from {_ckpt_path})")
                state.event_routing_head = event_head
            except Exception as e:
                state.event_routing_head = None
                state.event_routing_head_ckpt = None
                state.sbert_encoder = None
                print(f"  [WARN] EventRoutingHead init failed: {e}")

            # Phase D3: inference replicas poll the shared checkpoint volume
            # so they pick up the learner's periodic save() WITHOUT a restart.
            # Only inference runs this tick — a learner/mono brain writes its
            # own centroids and must not reload them out from under itself.
            try:
                from core import config as _cfg
                _is_inf = not _cfg.is_learner()
            except Exception:
                _is_inf = False  # fail-safe: mono/legacy never reloads
            if _is_inf:
                import threading as _thr
                _reload_secs = 30
                try:
                    _reload_secs = int(__import__("os").environ.get(
                        "BRAIN_CKPT_RELOAD_SECS", "30"))
                except Exception:
                    pass

                def _ckpt_reload_loop(_state, _interval):
                    import time as _t
                    while True:
                        _t.sleep(_interval)
                        try:
                            sh = getattr(_state, "space_routing_head", None)
                            sp = getattr(_state, "space_routing_head_ckpt", None)
                            if sh is not None and sp:
                                sh.maybe_reload(sp)
                            eh = getattr(_state, "event_routing_head", None)
                            ep = getattr(_state, "event_routing_head_ckpt", None)
                            if eh is not None and ep:
                                eh.maybe_reload(ep)
                        except Exception as _re:
                            print(f"  [WARN] ckpt reload tick: {_re}")

                _t = _thr.Thread(
                    target=_ckpt_reload_loop, args=(state, _reload_secs),
                    name="ckpt-reload", daemon=True)
                _t.start()
                state.ckpt_reload_thread = _t
                print(f"  [OK] Phase D3 inference ckpt-reload tick "
                      f"started (every {_reload_secs}s, mtime-gated)")

        elif cte is None:
            print("  [--] ContinuousThinking not available, radial_tick not connected")
        else:
            print("  [--] Radial/Seed not available, radial_tick not connected")

    except Exception as e:
        print(f"  [WARN] AgentLoop wiring failed: {e}")


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Startup / shutdown hook."""
    _init_brain_state(app.state, testing=getattr(app.state, "testing", False))
    if not app.state.testing:
        _init_production_modules(app.state)

    # Ingest Rowboat data on startup (while thinking is OFF)
    try:
        from core.rowboat_reader import read_all_manifests
        app.state._rowboat_data = read_all_manifests()
        stats = app.state._rowboat_data.get("stats", {})
        print(f"  [OK] Rowboat data ingested: {stats.get('bubble_count', 0)} bubbles, "
              f"{stats.get('idea_count', 0)} ideas")

        # Push bubbles + ideas into the unified KG in a background thread
        # so Brain startup doesn't wait for ~300 embeddings (~30-60s).
        kg = getattr(app.state, "qdrant_kg", None)
        if kg is not None:
            rowboat_data = app.state._rowboat_data
            def _bulk_rowboat_to_kg():
                try:
                    from core.qdrant_kg import BubbleDoc, IdeaDoc
                    bub_n = idea_n = 0
                    for b in rowboat_data.get("bubbles", []):
                        edges_raw = b.edges or []
                        edges_str = [
                            (e.get("target") or e.get("to") or str(e)) if isinstance(e, dict) else str(e)
                            for e in edges_raw
                        ]
                        kg.upsert_bubble(BubbleDoc(
                            bubble_id=b.id,
                            title=b.title,
                            description=b.description,
                            notes=[n.title for n in b.notes[:20]],
                            bubble_edges=edges_str,
                            metadata={"published_at": b.published_at},
                        ))
                        bub_n += 1
                    for idea in rowboat_data.get("all_ideas", []):
                        kg.upsert_idea(IdeaDoc(
                            idea_id=idea.id,
                            title=idea.title,
                            content=idea.content,
                            tags=idea.tags,
                            bubble_id=idea.bubble_id,
                            node_subtype=idea.node_type,
                            metadata={"bubble_title": idea.bubble_title},
                        ))
                        idea_n += 1
                    print(f"  [OK-async] Rowboat -> KG: {bub_n} bubbles, {idea_n} ideas upserted")
                except Exception as e:
                    print(f"  [WARN-async] Rowboat -> KG bulk upsert failed: {e}")
            import threading as _threading
            _threading.Thread(
                target=_bulk_rowboat_to_kg, daemon=True,
                name="RowboatToKG-bulk",
            ).start()
            print("  [OK] Rowboat -> KG bulk import scheduled (background)")
    except Exception as e:
        print(f"  [WARN] Rowboat ingest failed: {e}")

    # Seed 13 spaces + ~150 events into the KG so Graph kNN routing can
    # replace space_routing_head.pt / event_routing_head.pt.
    try:
        kg = getattr(app.state, "qdrant_kg", None)
        if kg is not None:
            from core.qdrant_kg import SpaceDoc, EventDoc
            from core.space_routing_head import SPACE_NAMES, EVENT_SPACE_MAP

            SPACE_DESCRIPTIONS = {
                "ideas": "Ideas space: capturing, exploring, expanding, linking thoughts",
                "bubbles": "Bubbles: containers for related ideas, with create/find/evaluate/promote operations",
                "coding": "Code generation, modification, preview, projects — anything code-like",
                "desktop": "Desktop automation: clicks, types, apps, screenshots, messaging, browser, moire",
                "research": "Web research, scraping, summarization, comparison, fact-finding",
                "n8n": "n8n workflow automation: create, list, status, execute workflows",
                "agentfarm": "Multi-agent teams: create_team, run, collaborate, results, templates",
                "schedule": "Scheduling: cron jobs, reminders, snooze, time-based triggers",
                "roarboot": "Knowledge graph Roarboot: search, query, email drafts, meeting briefs, decks",
                "minibook": "Minibook collaborative agent discussions and projects",
                "video": "Video generation: vision, demo building, lip-sync, voice clone, TTS",
                "flowzen": "Flowzen Rose recommender: recommend, accept, status",
                "mirofish": "MiroFish simulation + graph reasoning: predict, build graphs, interview",
            }

            def _bulk_spaces_events_to_kg():
                try:
                    space_n = event_n = 0
                    for space in SPACE_NAMES:
                        kg.upsert_space(SpaceDoc(
                            space_id=space,
                            title=space,
                            description=SPACE_DESCRIPTIONS.get(space, space),
                            source="manifest",
                        ))
                        space_n += 1
                    for event_id, space_id in EVENT_SPACE_MAP.items():
                        # Rich-ify: description + strategy derived from event_id.
                        parts = event_id.split(".")
                        verb = parts[-1].replace("_", " ") if parts else event_id
                        domain = parts[0] if parts else ""
                        desc = f"Event '{event_id}' — {verb} action in {domain} domain"
                        strat = f"Route to space '{space_id}' and execute {verb}"
                        kg.upsert_event(EventDoc(
                            event_id=event_id,
                            title=event_id,
                            trigger_description=desc,
                            typical_response_strategy=strat,
                            source="manifest",
                            metadata={"target_space": space_id},
                        ))
                        event_n += 1
                    print(f"  [OK-async] Spaces + Events -> KG: "
                          f"{space_n} spaces, {event_n} events upserted")
                except Exception as e:
                    print(f"  [WARN-async] Spaces/Events -> KG failed: {e}")

            # Gate (2026-06-08): der Bulk-Import re-embedded ~13 Spaces + ~150 Events
            # via Qwen3-forward-pass (CPU-bound) → pegte brain-core einen Core dauerhaft
            # + erzeugte die Qdrant-read/write-Flut, die den async HTTP-Server starvte
            # (per py-spy auf PID 1 als EINZIGE aktive Thread bestaetigt, root-caused
            # 2026-06-08). Gehoert wie alle KG-schreibenden Loops hinter das Master-Gate
            # → laeuft jetzt im brain-loops-Worker, NICHT im HTTP-Prozess.
            import threading as _threading
            if _loops_enabled():
                _threading.Thread(
                    target=_bulk_spaces_events_to_kg, daemon=True,
                    name="SpacesEventsToKG-bulk",
                ).start()
                print("  [OK] Spaces+Events -> KG bulk import scheduled (background)")
            else:
                print("  [SKIP] Spaces+Events -> KG bulk import (BRAIN_BACKGROUND_LOOPS=0)")
    except Exception as e:
        print(f"  [WARN] Spaces/Events KG sync failed: {e}")

    # Auto-start thinking — no reason to boot the brain and NOT think
    # (2026-06-08: respektiert BRAIN_BACKGROUND_LOOPS — im HTTP-Prozess aus,
    # damit der zweite Auto-Start das Master-Gate nicht umgeht).
    try:
        cte = getattr(app.state, 'continuous_thinking', None)
        if cte and not cte.is_running and _loops_enabled():
            cte.start()
            print(f"  [OK] ContinuousThinking auto-started")
        elif not _loops_enabled():
            print(f"  [SKIP] ContinuousThinking auto-start (BRAIN_BACKGROUND_LOOPS=0)")
    except Exception as e:
        print(f"  [WARN] ContinuousThinking auto-start failed: {e}")

    # Periodic log retrainer — scans logs/intents/*.jsonl every N seconds
    # and incrementally trains the EventRoutingHead on new entries so the
    # Brain's feedback loop closes without manual bootstrap.
    app.state.log_retrainer_task = None
    try:
        import os as _os
        from core.log_retrainer import periodic_retrainer_loop
        _retrain_interval = int(_os.getenv("BRAIN_RETRAIN_INTERVAL_SECONDS", "3600"))
        if (_retrain_interval > 0 and getattr(app.state, 'event_routing_head', None) is not None
                and _loops_enabled()):
            app.state.log_retrainer_task = asyncio.create_task(
                periodic_retrainer_loop(app.state, interval_seconds=_retrain_interval)
            )
            print(f"  [OK] Log retrainer scheduled (interval={_retrain_interval}s)")
        elif not _loops_enabled():
            print(f"  [SKIP] Log retrainer (BRAIN_BACKGROUND_LOOPS=0)")
        else:
            print(f"  [--] Log retrainer disabled (interval={_retrain_interval}, event_head missing)")
    except Exception as e:
        print(f"  [WARN] Log retrainer init failed: {e}")

    # Embedder-Warmup (2026-06-08): der Difficulty-Router laedt das Qwen3-Modell
    # beim ERSTEN classify lazy (~148s) — das verzoegerte den ersten echten Request
    # massiv. Hier im Hintergrund-Thread vorwaermen, damit das Modell bereit ist,
    # bevor der erste Intent kommt. Best-effort, blockiert den Start nicht.
    try:
        import threading as _thr
        def _warm_embedder():
            try:
                from core.difficulty_router import get_router
                get_router().classify("warmup")   # zieht Embedder.get() + encode einmal
                print("  [OK] Difficulty-Embedder vorgewaermt (Qwen geladen)")
            except Exception as _e:  # noqa: BLE001
                print(f"  [--] Embedder-Warmup uebersprungen: {_e}")
            # ToolScope (plans/dynamic-agent-tools-prompt.md): die 328-Tool-Matrix EINMALIG
            # hier vorberechnen — encode_batch(328) kostet auf CPU ~17 MIN und DARF NIE im
            # Request laufen (sonst Hang/Container-Kill, root-caused 2026-06-18). Nur wenn
            # DYNAMIC_TOOL_SCOPE an ist (sonst sinnlose 17 min). Embedder ist jetzt warm.
            if os.environ.get("DYNAMIC_TOOL_SCOPE", "0") not in ("0", "false", "False"):
                try:
                    import time as _t
                    from core.tool_scope_selector import get_selector
                    _t0 = _t.time()
                    get_selector()._tool_matrix()   # fuellt den (one-shot-TTL) Cache
                    print(f"  [OK] ToolScope-Matrix vorgewaermt ({_t.time() - _t0:.0f}s, 328 Tools)")
                except Exception as _e:  # noqa: BLE001
                    print(f"  [--] ToolScope-Vorwaermung uebersprungen: {_e}")
        _thr.Thread(target=_warm_embedder, daemon=True, name="EmbedderWarmup").start()
    except Exception:  # noqa: BLE001
        pass

    yield  # ---- app is running ----

    # Cancel the log retrainer task
    _retrain_task = getattr(app.state, 'log_retrainer_task', None)
    if _retrain_task is not None:
        _retrain_task.cancel()
        try:
            await _retrain_task
        except (asyncio.CancelledError, Exception):
            pass
        print("  [OK] Log retrainer stopped")

    # Teardown: persist all memory to disk
    consolidator = getattr(app.state, 'memory_consolidator', None)
    if consolidator:
        consolidator.stop()
        print("  [OK] Memory persisted to disk on shutdown")

    diary_drain = getattr(app.state, 'diary_drain', None)
    if diary_drain:
        diary_drain.stop()
        print("  [OK] DiaryDrain stopped on shutdown")

    # Persist EventRoutingHead centroids so learning survives restart
    event_head = getattr(app.state, 'event_routing_head', None)
    ckpt_path = getattr(app.state, 'event_routing_head_ckpt', None)
    if event_head is not None and ckpt_path:
        try:
            event_head.save(ckpt_path)
            print(f"  [OK] EventRoutingHead saved to {ckpt_path}")
        except Exception as e:
            print(f"  [WARN] EventRoutingHead save failed: {e}")

    # Persist SpaceRoutingHead centroids so learning survives restart
    space_head = getattr(app.state, 'space_routing_head', None)
    space_ckpt_path = getattr(app.state, 'space_routing_head_ckpt', None)
    if space_head is not None and space_ckpt_path:
        try:
            space_head.save(space_ckpt_path)
            print(f"  [OK] SpaceRoutingHead saved to {space_ckpt_path}")
        except Exception as e:
            print(f"  [WARN] SpaceRoutingHead save failed: {e}")


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app(testing: bool = False) -> FastAPI:
    """Build and return a fully-wired FastAPI application.

    Parameters
    ----------
    testing : bool
        When *True*, production module loading is skipped so the app
        can be exercised with the fast ``TestClient``.
    """
    app = FastAPI(
        title="The Brain — Nervous System",
        lifespan=_lifespan,
    )

    # Mark testing *before* lifespan fires
    app.state.testing = testing

    # -- CORS --
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # -- Thalamic middleware (Task 3) --
    from web.middleware.thalamic_gate import ThalamicGateMiddleware
    app.add_middleware(ThalamicGateMiddleware)

    # -- Static files --
    if _STATIC_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    # -- Templates on state so routers can share them --
    app.state.templates = templates

    # ------------------------------------------------------------------
    # Core routes (kept inline — only two)
    # ------------------------------------------------------------------

    @app.get("/api/health")
    async def health():
        return JSONResponse({
            "status": "alive",
            "timestamp": time.time(),
            "uptime": time.time() - _BOOT_TIME,
        })

    @app.get("/api/research/health")
    async def research_health():
        from spaces.research.execution_target import ResearchTarget

        report = ResearchTarget("research:web").health_check()
        return JSONResponse(report, status_code=200 if report["ok"] else 503)

    @app.get("/", response_class=HTMLResponse)
    async def root(request: Request):
        return templates.TemplateResponse(request, "brain_dashboard.html")

    # ------------------------------------------------------------------
    # Include routers
    # ------------------------------------------------------------------
    from web.routers.training import router as training_router
    app.include_router(training_router)

    from web.routers.oscillator import router as oscillator_router
    app.include_router(oscillator_router)

    from web.routers.swarm import router as swarm_router
    app.include_router(swarm_router)

    from web.routers.introspection import router as introspection_router
    app.include_router(introspection_router)

    from web.routers.knowledge import router as knowledge_router
    app.include_router(knowledge_router)

    from web.routers.cortex import router as cortex_router
    app.include_router(cortex_router)

    from web.streams.consciousness import router as consciousness_stream_router
    app.include_router(consciousness_stream_router)

    from web.streams.chat import router as chat_stream_router
    app.include_router(chat_stream_router)

    from web.routers.radial import router as radial_router
    app.include_router(radial_router)

    from web.routers.routing import router as routing_router
    app.include_router(routing_router)

    from web.routers.classification import router as classification_router
    app.include_router(classification_router)

    @app.get("/radial", response_class=HTMLResponse)
    async def radial_dashboard(request: Request):
        return templates.TemplateResponse(request, "radial_dashboard.html")

    @app.get("/brain", response_class=HTMLResponse)
    async def unified_brain_dashboard(request: Request):
        return templates.TemplateResponse(request, "unified_brain_dashboard.html")

    @app.get("/klotski3d", response_class=HTMLResponse)
    async def klotski_3d_dashboard(request: Request):
        return templates.TemplateResponse(request, "klotski_3d_rings.html")

    # Legacy compat — 307 redirects from old Flask paths
    from web.routers.legacy_compat import router as legacy_router
    app.include_router(legacy_router)

    return app


# ---------------------------------------------------------------------------
# Module-level app for ``uvicorn web.brain_server:app``
# ---------------------------------------------------------------------------
app = create_app(testing=False)


if __name__ == "__main__":
    import uvicorn
    # Pass the app object directly so uvicorn doesn't fork a subprocess that
    # re-imports via the import-string (which would resolve PATH-first python,
    # in our case pyenv-3.11 instead of the active venv).
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=5000,
        reload=False,
    )
