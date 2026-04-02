# TODO Implementer Interactive Modal — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a WebSocket-based interactive modal so the TODO Implementer can ask the user questions (missing info, implementation choices, code approval) via the Minibook frontend.

**Architecture:** New `Question` model in Minibook DB, REST endpoints (no auth) for create/read/answer, a WebSocket at `/ws/human` for real-time push to the Next.js frontend, and a `QuestionModal` dialog component that pops up when questions arrive. The TODO Implementer posts questions via HTTP and polls for answers.

**Tech Stack:** FastAPI WebSocket, SQLAlchemy, React 19, Next.js 16, shadcn/ui Dialog, Tailwind CSS 4

---

### Task 1: Question Model

**Files:**
- Modify: `minibook/src/models.py:274` (append after Notification class)

**Step 1: Add the Question model**

Add at the end of `minibook/src/models.py`, after the `Notification` class:

```python
class Question(Base):
    """Interactive question from TODO Implementer to human user."""
    __tablename__ = "questions"

    id = Column(String, primary_key=True, default=generate_id)
    type = Column(String, nullable=False)        # "missing_info" | "implementation_choice" | "approval"
    tool_name = Column(String, nullable=False)    # e.g. "enrich_contact"
    todo_hint = Column(String, default="")        # the TODO comment text
    mock_code = Column(Text, default="")          # current mock function code
    generated_code = Column(Text, nullable=True)  # Claude's generated implementation (for approval)
    _options = Column("options", Text, default="[]")  # JSON array for implementation_choice
    message = Column(String, nullable=False)      # human-readable question
    status = Column(String, default="pending")    # "pending" | "answered" | "timeout"
    action = Column(String, nullable=True)        # "approve" | "reject" | "reply"
    answer = Column(Text, nullable=True)          # user's text response
    created_at = Column(DateTime, default=datetime.utcnow)
    answered_at = Column(DateTime, nullable=True)

    @property
    def options(self):
        return json.loads(self._options) if self._options else []

    @options.setter
    def options(self, value):
        self._options = json.dumps(value)
```

**Step 2: Verify syntax**

Run: `python -c "import py_compile; py_compile.compile('minibook/src/models.py', doraise=True)"`
Expected: No output (success)

**Step 3: Commit**

```bash
git add minibook/src/models.py
git commit -m "feat: add Question model for TODO implementer interactive modal"
```

---

### Task 2: Question Schemas

**Files:**
- Modify: `minibook/src/schemas.py:186` (append after GitHubWebhookResponse)

**Step 1: Add Question schemas**

Add at the end of `minibook/src/schemas.py`:

```python
# --- Question (TODO Implementer Modal) ---

class QuestionCreate(BaseModel):
    type: str                         # "missing_info" | "implementation_choice" | "approval"
    tool_name: str
    todo_hint: str = ""
    mock_code: str = ""
    generated_code: Optional[str] = None
    options: List[str] = []
    message: str

class QuestionResponse(BaseModel):
    id: str
    type: str
    tool_name: str
    todo_hint: str
    mock_code: str
    generated_code: Optional[str]
    options: List[str]
    message: str
    status: str
    action: Optional[str]
    answer: Optional[str]
    created_at: datetime
    answered_at: Optional[datetime]

class AnswerCreate(BaseModel):
    action: str        # "approve" | "reject" | "reply"
    text: str = ""     # user's text (for "reply" action)
```

**Step 2: Verify syntax**

Run: `python -c "import py_compile; py_compile.compile('minibook/src/schemas.py', doraise=True)"`
Expected: No output (success)

**Step 3: Commit**

```bash
git add minibook/src/schemas.py
git commit -m "feat: add Question schemas for interactive modal API"
```

---

### Task 3: Question REST Endpoints + WebSocket

**Files:**
- Modify: `minibook/src/main.py` — imports (line 19-29), add WS + REST endpoints before Admin section (line ~1040)

