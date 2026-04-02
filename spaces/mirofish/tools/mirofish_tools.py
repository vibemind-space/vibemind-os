"""
MiroFish Tools - Voice-controllable tools for MiroFish prediction engine

Each tool wraps a MiroFishClient method and returns a
VibeMind-standard result dict with broadcast to Electron.
"""

import json
import logging
from typing import Dict, Any, Optional
from llm_config import get_model

logger = logging.getLogger(__name__)


def _broadcast_to_electron(message: Dict[str, Any]):
    """Broadcast message to Electron UI."""
    try:
        print(json.dumps(message), flush=True)
    except Exception as e:
        logger.error(f"Broadcast error: {e}")


# ── Status ──────────────────────────────────────────────────────────

def get_status() -> Dict[str, Any]:
    """Check MiroFish connection status."""
    from .mirofish_client import get_mirofish_client

    logger.info("mirofish.status: Checking connection")
    client = get_mirofish_client()
    result = client.get_status()

    _broadcast_to_electron({
        "type": "mirofish_status",
        "status": result.get("status", "unknown"),
        "message": result.get("message", ""),
    })

    return {
        "success": result.get("success", False),
        "message": result.get("message", ""),
        "response_hint": result.get("message", "MiroFish Status unbekannt."),
    }


# ── Prediction (End-to-End) ─────────────────────────────────────────

def simulate(
    requirement: str,
    text: str = None,
    file_path: str = None,
    agent_count: int = 100,
    rounds: int = 10,
) -> Dict[str, Any]:
    """
    Run a full MiroFish prediction simulation.

    Takes seed data (text or file), builds a knowledge graph,
    runs multi-agent simulation, and generates a prediction report.

    Args:
        requirement: What to predict/simulate (e.g., "Public reaction to product launch")
        text: Seed text content
        file_path: Path to a seed document (PDF, MD, TXT)
        agent_count: Number of simulated agents (default 100)
        rounds: Simulation rounds (default 10)

    Returns:
        VibeMind result dict with prediction report
    """
    from .mirofish_client import get_mirofish_client

    logger.info(f"mirofish.simulate: requirement='{requirement}', agents={agent_count}, rounds={rounds}")
    client = get_mirofish_client()

    file_paths = [file_path] if file_path else None

    _broadcast_to_electron({
        "type": "mirofish_status",
        "status": "simulating",
        "message": f"MiroFish Simulation gestartet: {requirement}",
    })

    result = client.run_prediction(
        requirement=requirement,
        text_content=text,
        file_paths=file_paths,
        agent_count=agent_count,
        rounds=rounds,
    )

    if result.get("success"):
        report_content = result.get("report", {}).get("markdown_content", "")
        _broadcast_to_electron({
            "type": "mirofish_result",
            "action": "simulate",
            "requirement": requirement,
            "report_id": result.get("report_id"),
            "graph_id": result.get("graph_id"),
            "simulation_id": result.get("simulation_id"),
        })
        return {
            "success": True,
            "message": report_content or result.get("message", "Simulation abgeschlossen."),
            "response_hint": f"MiroFish Vorhersage-Report fuer '{requirement}' ist fertig.",
            "report_id": result.get("report_id"),
        }
    else:
        _broadcast_to_electron({
            "type": "mirofish_status",
            "status": "error",
            "message": result.get("message", "Simulation fehlgeschlagen"),
        })
        return {
            "success": False,
            "message": result.get("message", "Simulation fehlgeschlagen."),
            "response_hint": "MiroFish Simulation konnte nicht durchgefuehrt werden.",
        }


# ── Graph Operations ────────────────────────────────────────────────

