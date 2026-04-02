"""
The Brain Nervous System — Unified FastAPI Server.

Replaces the old Flask micro-service sprawl with a single ASGI app.
All core module imports are lazy (inside _init_production_modules) so the
server can start — and be tested — without heavyweight dependencies.
"""

from __future__ import annotations

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
    state.socialization_metrics = None

    state._rowboat_data = None
    state._cached_clusters = None
    state._cached_thought_clusters = None

    state.testing = testing


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

        # ContinuousThinkingEngine: brain ALWAYS thinks
        moltbook_store = state.moltbook_store  # may be None
        cte = ContinuousThinkingEngine(
            moltbook=moltbook_store,
            interval_ms=500,
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
            n_agents = len(pool._agents) if hasattr(pool, '_agents') else '?'
            has_router = pool._router is not None
            print(f"  [OK] MicroAgentPool ({n_agents} agents, router={'YES' if has_router else 'NO'})")
        except Exception:
            pass

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

        # Start continuous thinking
        cte.start()
        print("  [OK] ContinuousThinking STARTED")

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
        state.dual_graph = DualGraph(save_dir='data/moltbook')
        # Load persisted episodic memory
        try:
            if state.dual_graph.load('memory'):
                kg_stats = state.dual_graph.kotlingraph.get_statistics()
                print(f"  [OK] Loaded episodic memory ({kg_stats['total_events']} events, {kg_stats['total_episodes']} episodes)")
        except Exception as e:
            print(f"  [WARN] Episodic memory load failed: {e}")

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
            interval_s=30.0,
        )
        state.memory_consolidator = consolidator
        if state.brain_chat:
            state.brain_chat.set_memory_consolidator(consolidator)
        consolidator.start()
        print("  [OK] MemoryConsolidator (30s sleep cycle, meta-graph=%s)" %
              ('YES' if getattr(state, 'meta_knowledge_graph', None) else 'NO'))
    except Exception as e:
        print(f"  [WARN] MemoryConsolidator failed: {e}")

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
        import os
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
                from core.space_routing_head import SpaceRoutingHead
                routing_head = SpaceRoutingHead()
                # Pre-train centroids from the complete event_type → space mapping
                seeded = routing_head.seed_from_event_map(planner.agent_loop)
                state.space_routing_head = routing_head
                print(f"  [OK] SpaceRoutingHead wired ({len(routing_head.space_names)} spaces, seeded {seeded} events)")
            except Exception as e:
                state.space_routing_head = None
                print(f"  [WARN] SpaceRoutingHead init failed: {e}")

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
    except Exception as e:
        print(f"  [WARN] Rowboat ingest failed: {e}")

    # Auto-start thinking — no reason to boot the brain and NOT think
    try:
        cte = getattr(app.state, 'continuous_thinking', None)
        if cte and not cte.is_running:
            cte.start()
            print(f"  [OK] ContinuousThinking auto-started")
    except Exception as e:
        print(f"  [WARN] ContinuousThinking auto-start failed: {e}")

    yield  # ---- app is running ----
    # Teardown: persist all memory to disk
    consolidator = getattr(app.state, 'memory_consolidator', None)
    if consolidator:
        consolidator.stop()
        print("  [OK] Memory persisted to disk on shutdown")


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
    uvicorn.run(
        "web.brain_server:app",
        host="0.0.0.0",
        port=5000,
        reload=False,
    )
