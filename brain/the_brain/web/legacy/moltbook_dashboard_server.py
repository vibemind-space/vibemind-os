"""
Moltbook Dashboard — Standalone server
All-in-one: wires MoltbookStore + Pipeline + Agents + BrainChat directly,
no unified_brain_service dependency.

Architecture (NEW):
    /api/brain/chat  → BrainChat → Thalamus routing → Modules → Response
    /api/brain/thoughts → ContinuousThinkingEngine → Live thought stream
    /api/orchestrate → Legacy pipeline (kept for backward compat)

The Brain ALWAYS thinks (ContinuousThinkingEngine).
Moltbook displays thoughts (visualization layer).
Thalamus routes everything (3-layer routing).

Usage:
    python web/moltbook_dashboard_server.py
    → http://localhost:5006
"""

import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from flask import Flask, jsonify, render_template, request
from flask_cors import CORS
from datetime import datetime
import time

app = Flask(__name__, template_folder='templates', static_folder='static')
CORS(app)

# ── Moltbook Wiring ────────────────────────────────────────────────

store = None
graph = None
feeder = None
evaluation_agent = None
curation_agent = None
research_agent = None
feedback_agent = None
orchestrator = None
debug_stream = None
analyzer = None
forum = None

# ── Brain Chat (NEW) ───────────────────────────────────────────────

brain_chat = None
continuous_thinking = None