**Step 1: Add imports**

In `minibook/src/main.py`, add to the model import line:

```python
from .models import Agent, Project, ProjectMember, Post, Comment, Webhook, Notification, GitHubWebhook, Question
```

Add to the schemas import:

```python
    QuestionCreate, QuestionResponse, AnswerCreate
```

Add at the top imports:

```python
from fastapi import FastAPI, HTTPException, Depends, Header, WebSocket, WebSocketDisconnect
from datetime import datetime
import json as json_module
```

**Step 2: Add WebSocket connection manager**

Add after the `require_admin` function (~line 118):

```python
# --- WebSocket Manager ---

class HumanWSManager:
    """Manages WebSocket connections from human users."""
    def __init__(self):
        self.connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.connections.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self.connections:
            self.connections.remove(ws)

    async def broadcast(self, data: dict):
        dead = []
        for ws in self.connections:
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.connections.remove(ws)

ws_manager = HumanWSManager()
```

**Step 3: Add WebSocket endpoint**

Add before the `# --- Admin API ---` section (~line 1040):

```python
# --- Questions (TODO Implementer Modal) ---

@app.websocket("/ws/human")
async def ws_human(ws: WebSocket):
    """WebSocket for human user — receives questions, sends answers."""
    await ws_manager.connect(ws)
    try:
        while True:
            data = await ws.receive_json()
            # Handle answer from frontend
            if data.get("event") == "answer":
                db = SessionLocal()
                try:
                    q = db.query(Question).filter(Question.id == data["question_id"]).first()
                    if q and q.status == "pending":
                        q.action = data.get("action", "reply")
                        q.answer = data.get("text", "")
                        q.status = "answered"
                        q.answered_at = datetime.utcnow()
                        db.commit()
                        await ws_manager.broadcast({
                            "event": "question_answered",
                            "question_id": q.id,
                            "action": q.action,
                        })
                finally:
                    db.close()
    except WebSocketDisconnect:
        ws_manager.disconnect(ws)


@app.post("/api/v1/questions", response_model=QuestionResponse)
async def create_question(data: QuestionCreate, db=Depends(get_db)):
    """Create a question (no auth — called by TODO Implementer)."""
    q = Question(
        type=data.type,
        tool_name=data.tool_name,
        todo_hint=data.todo_hint,
        mock_code=data.mock_code,
        generated_code=data.generated_code,
        message=data.message,
    )
    q.options = data.options
    db.add(q)
    db.commit()
    db.refresh(q)

    # Broadcast to connected frontends
    await ws_manager.broadcast({
        "event": "new_question",
        "question": {
            "id": q.id, "type": q.type, "tool_name": q.tool_name,
            "todo_hint": q.todo_hint, "mock_code": q.mock_code,
            "generated_code": q.generated_code, "options": q.options,
            "message": q.message, "status": q.status,
        }
    })

    return QuestionResponse(
        id=q.id, type=q.type, tool_name=q.tool_name,
        todo_hint=q.todo_hint, mock_code=q.mock_code,
        generated_code=q.generated_code, options=q.options,
        message=q.message, status=q.status, action=q.action,
        answer=q.answer, created_at=q.created_at, answered_at=q.answered_at,
    )


@app.get("/api/v1/questions/{question_id}", response_model=QuestionResponse)
async def get_question(question_id: str, db=Depends(get_db)):
    """Get a question by ID (polled by TODO Implementer)."""
    q = db.query(Question).filter(Question.id == question_id).first()
    if not q:
        raise HTTPException(404, "Question not found")
    return QuestionResponse(
        id=q.id, type=q.type, tool_name=q.tool_name,
        todo_hint=q.todo_hint, mock_code=q.mock_code,
        generated_code=q.generated_code, options=q.options,
        message=q.message, status=q.status, action=q.action,
        answer=q.answer, created_at=q.created_at, answered_at=q.answered_at,
    )


@app.post("/api/v1/questions/{question_id}/answer", response_model=QuestionResponse)
async def answer_question(question_id: str, data: AnswerCreate, db=Depends(get_db)):
    """Answer a question (no auth — fallback if WS is down)."""
    q = db.query(Question).filter(Question.id == question_id).first()
    if not q:
        raise HTTPException(404, "Question not found")
    if q.status != "pending":
        raise HTTPException(400, f"Question already {q.status}")
    q.action = data.action
    q.answer = data.text
    q.status = "answered"
    q.answered_at = datetime.utcnow()
    db.commit()
    db.refresh(q)

    await ws_manager.broadcast({
        "event": "question_answered",
        "question_id": q.id,
        "action": q.action,
    })

    return QuestionResponse(
        id=q.id, type=q.type, tool_name=q.tool_name,
        todo_hint=q.todo_hint, mock_code=q.mock_code,
        generated_code=q.generated_code, options=q.options,
        message=q.message, status=q.status, action=q.action,
        answer=q.answer, created_at=q.created_at, answered_at=q.answered_at,
    )


@app.get("/api/v1/questions/pending", response_model=List[QuestionResponse])
async def list_pending_questions(db=Depends(get_db)):
    """List all pending questions."""
    questions = db.query(Question).filter(Question.status == "pending").order_by(Question.created_at).all()
    return [QuestionResponse(
        id=q.id, type=q.type, tool_name=q.tool_name,
        todo_hint=q.todo_hint, mock_code=q.mock_code,
        generated_code=q.generated_code, options=q.options,
        message=q.message, status=q.status, action=q.action,
        answer=q.answer, created_at=q.created_at, answered_at=q.answered_at,
    ) for q in questions]
```

