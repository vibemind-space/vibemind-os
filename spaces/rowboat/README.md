# Roarboot Space

Rowboat Knowledge Graph integration for VibeMind.

## Overview

Roarboot integrates [Rowboat](https://github.com/rowboatlabs/rowboat) — an open-source AI coworker that turns work into a knowledge graph. Rowboat runs as a Docker container, and VibeMind communicates via the Rowboat Python SDK (with direct HTTP fallback).

## Architecture

```
Voice → Rachel → "roarboot.*" Events → RoarbootBackendAgent → Rowboat API → Docker Stack
                                                                                    ↓
                                                            Electron WebView ← Rowboat UI (:3000)
```

## Docker Stack

- **Rowboat** (:3000) — Main application (Next.js)
- **MongoDB** (:27017) — Data storage
- **Redis** (:6379) — Queuing
- **Qdrant** (:6333) — Vector search (RAG)

## Voice Commands

| Command (DE) | Event Type | Tool |
|---|---|---|
| "Durchsuche mein Wissen nach X" | `roarboot.search` | `search_knowledge` |
| "Was weiss ich ueber X?" | `roarboot.query` | `query_knowledge` |
| "Schreibe Email an X wegen Y" | `roarboot.email_draft` | `draft_email` |
| "Bereite Meeting mit X vor" | `roarboot.meeting_brief` | `generate_meeting_brief` |
| "Erstelle Praesentation ueber X" | `roarboot.deck` | `generate_deck` |
| "Notiz: ..." | `roarboot.voice_note` | `process_voice_note` |
| "Roarboot Status" | `roarboot.status` | `get_status` |
| "Oeffne Roarboot" | `roarboot.open` | `open_webview` |
| "Neues Gespraech mit Roarboot" | `roarboot.reset` | `reset_conversation` |
| "Starte Roarboot" | `roarboot.docker.start` | `start_docker` |
| "Stoppe Roarboot" | `roarboot.docker.stop` | `stop_docker` |
| "Starte Roarboot neu" | `roarboot.docker.restart` | `restart_docker` |
| "Roarboot Docker Status" | `roarboot.docker.status` | `docker_status` |

## Setup

1. Start Docker stack: `docker compose -f python/spaces/rowboat/rowboat/docker-compose.yml up -d`
2. Configure `.env`:
   ```
   ROWBOAT_ENABLED=true
   ROWBOAT_URL=http://localhost:3000
   ROWBOAT_API_KEY=your_key
   ROWBOAT_PROJECT_ID=your_project
   OPENAI_API_KEY=your_openai_key
   ```
3. Install Python SDK: `pip install rowboat` (optional — direct HTTP fallback available)

## Directory Structure

```
roarboot/
├── __init__.py              # Space exports (all components)
├── config.py                # RoarbootConfig
├── README.md                # This file
├── rowboat/                 # Git submodule (Rowboat repo)
├── agents/
│   ├── __init__.py
│   └── roarboot_agent.py    # RoarbootBackendAgent (Redis stream)
├── broadcast/
│   ├── __init__.py
│   └── roarboot_broadcast_agent.py  # RoarbootBroadcastAgent (fan-out)
├── tools/
│   ├── __init__.py
│   ├── roarboot_client.py   # Rowboat SDK wrapper + direct HTTP
│   ├── roarboot_tools.py    # Voice-controllable tools (knowledge, content)
│   └── docker_tools.py      # Docker management tools
├── workers/
│   ├── __init__.py
│   └── roarboot_workers.py  # HealthCheckWorker (Docker monitoring)
└── sub_agents/              # Sub-agents (reserved)
    └── __init__.py
```

## Components

### RoarbootClient
SDK wrapper with direct HTTP fallback. Supports per-context conversations:
- `search` context for knowledge searches
- `email` context for email drafting
- `meeting` context for meeting briefs
- `default` for general queries

### RoarbootBackendAgent
Extends `BaseBackendAgent`, listens to `events:tasks:roarboot` stream.
Maps 13 event types to tool functions via `EVENT_TO_TOOL`.

### RoarbootBroadcastAgent
Extends `BaseBroadcastAgent` for fan-out broadcast architecture.
Handles user profiling from knowledge management perspective.

### HealthCheckWorker
Background worker that monitors Docker stack health every 60s.
Auto-restarts containers if `ROWBOAT_AUTO_START=true`.