def initialize_moltbook():
    global store, graph, feeder, evaluation_agent, curation_agent
    global research_agent, feedback_agent, orchestrator, debug_stream, analyzer, forum
    global brain_chat, continuous_thinking

    print("Wiring Moltbook components …")

    from core.moltbook import MoltbookStore, MoltbookGraph
    store = MoltbookStore(config={'similarity_threshold': 0.3})
    graph = MoltbookGraph()
    print("  [OK] MoltbookStore + MoltbookGraph")

    from core.moltbook_agents import (
        MoltbookFeeder, EvaluationAgent, CurationAgent,
        ResearchAgent, FeedbackAgent
    )
    feeder = MoltbookFeeder(moltbook=store, agent_name="dashboard", graph=graph)
    evaluation_agent = EvaluationAgent(moltbook=store)
    curation_agent = CurationAgent(moltbook=store, graph=graph)
    research_feeder = MoltbookFeeder(moltbook=store, agent_name="research", graph=graph)
    research_agent = ResearchAgent(feeder=research_feeder)
    feedback_agent = FeedbackAgent(moltbook=store)
    print("  [OK] Feeder + Evaluation + Curation + Research + Feedback")

    # MoltbookForum: Multi-Agent Discussion
    from core.moltbook_agents import MoltbookForum
    forum = MoltbookForum(
        store=store, evaluator=evaluation_agent, curator=curation_agent,
        researcher=research_agent, feedback=feedback_agent, graph=graph,
    )
    print("  [OK] MoltbookForum (Multi-Agent Discussion)")

    # ── Wire the FULL thinking + speaking pipeline ──
    from core.moltbook_pipeline import (
        InputAnalyzer, ThinkingBudget, DebugStream,
        RealtimeResponseEngine, ThinkTalkOrchestrator, PerformanceMonitor,
        KnowledgeAugmentor,
    )

    # ThoughtStream: background associative thinking
    thought_stream = None
    try:
        from core.moltbook_thinking import ThoughtStream, MetaThinking
        thought_stream = ThoughtStream(moltbook=store)
        meta_thinking = MetaThinking()
        print("  [OK] ThoughtStream + MetaThinking")
    except Exception as e:
        meta_thinking = None
        print(f"  [--] ThoughtStream skipped: {e}")

    # InternalMonologue: 3-thread MIRROR thinking
    internal_monologue = None
    try:
        from core.moltbook_thinker import InternalMonologue
        internal_monologue = InternalMonologue(moltbook=store)
        print("  [OK] InternalMonologue (3-thread MIRROR)")
    except Exception as e:
        print(f"  [--] InternalMonologue skipped: {e}")

    # TalkerModule: thought -> natural language
    talker = None
    try:
        from core.moltbook_talker import TalkerModule
        talker = TalkerModule()
        print("  [OK] TalkerModule (Personality + HumanLike)")
    except Exception as e:
        print(f"  [--] TalkerModule skipped: {e}")

    # SpeculativeRetrieval + RelevanceScorer
    speculative = None
    relevance_scorer = None
    try:
        from core.moltbook_retrieval import SpeculativeRetrieval, RelevanceScorer
        speculative = SpeculativeRetrieval(moltbook=store)
        relevance_scorer = RelevanceScorer(moltbook=store)
        print("  [OK] SpeculativeRetrieval + RelevanceScorer")
    except Exception as e:
        print(f"  [--] Retrieval enhancements skipped: {e}")

    analyzer = InputAnalyzer()
    budget = ThinkingBudget()
    debug_stream = DebugStream(enabled=True)

    # KnowledgeAugmentor: Wikipedia + Web search for external knowledge
    augmentor_feeder = MoltbookFeeder(moltbook=store, agent_name="augmentor", graph=graph)
    knowledge_augmentor = KnowledgeAugmentor(moltbook=store, feeder=augmentor_feeder)
    print("  [OK] KnowledgeAugmentor (Wikipedia + Web)")

    # Wire the FULL engine with all components
    engine = RealtimeResponseEngine(
        moltbook=store,
        thought_stream=thought_stream,
        internal_monologue=internal_monologue,
        talker=talker,
        speculative=speculative,
        relevance_scorer=relevance_scorer,
        meta_thinking=meta_thinking,
        knowledge_augmentor=knowledge_augmentor,
    )
    orchestrator = ThinkTalkOrchestrator(
        engine=engine, analyzer=analyzer, budget_allocator=budget,
    )
    # Replace orchestrator's default DebugStream with our shared one
    orchestrator._debug = debug_stream
    print("  [OK] Full Pipeline (Analyzer + Thinker + Talker + Orchestrator)")

    # ═══════════════════════════════════════════════════════════════════
    # NEW: BrainChat + ContinuousThinking — Always-On Brain
    # ═══════════════════════════════════════════════════════════════════

    from core.brain_chat import BrainChat, ContinuousThinkingEngine

    # ContinuousThinkingEngine: brain ALWAYS thinks
    continuous_thinking = ContinuousThinkingEngine(
        thought_stream=thought_stream,
        moltbook=store,
        knowledge_augmentor=knowledge_augmentor,
        interval_ms=500,
    )
    print("  [OK] ContinuousThinkingEngine (always-on background thinking)")

    # Try to wire Thalamus routing (3-layer)
    l1_router = None
    l2_planner = None
    l3_router = None
    hierarchical_planner = None

    try:
        from core.task_feature_router import TaskFeatureRouter
        l1_router = TaskFeatureRouter()
        print("  [OK] Layer 1: TaskFeatureRouter")
    except Exception as e:
        print(f"  [--] L1 TaskFeatureRouter skipped: {e}")

    try:
        from core.conversation_path_planner import ConversationPathPlanner
        l2_planner = ConversationPathPlanner()
        print("  [OK] Layer 2: ConversationPathPlanner")
    except Exception as e:
        print(f"  [--] L2 ConversationPathPlanner skipped: {e}")

    try:
        from core.decision_router import DecisionRouter
        l3_router = DecisionRouter()
        print("  [OK] Layer 3: DecisionRouter")
    except Exception as e:
        print(f"  [--] L3 DecisionRouter skipped: {e}")

    # BrainChat: THE central chat entry point
    brain_chat = BrainChat(
        task_feature_router=l1_router,
        conversation_path_planner=l2_planner,
        decision_router=l3_router,
        hierarchical_planner=hierarchical_planner,
        continuous_thinking=continuous_thinking,
        internal_monologue=internal_monologue,
        knowledge_augmentor=knowledge_augmentor,
        talker=talker,
        moltbook=store,
        input_analyzer=analyzer,
        thinking_budget=budget,
    )
    print("  [OK] BrainChat (central routing through Thalamus)")

    # START continuous thinking — brain always thinks
    continuous_thinking.start()
    print("  [OK] ContinuousThinking STARTED — brain is always thinking!")

    # ── Seed sample knowledge ──
    sample_posts = [
        "Artificial intelligence is transforming how we process information and make decisions in both industry and research.",
        "Machine learning models can detect patterns in large datasets, enabling predictive analytics and automated classification.",
        "Neural networks are inspired by biological brain structures, using layers of interconnected nodes to process information.",
        "Reinforcement learning allows agents to learn optimal behavior through trial and error in complex environments.",
        "Natural language processing enables machines to understand, interpret, and generate human language with increasing fluency.",
    ]
    for text in sample_posts:
        feeder.post(content=text, tags=[])
    print(f"  [OK] Seeded {len(sample_posts)} knowledge entries")
    print(f"Moltbook ready.\n")