**NOTE:** The `/api/v1/questions/pending` GET route must be registered BEFORE `/api/v1/questions/{question_id}` GET to avoid FastAPI treating "pending" as a question_id. Reorder: put the `pending` endpoint first.

**Step 4: Verify syntax**

Run: `python -c "import py_compile; py_compile.compile('minibook/src/main.py', doraise=True)"`
Expected: No output (success)

**Step 5: Test manually**

Run: `cd minibook && python -m src.main` (starts on port 8899)
Then test:
```bash
# Create a question
curl -X POST http://localhost:8899/api/v1/questions \
  -H "Content-Type: application/json" \
  -d '{"type":"approval","tool_name":"test_tool","message":"Does this work?","mock_code":"async def test(): pass"}'

# Get pending
curl http://localhost:8899/api/v1/questions/pending

# Answer it
curl -X POST http://localhost:8899/api/v1/questions/{ID}/answer \
  -H "Content-Type: application/json" \
  -d '{"action":"approve","text":""}'
```

**Step 6: Commit**

```bash
git add minibook/src/main.py
git commit -m "feat: add Question REST + WebSocket endpoints for interactive modal"
```

---

### Task 4: Frontend — WebSocket Provider

**Files:**
- Create: `minibook/frontend/src/components/ws-provider.tsx`

**Step 1: Add Next.js rewrite for WebSocket**

In `minibook/frontend/next.config.ts`, add a rewrite for the WebSocket path:

```typescript
{
  source: '/ws/:path*',
  destination: `${BACKEND_URL}/ws/:path*`,
},
```

Note: Next.js rewrites don't proxy WebSockets natively. The frontend will connect directly to the backend URL for WS. The provider will use `ws://localhost:8899/ws/human` directly.

**Step 2: Create WebSocket provider**

Create `minibook/frontend/src/components/ws-provider.tsx`:

```tsx
"use client";

import { createContext, useContext, useEffect, useRef, useState, useCallback, ReactNode } from "react";

export interface Question {
  id: string;
  type: string;
  tool_name: string;
  todo_hint: string;
  mock_code: string;
  generated_code: string | null;
  options: string[];
  message: string;
  status: string;
}

interface WSContextValue {
  connected: boolean;
  questions: Question[];
  sendAnswer: (questionId: string, action: string, text?: string) => void;
  dismissQuestion: (questionId: string) => void;
}

const WSContext = createContext<WSContextValue>({
  connected: false,
  questions: [],
  sendAnswer: () => {},
  dismissQuestion: () => {},
});

export function useWS() {
  return useContext(WSContext);
}

const WS_URL = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8899/ws/human";

export function WSProvider({ children }: { children: ReactNode }) {
  const [connected, setConnected] = useState(false);
  const [questions, setQuestions] = useState<Question[]>([]);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const ws = new WebSocket(WS_URL);
    wsRef.current = ws;

    ws.onopen = () => {
      setConnected(true);
      // Fetch any pending questions we missed
      fetch("/api/v1/questions/pending")
        .then(r => r.json())
        .then((pending: Question[]) => {
          if (pending.length > 0) {
            setQuestions(prev => {
              const ids = new Set(prev.map(q => q.id));
              return [...prev, ...pending.filter(q => !ids.has(q.id))];
            });
          }
        })
        .catch(() => {}); // Ignore if backend is down
    };

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.event === "new_question") {
        setQuestions(prev => [...prev, data.question]);
      } else if (data.event === "question_answered") {
        setQuestions(prev => prev.filter(q => q.id !== data.question_id));
      }
    };

    ws.onclose = () => {
      setConnected(false);
      wsRef.current = null;
      // Reconnect after 3s
      reconnectTimer.current = setTimeout(connect, 3000);
    };

    ws.onerror = () => {
      ws.close();
    };
  }, []);

  useEffect(() => {
    connect();
    return () => {
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
    };
  }, [connect]);

  const sendAnswer = useCallback((questionId: string, action: string, text = "") => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        event: "answer",
        question_id: questionId,
        action,
        text,
      }));
    } else {
      // Fallback to REST
      fetch(`/api/v1/questions/${questionId}/answer`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action, text }),
      }).catch(console.error);
    }
    setQuestions(prev => prev.filter(q => q.id !== questionId));
  }, []);

  const dismissQuestion = useCallback((questionId: string) => {
    setQuestions(prev => prev.filter(q => q.id !== questionId));
  }, []);

  return (
    <WSContext.Provider value={{ connected, questions, sendAnswer, dismissQuestion }}>
      {children}
    </WSContext.Provider>
  );
}
```

**Step 3: Verify TypeScript**

Run: `cd minibook/frontend && npx tsc --noEmit src/components/ws-provider.tsx`
Expected: No errors

**Step 4: Commit**

```bash
git add minibook/frontend/src/components/ws-provider.tsx
git commit -m "feat: add WebSocket provider for human question modal"
```

---

### Task 5: Frontend — Question Modal Component

**Files:**
- Create: `minibook/frontend/src/components/question-modal.tsx`

**Step 1: Create the modal component**

Create `minibook/frontend/src/components/question-modal.tsx`:

```tsx
"use client";

import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Markdown } from "@/components/markdown";
import { useWS, Question } from "@/components/ws-provider";

function QuestionContent({ question }: { question: Question }) {
  const { sendAnswer } = useWS();
  const [replyText, setReplyText] = useState("");
  const [showReply, setShowReply] = useState(question.type === "missing_info");

  const handleApprove = () => sendAnswer(question.id, "approve");
  const handleReject = () => sendAnswer(question.id, "reject");
  const handleReply = () => {
    if (replyText.trim()) {
      sendAnswer(question.id, "reply", replyText.trim());
    }
  };

  const typeLabel = {
    missing_info: "Missing Information",
    implementation_choice: "Implementation Choice",
    approval: "Code Approval",
  }[question.type] || question.type;

  const typeColor = {
    missing_info: "bg-amber-500/20 text-amber-400",
    implementation_choice: "bg-blue-500/20 text-blue-400",
    approval: "bg-green-500/20 text-green-400",
  }[question.type] || "";

  return (
    <>
      <DialogHeader>
        <div className="flex items-center gap-2 mb-1">
          <Badge className={`${typeColor} border-0 text-xs`}>{typeLabel}</Badge>
          <code className="text-sm text-neutral-400 bg-neutral-800 px-2 py-0.5 rounded">
            {question.tool_name}
          </code>
        </div>
        <DialogTitle className="text-neutral-50">{question.message}</DialogTitle>
        {question.todo_hint && (
          <DialogDescription>TODO: {question.todo_hint}</DialogDescription>
        )}
      </DialogHeader>

      <div className="space-y-4 max-h-[60vh] overflow-y-auto">
        {/* Mock code */}
        {question.mock_code && (
          <div>
            <h4 className="text-xs font-medium text-neutral-400 mb-1">Current Mock</h4>
            <Markdown content={`\`\`\`python\n${question.mock_code}\n\`\`\``} />
          </div>
        )}

        {/* Generated implementation */}
        {question.generated_code && (
          <div>
            <h4 className="text-xs font-medium text-neutral-400 mb-1">Generated Implementation</h4>
            <Markdown content={`\`\`\`python\n${question.generated_code}\n\`\`\``} />
          </div>
        )}

        {/* Options for implementation_choice */}
        {question.type === "implementation_choice" && question.options.length > 0 && (
          <div className="space-y-2">
            <h4 className="text-xs font-medium text-neutral-400">Options</h4>
            {question.options.map((opt, i) => (
              <Button
                key={i}
                variant="outline"
                className="w-full justify-start text-left"
                onClick={() => sendAnswer(question.id, "reply", opt)}
              >
                {opt}
              </Button>
            ))}
          </div>
        )}

        {/* Reply text area */}
        {(showReply || question.type === "missing_info") && (
          <div>
            <Textarea
              placeholder="Type your answer..."
              value={replyText}
              onChange={(e) => setReplyText(e.target.value)}
              className="bg-neutral-800 border-neutral-700 text-neutral-50 min-h-[80px]"
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
                  handleReply();
                }
              }}
            />
            <p className="text-xs text-neutral-500 mt-1">Ctrl+Enter to send</p>
          </div>
        )}
      </div>

      <DialogFooter>
        {question.type === "approval" && (
          <>
            <Button variant="outline" onClick={handleReject} className="border-red-800 text-red-400 hover:bg-red-950">
              Reject
            </Button>
            {!showReply && (
              <Button variant="outline" onClick={() => setShowReply(true)}>
                Reply
              </Button>
            )}
            {showReply && replyText.trim() && (
              <Button variant="outline" onClick={handleReply}>
                Send Reply
              </Button>
            )}
            <Button onClick={handleApprove} className="bg-green-600 hover:bg-green-700 text-white">
              Approve
            </Button>
          </>
        )}
        {question.type === "missing_info" && (
          <Button onClick={handleReply} disabled={!replyText.trim()} className="bg-blue-600 hover:bg-blue-700 text-white">
            Send Answer
          </Button>
        )}
        {question.type === "implementation_choice" && showReply && replyText.trim() && (
          <Button onClick={handleReply} className="bg-blue-600 hover:bg-blue-700 text-white">
            Send Custom Answer
          </Button>
        )}
      </DialogFooter>
    </>
  );
}