def build_graph(
    requirement: str,
    text: str = None,
    file_path: str = None,
) -> Dict[str, Any]:
    """
    Build a MiroFish knowledge graph from seed data (without simulation).

    Args:
        requirement: Description of the domain
        text: Seed text content
        file_path: Path to a seed document

    Returns:
        VibeMind result dict with project_id and graph status
    """
    from .mirofish_client import get_mirofish_client

    logger.info(f"mirofish.graph.build: requirement='{requirement}'")
    client = get_mirofish_client()

    file_paths = [file_path] if file_path else None

    ontology_result = client.generate_ontology(
        requirement=requirement,
        text_content=text,
        file_paths=file_paths,
    )

    if not ontology_result.get("success"):
        return {
            "success": False,
            "message": ontology_result.get("message", "Ontologie-Erstellung fehlgeschlagen."),
            "response_hint": "MiroFish konnte die Ontologie nicht erstellen.",
        }

    project_id = ontology_result["project_id"]

    build_result = client.build_graph(project_id)
    if not build_result.get("success"):
        return {
            "success": False,
            "message": build_result.get("message", "Graph-Aufbau fehlgeschlagen."),
            "response_hint": "MiroFish konnte den Graph nicht aufbauen.",
        }

    _broadcast_to_electron({
        "type": "mirofish_result",
        "action": "graph_build",
        "project_id": project_id,
        "task_id": build_result.get("task_id"),
    })

    return {
        "success": True,
        "message": f"Graph-Aufbau gestartet fuer Projekt {project_id}.",
        "response_hint": "MiroFish Knowledge Graph wird aufgebaut.",
        "project_id": project_id,
        "task_id": build_result.get("task_id"),
    }


def search_graph(graph_id: str, query: str) -> Dict[str, Any]:
    """
    Search a MiroFish knowledge graph.

    Args:
        graph_id: Graph to search
        query: Search query

    Returns:
        VibeMind result dict with search results
    """
    from .mirofish_client import get_mirofish_client

    logger.info(f"mirofish.graph.search: graph='{graph_id}', query='{query}'")
    client = get_mirofish_client()
    result = client.search_graph(graph_id, query)

    if result.get("success"):
        _broadcast_to_electron({
            "type": "mirofish_result",
            "action": "graph_search",
            "graph_id": graph_id,
            "query": query,
        })
        return {
            "success": True,
            "message": json.dumps(result.get("results", {}), ensure_ascii=False, indent=2),
            "response_hint": f"MiroFish Graph-Suche nach '{query}' abgeschlossen.",
        }
    return {
        "success": False,
        "message": result.get("error", "Suche fehlgeschlagen."),
        "response_hint": "MiroFish Graph-Suche fehlgeschlagen.",
    }


def list_projects() -> Dict[str, Any]:
    """List all MiroFish projects."""
    from .mirofish_client import get_mirofish_client

    logger.info("mirofish.list_projects")
    client = get_mirofish_client()
    result = client.list_projects()

    if result.get("success"):
        projects = result.get("projects", [])
        if not projects:
            return {
                "success": True,
                "message": "Keine MiroFish-Projekte vorhanden.",
                "response_hint": "Es gibt noch keine MiroFish-Projekte.",
            }
        summary = "\n".join(
            f"  - {p.get('name', p.get('id', '?'))}" for p in projects
        )
        return {
            "success": True,
            "message": f"{len(projects)} Projekte:\n{summary}",
            "response_hint": f"Es gibt {len(projects)} MiroFish-Projekte.",
            "projects": projects,
        }
    return {
        "success": False,
        "message": result.get("error", "Projekt-Liste nicht verfuegbar."),
        "response_hint": "MiroFish-Projekte konnten nicht abgerufen werden.",
    }


# ── Report Chat ─────────────────────────────────────────────────────

def chat_report(report_id: str, question: str) -> Dict[str, Any]:
    """
    Chat with MiroFish about a prediction report.

    Args:
        report_id: Report to chat about
        question: Question about the report findings

    Returns:
        VibeMind result dict
    """
    from .mirofish_client import get_mirofish_client

    logger.info(f"mirofish.report.chat: report='{report_id}', q='{question}'")
    client = get_mirofish_client()
    result = client.chat_report(report_id, question)

    if result.get("success"):
        return {
            "success": True,
            "message": result.get("response", ""),
            "response_hint": "MiroFish hat die Frage zum Report beantwortet.",
        }
    return {
        "success": False,
        "message": result.get("error", "Report-Chat fehlgeschlagen."),
        "response_hint": "MiroFish konnte die Frage nicht beantworten.",
    }


# ── Interview ───────────────────────────────────────────────────────

