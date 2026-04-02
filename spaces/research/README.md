# Research Space (ZeroClaw)

Web research, URL scraping, and summarization with cross-space integration (Ideas, Rowboat).

## Architecture

```
IntentClassifier → research.* events
    ↓
ZeroClawResearchAgent (BaseBackendAgent)
    ↓
ZeroClaw Client (async HTTP)
    ├── Web research
    ├── URL scraping
    └── Content summarization
    ↓
Cross-space output:
    ├── IdeasRepository (save as Idea)
    └── Rowboat KG (push to knowledge graph)
```

## Agent

| Property | Value |
|----------|-------|
| **Class** | `ZeroClawResearchAgent` |
| **Stream** | `events:tasks:zeroclaw` |
| **File** | `agents/zeroclaw_research_agent.py` |

## Event Types (5)

| Event Type | Tool | Description |
|-----------|------|-------------|
| `research.web` | `web_research` | Research a topic on the web |
| `research.scrape` | `scrape_url` | Extract content from URL |
| `research.summarize` | `summarize_url` | Summarize URL content |
| `research.to_idea` | `research_to_idea` | Research + save as Idea |
| `research.to_rowboat` | `research_to_rowboat` | Research + push to Rowboat KG |

## Parameter Mapping (German → English)

| Event Type | Aliases → Tool Parameter |
|-----------|--------------------------|
| `research.web` | `thema, topic, suche, frage, text` → `query` |
| `research.scrape` | `link, seite, webseite, website` → `url` |
| `research.summarize` | `link, seite, webseite, website` → `url` |
| `research.to_idea` | `thema, topic, suche` → `query`; `name, titel` → `title` |
| `research.to_rowboat` | `thema, topic, suche` → `query` |

## Tool Details

### web_research(query)
Sends research query to ZeroClaw. Broadcasts `research_result` to Electron UI.

### scrape_url(url)
Fetches URL, extracts structured content via ZeroClaw. Broadcasts preview to Electron.

### summarize_url(url)
Fetches URL, generates concise summary with main points and key facts.

### research_to_idea(query, title=None)
**Chained operation:** Calls `web_research()` first, then saves findings to `ideas` table via `IdeasRepository`. Auto-generates title if not provided. Broadcasts `node_added`.

### research_to_rowboat(query)
**Chained operation:** Calls `web_research()` first, then pushes to Rowboat Knowledge Graph via `roarboot_client`. Broadcasts `roarboot_result`.

## Directory Structure

```
python/spaces/research/
├── agents/
│   ├── __init__.py                    # Singleton getter
│   └── zeroclaw_research_agent.py     # ZeroClawResearchAgent
└── tools/
    ├── __init__.py
    └── research_tools.py              # 5 tools (~293 lines)
```

## Configuration

```bash
USE_ZEROCLAW=true    # Enable research space
```

## Integration Points

| Component | Purpose |
|-----------|---------|
| ZeroClaw Client | Web research, scraping, summarization |
| IdeasRepository | Save research findings as ideas |
| Rowboat Client | Push findings to knowledge graph |
| Electron IPC | `research_result`, `node_added`, `roarboot_result` |