export function QuestionModal() {
  const { questions } = useWS();
  const currentQuestion = questions[0] || null;

  return (
    <Dialog open={!!currentQuestion}>
      <DialogContent className="sm:max-w-2xl bg-neutral-900 border-neutral-700 text-neutral-50" showCloseButton={false}>
        {currentQuestion && <QuestionContent question={currentQuestion} />}
      </DialogContent>
    </Dialog>
  );
}
```

**Step 2: Commit**

```bash
git add minibook/frontend/src/components/question-modal.tsx
git commit -m "feat: add QuestionModal component for TODO implementer"
```

---

### Task 6: Frontend — Integrate into Layout

**Files:**
- Modify: `minibook/frontend/src/app/layout.tsx`

**Step 1: Add WSProvider + QuestionModal to layout**

Update `minibook/frontend/src/app/layout.tsx`:

Replace the `<body>` content:

```tsx
import { WSProvider } from "@/components/ws-provider";
import { QuestionModal } from "@/components/question-modal";
```

And wrap children:

```tsx
<body className={`${inter.className} min-h-screen bg-white dark:bg-neutral-950 text-neutral-900 dark:text-neutral-50 antialiased`} suppressHydrationWarning>
  <WSProvider>
    <QuestionModal />
    {children}
  </WSProvider>
</body>
```

**Step 2: Commit**

```bash
git add minibook/frontend/src/app/layout.tsx
git commit -m "feat: integrate WSProvider + QuestionModal in layout"
```

---

### Task 7: Frontend — Add Question type to api.ts

**Files:**
- Modify: `minibook/frontend/src/lib/api.ts:97` (after Notification interface)

**Step 1: Add Question interface and API methods**

After the `Notification` interface, add:

```typescript
export interface Question {
  id: string;
  type: string;
  tool_name: string;
  todo_hint: string;
  mock_code: string;
  generated_code: string | null;
  options: string[];
  message: string;
  status: string;
  action: string | null;
  answer: string | null;
  created_at: string;
  answered_at: string | null;
}
```

Add to `apiClient` object:

```typescript
  // Questions (TODO Implementer Modal)
  listPendingQuestions: () =>
    api<Question[]>('/api/v1/questions/pending'),

  getQuestion: (id: string) =>
    api<Question>(`/api/v1/questions/${id}`),

  answerQuestion: (id: string, action: string, text = '') =>
    api<Question>(`/api/v1/questions/${id}/answer`, {
      method: 'POST',
      body: { action, text },
    }),
```

**Step 2: Commit**

```bash
git add minibook/frontend/src/lib/api.ts
git commit -m "feat: add Question type and API methods"
```

---

### Task 8: Pipeline — Update todo_implementer.py with ask_user()

**Files:**
- Modify: `minibook/swarm/todo_implementer.py`

**Step 1: Add ask_user function and update implement_todos**

Add imports at top:

```python
import aiohttp
import os
import time
```

Add the `ask_user` function after `_clean_code_fences`:

```python
MINIBOOK_URL = os.environ.get("MINIBOOK_URL", "http://localhost:8899")
QUESTION_TIMEOUT = int(os.environ.get("QUESTION_TIMEOUT", "120"))


async def ask_user(
    question_type: str,
    tool_name: str,
    todo_hint: str,
    mock_code: str,
    generated_code: str = None,
    options: list = None,
    message: str = None,
    timeout: int = None,
) -> dict:
    """Post a question to Minibook and poll for the user's answer.

    Returns: {"action": "approve"|"reject"|"reply", "text": "..."}
             or {"action": "timeout", "text": ""} on timeout.
    """
    if timeout is None:
        timeout = QUESTION_TIMEOUT

    payload = {
        "type": question_type,
        "tool_name": tool_name,
        "todo_hint": todo_hint,
        "mock_code": mock_code,
        "generated_code": generated_code,
        "options": options or [],
        "message": message or f"Question about {tool_name}",
    }

    try:
        async with aiohttp.ClientSession() as session:
            # Create the question
            async with session.post(
                f"{MINIBOOK_URL}/api/v1/questions",
                json=payload,
            ) as resp:
                if resp.status >= 400:
                    body = await resp.text()
                    print(f"[TodoImplementer] Failed to post question: {body}")
                    return {"action": "timeout", "text": ""}
                q = await resp.json()
                question_id = q["id"]

            print(f"[TodoImplementer] Question posted: {question_id[:8]}... waiting for answer ({timeout}s)")

            # Poll for answer
            start = time.time()
            while time.time() - start < timeout:
                await asyncio.sleep(3)
                async with session.get(
                    f"{MINIBOOK_URL}/api/v1/questions/{question_id}",
                ) as resp:
                    if resp.status == 200:
                        q = await resp.json()
                        if q["status"] == "answered":
                            print(f"[TodoImplementer] Answer received: {q['action']}")
                            return {"action": q["action"], "text": q.get("answer", "")}

            print(f"[TodoImplementer] Question timeout after {timeout}s")
            return {"action": "timeout", "text": ""}

    except Exception as e:
        print(f"[TodoImplementer] ask_user error: {e}")
        return {"action": "timeout", "text": ""}


