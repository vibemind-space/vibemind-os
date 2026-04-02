"""
Exploration Tools - Voice-callable tools for AI-Scientist-style idea exploration.

CANONICAL LOCATION - DO NOT MODIFY swarm/tools/exploration_tools.py directly.
That file re-exports from here for backward compatibility.

These tools integrate with the IdeaTreeSearch to provide voice-controlled
exploration of connections between ideas/bubbles.

Supports three exploration modes:
- auto: Autonomous exploration, results shown at end
- interactive: Asks user about each discovered connection
- guided: User steers exploration direction
"""

import asyncio
import json
import logging
import os
from typing import Optional, Dict, Any, List, Callable
from functools import wraps
from pathlib import Path

from llm_config import get_model

logger = logging.getLogger(__name__)

# Database path - resolve from spaces/ideas/tools/ to python/vibemind.db
_DB_PATH = Path(__file__).parent.parent.parent.parent / "vibemind.db"

# Global exploration state (singleton pattern for tool access)
_exploration_state: Dict[str, Any] = {
    "searcher": None,
    "clarification_agent": None,
    "current_session_id": None,
    "is_running": False,
    "exploration_mode": "auto",  # auto, interactive, guided
}


def _get_db_connection():
    """Get raw database connection for ExplorationRepository."""
    try:
        from data.database import get_database
        import sqlite3
        db = get_database()
        # Return raw SQLite connection (not the Database wrapper)
        # The repository needs cursor() and commit() methods
        conn = sqlite3.connect(str(db.db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn
    except ImportError:
        logger.warning("Database connection not available")
        return None


def _get_embedding_service():
    """Get embedding service."""
    try:
        from data.embedding_service import get_embedding_service
        return get_embedding_service()
    except ImportError:
        logger.warning("Embedding service not available")
        return None


def _get_electron_backend():
    """Get Electron backend for bubble access."""
    try:
        from electron_backend import get_backend
        return get_backend()
    except ImportError:
        logger.warning("Electron backend not available")
        return None


def _broadcast_event(event_type: str, data: Dict[str, Any]) -> None:
    """Broadcast an event to Electron frontend."""
    # Try standard workspace_tools pattern first
    try:
        from tools.workspace_tools import _broadcast_to_electron
        message = {"type": event_type, **data}
        _broadcast_to_electron(message)
        return
    except ImportError:
        pass

    # Fallback to direct backend access
    backend = _get_electron_backend()
    if backend:
        message = {"type": event_type, **data}
        backend.send_message(message)
    else:
        logger.debug(f"No backend to broadcast: {event_type}")


async def _synthesize_voice(text: str) -> None:
    """Synthesize voice using Rachel (if available)."""
    try:
        # Try TTS Queue first (best option for VibeMind)
        try:
            from swarm.tts_queue import TTSQueue, TTSPriority
            from swarm.event_buffer import get_event_buffer

            event_buffer = get_event_buffer()
            if event_buffer and hasattr(event_buffer, 'tts_queue') and event_buffer.tts_queue:
                await event_buffer.tts_queue.enqueue(
                    text,
                    priority=TTSPriority.USER_AGENT,
                    agent_name="Explorer"
                )
                return
        except (ImportError, AttributeError):
            pass

        # Try VoiceBridge (alternative option)
        backend = _get_electron_backend()
        if backend:
            if hasattr(backend, 'voice_bridge') and backend.voice_bridge:
                # Check if voice_bridge has async speak
                if hasattr(backend.voice_bridge, 'speak_async'):
                    await backend.voice_bridge.speak_async(text)
                elif hasattr(backend.voice_bridge, 'speak'):
                    backend.voice_bridge.speak(text)
                return
            elif hasattr(backend, 'voice_dialog') and backend.voice_dialog:
                # Fallback to voice_dialog
                if hasattr(backend.voice_dialog, 'speak'):
                    backend.voice_dialog.speak(text)
                return

        # Final fallback: just broadcast the text as a message
        _broadcast_event("exploration_voice", {
            "text": text,
            "agent": "Explorer"
        })
        logger.debug(f"Broadcasted voice text: {text[:50]}...")

    except Exception as e:
        logger.warning(f"Voice synthesis failed: {e}")


async def start_exploration(
    bubble_id: Optional[str] = None,
    depth: int = 4,
    context: Optional[str] = None,
    mode: str = "auto",  # "auto", "interactive", "guided"
) -> Dict[str, Any]:
    """
    Start exploring connections for a bubble.

    Voice triggers:
    - "Finde tiefere Verbindungen"
    - "Erforsche Zusammenhänge"
    - "Erkunde diese Idee"
    - "Finde Verbindungen interaktiv" (interactive mode)
    - "Finde Verbindungen automatisch" (auto mode)

    Args:
        bubble_id: Optional bubble ID to explore from (uses current if not specified)
        depth: Exploration depth 1-4 (default: all 4 stages)
        context: Optional context/query for exploration
        mode: Exploration mode - "auto", "interactive", or "guided"

    Returns:
        Dict with session_id and initial status
    """
    global _exploration_state

    if _exploration_state["is_running"]:
        return {
            "success": False,
            "message": "Eine Exploration läuft bereits. Stoppe sie zuerst mit 'Stopp Exploration'.",
            "session_id": _exploration_state["current_session_id"],
        }

    try:
        # Get components
        embedding_service = _get_embedding_service()
        backend = _get_electron_backend()

        if not embedding_service:
            return {
                "success": False,
                "message": "Embedding-Service nicht verfügbar.",
            }

        # Get current bubble if not specified
        if not bubble_id and backend:
            current_bubble = backend.current_bubble
            if current_bubble:
                bubble_id = current_bubble.get("id")

        # If no bubble_id, use first available bubble
        if not bubble_id:
            logger.debug("No bubble_id specified, will use first bubble after loading")
            # bubble_id will be set after we get all_bubbles

        # Get all bubbles
        all_bubbles = []
        if backend and hasattr(backend, 'get_all_bubbles_with_embeddings'):
            all_bubbles = backend.get_all_bubbles_with_embeddings()

        # Fallback: Get bubbles directly from database
        if len(all_bubbles) < 2:
            try:
                from data import IdeasRepository
                import json

                repo = IdeasRepository()
                ideas = repo.list(limit=100)

                for idea in ideas:
                    if idea.parent_id:
                        continue  # Skip child ideas

                    bubble = {
                        "id": idea.id,
                        "title": idea.title,
                        "description": idea.description or "",
                    }
                    if idea.embedding_vector:
                        try:
                            # Store as embedding_vector (key expected by ConnectionEvaluator)
                            # Handle both already-parsed list and JSON string
                            if isinstance(idea.embedding_vector, list):
                                bubble["embedding_vector"] = idea.embedding_vector
                            elif isinstance(idea.embedding_vector, str):
                                bubble["embedding_vector"] = json.loads(idea.embedding_vector)
                            else:
                                bubble["embedding_vector"] = None
                            bubble["embedding"] = bubble["embedding_vector"]  # Also store as "embedding" for compatibility
                        except (json.JSONDecodeError, TypeError):
                            bubble["embedding_vector"] = None
                            bubble["embedding"] = None
                    else:
                        bubble["embedding_vector"] = None
                        bubble["embedding"] = None

                    all_bubbles.append(bubble)

                logger.debug(f"Loaded {len(all_bubbles)} bubbles from database")
            except Exception as e:
                logger.warning(f"Failed to load bubbles from database: {e}")

        if len(all_bubbles) < 2:
            return {
                "success": False,
                "message": "Nicht genügend Bubbles für Exploration. Erstelle mehr Ideen.",
            }

        # Find root bubble
        root_bubble = None

        # If no bubble_id specified, use first bubble with embedding
        if not bubble_id:
            for b in all_bubbles:
                if b.get("embedding"):
                    root_bubble = b
                    bubble_id = b.get("id")
                    logger.debug(f"Using first bubble with embedding: {b.get('title')}")
                    break

        # Search for specified bubble_id
        if not root_bubble:
            for b in all_bubbles:
                if b.get("id") == bubble_id:
                    root_bubble = b
                    break

        if not root_bubble:
            # Last resort: use first bubble
            if all_bubbles:
                root_bubble = all_bubbles[0]
                bubble_id = root_bubble.get("id")
                logger.debug(f"Using first available bubble: {root_bubble.get('title')}")
            else:
                return {
                    "success": False,
                    "message": "Keine Bubbles gefunden.",
                }

        # Import and create searcher
        from spaces.ideas.explorer import (
            ConnectionEvaluator,
            ExplorationRepository,
            ExplorationClarificationAgent,
            ExplorationMode,
            InteractiveExplorationConfig,
        )
        from spaces.ideas.explorer.idea_tree_search import (
            IdeaTreeSearch,
            ExplorationConfig,
            ExplorationStage,
        )

        # Create evaluator
        evaluator = ConnectionEvaluator(embedding_service=embedding_service)

        # Create search config
        config = ExplorationConfig()

        # Create clarification agent for interactive modes
        clarification_agent = None
        interactive_config = None
        exploration_mode = ExplorationMode.AUTO

        if mode == "interactive":
            exploration_mode = ExplorationMode.INTERACTIVE
        elif mode == "guided":
            exploration_mode = ExplorationMode.GUIDED

        if exploration_mode != ExplorationMode.AUTO:
            interactive_config = InteractiveExplorationConfig(
                mode=exploration_mode,
                ask_on_discovery=True,
                ask_between_stages=True,
                use_voice=True,
                use_ui=True,
            )

            # Create event broadcaster wrapper
            async def event_broadcaster(event_type: str, payload: Dict) -> None:
                _broadcast_event(event_type, payload)

            clarification_agent = ExplorationClarificationAgent(
                config=interactive_config,
                event_broadcaster=event_broadcaster,
                voice_synthesizer=_synthesize_voice,
            )
            _exploration_state["clarification_agent"] = clarification_agent

        _exploration_state["exploration_mode"] = mode

        # Callback for discovered nodes
        async def on_node_discovered(node):
            """Broadcast node discovery to Electron."""
            _broadcast_event("exploration_node_discovered", {
                "node": node.to_visualization_dict(),
            })
            logger.info(f"Discovered: {node.source_bubble_title} -> {node.target_bubble_title}")

        # Callback for stage completion
        async def on_stage_complete(stage, nodes):
            """Broadcast stage completion."""
            _broadcast_event("exploration_stage_complete", {
                "stage": stage.name,
                "stage_number": stage.value,
                "nodes_count": len(nodes),
            })
            logger.info(f"Stage {stage.name} complete with {len(nodes)} nodes")

        # Create searcher with clarification agent
        searcher = IdeaTreeSearch(
            evaluator=evaluator,
            config=config,
            on_node_discovered=on_node_discovered,
            on_stage_complete=on_stage_complete,
            clarification_agent=clarification_agent,
            interactive_config=interactive_config,
        )

        # Determine stages to run
        stages = None
        if depth < 4:
            stages = [ExplorationStage(i) for i in range(1, depth + 1)]

        # Update state
        _exploration_state["searcher"] = searcher
        _exploration_state["is_running"] = True

        # Start exploration in background
        async def run_exploration():
            try:
                journal = await searcher.explore(
                    root_bubble=root_bubble,
                    all_bubbles=all_bubbles,
                    query=context or "",
                    stages=stages,
                    mode=exploration_mode,
                )

                _exploration_state["current_session_id"] = journal.session.id if journal.session else None

                # Save to database
                db = _get_db_connection()
                if db:
                    repo = ExplorationRepository(db)
                    repo.save_journal(journal)

                # Broadcast completion
                _broadcast_event("exploration_complete", {
                    "session_id": _exploration_state["current_session_id"],
                    "stats": journal.get_stats(),
                    "summary": journal.generate_summary(),
                    "mode": mode,
                })

                # Voice feedback on completion
                if mode != "interactive":  # Interactive already has voice feedback
                    summary = journal.generate_summary()
                    await _synthesize_voice(summary)

            except Exception as e:
                logger.error(f"Exploration failed: {e}")
                _broadcast_event("exploration_error", {
                    "error": str(e),
                })
            finally:
                _exploration_state["is_running"] = False
                _exploration_state["clarification_agent"] = None

        # Run in background
        asyncio.create_task(run_exploration())

        mode_message = ""
        if mode == "interactive":
            mode_message = " Im interaktiven Modus werde ich dich bei jeder Verbindung fragen."
        elif mode == "guided":
            mode_message = " Du kannst mir die Richtung vorgeben."

        return {
            "success": True,
            "message": f"Exploration gestartet für '{root_bubble.get('title', 'Unbekannt')}'. Ich suche nach Verbindungen...{mode_message}",
            "root_bubble": root_bubble.get("title"),
            "stages": depth,
            "mode": mode,
        }

    except Exception as e:
        logger.error(f"Failed to start exploration: {e}")
        _exploration_state["is_running"] = False
        return {
            "success": False,
            "message": f"Fehler beim Starten: {str(e)}",
        }


async def stop_exploration() -> Dict[str, Any]:
    """
    Stop the current exploration.

    Voice triggers:
    - "Stopp Exploration"
    - "Beende Suche"
    """
    global _exploration_state

    if not _exploration_state["is_running"]:
        return {
            "success": False,
            "message": "Keine Exploration läuft gerade.",
        }

    searcher = _exploration_state.get("searcher")
    if searcher:
        searcher.stop()

    return {
        "success": True,
        "message": "Exploration wird gestoppt...",
    }


async def get_exploration_status() -> Dict[str, Any]:
    """
    Get the status of the current exploration.

    Voice triggers:
    - "Exploration Status"
    - "Wie weit bist du?"
    """
    logger.debug("get_exploration_status: checking state")
    global _exploration_state

    if not _exploration_state["is_running"]:
        return {
            "status": "idle",
            "message": "Keine Exploration läuft gerade.",
        }

    searcher = _exploration_state.get("searcher")
    if searcher:
        progress = searcher.get_progress()
        return {
            "status": "running",
            "stage": progress.get("stage"),
            "stage_number": progress.get("stage_number"),
            "nodes_discovered": progress.get("nodes_discovered", 0),
            "best_score": progress.get("best_score", 0.0),
            "message": f"Stage {progress.get('stage_number', '?')}/4: {progress.get('nodes_discovered', 0)} Verbindungen gefunden.",
        }

    return {
        "status": "unknown",
        "message": "Status unbekannt.",
    }


async def accept_connection(connection_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Accept a discovered connection (saves it permanently).

    Voice triggers:
    - "Akzeptiere diese Verbindung"
    - "Speichere Verbindung"
    """
    logger.debug("accept_connection: connection_id=%s", connection_id)
    global _exploration_state

    searcher = _exploration_state.get("searcher")
    if not searcher or not searcher.journal:
        return {
            "success": False,
            "message": "Keine Exploration-Ergebnisse vorhanden.",
        }

    # If no ID specified, accept the best connection
    if not connection_id:
        best = searcher.journal.get_best_node()
        if best:
            connection_id = best.id

    if not connection_id:
        return {
            "success": False,
            "message": "Keine Verbindung zum Akzeptieren gefunden.",
        }

    # Find and mark as accepted
    node = searcher.journal.get_node_by_id(connection_id)
    if not node:
        return {
            "success": False,
            "message": f"Verbindung {connection_id} nicht gefunden.",
        }

    node.is_accepted = True

    # Save to discovered_edges
    db = _get_db_connection()
    if db:
        from spaces.ideas.explorer import ExplorationRepository
        repo = ExplorationRepository(db)
        edge_id = repo.save_discovered_edge(
            node,
            _exploration_state.get("current_session_id")
        )

        # Also update node status in exploration_nodes
        repo.update_node_status(node.id, is_accepted=True)

    # Broadcast to frontend
    backend = _get_electron_backend()
    if backend:
        backend.broadcast({
            "type": "connection_accepted",
            "edge": node.to_edge_dict(),
        })

    return {
        "success": True,
        "message": f"Verbindung '{node.source_bubble_title}' ↔ '{node.target_bubble_title}' gespeichert.",
        "edge_label": node.edge_label,
    }


async def reject_connection(connection_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Reject a discovered connection.

    Voice triggers:
    - "Lehne ab"
    - "Diese Verbindung ist nicht gut"
    """
    logger.debug("reject_connection: connection_id=%s", connection_id)
    global _exploration_state

    searcher = _exploration_state.get("searcher")
    if not searcher or not searcher.journal:
        return {
            "success": False,
            "message": "Keine Exploration-Ergebnisse vorhanden.",
        }

    # If no ID specified, reject the most recently shown
    if not connection_id:
        # Get the last node
        if searcher.journal.nodes:
            connection_id = searcher.journal.nodes[-1].id

    if not connection_id:
        return {
            "success": False,
            "message": "Keine Verbindung zum Ablehnen gefunden.",
        }

    node = searcher.journal.get_node_by_id(connection_id)
    if not node:
        return {
            "success": False,
            "message": f"Verbindung {connection_id} nicht gefunden.",
        }

    node.is_rejected = True
    node.is_valid = False

    # Update in database
    db = _get_db_connection()
    if db:
        from spaces.ideas.explorer import ExplorationRepository
        repo = ExplorationRepository(db)
        repo.update_node_status(node.id, is_rejected=True)

    return {
        "success": True,
        "message": f"Verbindung abgelehnt.",
    }


async def explore_deeper() -> Dict[str, Any]:
    """
    Go one stage deeper in exploration.

    Voice triggers:
    - "Gehe tiefer"
    - "Erkunde weiter"
    """
    global _exploration_state

    if not _exploration_state["is_running"]:
        return {
            "success": False,
            "message": "Keine Exploration läuft. Starte mit 'Finde tiefere Verbindungen'.",
        }

    searcher = _exploration_state.get("searcher")
    if searcher:
        progress = searcher.get_progress()
        current_stage = progress.get("stage_number", 0)

        if current_stage >= 4:
            return {
                "success": False,
                "message": "Bereits auf maximaler Tiefe (Stage 4).",
            }

        return {
            "success": True,
            "message": f"Exploration läuft bereits auf Stage {current_stage}. Warte auf Abschluss...",
        }

    return {
        "success": False,
        "message": "Exploration-Status unbekannt.",
    }


async def visualize_exploration() -> Dict[str, Any]:
    """
    Get visualization data for exploration results.

    Voice triggers:
    - "Zeige gefundene Verbindungen"
    - "Was hast du gefunden?"
    """
    logger.debug("visualize_exploration: fetching visualization data")
    global _exploration_state

    searcher = _exploration_state.get("searcher")
    if not searcher or not searcher.journal:
        return {
            "success": False,
            "message": "Keine Exploration-Ergebnisse vorhanden.",
        }

    journal = searcher.journal
    viz_data = journal.to_visualization_data()

    # Generate voice summary
    summary = journal.generate_summary(include_reasoning=True)

    # Broadcast to frontend
    _broadcast_event("exploration_visualization", {
        "data": viz_data,
    })

    return {
        "success": True,
        "message": summary,
        "stats": journal.get_stats(),
        "best_connections": [n.to_visualization_dict() for n in journal.get_best_nodes(top_k=5)],
    }


async def respond_to_exploration_question(
    question_id: str,
    response_type: str,
    selected_option: Optional[str] = None,
    custom_text: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Respond to an exploration question (from UI or voice).

    This is called by the Electron frontend when user clicks a button
    or by voice recognition when user responds verbally.

    Args:
        question_id: ID of the question being answered
        response_type: Type of response - 'accept', 'reject', 'explore_deeper', 'continue', 'stop'
        selected_option: Selected option label (if applicable)
        custom_text: Custom text response (for free-form responses)

    Returns:
        Dict with success status
    """
    global _exploration_state

    clarification_agent = _exploration_state.get("clarification_agent")
    if not clarification_agent:
        return {
            "success": False,
            "message": "Kein aktiver Clarification-Agent.",
        }

    success = clarification_agent.handle_external_response(
        question_id=question_id,
        response_type=response_type,
        selected_option=selected_option,
        custom_text=custom_text,
    )

    return {
        "success": success,
        "message": "Antwort empfangen." if success else "Antwort konnte nicht verarbeitet werden.",
    }


async def generate_complete_research_paper(
    sections: List[Dict[str, Any]],
    paper_title: Optional[str] = None,
    target_journal: str = "general",
    citation_style: str = "APA",
) -> Dict[str, Any]:
    """
    Generate complete research paper using AI-Scientist methodology.

    Voice triggers:
    - "Generiere komplettes Paper"
    - "Schreibe Research Paper"
    - "Erstelle wissenschaftliches Paper"

    Args:
        sections: Parsed and optimized paper sections
        paper_title: Optional custom title
        target_journal: Target publication (general, nature, science, etc.)
        citation_style: Citation format (APA, MLA, Chicago, IEEE)

    Returns:
        Dict with complete paper, metadata, and quality metrics
    """
    try:
        if not sections:
            return {
                "success": False,
                "message": "Keine Abschnitte für Paper-Generierung vorhanden.",
            }

        # Generate complete paper
        paper_content = await _generate_full_paper(sections, paper_title, target_journal, citation_style)

        # Quality assessment
        quality_metrics = await _assess_paper_quality(paper_content)

        return {
            "success": True,
            "paper": paper_content,
            "quality_metrics": quality_metrics,
            "word_count": len(paper_content.get("full_text", "").split()),
            "section_count": len(paper_content.get("sections", [])),
            "message": f"Research Paper generiert: {len(paper_content.get('full_text', ''))} Zeichen",
        }

    except Exception as e:
        logger.error(f"Paper generation failed: {e}")
        return {
            "success": False,
            "message": f"Paper-Generierung fehlgeschlagen: {str(e)}",
        }

async def optimize_paper_coherence(
    sections: List[Dict[str, Any]],
    target_audience: str = "academic",
) -> Dict[str, Any]:
    """
    Optimize coherence and logical flow between paper sections.

    Voice triggers:
    - "Optimiere Paper-Fluss"
    - "Verbessere Kohärenz"
    - "Strukturiere Paper logisch"

    Args:
        sections: Parsed paper sections
        target_audience: Target audience (academic, industry, general)

    Returns:
        Dict with optimized sections and coherence analysis
    """
    try:
        if not sections or len(sections) < 2:
            return {
                "success": False,
                "message": "Mindestens 2 Abschnitte für Kohärenz-Optimierung benötigt.",
            }

        # Analyze current flow
        flow_analysis = await _analyze_section_flow(sections)

        # Optimize transitions and coherence
        optimized_sections = await _optimize_section_transitions(sections, flow_analysis, target_audience)

        return {
            "success": True,
            "optimized_sections": optimized_sections,
            "flow_analysis": flow_analysis,
            "coherence_score": flow_analysis.get("overall_coherence", 0.0),
            "message": f"Kohärenz optimiert. Score: {flow_analysis.get('overall_coherence', 0.0):.2f}",
        }

    except Exception as e:
        logger.error(f"Coherence optimization failed: {e}")
        return {
            "success": False,
            "message": f"Kohärenz-Optimierung fehlgeschlagen: {str(e)}",
        }

async def _analyze_section_flow(sections: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Analyze logical flow between sections."""
    try:
        client = _get_llm_client()

        sections_text = "\n".join([f"{s.get('type', 'unknown')}: {s.get('content', '')[:200]}" for s in sections])

        prompt = f"""
Analysiere den logischen Fluss zwischen diesen Paper-Abschnitten:

{sections_text}

Bewerte auf einer Skala von 0.0 bis 1.0:
- overall_coherence: Gesamte logische Kohärenz
- transition_quality: Qualität der Übergänge
- logical_progression: Logische Weiterentwicklung der Argumentation

Identifiziere auch:
- missing_transitions: Fehlende Übergänge
- logical_gaps: Logische Lücken
- improvement_suggestions: Verbesserungsvorschläge

Formatiere als JSON:
{{
  "overall_coherence": 0.8,
  "transition_quality": 0.7,
  "logical_progression": 0.9,
  "missing_transitions": ["Übergang von Intro zu Methods fehlt"],
  "logical_gaps": ["Begründung für Methodenwahl"],
  "improvement_suggestions": ["Füge Überleitung hinzu"]
}}
"""

        response = client.chat.completions.create(
            model=get_model("exploration"),
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=1500,
        )

        content = response.choices[0].message.content.strip()
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()

        return json.loads(content)

    except Exception as e:
        logger.error(f"Flow analysis failed: {e}")
        return {
            "overall_coherence": 0.5,
            "transition_quality": 0.5,
            "logical_progression": 0.5,
            "missing_transitions": [],
            "logical_gaps": ["Analyse fehlgeschlagen"],
            "improvement_suggestions": ["Manuelle Überprüfung empfohlen"]
        }

async def _optimize_section_transitions(
    sections: List[Dict[str, Any]],
    flow_analysis: Dict[str, Any],
    target_audience: str
) -> List[Dict[str, Any]]:
    """Optimize transitions between sections."""
    try:
        client = _get_llm_client()

        sections_text = "\n".join([f"{s.get('type', 'unknown')}: {s.get('content', '')[:300]}" for s in sections])

        prompt = f"""
Optimiere die Übergänge zwischen diesen Paper-Abschnitten für {target_audience} Publikum.

Aktuelle Abschnitte:
{sections_text}

Flow-Analyse:
{json.dumps(flow_analysis, indent=2)}

Generiere optimierte Abschnitte mit besseren Übergängen.
Füge bei Bedarf Überleitungen hinzu und verbessere die logische Progression.

Formatiere als JSON-Array von optimierten Abschnitten:
[{{
  "type": "introduction",
  "title": "Introduction",
  "content": "Optimierter Text mit besseren Übergängen...",
  "transitions": ["Verbindung zum nächsten Abschnitt"]
}}]
"""

        response = client.chat.completions.create(
            model=get_model("exploration"),
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=3000,
        )

        content = response.choices[0].message.content.strip()
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()

        optimized = json.loads(content)
        return optimized

    except Exception as e:
        logger.error(f"Transition optimization failed: {e}")
        # Return original sections if optimization fails
        return sections

async def _generate_full_paper(
    sections: List[Dict[str, Any]],
    paper_title: Optional[str],
    target_journal: str,
    citation_style: str
) -> Dict[str, Any]:
    """Generate complete research paper using AI-Scientist approach."""
    try:
        client = _get_llm_client()

        sections_text = "\n\n".join([f"## {s.get('title', s.get('type', 'Unknown'))}\n{s.get('content', '')}" for s in sections])

        prompt = f"""
Schreibe ein komplettes wissenschaftliches Research Paper basierend auf diesen Abschnitten.

Titel: {paper_title or 'Generated Research Paper'}
Ziel-Journal: {target_journal}
Zitierstil: {citation_style}

Verfügbare Abschnitte:
{sections_text}

Generiere ein vollständiges Paper mit:
1. Titel und Abstract
2. Einleitung
3. Methodik
4. Ergebnisse
5. Diskussion
6. Schlussfolgerung
7. Literaturverzeichnis

Stelle sicher, dass:
- Logischer Fluss zwischen Abschnitten besteht
- Wissenschaftliche Standards eingehalten werden
- Alle wichtigen Punkte aus den Original-Abschnitten integriert sind
- Das Paper für {target_journal} geeignet ist

Formatiere als JSON:
{{
  "title": "Paper Titel",
  "abstract": "Zusammenfassung...",
  "sections": [
    {{
      "heading": "Introduction",
      "content": "Vollständiger Text...",
      "word_count": 450
    }}
  ],
  "full_text": "Komplettes Paper als zusammenhängender Text...",
  "references": ["Literaturverzeichnis"],
  "metadata": {{
    "word_count": 2500,
    "target_journal": "{target_journal}",
    "citation_style": "{citation_style}"
  }}
}}
"""

        response = client.chat.completions.create(
            model=get_model("exploration"),
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=6000,
        )

        content = response.choices[0].message.content.strip()
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()

        return json.loads(content)

    except Exception as e:
        logger.error(f"Full paper generation failed: {e}")
        # Fallback: simple concatenation
        full_text = "\n\n".join([f"# {s.get('title', s.get('type', ''))}\n\n{s.get('content', '')}" for s in sections])
        return {
            "title": paper_title or "Generated Paper",
            "full_text": full_text,
            "sections": sections,
            "metadata": {"fallback": True, "error": str(e)}
        }

async def _assess_paper_quality(paper_content: Dict[str, Any]) -> Dict[str, Any]:
    """Assess quality of generated paper."""
    try:
        client = _get_llm_client()

        paper_text = paper_content.get("full_text", "")

        prompt = f"""
Bewerte die Qualität dieses Research Papers auf einer Skala von 1-10:

{paper_text[:2000]}...

Bewerte:
- scientific_rigor: Wissenschaftliche Strenge (1-10)
- clarity: Klarheit der Argumentation (1-10)
- completeness: Vollständigkeit (1-10)
- flow: Logischer Fluss (1-10)
- originality: Originalität (1-10)

Formatiere als JSON:
{{
  "scientific_rigor": 8,
  "clarity": 7,
  "completeness": 9,
  "flow": 8,
  "originality": 6,
  "overall_score": 7.6,
  "strengths": ["Stärke 1"],
  "weaknesses": ["Verbesserungspunkt 1"],
  "recommendations": ["Empfehlung 1"]
}}
"""

        response = client.chat.completions.create(
            model=get_model("exploration"),
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=1000,
        )

        content = response.choices[0].message.content.strip()
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()

        assessment = json.loads(content)

        # Calculate overall score
        scores = [assessment.get(k, 5) for k in ["scientific_rigor", "clarity", "completeness", "flow", "originality"]]
        assessment["overall_score"] = round(sum(scores) / len(scores), 1)

        return assessment

    except Exception as e:
        logger.error(f"Quality assessment failed: {e}")
        return {
            "scientific_rigor": 5,
            "clarity": 5,
            "completeness": 5,
            "flow": 5,
            "originality": 5,
            "overall_score": 5.0,
            "error": str(e)
        }

async def generate_requirements_from_sections(
    sections: List[Dict[str, Any]],
    project_context: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Generate architectural requirements document from parsed sections.

    Voice triggers:
    - "Generiere Requirements aus Abschnitten"
    - "Erstelle Arch-Requirements"
    - "Mache Requirements-Dokument"

    Args:
        sections: Parsed paper sections from parse_bubble_content_for_paper
        project_context: Optional project context for requirements

    Returns:
        Dict with structured requirements document
    """
    try:
        if not sections:
            return {
                "success": False,
                "message": "Keine Abschnitte zum Generieren von Requirements.",
            }

        # Extract relevant content for requirements
        relevant_content = ""
        for section in sections:
            content_type = section.get("type", "").lower()
            if content_type in ["methodology", "experiments", "results", "discussion", "conclusion"]:
                relevant_content += f"\n{section.get('title', '')}: {section.get('content', '')}"

        if not relevant_content.strip():
            return {
                "success": False,
                "message": "Keine relevanten Abschnitte für Requirements gefunden.",
            }

        # Generate requirements using LLM
        requirements_doc = await _generate_requirements_with_llm(relevant_content, project_context)

        return {
            "success": True,
            "requirements": requirements_doc,
            "message": f"Requirements-Dokument mit {len(requirements_doc.get('requirements', []))} Anforderungen generiert.",
        }

    except Exception as e:
        logger.error(f"Requirements generation failed: {e}")
        return {
            "success": False,
            "message": f"Requirements-Generierung fehlgeschlagen: {str(e)}",
        }

async def parse_bubble_content_for_paper(
    bubble_id: Optional[str] = None,
    content_text: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Parse bubble content to extract research paper components.

    Voice triggers:
    - "Analysiere Bubble für Paper"
    - "Extrahiere Paper-Abschnitte"
    - "Parse Research Content"

    Args:
        bubble_id: Optional bubble ID to parse (uses current if not specified)
        content_text: Optional direct text content to parse

    Returns:
        Dict with extracted paper sections and metadata
    """
    try:
        # Get content from bubble if not provided directly
        if not content_text and bubble_id:
            # Use database path from module level
            import sqlite3
            conn = sqlite3.connect(str(_DB_PATH))
            cursor = conn.cursor()
            cursor.execute("SELECT content FROM canvas_nodes WHERE id = ?", (bubble_id,))
            row = cursor.fetchone()
            conn.close()
            if row and row[0]:
                content_text = row[0]

        if not content_text:
            return {
                "success": False,
                "message": "Keine Inhalte zum Parsen gefunden.",
            }

        # Use LLM to parse content into paper sections
        sections = await _parse_content_with_llm(content_text)

        return {
            "success": True,
            "bubble_id": bubble_id,
            "sections": sections,
            "section_count": len(sections),
            "message": f"{len(sections)} Paper-Abschnitte extrahiert.",
        }

    except Exception as e:
        logger.error(f"Content parsing failed: {e}")
        return {
            "success": False,
            "message": f"Parsing fehlgeschlagen: {str(e)}",
        }

async def set_exploration_direction(
    bubble_id: Optional[str] = None,
    direction: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Set the exploration direction (for guided mode).

    Voice triggers:
    - "Erkunde Richtung Marketing"
    - "Fokussiere auf KI"
    - "Geh in Richtung..."

    Args:
        bubble_id: Optional specific bubble to focus on
        direction: Text description of direction to explore

    Returns:
        Dict with status
    """
    global _exploration_state

    if not _exploration_state["is_running"]:
        return {
            "success": False,
            "message": "Keine Exploration läuft. Starte mit 'Finde Verbindungen guided'.",
        }

    if _exploration_state["exploration_mode"] != "guided":
        return {
            "success": False,
            "message": "Nicht im guided Modus. Starte mit 'Finde Verbindungen guided'.",
        }

    searcher = _exploration_state.get("searcher")
    if searcher and searcher.journal:
        searcher.journal.session.metadata["user_direction"] = direction
        searcher.journal.session.metadata["focus_bubble_id"] = bubble_id

        _broadcast_event("exploration_direction_set", {
            "direction": direction,
            "bubble_id": bubble_id,
        })

        return {
            "success": True,
            "message": f"Exploration fokussiert auf: {direction or bubble_id}",
        }

    return {
        "success": False,
        "message": "Exploration-Status unbekannt.",
    }


# ============================================================
# AutoGen-basiertes Multi-Agenten-Research-System
# ============================================================

# AutoGen Imports
try:
    from autogen_ext.runtimes.grpc import GrpcWorkerAgentRuntimeHost
    from autogen_agentchat.agents import AssistantAgent
    from autogen_agentchat.teams import DiGraphBuilder, GraphFlow
    from autogen_ext.models.openai import OpenAIChatCompletionClient
except ImportError as e:
    logger.warning(f"AutoGen nicht installiert. Installiere mit: pip install 'autogen-ext[grpc]'")
    # AutoGen Funktionen werden nicht verfügbar, wenn nicht installiert


async def conduct_autogen_research(
    topic: str,
    requirements: List[str],
    language: str = "de",
    max_concurrent_workers: int = 5,
) -> Dict[str, Any]:
    """
    Führe Multi-Agenten-Forschung mit AutoGen durch.

    Args:
        topic: Hauptthema des Papers
        requirements: Liste von Anforderungen/Features
        language: Sprache der Ausgabe
        max_concurrent_workers: Maximale Anzahl gleichzeitiger Worker Agents

    Returns:
        Dict mit Requirements, Paper und Quality Report
    """
    try:
        from spaces.ideas.tools.autogen_research import (
            get_research_system,
            conduct_autogen_research as _conduct_autogen_research,
            start_autogen_host,
            stop_autogen_host,
        )

        # Führe Forschung durch
        result = await _conduct_autogen_research(
            topic=topic,
            requirements=requirements,
            language=language,
            max_concurrent_workers=max_concurrent_workers,
        )

        return result

    except ImportError as e:
        logger.error(f"AutoGen import failed: {e}")
        return {
            "success": False,
            "message": f"AutoGen nicht installiert. Installiere mit: pip install 'autogen-ext[grpc]'"
        }
    except Exception as e:
        logger.error(f"AutoGen research failed: {e}")
        return {
            "success": False,
            "message": f"Forschung fehlgeschlagen: {str(e)}"
        }


async def explore_bubble_complete(
    bubble_id: Optional[str] = None,
    output_type: str = "paper",
    exploration_mode: str = "auto",
    depth: int = 4,
    target_journal: str = "general",
    citation_style: str = "APA",
) -> Dict[str, Any]:
    """
    One-Shot Bubble Exploration: Kombiniert Inter-Bubble und Intra-Bubble Exploration.

    Fuehrt automatisch die komplette Pipeline aus:
    1. parse_bubble_content_for_paper() -> sections
    2. start_exploration() -> connections (parallel, wenn output_type connections/all)
    3. generate_requirements_from_sections() -> requirements
    4. optimize_paper_coherence() -> optimized_sections
    5. generate_complete_research_paper() -> paper

    Voice-Trigger:
    - "Analysiere diese Bubble komplett"
    - "Generiere ein Paper aus dieser Bubble"
    - "Finde alle Verbindungen und erstelle Requirements"
    - "Komplette Analyse"

    Args:
        bubble_id: Optional Bubble ID (nutzt aktuelle Bubble wenn nicht angegeben)
        output_type: Was generiert werden soll:
            - "paper": Nur Paper generieren
            - "requirements": Nur Requirements generieren
            - "connections": Nur Verbindungen finden
            - "all": Alles (Paper + Requirements + Connections)
        exploration_mode: Modus fuer Verbindungssuche ("auto", "interactive", "guided")
        depth: Exploration-Tiefe 1-4 (default: 4)
        target_journal: Ziel-Journal fuer Paper (general, nature, science)
        citation_style: Zitierstil (APA, MLA, Chicago, IEEE)

    Returns:
        Dict mit paper, requirements, connections, quality_metrics
    """
    results = {
        "success": True,
        "bubble_id": bubble_id,
        "output_type": output_type,
        "connections": [],
        "sections": [],
        "requirements": {},
        "paper": {},
        "quality_metrics": {},
        "stages_completed": [],
    }

    try:
        # Get current bubble if not specified
        if not bubble_id:
            try:
                from swarm.context import get_bubble_context_provider
                ctx = get_bubble_context_provider().get_current_context()
                bubble_id = ctx.get("bubble_id")
                results["bubble_id"] = bubble_id
            except Exception:
                pass

        if not bubble_id:
            return {
                "success": False,
                "message": "Keine Bubble angegeben. Bitte gib eine Bubble ID an oder navigiere zuerst in eine Bubble.",
            }

        logger.info(f"[explore_bubble_complete] Starting for bubble {bubble_id}, output_type={output_type}")
        _broadcast_event("exploration_complete_started", {
            "bubble_id": bubble_id,
            "output_type": output_type,
        })

        # Step 1: Parse Bubble Content
        logger.info("[explore_bubble_complete] Step 1: Parsing bubble content...")
        parse_result = await parse_bubble_content_for_paper(bubble_id=bubble_id)
        if not parse_result.get("success"):
            return {
                "success": False,
                "message": f"Parse fehlgeschlagen: {parse_result.get('message')}",
                "stage": "parse",
            }
        results["sections"] = parse_result.get("sections", [])
        results["stages_completed"].append("parse")
        logger.info(f"[explore_bubble_complete] Parsed {len(results['sections'])} sections")

        # Step 2: Start Connection Exploration (parallel, non-blocking)
        exploration_task = None
        if output_type in ["connections", "all"]:
            logger.info("[explore_bubble_complete] Step 2: Starting connection exploration (async)...")
            exploration_task = asyncio.create_task(
                start_exploration(bubble_id=bubble_id, depth=depth, mode=exploration_mode)
            )

        # Step 3: Generate Requirements
        if output_type in ["requirements", "paper", "all"]:
            if results["sections"]:
                logger.info("[explore_bubble_complete] Step 3: Generating requirements...")
                req_result = await generate_requirements_from_sections(
                    sections=results["sections"]
                )
                if req_result.get("success"):
                    results["requirements"] = req_result.get("requirements", {})
                    results["stages_completed"].append("requirements")
                    logger.info(f"[explore_bubble_complete] Generated {len(results['requirements'])} requirements")
                else:
                    logger.warning(f"[explore_bubble_complete] Requirements generation failed: {req_result.get('message')}")

        # Step 4 & 5: Optimize Coherence and Generate Paper
        if output_type in ["paper", "all"]:
            if results["sections"]:
                logger.info("[explore_bubble_complete] Step 4: Optimizing coherence...")
                coherence_result = await optimize_paper_coherence(
                    sections=results["sections"]
                )
                if coherence_result.get("success"):
                    optimized_sections = coherence_result.get("optimized_sections", results["sections"])
                    results["stages_completed"].append("coherence")
                    logger.info(f"[explore_bubble_complete] Coherence score: {coherence_result.get('coherence_score', 0):.2f}")
                else:
                    optimized_sections = results["sections"]
                    logger.warning("[explore_bubble_complete] Coherence optimization failed, using original sections")

                # Step 5: Generate Paper
                logger.info("[explore_bubble_complete] Step 5: Generating paper...")
                paper_result = await generate_complete_research_paper(
                    sections=optimized_sections,
                    target_journal=target_journal,
                    citation_style=citation_style,
                )
                if paper_result.get("success"):
                    results["paper"] = paper_result.get("paper", {})
                    results["quality_metrics"] = paper_result.get("quality_metrics", {})
                    results["stages_completed"].append("paper")
                    logger.info(f"[explore_bubble_complete] Paper generated: {paper_result.get('word_count', 0)} words")
                else:
                    logger.warning(f"[explore_bubble_complete] Paper generation failed: {paper_result.get('message')}")

        # Wait for exploration if started
        if exploration_task:
            logger.info("[explore_bubble_complete] Waiting for connection exploration to complete...")
            try:
                exploration_result = await asyncio.wait_for(exploration_task, timeout=120.0)
                if exploration_result.get("success"):
                    results["connections"] = exploration_result.get("connections", [])
                    results["stages_completed"].append("connections")
                    logger.info(f"[explore_bubble_complete] Found {len(results['connections'])} connections")
            except asyncio.TimeoutError:
                logger.warning("[explore_bubble_complete] Connection exploration timed out")
                results["connections"] = []

        # Build summary message
        summary_parts = []
        if results["sections"]:
            summary_parts.append(f"{len(results['sections'])} Abschnitte geparst")
        if results["requirements"]:
            summary_parts.append(f"{len(results['requirements'])} Requirements generiert")
        if results["connections"]:
            summary_parts.append(f"{len(results['connections'])} Verbindungen gefunden")
        if results["paper"]:
            word_count = results.get("quality_metrics", {}).get("word_count", 0) or len(results["paper"].get("full_text", "").split())
            summary_parts.append(f"Paper mit {word_count} Woertern generiert")

        results["message"] = "Exploration abgeschlossen: " + ", ".join(summary_parts) if summary_parts else "Keine Ergebnisse"

        # Broadcast completion
        _broadcast_event("exploration_complete_finished", {
            "bubble_id": bubble_id,
            "output_type": output_type,
            "stages_completed": results["stages_completed"],
            "sections_count": len(results["sections"]),
            "connections_count": len(results["connections"]),
            "has_paper": bool(results["paper"]),
        })

        # Voice feedback
        await _synthesize_voice(results["message"])

        return results

    except Exception as e:
        logger.error(f"[explore_bubble_complete] Failed: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "message": f"Exploration fehlgeschlagen: {str(e)}",
            "stages_completed": results.get("stages_completed", []),
        }


# ============================================================
# Tool Registration for Voice Interface
# ============================================================

EXPLORATION_TOOLS = [
    {
        "name": "explore_bubble_complete",
        "description": "One-Shot Exploration: Analysiert Bubble komplett, findet Verbindungen, generiert Requirements und Paper in einem Schritt",
        "function": explore_bubble_complete,
        "parameters": {
            "bubble_id": {"type": "string", "description": "Optional: Bubble ID (nutzt aktuelle Bubble wenn leer)"},
            "output_type": {
                "type": "string",
                "description": "Was generiert werden soll: 'paper', 'requirements', 'connections', 'all'",
                "enum": ["paper", "requirements", "connections", "all"],
                "default": "paper",
            },
            "exploration_mode": {
                "type": "string",
                "description": "Modus fuer Verbindungssuche: 'auto', 'interactive', 'guided'",
                "enum": ["auto", "interactive", "guided"],
                "default": "auto",
            },
            "depth": {"type": "integer", "description": "Exploration-Tiefe 1-4", "default": 4},
            "target_journal": {"type": "string", "description": "Ziel-Journal (general, nature, science)", "default": "general"},
            "citation_style": {"type": "string", "description": "Zitierstil (APA, MLA, Chicago, IEEE)", "default": "APA"},
        },
    },
    {
        "name": "start_exploration",
        "description": "Starte tiefe Verbindungssuche zwischen Ideen (AI-Scientist Tree Search)",
        "function": start_exploration,
        "parameters": {
            "bubble_id": {"type": "string", "description": "Optional: Bubble ID zum Erkunden"},
            "depth": {"type": "integer", "description": "Exploration-Tiefe 1-4 (default: 4)"},
            "context": {"type": "string", "description": "Optional: Kontext/Query"},
            "mode": {
                "type": "string",
                "description": "Explorations-Modus: 'auto' (autonom), 'interactive' (fragt bei jeder Verbindung), 'guided' (User gibt Richtung vor)",
                "enum": ["auto", "interactive", "guided"],
                "default": "auto",
            },
        },
    },
    {
        "name": "parse_bubble_content_for_paper",
        "description": "Parse Bubble-Content in Research Paper Abschnitte (Intra-Bubble Exploration)",
        "function": parse_bubble_content_for_paper,
        "parameters": {
            "bubble_id": {"type": "string", "description": "Bubble ID zum Parsen"},
            "content_text": {"type": "string", "description": "Optional: Direkter Text zum Parsen"},
        },
    },
    {
        "name": "generate_requirements_from_sections",
        "description": "Generiere Architektur-Requirements aus geparsten Paper-Abschnitten",
        "function": generate_requirements_from_sections,
        "parameters": {
            "sections": {"type": "array", "description": "Geparste Paper-Abschnitte"},
            "project_context": {"type": "string", "description": "Optional: Projekt-Kontext"},
        },
    },
    {
        "name": "optimize_paper_coherence",
        "description": "Optimiere Kohärenz und logischen Fluss zwischen Paper-Abschnitten",
        "function": optimize_paper_coherence,
        "parameters": {
            "sections": {"type": "array", "description": "Paper-Abschnitte"},
            "target_audience": {"type": "string", "description": "Zielpublikum (academic, industry, general)", "default": "academic"},
        },
    },
    {
        "name": "generate_complete_research_paper",
        "description": "Generiere komplettes Research Paper aus geparsten Abschnitten",
        "function": generate_complete_research_paper,
        "parameters": {
            "sections": {"type": "array", "description": "Geparste Paper-Abschnitte"},
            "paper_title": {"type": "string", "description": "Optional: Paper-Titel"},
            "target_journal": {"type": "string", "description": "Ziel-Journal (general, nature, science)", "default": "general"},
            "citation_style": {"type": "string", "description": "Zitierstil (APA, MLA, Chicago, IEEE)", "default": "APA"},
        },
    },
    {
        "name": "stop_exploration",
        "description": "Stoppe die laufende Exploration",
        "function": stop_exploration,
        "parameters": {},
    },
    {
        "name": "get_exploration_status",
        "description": "Status der laufenden Exploration abfragen",
        "function": get_exploration_status,
        "parameters": {},
    },
    {
        "name": "accept_connection",
        "description": "Entdeckte Verbindung akzeptieren und speichern",
        "function": accept_connection,
        "parameters": {
            "connection_id": {"type": "string", "description": "Optional: Verbindungs-ID"},
        },
    },
    {
        "name": "reject_connection",
        "description": "Entdeckte Verbindung ablehnen",
        "function": reject_connection,
        "parameters": {
            "connection_id": {"type": "string", "description": "Optional: Verbindungs-ID"},
        },
    },
    {
        "name": "explore_deeper",
        "description": "Eine Stufe tiefer erkunden",
        "function": explore_deeper,
        "parameters": {},
    },
    {
        "name": "visualize_exploration",
        "description": "Exploration-Ergebnisse anzeigen",
        "function": visualize_exploration,
        "parameters": {},
    },
    {
        "name": "respond_to_exploration_question",
        "description": "Antworte auf eine Exploration-Frage (von UI oder Voice)",
        "function": respond_to_exploration_question,
        "parameters": {
            "question_id": {"type": "string", "description": "ID der Frage"},
            "response_type": {
                "type": "string",
                "description": "Antwort-Typ",
                "enum": ["accept", "reject", "explore_deeper", "continue", "stop"],
            },
            "selected_option": {"type": "string", "description": "Ausgewählte Option"},
            "custom_text": {"type": "string", "description": "Freitext-Antwort"},
        },
    },
    {
        "name": "set_exploration_direction",
        "description": "Setze Exploration-Richtung (für guided Modus)",
        "function": set_exploration_direction,
        "parameters": {
            "bubble_id": {"type": "string", "description": "Optional: Fokus-Bubble ID"},
            "direction": {"type": "string", "description": "Richtungsbeschreibung"},
        },
    },
]


def _get_llm_client():
    """Get OpenRouter LLM client."""
    try:
        from openai import OpenAI
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY not set")
        return OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
        )
    except ImportError:
        logger.error("OpenAI client not available")
        raise


def _extract_text_from_structured_content(content_json: Dict[str, Any]) -> str:
    """Extract plain text from structured content for parsing."""
    if not content_json:
        return ""

    content_type = content_json.get("type", "note")

    # Use existing extraction logic from format_dispatcher
    from tools.format_dispatcher import _extract_content_text
    return _extract_content_text(content_json, "")

async def _parse_content_with_llm(content_text: str) -> List[Dict[str, Any]]:
    """Use LLM to parse content into research paper sections."""
    try:
        client = _get_llm_client()

        prompt = f"""
Analysiere diesen Text und extrahiere die einzelnen Komponenten für ein wissenschaftliches Research Paper.

Identifiziere die folgenden Abschnitte (falls vorhanden):
- Abstract/Zusammenfassung
- Introduction/Einleitung
- Problemstellung/Research Question
- Literature Review/Literaturübersicht
- Methodology/Methodik
- Experiments/Versuche
- Results/Ergebnisse
- Discussion/Diskussion
- Conclusion/Schlussfolgerung
- Future Work/Zukünftige Arbeiten
- References/Literaturverzeichnis

TEXT ZUM PARSEN:
{content_text}

Formatiere die Antwort als JSON:
{{
  "sections": [
    {{
      "type": "abstract",
      "title": "Abstract",
      "content": "Vollständiger Text des Abschnitts",
      "confidence": 0.9
    }},
    {{
      "type": "introduction",
      "title": "Introduction",
      "content": "Vollständiger Text des Abschnitts",
      "confidence": 0.8
    }}
  ]
}}

WICHTIG:
- Extrahiere nur tatsächlich vorhandene Abschnitte
- confidence: Wie sicher bist du, dass dieser Abschnitt korrekt identifiziert wurde (0.0-1.0)
- Wenn ein Abschnitt nicht vorhanden ist, nicht erfinden
- Behalte den originalen Text bei, formatiere nur die Struktur
"""

        response = client.chat.completions.create(
            model=get_model("exploration"),
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=3000,
        )

        content = response.choices[0].message.content.strip()

        # Extract JSON
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()

        result = json.loads(content)
        return result.get("sections", [])

    except Exception as e:
        logger.error(f"LLM parsing failed: {e}")
        # Fallback: return raw content as single section
        return [{
            "type": "raw_content",
            "title": "Raw Content",
            "content": content_text,
            "confidence": 0.1
        }]

async def _generate_requirements_with_llm(content: str, context: Optional[str] = None) -> Dict[str, Any]:
    """Generate architectural requirements document using LLM."""
    try:
        client = _get_llm_client()

        context_info = f"\nProjekt-Kontext: {context}" if context else ""

        prompt = f"""
Analysiere diesen wissenschaftlichen/technischen Inhalt und generiere ein strukturiertes Requirements-Dokument für ein Architektur-Team.

Identifiziere alle technischen Anforderungen, funktionalen Requirements und System-Spezifikationen.

{content}{context_info}

Formatiere als JSON Requirements-Dokument:
{{
  "title": "Requirements-Dokument Titel",
  "version": "1.0",
  "date": "YYYY-MM-DD",
  "author": "Generated by AI-Scientist",
  "requirements": [
    {{
      "id": "REQ-001",
      "category": "functional|non-functional|technical|performance|security",
      "priority": "must_have|should_have|nice_to_have",
      "title": "Kurzer Titel der Anforderung",
      "description": "Detaillierte Beschreibung",
      "acceptance_criteria": [
        "Konkretes Kriterium 1",
        "Konkretes Kriterium 2"
      ],
      "dependencies": ["REQ-XYZ"],
      "estimated_effort": "low|medium|high",
      "stakeholders": ["Architektur-Team", "Entwicklung"]
    }}
  ],
  "constraints": [
    {{
      "type": "technical|business|regulatory",
      "description": "Constraint-Beschreibung"
    }}
  ],
  "assumptions": [
    "Annahme 1",
    "Annahme 2"
  ]
}}

WICHTIG:
- Erstelle nur tatsächlich aus dem Inhalt abgeleitete Requirements
- Verwende standardisierte Kategorien
- Stelle sicher, dass Requirements messbar und testbar sind
- Prioritäten: must_have (kritisch), should_have (wichtig), nice_to_have (optional)
- Kategorien: functional (Funktionen), non-functional (Qualität), technical (Technik)
"""

        response = client.chat.completions.create(
            model=get_model("exploration"),
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=4000,
        )

        content = response.choices[0].message.content.strip()

        # Extract JSON
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()

        result = json.loads(content)
        return result

    except Exception as e:
        logger.error(f"Requirements LLM generation failed: {e}")
        # Fallback: basic requirements structure
        return {
            "title": "Generated Requirements",
            "version": "1.0",
            "requirements": [{
                "id": "REQ-001",
                "category": "functional",
                "priority": "must_have",
                "title": "Basic System Functionality",
                "description": f"Implement core functionality based on: {content[:200]}...",
                "acceptance_criteria": ["System must be functional"],
                "estimated_effort": "medium"
            }],
            "constraints": [],
            "assumptions": ["Content analysis may be incomplete"]
        }

def get_exploration_tools():
    """Get list of exploration tools for registration."""
    return EXPLORATION_TOOLS


__all__ = [
    "start_exploration",
    "stop_exploration",
    "get_exploration_status",
    "accept_connection",
    "reject_connection",
    "explore_deeper",
    "visualize_exploration",
    "respond_to_exploration_question",
    "set_exploration_direction",
    "parse_bubble_content_for_paper",
    "generate_requirements_from_sections",
    "optimize_paper_coherence",
    "generate_complete_research_paper",
    "explore_bubble_complete",
    "conduct_autogen_research",
    "get_exploration_tools",
    "EXPLORATION_TOOLS",
]
