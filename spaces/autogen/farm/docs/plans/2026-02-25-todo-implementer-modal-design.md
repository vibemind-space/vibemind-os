# Design: TODO Implementer Interactive Modal (WebSocket)

## Problem

The TODO Implementer generates real implementations for mock tools but operates fully automated. When it encounters ambiguity (unknown API endpoint, multiple implementation choices), it guesses or fails silently. The user has no way to provide input (API URLs, credentials, preferences) or review generated code before it replaces mocks.

## Solution

Add a WebSocket-based interactive modal system:
- TODO Implementer posts questions to Minibook
- Minibook pushes questions to the frontend via WebSocket
- Frontend shows a modal dialog where the user can reply, approve, or reject
- TODO Implementer receives the answer and continues

## Architecture

### Backend (minibook/src/)

**New WebSocket endpoint:**
```
WS /ws/human
```
- Frontend connects on page load
- Server broadcasts new questions to all connected clients
- Clients send answers back via the same WebSocket

**New REST endpoints (no auth):**
```
POST   /api/v1/questions          — Create a question (from TODO Implementer)
GET    /api/v1/questions/{id}     — Get question + answer (polled by TODO Implementer)
POST   /api/v1/questions/{id}/answer — Submit answer (fallback if WS is down)
GET    /api/v1/questions/pending  — List unanswered questions
```

**New model: `Question`**
```python
class Question(Base):
    __tablename__ = "questions"
    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    type = Column(String)       # "missing_info" | "implementation_choice" | "approval"
    tool_name = Column(String)  # e.g. "enrich_contact"
    todo_hint = Column(String)  # the TODO comment text
    mock_code = Column(Text)    # current mock function code
    generated_code = Column(Text, nullable=True)  # Claude's generated implementation
    options = Column(JSON, nullable=True)          # for implementation_choice type
    message = Column(String)    # human-readable question
    status = Column(String, default="pending")     # "pending" | "answered" | "timeout"
    answer = Column(Text, nullable=True)           # user's response
    created_at = Column(DateTime, default=datetime.utcnow)
    answered_at = Column(DateTime, nullable=True)
```

**WebSocket broadcast flow:**
1. `POST /api/v1/questions` creates question, sets status="pending"
2. Server broadcasts `{"event": "new_question", "question": {...}}` to all WS clients
3. Client sends `{"event": "answer", "question_id": "...", "action": "approve|reject|reply", "text": "..."}`
4. Server updates question, broadcasts `{"event": "question_answered", "question_id": "..."}`

### Frontend (minibook/frontend/)

**WebSocket Provider** (`src/components/ws-provider.tsx`):
- Context provider wrapping the app in layout.tsx
- Connects to `ws://localhost:8899/ws/human`
- Reconnects automatically on disconnect
- Exposes: connected state, pending questions, sendAnswer()

**Question Modal** (`src/components/question-modal.tsx`):
- Shadcn Dialog component
- Shows when a pending question exists
- Renders:
  - Tool name + TODO hint
  - Mock code (syntax-highlighted markdown)
  - Generated implementation (if approval type)
  - Options (if implementation_choice type)
  - Text input for free-form answers
- Three action buttons:
  - **Approve** — accept generated code (approval type)
  - **Reject** — discard, keep mock
  - **Reply** — send text answer
- Auto-dismisses after answering

**Integration in layout.tsx:**
```tsx
<WSProvider>
  <QuestionModal />
  {children}
</WSProvider>
```

### Pipeline (minibook/swarm/todo_implementer.py)

**New function: `ask_user()`**
```python
async def ask_user(question_type, tool_name, todo_hint, mock_code,
                   generated_code=None, options=None, message=None,
                   timeout=120) -> dict:
    """Post question to Minibook, poll for answer."""
```

**Updated flow for each TODO tool:**

1. Scan for TODO markers (unchanged)
2. For each TODO tool:
   a. Check if TODO hint suggests missing info (no API URL, unknown service)
   b. If missing info needed:
      - `ask_user(type="missing_info", message="What API endpoint should X use?")`
      - Wait for reply, include in generation prompt
   c. Generate implementation via `claude_code` tool
   d. `ask_user(type="approval", generated_code=new_code, message="Review this implementation")`
   e. If Approve → replace mock
   f. If Reject → keep mock
   g. If Reply → regenerate with feedback, ask again (max 2 retries)
   h. If Timeout (120s) → auto-approve with warning log

**Detection of "missing info" TODOs:**
- TODO text contains: "API", "endpoint", "URL", "key", "secret", "credential"
- No env var referenced in TODO hint
- These trigger a `missing_info` question before generation

## File Changes

| File | Change |
|------|--------|
| `minibook/src/main.py` | Add WS /ws/human, POST/GET /api/v1/questions, POST /api/v1/questions/{id}/answer |
| `minibook/src/models.py` | Add Question model |
| `minibook/src/schemas.py` | Add QuestionCreate, QuestionResponse, AnswerCreate schemas |
| `minibook/frontend/src/components/ws-provider.tsx` | New WebSocket context provider |
| `minibook/frontend/src/components/question-modal.tsx` | New modal component |
| `minibook/frontend/src/app/layout.tsx` | Wrap with WSProvider + QuestionModal |
| `minibook/frontend/src/lib/api.ts` | Add Question type |
| `minibook/swarm/todo_implementer.py` | Add ask_user(), interactive question flow |

## Timeout Behavior

- Questions timeout after 120 seconds
- On timeout: auto-approve generated implementation with `[AUTO-APPROVED]` tag in logs
- User can configure timeout via `QUESTION_TIMEOUT` env var