# ═══════════════════════════════════════════════════════════════════
# Brain Chat API (NEW — primary entry point)
# ═══════════════════════════════════════════════════════════════════

@app.route('/api/brain/chat', methods=['POST'])
def brain_chat_endpoint():
    """
    THE primary chat endpoint — routes through Thalamus.

    Everything goes through BrainChat → Thalamus routing → Modules → Response.
    Returns response + thought trace (for Moltbook to visualize).
    """
    data = request.json or {}
    message = data.get('message', data.get('prompt', ''))
    if not message:
        return jsonify({'error': 'No message'}), 400

    result = brain_chat.send(message)

    return jsonify({
        **result.to_dict(),
        'timestamp': datetime.now().isoformat(),
    })


@app.route('/api/brain/thoughts')
def brain_thoughts():
    """
    Get continuous background thoughts — Moltbook visualization endpoint.

    The brain is ALWAYS thinking. This endpoint returns the latest thoughts
    for the Moltbook dashboard to display as a "window into the brain".

    Query params:
        n: number of recent thoughts (default 20)
        since: timestamp — only return thoughts after this time
    """
    if not continuous_thinking:
        return jsonify({'thoughts': [], 'stats': {}, 'thinking': False})

    n = request.args.get('n', 20, type=int)
    since = request.args.get('since', 0.0, type=float)

    if since > 0:
        thoughts = continuous_thinking.get_thoughts_since(since)
    else:
        thoughts = continuous_thinking.get_recent_thoughts(n)

    return jsonify({
        'thoughts': [
            {
                'timestamp': t.timestamp,
                'content': t.content,
                'category': t.category,
                'topic': t.topic,
                'relevance': round(t.relevance, 3),
                'emotional_valence': round(t.emotional_valence, 3),
                'arousal': round(t.arousal, 3),
            }
            for t in thoughts
        ],
        'stats': continuous_thinking.get_stats(),
        'thinking': continuous_thinking.is_running,
        'mode': continuous_thinking.mode,
    })


@app.route('/api/brain/state')
def brain_state():
    """Full brain state: routing + thinking + knowledge."""
    chat_stats = brain_chat.get_stats() if brain_chat else {}
    thinking_stats = continuous_thinking.get_stats() if continuous_thinking else {}

    # Get the most recent thought
    recent_thoughts = []
    if continuous_thinking:
        recent = continuous_thinking.get_recent_thoughts(5)
        recent_thoughts = [
            {'content': t.content[:100], 'category': t.category, 'timestamp': t.timestamp}
            for t in recent
        ]

    return jsonify({
        'brain_chat': chat_stats,
        'continuous_thinking': thinking_stats,
        'recent_thoughts': recent_thoughts,
        'timestamp': datetime.now().isoformat(),
    })


# ═══════════════════════════════════════════════════════════════════
# Legacy API Routes (kept for backward compatibility)
# ═══════════════════════════════════════════════════════════════════

@app.route('/')
def index():
    return render_template('moltbook_dashboard.html')


@app.route('/api/state')
def get_state():
    """Full system overview."""
    all_entries = store.get_active_entries(top_k=500)
    sources, types = {}, {}
    total_conf, total_rel = 0.0, 0.0
    for e in all_entries:
        sources[e.source_agent] = sources.get(e.source_agent, 0) + 1
        types[e.entry_type] = types.get(e.entry_type, 0) + 1
        total_conf += e.confidence
        total_rel += e.relevance_score
    n = len(all_entries) or 1

    return jsonify({
        'store': {
            'total_entries': len(all_entries),
            'sources': sources,
            'types': types,
            'avg_confidence': round(total_conf / n, 3),
            'avg_relevance': round(total_rel / n, 3),
        },
        'feeder': feeder.get_stats() if feeder else {},
        'evaluation': evaluation_agent.get_stats() if evaluation_agent else {},
        'curation': curation_agent.get_stats() if curation_agent else {},
        'research': research_agent.get_stats() if research_agent else {},
        'feedback': feedback_agent.get_stats() if feedback_agent else {},
        'pipeline': orchestrator.get_stats() if orchestrator else {},
        'forum': forum.get_stats() if forum else {},
        'brain_chat': brain_chat.get_stats() if brain_chat else {},
        'continuous_thinking': continuous_thinking.get_stats() if continuous_thinking else {},
        'timestamp': datetime.now().isoformat(),
    })


