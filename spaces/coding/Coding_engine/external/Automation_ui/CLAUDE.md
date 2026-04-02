# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

The Trusted Login System is a modern authentication and desktop automation platform combining secure authentication with advanced desktop integration capabilities. The system enables:

- **Desktop Streaming**: Real-time desktop screen capture and streaming via WebSocket
- **Multi-Monitor Support**: Simultaneous streaming from multiple desktop clients
- **Workflow Automation**: Node-based workflow system for desktop automation tasks
- **OCR Integration**: Text extraction from desktop screens using OCR regions
- **Remote Desktop Control**: Click actions, text input, and keyboard control
- **Supabase Integration**: Edge functions for WebSocket relay and processing

## Technology Stack

### Frontend

- **React 18** with TypeScript
- **Vite** (dev server on port 5173)
- **Tailwind CSS** + shadcn/ui components
- **Zustand** for state management
- **React Query** (@tanstack/react-query) for API/data fetching
- **React Router** for navigation
- **Playwright** for E2E testing

### Backend

- **FastAPI** (Python 3.9+) on port 8007
  - Integrated WebSocket support
  - RESTful API endpoints (`/api/v1`, `/api/automation`, `/api/workflows`, etc.)
  - Desktop automation services (PyAutoGUI, OCR with Tesseract/EasyOCR/PaddleOCR)
  - Service Manager for lifecycle management
  - Live desktop streaming and control
- **Supabase** Edge Functions (Deno runtime)
  - `live-desktop-stream`: WebSocket relay for desktop streaming
  - `desktop-actions`: Desktop control commands
  - `ocr-processor`: OCR text extraction
  - `filesystem-bridge`: File operations
- **PostgreSQL** (via Supabase)
- **WebSockets** for real-time communication (both FastAPI and Supabase)

## Development Commands

### Quick Start (All Services)

```bash
# Start ALL services with one command (recommended)
scripts\start-all.bat

# This starts:
# - FastAPI Backend (port 8007)
# - MoireServer (port 8766)
# - Moire Agents worker
# - Frontend (port 3003)
# - Desktop Client (dual-monitor streaming)
# Opens http://localhost:3003/electron automatically
```

### Frontend Commands

```bash
# Start frontend development server (runs on http://localhost:5173 or 3003)
npm run dev

# Build for production
npm run build

# Build in development mode
npm run build:dev

# Lint code
npm run lint

# Preview production build
npm run preview
```

### Backend Commands

```bash
# Start FastAPI backend server (runs on http://localhost:8007)
cd backend
python server.py
# OR with uvicorn directly
uvicorn server:app --host 0.0.0.0 --port 8007 --reload

# Run backend tests
cd backend
pytest

# Run specific test file
pytest tests/test_name.py

# Run tests with coverage
pytest --cov=app tests/
```

### External Repository Management

The project uses external repositories managed via scripts:

```bash
# Update external repositories from config/external-repos.json
npm run update-external

# Force update even if no changes detected
npm run update-external:force

# Update with verbose logging
npm run update-external:verbose
```

### Branch Management

```bash
# List all branches
npm run branch:list

# Switch between branches
npm run branch:switch

# Create new branch
npm run branch:create

# Update branch
npm run branch:update
```

### Testing

```bash
# Run Playwright E2E tests (uses http://localhost:5173 - auto-starts dev server)
npx playwright test

# Run tests in UI mode
npx playwright test --ui

# Run tests in specific browser
npx playwright test --project=chromium

# Run tests without starting dev server (if already running)
npx playwright test --headed
```

## Architecture

### Dual Backend Architecture

The system uses **two complementary backend services**:

1. **FastAPI Backend** (Port 8007)
   - Primary API server for desktop automation
   - Direct WebSocket connections at `ws://localhost:8007/ws/live-desktop`
   - RESTful API endpoints for automation, workflows, OCR, and shell commands
   - Python-based desktop control (PyAutoGUI, Tesseract OCR, etc.)
   - Service Manager coordinates all backend services

2. **Supabase Edge Functions** (Deno runtime)
   - Cloud-based WebSocket relay at `wss://{YOUR_SUPABASE_PROJECT_ID}.supabase.co/functions/v1/live-desktop-stream`
   - Acts as intermediary between desktop clients and web clients
   - Serverless functions for processing and routing
   - PostgreSQL database integration

