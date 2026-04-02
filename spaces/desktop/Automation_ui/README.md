# Automation UI

Desktop Automation Platform with real-time streaming, workflow automation, and AI-powered screen analysis.

---

## Features

- **Desktop Streaming** - Real-time multi-monitor screen capture via WebSocket
- **AI Screen Analysis** - Video Agent (Nemotron VL) with Guardian Mode for auto-correction
- **Workflow Automation** - Node-based workflow system (14 node types)
- **OCR Integration** - Text extraction via Tesseract, EasyOCR, PaddleOCR
- **Remote Desktop Control** - Mouse, keyboard, scroll actions
- **LLM Intent Agent** - Natural language desktop commands via Claude Opus
- **MCP Server** - 32 tools for desktop automation

---

## Quick Start

### Prerequisites

- Node.js 18+
- Python 3.9+
- Windows 10/11 (for desktop automation)

### Installation

```bash
# Clone repository
git clone https://github.com/Flissel/Automation_ui.git
cd Automation_ui

# Install dependencies
npm install
cd backend && pip install -r requirements.txt && cd ..

# Setup environment
cp .env.example .env
# Edit .env with your API keys

# Start all services
scripts\start-all.bat
```

This starts Frontend (port 3003), Backend (port 8007), MoireServer, and Desktop Client.

### Docker (optional)

```bash
docker compose up -d
# Desktop client must run on host (needs monitor access)
python desktop-client/dual_screen_capture_client.py
```

---

## Architecture

| Component | Tech | Port |
| --------- | ---- | ---- |
| Frontend | React 18 + TypeScript + Vite | 3003 |
| Backend | FastAPI + Python 3.9+ | 8007 |
| Desktop Client | Python (mss + pyautogui) | - |
| MoireServer | Node.js | 8766 |
| PostgreSQL | Docker | 5432 |
| Redis | Docker | 6379 |

See [CLAUDE.md](CLAUDE.md) for detailed architecture documentation.

---

## Documentation

- [Architecture: LLM System](docs/en/architecture/llm-architecture.md)
- [Contributing](CONTRIBUTING.md)
- [Security Policy](SECURITY.md)
- [Changelog](CHANGELOG.md)

---

## Support

- [GitHub Issues](https://github.com/Flissel/Automation_ui/issues)
- [GitHub Discussions](https://github.com/Flissel/Automation_ui/discussions)

---

## License

MIT License - see [LICENSE](LICENSE) for details.