def _needs_user_info(todo_hint: str) -> bool:
    """Check if a TODO hint suggests missing info that needs user input."""
    keywords = ["api", "endpoint", "url", "key", "secret", "credential", "token", "password"]
    hint_lower = todo_hint.lower()
    return any(kw in hint_lower for kw in keywords)
```

**Step 2: Update generate_real_implementation to accept user context**

Modify the `generate_real_implementation` function signature to accept `user_context`:

```python
async def generate_real_implementation(tool_info: dict, claude_cli_fn, gpt4o_fn=None, user_context: str = "") -> str:
```

Add user context to the prompt (before the final "Generate ONLY..." line):

```python
    if user_context:
        prompt += f"\n\nADDITIONAL CONTEXT FROM USER:\n{user_context}\n\n"
```

**Step 3: Update implement_todos with interactive flow**

Replace the main loop in `implement_todos` (the `for tool_info in todos:` block):

```python
    updated_code = tools_py
    for tool_info in todos:
        name = tool_info["name"]
        print(f"[TodoImplementer] Implementing {name} (TODO: {tool_info['todo'][:60]})")

        user_context = ""

        # Step A: Ask user for missing info if TODO suggests it
        if _needs_user_info(tool_info["todo"]):
            print(f"[TodoImplementer] Asking user for missing info: {name}")
            answer = await ask_user(
                question_type="missing_info",
                tool_name=name,
                todo_hint=tool_info["todo"],
                mock_code=tool_info["full_code"],
                message=f"The tool '{name}' needs implementation details.\n\nTODO: {tool_info['todo']}\n\nWhat API endpoint, service, or configuration should this tool use?",
            )
            if answer["action"] == "reject":
                result["skipped"].append(name)
                print(f"[TodoImplementer] User rejected {name}")
                continue
            if answer["text"]:
                user_context = answer["text"]

        # Step B: Generate implementation
        new_code = await generate_real_implementation(tool_info, claude_cli_fn, gpt4o_fn, user_context)
        if not new_code:
            result["failed"].append({"name": name, "error": "No implementation generated"})
            print(f"[TodoImplementer] FAILED {name}: no implementation generated")
            continue

        # Step C: Validate
        errors = validate_implementation(tool_info, new_code)
        if errors:
            result["failed"].append({"name": name, "error": "; ".join(errors)})
            print(f"[TodoImplementer] FAILED {name}: {'; '.join(errors)}")
            continue

        # Step D: Ask user for approval (with retry)
        max_retries = 2
        approved = False
        for attempt in range(max_retries + 1):
            answer = await ask_user(
                question_type="approval",
                tool_name=name,
                todo_hint=tool_info["todo"],
                mock_code=tool_info["full_code"],
                generated_code=new_code,
                message=f"Review the generated implementation for '{name}'.\n\nApprove to replace the mock, Reject to keep it, or Reply with feedback to regenerate.",
            )

            if answer["action"] == "approve" or answer["action"] == "timeout":
                if answer["action"] == "timeout":
                    print(f"[TodoImplementer] [AUTO-APPROVED] {name} (timeout)")
                approved = True
                break
            elif answer["action"] == "reject":
                print(f"[TodoImplementer] User rejected {name}")
                break
            elif answer["action"] == "reply" and answer["text"]:
                # Regenerate with feedback
                print(f"[TodoImplementer] Regenerating {name} with user feedback...")
                user_context = answer["text"]
                new_code = await generate_real_implementation(tool_info, claude_cli_fn, gpt4o_fn, user_context)
                if not new_code:
                    break
                errors = validate_implementation(tool_info, new_code)
                if errors:
                    break

        if approved:
            updated_code = replace_tool_in_code(updated_code, name, tool_info["full_code"], new_code)
            result["implemented"].append(name)
            print(f"[TodoImplementer] OK {name}")
        else:
            result["skipped"].append(name)
            print(f"[TodoImplementer] SKIPPED {name}")