**Usage Decision**:

- Use **FastAPI backend** when running locally with direct desktop access
- Use **Supabase Edge Functions** for cloud-based relay or when desktop clients are remote

### WebSocket Communication Pattern

The system supports **both direct and relay architectures** for desktop streaming:

1. **Desktop Clients** (Python/external agents) connect to Supabase Edge Function with `client_type=desktop`
2. **Web Clients** (React frontend) connect with `client_type=web`
3. **Edge Function** (`live-desktop-stream`) acts as relay between desktop and web clients

**Important**: All WebSocket connections MUST go through the centralized configuration in `src/config/websocketConfig.ts`. This file provides:

- Base URL configuration (Supabase Edge Function URL)
- Client factory functions (`createWebClient`, `createMultiDesktopClient`, etc.)
- Handshake message standardization
- Connection utilities

**WebSocket Message Flow**:

```
Desktop Client → Edge Function → Web Client (for frames)
Web Client → Edge Function → Desktop Client (for commands)
```

**Key Message Types**:

- `handshake`: Client identification and capabilities
- `start_capture`/`stop_capture`: Control desktop streaming
- `frame_data`: Desktop screen frames (base64 encoded)
- `mouse_click`/`keyboard_input`: Remote control actions
- `start_ocr_extraction`/`stop_ocr_extraction`: OCR control
- `get_desktop_clients`: Request list of available desktop clients

### Directory Structure

```
src/                    # Frontend source code
├── components/         # React components (shadcn/ui based)
│   ├── layout/        # Navigation and layout components
│   ├── trae/          # TRAE-specific components
│   │   ├── liveDesktop/          # Live desktop streaming components
│   │   ├── virtualDesktop/       # Virtual desktop management
│   │   ├── workflow/             # Workflow execution and visualization
│   │   └── nodes/                # Custom workflow node components
│   └── ui/            # shadcn/ui components (Button, Dialog, etc.)
├── config/            # Configuration files
│   ├── websocketConfig.ts        # CENTRALIZED WebSocket config (MUST use this!)
│   └── nodes/                    # Node type definitions for workflows
├── hooks/             # React custom hooks
│   ├── useWebSocketReconnect.ts  # Auto-reconnection hook (RECOMMENDED)
│   └── useWebSocketConnection.ts # Basic WebSocket hook
├── integrations/
│   └── supabase/      # Supabase client and types
├── lib/               # Utility libraries
├── pages/             # Route pages
│   ├── Dashboard.tsx
│   ├── MultiDesktopStreams.tsx   # Multiple desktop streams grid
│   ├── VirtualDesktops.tsx       # Virtual desktop management
│   ├── Workflow.tsx              # Workflow automation UI
│   └── Auth.tsx
├── services/          # Service layer for API/WebSocket communication
│   ├── desktopStreamService.ts   # Desktop streaming commands
│   ├── liveDesktopService.ts     # Live desktop integration
│   ├── desktopControlService.ts  # Remote control actions
│   ├── virtualDesktopManager.ts  # Virtual desktop management
│   ├── ocrBackendService.ts      # OCR operations
│   └── filesystemBridge.ts       # File operations
├── stores/            # Zustand state management
│   └── workflowStore.ts
├── types/             # TypeScript type definitions
├── utils/             # Utility functions
├── workflows/         # Workflow system (see workflows/README.md)
│   └── README.md      # Comprehensive workflow documentation
└── App.tsx            # Main app component with routing

backend/               # FastAPI Python backend
├── app/
│   ├── main.py        # FastAPI application factory
│   ├── config.py      # Configuration management
│   ├── routers/       # API route handlers
│   │   ├── automation.py     # Desktop automation endpoints
│   │   ├── workflows.py      # Workflow execution
│   │   ├── desktop.py        # Desktop control
│   │   ├── ocr.py            # OCR processing
│   │   ├── websocket.py      # WebSocket handlers
│   │   └── health.py         # Health check endpoints
│   ├── services/      # Business logic services
│   │   ├── manager.py                    # Service lifecycle manager
│   │   ├── click_automation_service.py   # Click automation
│   │   ├── desktop_service.py            # Desktop operations
│   │   └── node_service.py               # Node execution
│   ├── models/        # Data models
│   ├── schemas/       # Pydantic schemas
│   └── websocket/     # WebSocket connection management
├── tests/             # Backend tests
├── server.py          # Server entry point
└── requirements.txt   # Python dependencies

supabase/              # Supabase Edge Functions
├── functions/         # Edge Functions (Deno)
│   ├── live-desktop-stream/    # Main WebSocket relay
│   ├── desktop-actions/
│   ├── ocr-processor/
│   └── filesystem-bridge/
└── config.toml        # Supabase configuration (project: {YOUR_SUPABASE_PROJECT_ID})

scripts/
├── update-external-repos.js    # External repo management
└── branch-manager.js           # Git branch utilities
```