def interview_agent(
    simulation_id: str, agent_name: str, question: str
) -> Dict[str, Any]:
    """
    Interview a simulated agent from a MiroFish simulation.

    Args:
        simulation_id: Simulation containing the agent
        agent_name: Name of the agent to interview
        question: Question to ask

    Returns:
        VibeMind result dict
    """
    from .mirofish_client import get_mirofish_client

    logger.info(f"mirofish.interview: sim='{simulation_id}', agent='{agent_name}'")
    client = get_mirofish_client()
    result = client.interview_agent(simulation_id, agent_name, question)

    if result.get("success"):
        _broadcast_to_electron({
            "type": "mirofish_result",
            "action": "interview",
            "simulation_id": simulation_id,
            "agent_name": agent_name,
        })
        return {
            "success": True,
            "message": result.get("response", ""),
            "response_hint": f"Interview mit Agent '{agent_name}' abgeschlossen.",
        }
    return {
        "success": False,
        "message": result.get("error", "Interview fehlgeschlagen."),
        "response_hint": f"Interview mit '{agent_name}' fehlgeschlagen.",
    }


# ── Bridge: Rowboat → MiroFish ─────────────────────────────────────

def predict_from_knowledge(
    requirement: str,
    query: str = None,
    agent_count: int = 100,
    rounds: int = 10,
) -> Dict[str, Any]:
    """
    Pull knowledge from Rowboat and run MiroFish prediction on it.

    Bridges Rowboat (knowledge graph) → MiroFish (prediction engine):
    1. Searches Rowboat knowledge for relevant context
    2. Feeds the result as seed data into MiroFish
    3. Runs full prediction pipeline (ontology → graph → simulation → report)

    Args:
        requirement: What to predict (e.g., "Wie reagieren Nutzer auf Feature X?")
        query: Optional search query for Rowboat (defaults to requirement)
        agent_count: Number of simulated agents
        rounds: Simulation rounds

    Returns:
        VibeMind result dict with prediction report
    """
    logger.info(f"mirofish.predict_from_knowledge: requirement='{requirement}'")

    # Step 1: Pull context from Rowboat
    search_query = query or requirement
    rowboat_text = ""

    try:
        from spaces.rowboat.tools.roarboot_client import get_roarboot_client
        rowboat = get_roarboot_client()
        knowledge = rowboat.search_knowledge(search_query)
        if knowledge.get("success") and knowledge.get("response"):
            rowboat_text = knowledge["response"]
            logger.info(f"mirofish.predict_from_knowledge: Got {len(rowboat_text)} chars from Rowboat")
    except Exception as e:
        logger.warning(f"mirofish.predict_from_knowledge: Rowboat unavailable: {e}")

    if not rowboat_text:
        # Fallback: use requirement as seed text
        rowboat_text = requirement
        logger.info("mirofish.predict_from_knowledge: No Rowboat data, using requirement as seed")

    _broadcast_to_electron({
        "type": "mirofish_status",
        "status": "bridging",
        "message": f"Rowboat-Daten geladen, starte MiroFish Vorhersage...",
    })

    # Step 2: Feed into MiroFish simulation
    from .mirofish_client import get_mirofish_client
    client = get_mirofish_client()

    result = client.run_prediction(
        requirement=requirement,
        text_content=f"=== Rowboat Knowledge Context ===\n{rowboat_text}\n\n=== Prediction Requirement ===\n{requirement}",
        agent_count=agent_count,
        rounds=rounds,
    )

    if result.get("success"):
        report_content = result.get("report", {}).get("markdown_content", "")

        # Step 3: Upload report back to Rowboat for future RAG
        try:
            from spaces.rowboat.tools.roarboot_tools import upload_document
            upload_document(
                text=report_content[:5000] if report_content else "",
                title=f"MiroFish Prediction: {requirement[:80]}",
            )
            logger.info("mirofish.predict_from_knowledge: Report uploaded to Rowboat")
        except Exception as e:
            logger.warning(f"mirofish.predict_from_knowledge: Could not upload to Rowboat: {e}")

        _broadcast_to_electron({
            "type": "mirofish_result",
            "action": "predict_from_knowledge",
            "requirement": requirement,
            "report_id": result.get("report_id"),
        })

        return {
            "success": True,
            "message": report_content or result.get("message", "Vorhersage abgeschlossen."),
            "response_hint": f"MiroFish Vorhersage basierend auf Rowboat-Daten fuer '{requirement}' ist fertig.",
            "report_id": result.get("report_id"),
        }
    else:
        return {
            "success": False,
            "message": result.get("message", "Vorhersage fehlgeschlagen."),
            "response_hint": "MiroFish Vorhersage konnte nicht durchgefuehrt werden.",
        }