@app.route('/api/entries')
def get_entries():
    """Recent entries."""
    top_k = request.args.get('top_k', 30, type=int)
    raw = store.get_active_entries(top_k=min(top_k, 200))
    entries = []
    for e in raw:
        entries.append({
            'id': e.id,
            'content': e.content[:300],
            'source': e.source_agent,
            'type': e.entry_type,
            'confidence': round(e.confidence, 3),
            'relevance': round(e.relevance_score, 3),
            'tags': list(e.tags),
            'accessed': e.accessed_count,
            'age_hours': round((time.time() - e.created_at) / 3600, 1),
        })
    return jsonify({'entries': entries, 'count': len(entries)})


@app.route('/api/search', methods=['POST'])
def search():
    """Semantic search."""
    data = request.json or {}
    query = data.get('query', '')
    top_k = data.get('top_k', 10)
    if not query:
        return jsonify({'error': 'No query'}), 400
    raw = store.query_semantic(query, top_k=top_k, threshold=0.05)
    results = [{
        'id': e.id,
        'content': e.content[:300],
        'source': e.source_agent,
        'confidence': round(e.confidence, 3),
        'relevance': round(e.relevance_score, 3),
        'tags': list(e.tags),
    } for e in raw]
    return jsonify({'results': results, 'count': len(results), 'query': query})


@app.route('/api/feed', methods=['POST'])
def feed():
    """Feed new knowledge via Feeder."""
    data = request.json or {}
    content = data.get('content', '')
    tags = data.get('tags', [])
    confidence = data.get('confidence', 0.6)
    if not content:
        return jsonify({'error': 'No content'}), 400
    entry = feeder.post(content=content, tags=tags, confidence=confidence)
    return jsonify({
        'success': True,
        'entry_id': entry.id,
        'content': entry.content[:200],
    })