### Workflow System

The project includes a comprehensive node-based workflow system located in `src/workflows/`. **IMPORTANT**: Read `src/workflows/README.md` for complete documentation.

**Supported Node Types** (14 total):

- Trigger: `manual_trigger`, `webhook_trigger`
- Configuration: `websocket_config`
- Interface: `live_desktop`
- Actions: `click_action`, `type_text_action`, `http_request_action`, `delay`
- Logic: `if_condition`
- OCR: `ocr_region`, `ocr_extract`
- Integration: `n8n_webhook`, `send_to_filesystem`
- Results: `workflow_result`

**Key Workflow Files**:

- `exampleWorkflows.ts`: Pre-designed workflow templates
- `workflowValidator.ts`: Node compatibility validation
- `workflowManager.ts`: Execution coordinator
- `workflowUtils.ts`: Execution utilities

### Service Layer Pattern

Services in `src/services/` follow a static class pattern:

```typescript
export class DesktopStreamService {
  static startStream(
    websocket: WebSocket,
    desktopClientId: string,
    monitorId?: string,
  ): boolean {
    // Send command via WebSocket
  }

  static stopStream(websocket: WebSocket, desktopClientId: string): boolean {
    // Send command via WebSocket
  }
}
```

All WebSocket communication should use `sendWebSocketMessage()` from `websocketConfig.ts`.

### Import Aliases

The project uses `@/` for absolute imports:

```typescript
import { Button } from "@/components/ui/button";
import { DesktopStreamService } from "@/services/desktopStreamService";
import { createWebClient } from "@/config/websocketConfig";
```

## Key Development Patterns

### WebSocket Connection Setup

**ALWAYS use the centralized WebSocket config**:

#### Option 1: Manual WebSocket Management (Legacy)

```typescript
import {
  createWebClient,
  sendWebSocketMessage,
} from "@/config/websocketConfig";

// Create WebSocket client with standardized config
const { websocket, handshakeMessage, clientId } =
  createWebClient("ComponentName");

websocket.onopen = () => {
  sendWebSocketMessage(websocket, handshakeMessage);
};

websocket.onmessage = (event) => {
  const message = JSON.parse(event.data);

  switch (message.type) {
    case "frame_data":
      // Handle desktop frame
      break;
    case "desktop_clients_list":
      // Handle available desktop clients
      break;
  }
};
```

#### Option 2: Automatic Reconnection Hook (Recommended)

For production-ready WebSocket connections with automatic reconnection, exponential backoff, and connection status management:

```typescript
import { useWebSocketReconnect } from '@/hooks/useWebSocketReconnect';
import { createMultiDesktopClientUrl } from '@/config/websocketConfig';
import { ConnectionStatusIndicator } from '@/components/ui/connection-status';

const MyComponent = () => {
  const { url, handshakeMessage } = createMultiDesktopClientUrl('my_component');

  const {
    websocket,
    status,
    isConnected,
    reconnectAttempt,
    lastError,
    sendMessage,
    reconnect,
    disconnect,
  } = useWebSocketReconnect({
    url,
    handshakeMessage,
    onOpen: (ws) => {
      console.log('Connected!');
      sendMessage({ type: 'get_desktop_clients' });
    },
    onMessage: (event, ws) => {
      const message = JSON.parse(event.data);
      // Handle messages
    },
  });

  return (
    <>
      <ConnectionStatusIndicator
        status={status}
        reconnectAttempt={reconnectAttempt}
        lastError={lastError}
        onReconnect={reconnect}
      />
      {/* Your component UI */}
    </>
  );
};
```