# ── Bubble Evaluation Predictive Layer ────────────────────────────

# Per-agent evaluation prompts (domain-specific)
_EVALUATION_PROMPTS = {
    "coding": (
        "Du bist ein Code-Experte. Bewerte diese Bubble auf Code-Readiness.\n"
        "Frage: Reicht die Spezifikation fuer eine Code-Generierung?\n"
        "Pruefe: API-Endpunkte, Tech-Stack, Datenmodelle, Fehlerbehandlung.\n"
        "Antworte NUR mit JSON: {\"score\": 0-25, \"assessment\": \"...\", \"missing\": [\"...\"]}"
    ),
    "swe_design": (
        "Du bist ein Requirements-Experte. Bewerte diese Bubble auf Vollstaendigkeit.\n"
        "Frage: Sind die Anforderungen vollstaendig definiert?\n"
        "Pruefe: User Stories, Akzeptanzkriterien, Scope, Abhaengigkeiten.\n"
        "Antworte NUR mit JSON: {\"score\": 0-25, \"assessment\": \"...\", \"missing\": [\"...\"]}"
    ),
    "research": (
        "Du bist ein Recherche-Experte. Bewerte diese Bubble auf Domaenen-Verstaendnis.\n"
        "Frage: Ist die Domaene gut genug verstanden fuer eine Umsetzung?\n"
        "Pruefe: Quellen, Referenzen, Konkurrenzanalyse, offene Fragen.\n"
        "Antworte NUR mit JSON: {\"score\": 0-25, \"assessment\": \"...\", \"missing\": [\"...\"]}"
    ),
    "roarboot": (
        "Du bist ein Wissens-Experte. Bewerte ob relevantes Vorwissen vorhanden ist.\n"
        "Frage: Gibt es genuegend Kontext und Vorwissen fuer dieses Projekt?\n"
        "Pruefe: Dokumentation, bestehende Patterns, wiederverwendbare Komponenten.\n"
        "Antworte NUR mit JSON: {\"score\": 0-25, \"assessment\": \"...\", \"missing\": [\"...\"]}"
    ),
    "ideas": (
        "Du bist ein Ideen-Experte. Bewerte ob alle Sub-Ideen ausgearbeitet sind.\n"
        "Frage: Sind alle Teilaspekte dieser Bubble durchdacht?\n"
        "Pruefe: Vollstaendigkeit der Unterpunkte, Tiefe, Vernetzung, Luecken.\n"
        "Antworte NUR mit JSON: {\"score\": 0-25, \"assessment\": \"...\", \"missing\": [\"...\"]}"
    ),
}


def _parse_evaluation_response(text: str) -> Dict[str, Any]:
    """Parse structured evaluation response from agent (JSON or fallback)."""
    import re

    # Try direct JSON parse
    try:
        # Find JSON in response (may be wrapped in text)
        match = re.search(r'\{[^{}]*"score"[^{}]*\}', text, re.DOTALL)
        if match:
            data = json.loads(match.group())
            return {
                "score": min(25, max(0, int(data.get("score", 0)))),
                "assessment": str(data.get("assessment", "")),
                "missing": list(data.get("missing", [])),
            }
    except (json.JSONDecodeError, ValueError):
        pass

    # Fallback: extract score from text
    score = 10  # default middle score
    score_match = re.search(r'(\d+)\s*/?\s*25', text)
    if score_match:
        score = min(25, max(0, int(score_match.group(1))))

    return {
        "score": score,
        "assessment": text[:500] if text else "Keine strukturierte Bewertung erhalten.",
        "missing": [],
    }