@app.route('/api/orchestrate', methods=['POST'])
def orchestrate():
    """
    Legacy pipeline endpoint — now delegates to BrainChat.

    If BrainChat is available, routes through it (Thalamus routing).
    Falls back to the old ThinkTalkOrchestrator if not.
    """
    data = request.json or {}
    prompt = data.get('prompt', '')
    if not prompt:
        return jsonify({'error': 'No prompt'}), 400
    t0 = time.time()

    # NEW: Route through BrainChat if available
    if brain_chat:
        result = brain_chat.send(prompt)
        elapsed = round((time.time() - t0) * 1000, 1)

        # Auto-trigger forum discussion
        discussion_data = None
        if forum:
            try:
                thread = forum.discuss(prompt, top_k=5)
                discussion_data = thread.to_dict()
            except Exception:
                pass

        # Direct retrieval so we can show context entries in UI
        context_entries = []
        try:
            scored_entries = store.query_semantic(prompt, top_k=5, threshold=0.05, return_scores=True)
            if scored_entries:
                context_entries = [{
                    'id': e.id,
                    'content': e.content[:200],
                    'confidence': round(e.confidence, 3),
                    'relevance': round(e.relevance_score, 3),
                    'similarity': round(sim, 4),
                    'combined_score': round(comb, 4),
                    'tags': list(e.tags),
                    'source': e.source_agent,
                } for e, sim, comb in scored_entries]
        except Exception:
            pass

        return jsonify({
            'analysis': {
                'intent': result.task_type,
                'routing_mode': result.routing_mode,
                'dominant_areas': result.dominant_areas,
            },
            'response': {
                'text': result.response_text,
                'confidence': round(result.confidence, 3),
                'sources': result.sources,
                'quality_passed': True,
            },
            'context_entries': context_entries,
            'discussion': discussion_data,
            'routing': {
                'mode': result.routing_mode,
                'weights': result.routing_weights[:10] if result.routing_weights else [],
                'dominant_areas': result.dominant_areas,
                'task_type': result.task_type,
            },
            'thought_trace': [
                {
                    'timestamp': t.timestamp,
                    'category': t.category,
                    'content': t.content,
                    'module': t.module,
                }
                for t in result.thought_trace
            ],
            'timing': {
                'routing_ms': round(result.routing_time_ms, 1),
                'think_ms': round(result.thinking_time_ms, 1),
                'speak_ms': round(result.speaking_time_ms, 1),
                'total_ms': round(result.total_time_ms, 1),
            },
            'stats': {
                'augmented': result.augmented,
                'augment_source': result.augment_source,
            },
            'elapsed_ms': elapsed,
            'timestamp': datetime.now().isoformat(),
        })

    # FALLBACK: Legacy pipeline (if BrainChat not wired)
    context_entries = []
    try:
        scored_entries = store.query_semantic(prompt, top_k=5, threshold=0.05, return_scores=True)
        if scored_entries:
            context_entries = [{
                'id': e.id,
                'content': e.content[:200],
                'confidence': round(e.confidence, 3),
                'relevance': round(e.relevance_score, 3),
                'similarity': round(sim, 4),
                'combined_score': round(comb, 4),
                'tags': list(e.tags),
                'source': e.source_agent,
            } for e, sim, comb in scored_entries]
        else:
            raw_entries = store.get_active_entries(top_k=5)
            context_entries = [{
                'id': e.id,
                'content': e.content[:200],
                'confidence': round(e.confidence, 3),
                'relevance': round(e.relevance_score, 3),
                'similarity': 0.0,
                'combined_score': 0.0,
                'tags': list(e.tags),
                'source': e.source_agent,
            } for e in raw_entries]
    except Exception:
        pass

    result = orchestrator.process(prompt)

    # Auto-trigger forum discussion
    discussion_data = None
    if forum:
        try:
            thread = forum.discuss(prompt, top_k=5)
            discussion_data = thread.to_dict()
        except Exception:
            pass

    elapsed = round((time.time() - t0) * 1000, 1)

    analysis_dict = {}
    if result.input_analysis:
        analysis_dict = {
            'intent': result.input_analysis.intent,
            'complexity': round(result.input_analysis.complexity, 3),
            'urgency': round(result.input_analysis.urgency, 3),
            'topics': result.input_analysis.topics,
            'emotional_tone': round(result.input_analysis.emotional_tone, 3),
            'expected_length': result.input_analysis.expected_length,
        }

    return jsonify({
        'analysis': analysis_dict,
        'response': {
            'text': result.response_text,
            'confidence': round(result.confidence, 3),
            'sources': result.sources,
            'quality_passed': result.quality_passed,
        },
        'context_entries': context_entries,
        'discussion': discussion_data,
        'timing': {
            'think_ms': round(result.think_time_ms, 1),
            'speak_ms': round(result.speak_time_ms, 1),
            'retrieve_ms': round(result.retrieve_time_ms, 1),
            'total_ms': round(result.total_time_ms, 1),
        },
        'stats': {
            'entries_retrieved': result.entries_retrieved,
            'speculative_hits': result.speculative_hits,
            'thoughts_consulted': result.thoughts_consulted,
        },
        'elapsed_ms': elapsed,
        'timestamp': datetime.now().isoformat(),
    })



@app.route('/api/evaluate', methods=['POST'])
def evaluate():
    """Evaluate an entry by ID."""
    data = request.json or {}
    entry_id = data.get('entry_id', '')
    if not entry_id:
        return jsonify({'error': 'No entry_id'}), 400
    entry = store.get_entry(entry_id)
    if not entry:
        return jsonify({'error': 'Entry not found'}), 404
    result = evaluation_agent.evaluate(entry)
    return jsonify({
        'entry_id': entry_id,
        'score': round(result.score, 3),
        'relevance': round(result.relevance, 3),
        'novelty': round(result.novelty, 3),
        'consistency': round(result.consistency, 3),
        'action': result.action,
    })


@app.route('/api/curate', methods=['POST'])
def curate():
    """Run curation cycle."""
    actions = curation_agent.curate()
    return jsonify({
        'actions': [{
            'action_type': a.action_type,
            'entry_ids': a.entry_ids,
            'reason': a.reason,
        } for a in actions],
        'count': len(actions),
    })


@app.route('/api/feedback', methods=['POST'])
def record_feedback():
    """Record user feedback."""
    data = request.json or {}
    sentiment = data.get('sentiment', 0.0)
    entry_ids = data.get('entry_ids', [])
    correction = data.get('correction', None)
    feedback_agent.record_feedback(
        sentiment=sentiment,
        contributing_entry_ids=entry_ids,
        correction=correction,
    )
    return jsonify({'success': True, 'stats': feedback_agent.get_stats()})


