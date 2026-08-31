# VibeMind OS

**The Open-Source AI Operating System** — Voice-controlled, multi-agent, 40+ channels, built by one person.

## Architecture

```
VibeMind-OS/
├── brain/          the_brain               Neuroscience-inspired cognitive routing (standalone)
├── bridge/         brain-openfang-bridge   Routes Brain decisions to OpenFang agents (Claude Code)
├── spaces/         Domain Spaces           14 AI spaces extracted from voice (ideas, coding, desktop, ...)
├── voice/          VibeMind-VoiceDialog    Voice input + intent orchestration + 3D Electron UI
├── ops/            vibemind-os             Operations — email pipeline, pitch deck, MCP tools
├── shared/         vibemind-shared         Shared LLM client (pip install vibemind-shared)
├── security/       vibemind-security       Security research — 30 PoCs, red/blue team
├── x-pathfinder/   x-pathfinder            Backer discovery — evolutionary Twitter scraping
├── langdock-mcp/   langdock-mcp            Langdock API — 35 MCP tools
├── la-fungus-search/ la_fungus_search      Semantic search engine (Qdrant + embeddings)
├── openclaude/     openclaude              OpenClaude HTTP service + Docker deployment
├── coding-engine/  DaveFelix-Coding-Engine  Autonomous code generation (10 AI agents)
├── openclaw/       openclaw                Fork: personal AI assistant (40+ channels)
└── openfang/       openfang                Fork: Agent OS (Rust, 53 tools, 27 LLMs)
```

## Quick Start

```bash
# Clone everything
git clone --recurse-submodules https://github.com/Flissel/VibeMind-OS.git
cd VibeMind-OS

# Or if already cloned:
git submodule update --init --recursive

# Configure API keys
cp .env.example .env
# Edit .env — add at least one LLM key (Groq is free: https://console.groq.com/)

# Start Brain + OpenFang + Bridge
./start.sh
```

### Services

| Service  | Port  | Description                                |
| -------- | ----- | ------------------------------------------ |
| Brain    | 5000  | Cognitive routing (Hebbian learning)       |
| OpenFang | 50051 | Agent OS (57 tools, 27 LLMs)               |
| Bridge   | 5100  | Routes Brain decisions to OpenFang agents   |

### Test the routing chain

```bash
curl -X POST http://localhost:5100/bridge/route \
  -H "Content-Type: application/json" \
  -d '{"task": "Write a fibonacci function in Python"}'
```

### Voice workspace (Electron 3D UI)
```bash
cd voice && pip install -r requirements.txt
python python/electron_backend.py
```

## What Each Repo Does

| Repo | Purpose | Tech |
|------|---------|------|
| **voice** | Voice-controlled 3D AI workspace with 14 domain spaces | Python, Electron, Three.js |
| **ops** | Email campaigns, pitch deck generation, PC monitoring MCPs | Python, SMTP, LLM |
| **shared** | Multi-provider LLM client factory (OpenAI, Anthropic, Gemini, Groq, Ollama) | Python pip package |
| **security** | 30 security PoCs: injection chains, red/blue team, forensics, scanning | Python, AutoGen |
| **x-pathfinder** | Evolutionary X/Twitter discovery + backer scoring for crowdfunding | Python, genetic algorithms |
| **langdock-mcp** | MCP server for Langdock API (35 tools), AutoGen multi-agent team | Python, FastMCP |
| **davelovable** | AI-powered web development platform with multi-agent orchestration | React, Node.js |
| **openclaw** | Personal AI assistant across 40+ messaging channels | Node.js (fork) |
| **openfang** | Agent Operating System — 27 LLMs, 53 tools, WASM sandbox | Rust (fork) |

## The Stack

```
User speaks / types / messages
        |
  ┌─────┴──────────────────────────────┐
  │  voice/    3D UI + Voice Input      │
  │  openclaw/ Telegram/WhatsApp/Slack  │
  │  openfang/ 40 channels + 27 LLMs   │
  └─────┬──────────────────────────────┘
        |
  ┌─────┴──────────────────────────────┐
  │  Swarm Orchestrator + AutoGen       │
  │  14 Domain Spaces + Intent Router   │
  └─────┬──────────────────────────────┘
        |
  ┌─────┴──────────────────────────────┐
  │  shared/       LLM client factory   │
  │  langdock-mcp/ Enterprise AI API    │
  │  ops/          Email + Pitch + MCPs │
  │  security/     Monitoring + Defense │
  └────────────────────────────────────┘
```

## License

MIT License — see each repo for details.

## Author

**Felix Baumann** ([@Flissel](https://github.com/Flissel)) — built entirely solo.