**Reconnection Features:**

- Automatic reconnection with exponential backoff (5s → 10s → 20s → 40s → 60s)
- Configurable max attempts (default: 10)
- Preserves handshake and state across reconnections
- Visual connection status indicators
- Manual reconnect/disconnect controls
- See `src/hooks/useWebSocketReconnect.example.tsx` for detailed examples

### Desktop Client Management

To get list of available desktop clients:

```typescript
import { DesktopStreamService } from "@/services/desktopStreamService";

DesktopStreamService.getDesktopClients(websocket);
```

To start/stop streaming:

```typescript
// Start stream from specific desktop client and monitor
DesktopStreamService.startStream(websocket, "desktop_001", "monitor_0");

// Stop stream
DesktopStreamService.stopStream(websocket, "desktop_001");
```

### Mock Desktop Clients

The Edge Function provides mock desktop clients for testing when no real desktop clients are connected:

- `desktop_001`: Main Workstation (2 monitors)
- `desktop_002`: Development PC (1 monitor)
- `desktop_003`: Test Machine (2 monitors)

Mock clients send SVG-based frames with timestamps for visual testing.

### Component Development

The project uses shadcn/ui components. When adding new UI components:

1. Components are in `src/components/ui/`
2. Follow the shadcn/ui pattern with Radix UI primitives
3. Use Tailwind CSS for styling with `cn()` utility for conditional classes
4. TypeScript is required for all components

### State Management

- **Zustand** for global state (currently minimal, mainly `workflowStore`)
- **React Query** for server state and caching
- Local component state for UI-specific state

## MCP Server Integration

The project includes an MCP (Model Context Protocol) server for desktop automation, configured in `.claude/mcp.json`:

```json
{
  "mcpServers": {
    "desktop-automation": {
      "command": "python",
      "args": ["backend/moire_agents/mcp_server_handoff.py"]
    }
  }
}
```

**Available MCP Tools (32 total)**:

| Category                | Tools                                                                                                                                                                                             |
| ----------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Core Automation**     | `handoff_plan`, `handoff_execute`, `handoff_validate`, `handoff_action`, `handoff_status`                                                                                                         |
| **Screen/OCR**          | `handoff_read_screen`, `handoff_get_focus`, `handoff_scroll`                                                                                                                                      |
| **Event Queue**         | `handoff_event_add`, `handoff_event_status`, `handoff_event_list`, `handoff_event_cancel`, `handoff_batch_execute`                                                                                |
| **User Interaction**    | `handoff_clarify`, `handoff_clarify_check`, `handoff_notify`                                                                                                                                      |
| **File/System**         | `handoff_shell`, `handoff_file_search`, `handoff_file_open`, `handoff_dir_list`, `handoff_file_read`, `handoff_file_write`, `handoff_process_list`, `handoff_process_kill`, `handoff_system_info` |
| **Smart Elements**      | `handoff_find_element`, `handoff_scroll_to`                                                                                                                                                       |
| **Document Processing** | `handoff_doc_scan`, `handoff_doc_edit`, `handoff_doc_apply`, `handoff_doc_export`, `handoff_doc_list`                                                                                             |
| **Claude CLI**          | `claude_cli_run`, `claude_cli_skill`, `claude_cli_status`                                                                                                                                         |

## Desktop Client

The Python desktop client (`desktop-client/dual_screen_capture_client.py`) captures all monitors and streams via WebSocket:

```bash
# Start with local backend
python dual_screen_capture_client.py --server-url ws://localhost:8007/ws/live-desktop

# Start with Supabase relay
python dual_screen_capture_client.py --server-url wss://{YOUR_SUPABASE_PROJECT_ID}.supabase.co/functions/v1/live-desktop-stream
```

**Features**:

- Multi-monitor capture using `mss` library
- DPI-awareness for correct multi-monitor screenshots on Windows
- Auto-reconnect with exponential backoff
- Graceful shutdown handling (SIGTERM/SIGINT)
- Frame format: base64 JPEG with `monitorId` field (`monitor_0`, `monitor_1`, etc.)