@app.route('/api/research/cycle', methods=['POST'])
def research_cycle():
    """Run one research agent cycle."""
    gaps = research_agent.check_for_gaps()
    results = []
    for gap in gaps[:3]:
        r = research_agent.process_gap(gap)
        if r:
            results.append({
                'topic': gap.get('topic', 'unknown'),
                'entry_id': r.id,
                'content': r.content[:200],
            })
    return jsonify({'gaps_found': len(gaps), 'researched': results})


@app.route('/api/debug')
def get_debug():
    """Debug stream output."""
    n = request.args.get('n', 30, type=int)
    if debug_stream:
        return jsonify({
            'enabled': debug_stream.enabled,
            'entries': debug_stream.get_recent(n),
            'formatted': debug_stream.get_formatted(n),
            'stats': debug_stream.get_stats(),
        })
    return jsonify({'enabled': False, 'entries': [], 'formatted': ''})


# ── Forum: Multi-Agent Discussion ─────────────────────────────────

@app.route('/api/forum/discuss', methods=['POST'])
def forum_discuss():
    """Run a multi-agent discussion about a topic."""
    data = request.json or {}
    query = data.get('query', data.get('topic', ''))
    if not query:
        return jsonify({'error': 'No query/topic'}), 400
    thread = forum.discuss(query, top_k=data.get('top_k', 5))
    return jsonify(thread.to_dict())


@app.route('/api/forum/history')
def forum_history():
    """Get recent discussion history."""
    n = request.args.get('n', 10, type=int)
    return jsonify({
        'discussions': forum.get_recent_discussions(n),
        'total': forum._total_discussions,
    })


@app.route('/api/graph')
def get_graph():
    """Get knowledge graph structure for visualization."""
    nodes = []
    edges = []
    edge_set = set()  # track (src,dst) to avoid duplicates
    all_entries = store.get_active_entries(top_k=100)
    for e in all_entries:
        nodes.append({
            'id': e.id,
            'label': e.content[:40],
            'source': e.source_agent,
            'confidence': round(e.confidence, 3),
            'tags': list(e.tags),
        })
    # Explicit graph edges
    if graph:
        for src_id, neighbors in graph._edges.items():
            for dst_id, edge_data in neighbors.items():
                key = (src_id, dst_id)
                if key not in edge_set:
                    edge_set.add(key)
                    edges.append({
                        'source': src_id,
                        'target': dst_id,
                        'type': edge_data.get('type', 'related'),
                        'weight': round(edge_data.get('weight', 0.5), 3),
                    })
    # Inferred edges: entries sharing tags
    tag_map = {}
    for e in all_entries:
        for tag in e.tags:
            tag_map.setdefault(tag, []).append(e.id)
    for tag, ids in tag_map.items():
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                key = tuple(sorted([ids[i], ids[j]]))
                if key not in edge_set:
                    edge_set.add(key)
                    edges.append({
                        'source': ids[i],
                        'target': ids[j],
                        'type': f'shared:{tag}',
                        'weight': 0.6,
                    })
    # Inferred edges: semantic similarity between entries
    if len(all_entries) <= 50:
        idx = store._semantic_index
        for i, e1 in enumerate(all_entries):
            if e1.semantic_embedding is None:
                continue
            for j in range(i + 1, len(all_entries)):
                e2 = all_entries[j]
                if e2.semantic_embedding is None:
                    continue
                key = tuple(sorted([e1.id, e2.id]))
                if key in edge_set:
                    continue
                sim = float(e1.semantic_embedding @ e2.semantic_embedding)
                if sim > 0.15:
                    edge_set.add(key)
                    edges.append({
                        'source': e1.id,
                        'target': e2.id,
                        'type': 'semantic',
                        'weight': round(sim, 3),
                    })
    return jsonify({'nodes': nodes, 'edges': edges})


# ── Main ───────────────────────────────────────────────────────────

if __name__ == '__main__':
    print("=" * 60)
    print("  MOLTBOOK DASHBOARD — THE BRAIN IS ALWAYS THINKING")
    print("=" * 60)
    initialize_moltbook()
    print("=" * 60)
    print("  http://localhost:5006")
    print("  Chat: POST /api/brain/chat  {'message': '...'}")
    print("  Thoughts: GET /api/brain/thoughts")
    print("=" * 60)
    app.run(host='0.0.0.0', port=5006, debug=False)