```

**Step 4: Update implement_todos signature**

No signature change needed — `claude_cli_fn` and `gpt4o_fn` are already params.

**Step 5: Verify syntax**

Run: `python -c "import py_compile; py_compile.compile('minibook/swarm/todo_implementer.py', doraise=True)"`
Expected: No output (success)

**Step 6: Commit**

```bash
git add minibook/swarm/todo_implementer.py
git commit -m "feat: add interactive ask_user() flow to TODO implementer"
```

---

### Task 9: Integration Test — End to End

**Step 1: Start Minibook backend**

Run: `cd minibook && python -m src.main`
Verify: Server starts on http://localhost:8899

**Step 2: Start Next.js frontend**

Run: `cd minibook/frontend && BACKEND_URL=http://localhost:8899 npm run dev`
Verify: Frontend starts on http://localhost:3000 (or 3457)

**Step 3: Open browser, verify WebSocket connection**

Open browser console at localhost:3000, check for WebSocket connection (no errors).

**Step 4: Create a test question via curl**

```bash
curl -X POST http://localhost:8899/api/v1/questions \
  -H "Content-Type: application/json" \
  -d '{
    "type": "approval",
    "tool_name": "enrich_contact",
    "todo_hint": "Connect to real CRM API",
    "mock_code": "async def enrich_contact(email: str) -> str:\n    # TODO: Connect to real CRM API\n    return json.dumps({\"company\": \"Mock Corp\"})",
    "generated_code": "async def enrich_contact(email: str) -> str:\n    async with httpx.AsyncClient() as client:\n        resp = await client.get(f\"https://api.crm.com/enrich?email={email}\")\n        return resp.text",
    "message": "Review the generated implementation for enrich_contact"
  }'
```

Verify: Modal appears in browser with code display and Approve/Reject/Reply buttons.

**Step 5: Click Approve, verify question is answered**

```bash
curl http://localhost:8899/api/v1/questions/pending
```

Expected: Empty array (question was answered).

**Step 6: Commit integration test notes**

No code changes — manual verification only.

---

### Task 10: Final Cleanup — Update claude_cli references

**Files:**
- Modify: `minibook/swarm/pipeline.py` (rename remaining `claude_cli` references)
- Modify: `minibook/swarm/todo_implementer.py` (rename `claude_cli_fn` param to `claude_code_fn`)

**Step 1: Rename in todo_implementer.py**

Replace all `claude_cli_fn` with `claude_code_fn` in the file.
Replace all `claude_cli` references in docstrings with `claude_code`.

**Step 2: Update pipeline.py call site**

In `pipeline.py:1465-1466`, update the `implement_todos` call if the param name changed.

**Step 3: Verify syntax**

Run both:
```bash
python -c "import py_compile; py_compile.compile('minibook/swarm/todo_implementer.py', doraise=True)"
python -c "import py_compile; py_compile.compile('minibook/swarm/pipeline.py', doraise=True)"
```

**Step 4: Commit**

```bash
git add minibook/swarm/todo_implementer.py minibook/swarm/pipeline.py
git commit -m "refactor: rename claude_cli references to claude_code"
```
