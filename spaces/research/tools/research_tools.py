"""
Research Tools - ZeroClaw-powered web research

Tools for web research, scraping, and summarization.
Results can be stored as Ideas or pushed to Rowboat Knowledge Graph.
"""

import json
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


def _broadcast_to_electron(message: Dict[str, Any]):
    """Broadcast message to Electron UI."""
    try:
        print(json.dumps(message), flush=True)
    except Exception as e:
        logger.error(f"Broadcast error: {e}")


async def _query_zeroclaw(prompt: str) -> Dict[str, Any]:
    """Send a query to ZeroClaw and return the result."""
    from swarm.zeroclaw.client import get_zeroclaw_client

    client = get_zeroclaw_client()
    return await client.send_message(prompt)


def web_research(query: str) -> Dict[str, Any]:
    """
    Research a topic on the web via ZeroClaw.

    Args:
        query: Research query

    Returns:
        VibeMind result dict with research findings
    """
    import asyncio

    logger.info(f"research.web: query='{query}'")

    prompt = (
        f"Research the following topic thoroughly using web search. "
        f"Provide a comprehensive summary with key findings and sources.\n\n"
        f"Topic: {query}"
    )

    try:
        result = asyncio.get_event_loop().run_until_complete(_query_zeroclaw(prompt))
    except RuntimeError:
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(_query_zeroclaw(prompt))
        loop.close()

    response_text = result.get("response", "Keine Ergebnisse gefunden.")

    _broadcast_to_electron({
        "type": "research_result",
        "action": "web_research",
        "query": query,
        "result": response_text[:500],
    })

    return {
        "success": result.get("success", False),
        "message": response_text,
        "response_hint": f"Hier sind meine Recherche-Ergebnisse zu {query}.",
        "data": {
            "query": query,
            "findings": response_text,
            "tool_results": result.get("tool_results", []),
        },
    }


def scrape_url(url: str) -> Dict[str, Any]:
    """
    Scrape a URL and extract content via ZeroClaw.

    Args:
        url: URL to scrape

    Returns:
        VibeMind result dict with scraped content
    """
    import asyncio

    logger.info(f"research.scrape: url='{url}'")

    prompt = (
        f"Fetch and extract the main content from this URL. "
        f"Return the key information in a structured format.\n\n"
        f"URL: {url}"
    )

    try:
        result = asyncio.get_event_loop().run_until_complete(_query_zeroclaw(prompt))
    except RuntimeError:
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(_query_zeroclaw(prompt))
        loop.close()

    response_text = result.get("response", "Konnte URL nicht laden.")

    _broadcast_to_electron({
        "type": "research_result",
        "action": "scrape",
        "url": url,
        "result": response_text[:500],
    })

    return {
        "success": result.get("success", False),
        "message": response_text,
        "response_hint": f"Ich habe den Inhalt von {url} extrahiert.",
        "data": {"url": url, "content": response_text},
    }


def summarize_url(url: str) -> Dict[str, Any]:
    """
    Summarize the content of a URL via ZeroClaw.

    Args:
        url: URL to summarize

    Returns:
        VibeMind result dict with summary
    """
    import asyncio

    logger.info(f"research.summarize: url='{url}'")

    prompt = (
        f"Fetch this URL and provide a concise summary of its content. "
        f"Include the main points, key facts, and any important details.\n\n"
        f"URL: {url}"
    )

    try:
        result = asyncio.get_event_loop().run_until_complete(_query_zeroclaw(prompt))
    except RuntimeError:
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(_query_zeroclaw(prompt))
        loop.close()

    response_text = result.get("response", "Konnte nicht zusammenfassen.")

    return {
        "success": result.get("success", False),
        "message": response_text,
        "response_hint": f"Hier ist die Zusammenfassung von {url}.",
        "data": {"url": url, "summary": response_text},
    }