## Important Notes

### WebSocket URLs

- **DO NOT hardcode WebSocket URLs** in components
- **ALWAYS import from** `@/config/websocketConfig.ts`
- Edge Function URL format: `wss://{project-id}.supabase.co/functions/v1/{endpoint}`
- Current project ID: `{YOUR_SUPABASE_PROJECT_ID}`

### Environment Variables

**Frontend (.env)**:

```bash
VITE_BACKEND_URL=http://localhost:8007          # FastAPI backend URL
VITE_WS_URL=ws://localhost:8007/ws              # WebSocket URL (optional)
VITE_ENV=development                            # Environment mode
VITE_SUPABASE_PROJECT_ID={YOUR_SUPABASE_PROJECT_ID}   # Supabase project ID (optional)
```

**Backend**:

- Environment variables can be set in backend/.env or via system environment
- Main variables: `HOST`, `PORT`, `WS_PORT`, `LOG_LEVEL`, `ENVIRONMENT`, `DEBUG`
- See `.env.example` for reference

### Git Pre-commit Hooks

The project uses Husky for git hooks with lint-staged:

- ESLint auto-fix on `.{js,jsx,ts,tsx}` files
- Prettier formatting on `.{js,jsx,ts,tsx,json,css,md}` files

### External Repository System

The project can pull code from external repositories defined in `config/external-repos.json`. This supports selective file copying with include/exclude patterns.

### Testing Considerations

- Playwright tests expect dev server on `http://localhost:5173` (Vite default port)
- Tests automatically start dev server via `webServer` config in `playwright.config.ts`
- Tests run against Chromium, Firefox, and WebKit
- Update `playwright.config.ts` if changing ports or test configuration

## Common Tasks

### Adding a New Page/Route

1. Create component in `src/pages/`
2. Add route in `src/App.tsx` ABOVE the catch-all `*` route
3. Add navigation link in `src/components/layout/Navigation.tsx`

### Adding a New Desktop Command

1. Add command type to `DesktopStreamService` in `src/services/desktopStreamService.ts`
2. Implement handler in `supabase/functions/live-desktop-stream/index.ts`
3. Update desktop client (external) to handle new command

### Working with Workflows

1. Review `src/workflows/README.md` for comprehensive documentation
2. Use pre-designed templates from `exampleWorkflows.ts`
3. Validate workflows with `WorkflowValidator` before execution
4. Reference node compatibility matrix for valid connections

### Adding a New Backend API Endpoint

1. Create route handler in `backend/app/routers/` (e.g., `my_feature.py`)
2. Define Pydantic schemas in `backend/app/schemas/` if needed
3. Implement business logic in `backend/app/services/`
4. Register router in `backend/app/main.py` using `app.include_router()`
5. Add tests in `backend/tests/test_my_feature.py`

### Adding a New Service to Backend

1. Create service class in `backend/app/services/`
2. Implement service lifecycle methods (`initialize()`, `cleanup()`)
3. Register service in `backend/app/services/manager.py` (ServiceManager)
4. Access via `app.state.service_manager` in route handlers

### Debugging WebSocket Issues

**Frontend WebSocket Debugging**:

1. Check `websocketConfig.ts` for correct base URL
2. Verify Edge Function is deployed and accessible (for Supabase)
3. Check browser console for WebSocket connection errors
4. Use mock desktop clients for testing frontend without real desktop agents
5. Monitor Edge Function logs in Supabase dashboard
6. Check if `VITE_WS_URL` environment variable is set correctly

**Backend WebSocket Debugging**:

1. Verify FastAPI server is running on port 8007
2. Check WebSocket endpoint at `ws://localhost:8007/ws/live-desktop`
3. Review backend logs for connection errors
4. Test WebSocket connection with tools like wscat: `wscat -c ws://localhost:8007/ws/live-desktop`
5. Ensure CORS is properly configured in `backend/app/main.py`

**Debugging Backend API Issues**:

1. Check FastAPI interactive docs at `http://localhost:8007/docs`
2. Review backend logs for errors (logged via loguru)
3. Verify service initialization in ServiceManager
4. Check CORS configuration for frontend origin
5. Test endpoints with curl or Postman
6. Run backend tests: `cd backend && pytest -v`