def _format_readiness_report(
    bubble_name: str,
    total_score: int,
    prediction: str,
    per_agent: Dict[str, Dict],
    missing_items: list,
    created_count: int = 0,
) -> str:
    """Format a markdown readiness report."""
    pred_icon = {"GO": "GO", "NEEDS_WORK": "NACHARBEIT NOETIG", "NOT_READY": "NICHT BEREIT"}
    lines = [
        f"# Bubble Evaluation: {bubble_name}",
        f"",
        f"Gesamtscore: {total_score}/100 — {pred_icon.get(prediction, prediction)}",
        f"",
    ]

    # Per-agent breakdown
    agent_labels = {
        "vibemind_coding": "Coding",
        "vibemind_swe_design": "SWE Design",
        "vibemind_research": "Research",
        "vibemind_rowboat": "Rowboat",
        "vibemind_ideas": "Ideas",
    }
    for agent_name, data in per_agent.items():
        label = agent_labels.get(agent_name, agent_name)
        score = data.get("score", 0)
        assessment = data.get("assessment", "")
        lines.append(f"  {label} [{score}/25]: {assessment[:120]}")

    if missing_items:
        lines.append(f"")
        lines.append(f"Fehlend:")
        for item in missing_items[:10]:
            lines.append(f"  - {item}")

    if created_count > 0:
        lines.append(f"")
        lines.append(f"{created_count} fehlende Punkte als TODO-Ideen in der Bubble erstellt.")

    return "\n".join(lines)


def _create_missing_ideas(bubble_id: str, missing_items: list) -> list:
    """Append missing items to the bubble's description instead of creating separate nodes."""
    created = []
    try:
        from data import IdeasRepository

        repo = IdeasRepository()
        bubble = repo.get(bubble_id)
        if not bubble:
            logger.warning(f"mirofish.evaluate: Bubble {bubble_id} not found for TODO merge")
            return created

        # Filter valid items
        valid_items = [item for item in missing_items[:25] if item and len(item) >= 3]
        if not valid_items:
            return created

        # Build TODO section
        todo_section = "\n\n--- MiroFish Evaluation: Offene Punkte ---"
        for i, item in enumerate(valid_items, 1):
            todo_section += f"\n{i}. {item}"
            created.append({"title": f"TODO: {item[:80]}"})

        # Remove previous MiroFish section if present, then append new one
        desc = bubble.description or ""
        marker = "--- MiroFish Evaluation: Offene Punkte ---"
        if marker in desc:
            desc = desc[:desc.index(marker)].rstrip()

        bubble.description = desc + todo_section
        repo.update(bubble)

        logger.info(f"mirofish.evaluate: Merged {len(created)} TODOs into bubble {bubble_id} description")

    except Exception as e:
        logger.warning(f"mirofish.evaluate: Could not merge TODOs into bubble: {e}")

    return created


