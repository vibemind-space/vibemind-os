# Web Dashboard Guide

## Startup

```bash
python -m web.brain_server    # Port 5000
```

All dashboards are served from the unified brain server.

## Dashboards

### Unified Brain Dashboard (`/brain`)

The main visualization showing the brain as an interactive SVG with:

- **5 Concentric Rings**: Sensory, Pattern, Semantic, Abstract, Meta — opacity reflects activation level
- **10 Bridge Sectors**: Neuromod, Cortex, Limbic, SleepWake, Motor, Defense, Memory, Integration, Visceral, Social — color intensity reflects bridge activity
- **9 Cognitive Phase Dots**: PERCEIVE through CONSOLIDATE — active phase glows green
- **Center Display**: Frequency mode (delta/theta/alpha/beta/gamma), agent state, Hz

**Right Panel — Modulation:**
- 4 modulation factor gauges (attention gain, precision boost, FFN throughput, threshold mod)
- Experience buffer statistics
- Ring norms history chart (Chart.js)

**Left Panel — Chat:**
- WebSocket chat with GPT-4o
- Responses colored by live brain state (valence, arousal, neuromodulation)
- Semantic thought matching against 200 recent background thoughts
- Shows model, latency, matched thought count

**Data Sources:**
- SSE stream from `/api/radial/stream` (2Hz real-time)
- Poll `/api/modulation` (2s), `/api/cortex/thoughts` (3s)
- Poll `/api/brain/cognitive_loop` (2s), `/api/brain/frequency` (5s)

### Brain Dashboard (`/`)

Classic dashboard with:
- Thalamic gate distribution chart
- Goal tracking and CTM status
- Strategy library
- Chat interface (legacy)
- Alert monitoring

### Radial Dashboard (`/radial`)

Detailed radial attention network view:
- All 10 bridge states with individual metrics
- 5 ring activation norms over time
- 29 hook values (H1-H29) with real-time updates
- 4 modulation composite factors
- DualProcess router state (System 1 vs System 2)

## Chat System

The chat at `/brain` uses WebSocket (`/ws/chat`) with this pipeline:

1. **Snapshot brain state** — reads rings, bridges, modulation, frequency from live RadialAttentionNetwork
2. **Embed user message** — 384-dim via sentence-transformers (all-MiniLM-L6-v2)
3. **Match background thoughts** — cosine similarity against 200 recent ContinuousThoughts, top 5
4. **Build prompt** — system instructions + brain state + matched thoughts + conversation history
5. **Call GPT-4o** — via MultiLLMRouter (`communication` function)
6. **Return response** — with thought context, brain state summary, latency

Brain state subtly influences tone: high arousal = more energetic, negative valence = cautious, high dopamine = enthusiastic, high sleep pressure = dreamy.

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Server health |
| `/api/radial/state` | GET | Full radial network state |
| `/api/radial/stream` | GET (SSE) | Live 2Hz bridge/ring/modulation stream |
| `/api/modulation` | GET | 29 hook values + 4 factors |
| `/api/experience-buffer/stats` | GET | Buffer stats |
| `/api/cortex/thoughts` | GET | Recent background thoughts |
| `/api/brain/cognitive_loop` | GET | Current cognitive loop phase |
| `/api/brain/frequency` | GET | Current frequency mode |
| `/ws/chat` | WebSocket | Brain-state-aware chat |

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Dashboard blank | Check browser console (F12); ensure server is running |
| SSE not connecting | Verify `/api/radial/stream` returns data via curl |
| Chat shows "disconnected" | Refresh page; check WebSocket connection in Network tab |
| No LLM responses | Check `OPENROUTER_API_KEY` in `.env` |
| Slow first response | First LLM call + embedding model load can take 3-5s |