def research_to_idea(query: str, title: str = None) -> Dict[str, Any]:
    """
    Research a topic and save results as a new Idea in the current space.

    Args:
        query: Research query
        title: Optional idea title (defaults to query)

    Returns:
        VibeMind result dict
    """
    import asyncio

    logger.info(f"research.to_idea: query='{query}', title='{title}'")

    # First, do the research
    research_result = web_research(query)

    if not research_result.get("success"):
        return research_result

    findings = research_result.get("data", {}).get("findings", "")
    idea_title = title or f"Research: {query[:50]}"

    # Save as idea using existing IdeasRepository
    try:
        from data import IdeasRepository

        repo = IdeasRepository()
        idea = repo.create(
            title=idea_title,
            description=findings[:2000],
        )

        _broadcast_to_electron({
            "type": "node_added",
            "node": {
                "id": idea.id if hasattr(idea, "id") else str(idea),
                "title": idea_title,
                "description": findings[:200],
                "node_type": "idea",
            },
        })

        return {
            "success": True,
            "message": f"Recherche zu '{query}' als Idee '{idea_title}' gespeichert.",
            "response_hint": f"Ich habe die Recherche als Idee gespeichert: {idea_title}.",
            "data": {
                "query": query,
                "idea_title": idea_title,
                "findings_preview": findings[:300],
            },
        }

    except Exception as e:
        logger.error(f"Failed to save research as idea: {e}")
        return {
            "success": False,
            "message": f"Recherche erfolgreich, aber Speichern fehlgeschlagen: {e}",
            "response_hint": "Die Recherche war erfolgreich, aber ich konnte sie nicht als Idee speichern.",
            "data": {"query": query, "findings": findings[:500]},
        }


def research_to_rowboat(query: str) -> Dict[str, Any]:
    """
    Research a topic and push results into Rowboat Knowledge Graph.

    Args:
        query: Research query

    Returns:
        VibeMind result dict
    """
    import asyncio

    logger.info(f"research.to_rowboat: query='{query}'")

    # First, do the research
    research_result = web_research(query)

    if not research_result.get("success"):
        return research_result

    findings = research_result.get("data", {}).get("findings", "")

    # Push to Rowboat via existing client
    try:
        from spaces.rowboat.tools.roarboot_client import get_roarboot_client

        rowboat = get_roarboot_client()
        store_prompt = (
            f"Speichere diese Recherche-Ergebnisse im Knowledge Graph.\n\n"
            f"Thema: {query}\n\n"
            f"Ergebnisse:\n{findings[:3000]}"
        )
        rowboat_result = rowboat.chat(store_prompt, context="research")

        _broadcast_to_electron({
            "type": "roarboot_result",
            "action": "research_stored",
            "query": query,
            "result": f"Recherche zu '{query}' in Rowboat gespeichert.",
        })

        return {
            "success": True,
            "message": f"Recherche zu '{query}' in Rowboat Knowledge Graph gespeichert.",
            "response_hint": f"Die Recherche zu {query} ist jetzt im Knowledge Graph.",
            "data": {
                "query": query,
                "findings_preview": findings[:300],
                "rowboat_response": rowboat_result.get("response", "")[:200],
            },
        }

    except ImportError:
        logger.warning("Rowboat client not available")
        return {
            "success": False,
            "message": "Rowboat ist nicht konfiguriert. Recherche war erfolgreich aber konnte nicht gespeichert werden.",
            "response_hint": "Rowboat ist nicht verfuegbar.",
            "data": {"query": query, "findings": findings[:500]},
        }
    except Exception as e:
        logger.error(f"Failed to push research to Rowboat: {e}")
        return {
            "success": False,
            "message": f"Recherche erfolgreich, Rowboat-Update fehlgeschlagen: {e}",
            "response_hint": "Die Recherche war erfolgreich, aber Rowboat konnte nicht aktualisiert werden.",
            "data": {"query": query, "findings": findings[:500]},
        }