def evaluate_bubble_readiness(bubble_name: str) -> Dict[str, Any]:
    """
    Evaluate a bubble's readiness for code generation using
    MiroFish knowledge graph + Minibook expert panel.

    Flow:
    1. Collect bubble content (ideas, nodes, edges)
    2. Build MiroFish knowledge graph (optional)
    3. Post evaluation to Minibook with @mentions to 5 agents
    4. Aggregate scores into Go/No-Go report

    Args:
        bubble_name: Name of the bubble to evaluate

    Returns:
        VibeMind result dict with scores, prediction, missing items
    """
    import time
    from data import IdeasRepository

    logger.info(f"mirofish.evaluate: bubble='{bubble_name}'")

    # ── Step 1: Collect bubble content ──
    ideas_repo = IdeasRepository()
    bubble = ideas_repo.get_by_title_fuzzy(bubble_name)
    if not bubble:
        return {
            "success": False,
            "message": f"Bubble '{bubble_name}' nicht gefunden.",
            "response_hint": f"Die Bubble '{bubble_name}' existiert nicht.",
        }

    # Collect content from bubble
    try:
        from tools.bubble_requirements_tool import process_bubble_requirements
        bubble_data = process_bubble_requirements(bubble.id)
    except Exception as e:
        logger.warning(f"mirofish.evaluate: requirements tool failed: {e}")
        bubble_data = {"metadata": {"bubble_title": bubble.title}, "nodes": [], "edges": []}

    # Build content text — include child ideas + canvas nodes
    content_parts = [
        f"# Bubble: {bubble.title}",
        f"Beschreibung: {bubble.description or 'Keine'}",
    ]

    # Load child ideas (ideas with parent_id = bubble.id)
    try:
        all_ideas = ideas_repo.list()
        child_ideas = [i for i in all_ideas if i.parent_id == bubble.id]
        if child_ideas:
            content_parts.append(f"\n## Kind-Ideen ({len(child_ideas)} Stueck)")
            for ci in child_ideas:
                content_parts.append(f"\n### {ci.title}")
                if ci.description:
                    content_parts.append(ci.description)
            logger.info(f"mirofish.evaluate: loaded {len(child_ideas)} child ideas")
    except Exception as e:
        logger.warning(f"mirofish.evaluate: child ideas load failed: {e}")

    # Canvas nodes from bubble_requirements_tool
    for node in bubble_data.get("nodes", []):
        title = node.get("title", "")
        content = node.get("content", "") or node.get("description", "")
        if title:
            content_parts.append(f"\n## {title}")
        if content:
            content_parts.append(content[:500])
    if bubble_data.get("requirements"):
        content_parts.append("\n## Requirements")
        for req in bubble_data["requirements"][:10]:
            content_parts.append(f"- {req.get('text', req) if isinstance(req, dict) else req}")

    content_text = "\n".join(content_parts)
    logger.info(f"mirofish.evaluate: content_text length={len(content_text)} chars")

    _broadcast_to_electron({
        "type": "mirofish_status",
        "status": "evaluating",
        "message": f"Evaluiere Bubble '{bubble_name}'...",
    })

    # ── Step 2: Build MiroFish Knowledge Graph (optional) ──
    graph_summary = ""
    graph_id = None
    try:
        from .mirofish_client import get_mirofish_client
        client = get_mirofish_client()
        status = client.get_status()
        if status.get("success"):
            result = client.build_graph_from_text(
                requirement=f"Analyse der Bubble '{bubble_name}' fuer Code-Readiness Bewertung",
                text_content=content_text,
            )
            if result.get("success"):
                graph_id = result["graph_id"]
                graph_summary = result.get("summary", "")
                logger.info(f"mirofish.evaluate: graph built: {graph_id}")
    except Exception as e:
        logger.warning(f"mirofish.evaluate: graph build skipped: {e}")

    # ── Step 3: Multi-agent LLM evaluation (5 perspectives) ──
    agent_responses = {}
    try:
        client_llm, model = _get_llm_client()
        if not client_llm:
            raise RuntimeError("No LLM client available")

        target_spaces = ["coding", "swe_design", "research", "rowboat", "ideas"]
        agent_label_map = {
            "coding": "vibemind_coding",
            "swe_design": "vibemind_swe_design",
            "research": "vibemind_research",
            "rowboat": "vibemind_rowboat",
            "ideas": "vibemind_ideas",
        }

        # Truncated content for each agent call
        eval_content = content_text[:4000]
        if graph_summary:
            eval_content += f"\n\n=== Knowledge Graph ===\n{graph_summary}"

        # GPT-5+ uses max_completion_tokens, older models use max_tokens
        token_param = {}
        if model and model.startswith("gpt-"):
            token_param["max_completion_tokens"] = 500
        else:
            token_param["max_tokens"] = 500

        for space_key in target_spaces:
            agent_name = agent_label_map[space_key]
            prompt = _EVALUATION_PROMPTS.get(space_key, "")

            try:
                response = client_llm.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": prompt},
                        {"role": "user", "content": eval_content},
                    ],
                    temperature=0.3,
                    **token_param,
                )
                raw = response.choices[0].message.content or ""
                agent_responses[agent_name] = raw
                logger.info(f"mirofish.evaluate: {agent_name} responded ({len(agent_responses)}/5)")
            except Exception as e:
                logger.warning(f"mirofish.evaluate: {agent_name} LLM call failed: {e}")
                agent_responses[agent_name] = ""

        target_agent_names = list(agent_label_map.values())

    except Exception as e:
        logger.warning(f"mirofish.evaluate: Multi-agent eval failed ({e}), using single-agent fallback")
        return _evaluate_bubble_fallback(bubble_name, bubble, content_text, graph_summary, graph_id)

    # ── Step 5: Parse and aggregate scores ──
    total_score = 0
    per_agent_scores = {}
    missing_items = []

    for agent_name in target_agent_names:
        response_text = agent_responses.get(agent_name, "")
        parsed = _parse_evaluation_response(response_text)
        score = parsed["score"]
        total_score += score
        per_agent_scores[agent_name] = {
            "score": score,
            "assessment": parsed["assessment"],
        }
        missing_items.extend(parsed["missing"])

    # Determine prediction
    if total_score >= 60:
        prediction = "GO"
    elif total_score >= 40:
        prediction = "NEEDS_WORK"
    else:
        prediction = "NOT_READY"

    # ── Step 6: Update bubble score + broadcast ──
    # Map agent scores to Idea dimensions (0-25 → 0-10)
    coding_score = per_agent_scores.get("vibemind_coding", {}).get("score", 0)
    design_score = per_agent_scores.get("vibemind_swe_design", {}).get("score", 0)
    research_score = per_agent_scores.get("vibemind_research", {}).get("score", 0)
    ideas_score = per_agent_scores.get("vibemind_ideas", {}).get("score", 0)

    bubble.feasibility = coding_score / 2.5     # 0-10
    bubble.impact = design_score / 2.5          # 0-10
    bubble.novelty = research_score / 2.5       # 0-10
    bubble.urgency = ideas_score / 2.5          # 0-10
    bubble.score = bubble.calculate_score()
    bubble.status = "scored"
    ideas_repo.update(bubble)

    # ── Step 7: Auto-create missing items as ideas in the bubble ──
    created_ideas = []
    if missing_items:
        created_ideas = _create_missing_ideas(bubble.id, missing_items)

    report_text = _format_readiness_report(
        bubble_name, total_score, prediction, per_agent_scores, missing_items,
        created_count=len(created_ideas),
    )

    _broadcast_to_electron({
        "type": "mirofish_result",
        "action": "evaluate_readiness",
        "bubble_name": bubble_name,
        "total_score": total_score,
        "prediction": prediction,
        "per_agent": per_agent_scores,
        "missing_items": missing_items,
        "created_ideas": created_ideas,
        "graph_id": graph_id,
    })

    return {
        "success": True,
        "message": report_text,
        "response_hint": f"Bubble '{bubble_name}' hat {total_score}/100 Punkte. {len(created_ideas)} fehlende Punkte als Ideen erstellt.",
        "total_score": total_score,
        "prediction": prediction,
        "per_agent_scores": per_agent_scores,
        "missing_items": missing_items,
        "created_ideas": created_ideas,
    }


