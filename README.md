# VibeMind OS

**The Open-Source AI Operating System** — Voice-controlled, multi-agent, 40+ channels, built by one person.

## Architecture

```
VibeMind-OS/
├── voice/          VibeMind-VoiceDialog    The Product — 14 AI spaces, 3D UI, voice control
├── ops/            vibemind-os             Operations — email pipeline, pitch deck, MCP tools
├── shared/         vibemind-shared         Shared LLM client (pip install vibemind-shared)
├── security/       vibemind-security       Security research — 30 PoCs, red/blue team
├── x-pathfinder/   x-pathfinder            Backer discovery — evolutionary Twitter scraping
├── langdock-mcp/   langdock-mcp            Langdock API — 35 MCP tools
├── la-fungus-search/ la_fungus_search      Semantic search engine (Qdrant + embeddings)
├── openclaude/     openclaude              OpenClaude HTTP service + Docker deployment
├── clawcode/       ClawCode                Docker Claude integration
├── davelovable/    DaveLovable             AI web development platform
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

# Install shared package
cd shared && pip install -e . && cd ..

# Start the voice workspace
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
| **clawcode** | Docker-based Claude Code integration with credential management | Docker, TypeScript |
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