def _get_llm_client():
    """Get LLM client for fallback evaluation. Tries OpenAI first, then OpenRouter."""
    try:
        import os
        from openai import OpenAI

        # Priority 1: OpenAI (GPT-5.4)
        openai_key = os.getenv("OPENAI_API_KEY")
        if openai_key:
            return OpenAI(api_key=openai_key), get_model("mirofish_eval")

        # Priority 2: OpenRouter
        or_key = os.getenv("OPENROUTER_API_KEY")
        if or_key:
            return OpenAI(api_key=or_key, base_url="https://openrouter.ai/api/v1"), get_model("mirofish_openrouter")
    except ImportError:
        pass
    return None, None


def _evaluate_bubble_fallback(
    bubble_name: str,
    bubble,
    content_text: str,
    graph_summary: str,
    graph_id: Optional[str],
) -> Dict[str, Any]:
    """Fallback: single-agent LLM evaluation when Minibook is unavailable."""
    import os
    import re
    from data import IdeasRepository

    logger.info(f"mirofish.evaluate fallback: LLM evaluation for '{bubble_name}'")

    prompt = (
        f"Du bist ein Software-Architektur-Experte. Bewerte diese Bubble auf Projekt-Readiness.\n\n"
        f"=== BUBBLE CONTENT ===\n{content_text[:4000]}\n\n"
    )
    if graph_summary:
        prompt += f"=== KNOWLEDGE GRAPH ===\n{graph_summary}\n\n"
    prompt += (
        "Bewerte in 5 Dimensionen (je 0-25 Punkte):\n"
        "1. coding: Code-Readiness (API-Spec, Tech-Stack, Datenmodelle)\n"
        "2. design: Requirements (User Stories, Akzeptanzkriterien, Scope)\n"
        "3. research: Domaenen-Wissen (Quellen, Recherche, offene Fragen)\n"
        "4. knowledge: Vorwissen (Dokumentation, bestehende Patterns)\n"
        "5. ideas: Ideen-Tiefe (Sub-Ideen, Vernetzung, Vollstaendigkeit)\n\n"
        "Antworte NUR mit validem JSON (kein anderer Text):\n"
        '{"coding": 0, "design": 0, "research": 0, "knowledge": 0, "ideas": 0, '
        '"prediction": "GO", "missing": ["item1", "item2"], '
        '"summary": "Kurze Zusammenfassung der Bewertung"}'
    )

    # Try LLM evaluation
    client, model = _get_llm_client()
    total_score = 0
    prediction = "NOT_READY"
    missing_items = []
    per_agent_scores = {}
    summary_text = ""

    if client:
        try:
            logger.info(f"mirofish.evaluate fallback: using {model}")
            # GPT-5+ uses max_completion_tokens, older models use max_tokens
            token_param = {}
            if model and model.startswith("gpt-"):
                token_param["max_completion_tokens"] = 1000
            else:
                token_param["max_tokens"] = 1000

            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                **token_param,
            )
            raw = response.choices[0].message.content or ""
            logger.info(f"mirofish.evaluate fallback: LLM response length={len(raw)}")

            # Parse JSON from response
            match = re.search(r'\{[^{}]*"coding"[^{}]*\}', raw, re.DOTALL)
            if match:
                data = json.loads(match.group())
                dims = {
                    "coding": min(25, max(0, int(data.get("coding", 0)))),
                    "design": min(25, max(0, int(data.get("design", 0)))),
                    "research": min(25, max(0, int(data.get("research", 0)))),
                    "knowledge": min(25, max(0, int(data.get("knowledge", 0)))),
                    "ideas": min(25, max(0, int(data.get("ideas", 0)))),
                }
                total_score = sum(dims.values())
                prediction = data.get("prediction", "NEEDS_WORK")
                if prediction not in ("GO", "NEEDS_WORK", "NOT_READY"):
                    prediction = "GO" if total_score >= 60 else "NEEDS_WORK" if total_score >= 40 else "NOT_READY"
                missing_items = list(data.get("missing", []))
                summary_text = data.get("summary", "")

                # Map to per-agent format for consistency
                label_map = {
                    "coding": "LLM:Coding",
                    "design": "LLM:Design",
                    "research": "LLM:Research",
                    "knowledge": "LLM:Knowledge",
                    "ideas": "LLM:Ideas",
                }
                for key, score in dims.items():
                    per_agent_scores[label_map[key]] = {
                        "score": score,
                        "assessment": summary_text,
                    }

                # Update bubble score
                ideas_repo = IdeasRepository()
                bubble.feasibility = dims["coding"] / 2.5
                bubble.impact = dims["design"] / 2.5
                bubble.novelty = dims["research"] / 2.5
                bubble.urgency = dims["ideas"] / 2.5
                bubble.score = bubble.calculate_score()
                bubble.status = "scored"
                ideas_repo.update(bubble)

        except Exception as e:
            logger.warning(f"mirofish.evaluate fallback: LLM error: {e}")

    if total_score == 0:
        # No LLM available — static fallback
        total_score = 15
        prediction = "NOT_READY"
        missing_items = ["Keine LLM-Bewertung moeglich (OpenRouter API Key fehlt?)"]

    # Auto-create missing items as ideas in the bubble
    created_ideas = []
    if missing_items:
        created_ideas = _create_missing_ideas(bubble.id, missing_items)

    report_text = _format_readiness_report(
        bubble_name, total_score, prediction, per_agent_scores, missing_items,
        created_count=len(created_ideas),
    )

    _broadcast_to_electron({
        "type": "mirofish_result",
        "action": "evaluate_readiness",
        "bubble_name": bubble_name,
        "total_score": total_score,
        "prediction": prediction,
        "per_agent": per_agent_scores,
        "missing_items": missing_items,
        "created_ideas": created_ideas,
        "graph_id": graph_id,
        "fallback": True,
    })

    return {
        "success": True,
        "message": report_text,
        "response_hint": f"Bubble '{bubble_name}' hat {total_score}/100 Punkte. {len(created_ideas)} fehlende Punkte als TODO-Ideen erstellt.",
        "total_score": total_score,
        "prediction": prediction,
        "per_agent_scores": per_agent_scores,
        "missing_items": missing_items,
        "created_ideas": created_ideas,
    }


__all__ = [
    "get_status",
    "simulate",
    "build_graph",
    "search_graph",
    "list_projects",
    "chat_report",
    "interview_agent",
    "predict_from_knowledge",
    "evaluate_bubble_readiness",
]
