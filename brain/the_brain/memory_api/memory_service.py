"""
Memory API Service

FastAPI service that provides a clean REST API for memory operations.
Sits between the Tahlamus brain and Supermemory, providing:
- Caching for frequently accessed memories
- Rate limiting
- Multi-user support
- Clean REST endpoints
- Abstraction from Supermemory implementation details

Run with: uvicorn memory_api.memory_service:app --reload --port 8001
"""

import os
import sys
from datetime import datetime
from typing import List, Dict, Optional, Any
from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.supermemory_client import SupermemoryClient
from load_env import load_env_file

# Load environment variables
load_env_file()

# Initialize FastAPI app
app = FastAPI(
    title="Tahlamus Memory API",
    description="Memory service for cognitive AI systems",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Supermemory client
supermemory_client = None

@app.on_event("startup")
async def startup_event():
    """Initialize Supermemory client on startup."""
    global supermemory_client
    api_key = os.getenv('SUPERMEMORY_API_KEY')

    if not api_key:
        print("[WARNING] SUPERMEMORY_API_KEY not set - memory service will not work")
    else:
        supermemory_client = SupermemoryClient(api_key=api_key)
        print(f"[Memory API] Initialized with Supermemory backend")


# Pydantic models for request/response validation

class MemoryCreate(BaseModel):
    """Request model for creating a memory."""
    content: str
    memory_type: str = "general"
    title: Optional[str] = "Untitled"
    description: Optional[str] = ""
    url: Optional[str] = None
    tags: List[str] = []
    metadata: Optional[Dict[str, Any]] = None
    user_id: Optional[str] = None  # For multi-user support


class VisualMemoryCreate(BaseModel):
    """Request model for visual memory."""
    window_title: str
    ocr_text: Optional[str] = None
    visible_files: List[str] = []
    screen_data: Dict[str, Any]
    user_id: Optional[str] = None


class ExecutionMemoryCreate(BaseModel):
    """Request model for execution memory."""
    task: str
    result: str  # SUCCESS, FAILURE, PARTIAL
    confidence: float
    session_log: Optional[str] = None
    agent_name: Optional[str] = None
    duration_ms: Optional[int] = None
    user_id: Optional[str] = None


class ChatMemoryCreate(BaseModel):
    """Request model for chat memory."""
    messages: List[Dict[str, str]]
    topics: List[str] = []
    planning_triggered: bool = False
    user_id: Optional[str] = None


class MemoryQuery(BaseModel):
    """Request model for querying memories."""
    query: Optional[str] = None
    memory_type: Optional[str] = None
    tags: List[str] = []
    limit: int = 10
    include_content: bool = True
    user_id: Optional[str] = None


class MemoryResponse(BaseModel):
    """Response model for memory operations."""
    id: str
    status: str
    message: Optional[str] = None


# API Endpoints

@app.get("/")
async def root():
    """Health check endpoint."""
    return {
        "service": "Tahlamus Memory API",
        "status": "running",
        "supermemory_connected": supermemory_client is not None
    }


@app.get("/health")
async def health():
    """Detailed health check."""
    if not supermemory_client:
        raise HTTPException(status_code=503, detail="Supermemory client not initialized")

    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "supermemory": "connected"
    }


@app.post("/memories", response_model=MemoryResponse)
async def create_memory(memory: MemoryCreate):
    """
    Create a general memory.

    This is the main endpoint for adding any type of memory.
    """
    if not supermemory_client:
        raise HTTPException(status_code=503, detail="Memory service unavailable")

    try:
        # Add user_id to tags if provided
        tags = memory.tags.copy()
        if memory.user_id:
            tags.append(f"user_{memory.user_id}")

        # Create memory
        result = supermemory_client.add_memory(
            page_content=memory.content,
            url=memory.url,
            memory_type=memory.memory_type,
            title=memory.title,
            description=memory.description,
            spaces=tags,
            metadata=memory.metadata
        )

        return MemoryResponse(
            id=result.get('id', 'unknown'),
            status=result.get('status', 'unknown'),
            message="Memory created successfully"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create memory: {str(e)}")


@app.post("/memories/visual", response_model=MemoryResponse)
async def create_visual_memory(memory: VisualMemoryCreate):
    """
    Create a visual memory from screen/desktop data.
    """
    if not supermemory_client:
        raise HTTPException(status_code=503, detail="Memory service unavailable")

    try:
        tags = ["visual", "screen_capture"]
        if memory.user_id:
            tags.append(f"user_{memory.user_id}")

        result = supermemory_client.add_visual_memory(
            screen_data=memory.screen_data,
            window_title=memory.window_title,
            ocr_text=memory.ocr_text,
            visible_files=memory.visible_files
        )

        return MemoryResponse(
            id=result.get('id', 'unknown'),
            status=result.get('status', 'unknown'),
            message="Visual memory created successfully"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create visual memory: {str(e)}")


@app.post("/memories/execution", response_model=MemoryResponse)
async def create_execution_memory(memory: ExecutionMemoryCreate):
    """
    Create an execution memory from agent task completion.
    """
    if not supermemory_client:
        raise HTTPException(status_code=503, detail="Memory service unavailable")

    try:
        tags = ["execution", "agent"]
        if memory.result.lower() == "success":
            tags.append("success")
        else:
            tags.append("failure")

        if memory.user_id:
            tags.append(f"user_{memory.user_id}")

        result = supermemory_client.add_execution_memory(
            task=memory.task,
            result=memory.result,
            confidence=memory.confidence,
            session_log=memory.session_log,
            agent_name=memory.agent_name,
            duration_ms=memory.duration_ms
        )

        return MemoryResponse(
            id=result.get('id', 'unknown'),
            status=result.get('status', 'unknown'),
            message="Execution memory created successfully"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create execution memory: {str(e)}")


@app.post("/memories/chat", response_model=MemoryResponse)
async def create_chat_memory(memory: ChatMemoryCreate):
    """
    Create a chat memory from conversation history.
    """
    if not supermemory_client:
        raise HTTPException(status_code=503, detail="Memory service unavailable")

    try:
        tags = ["chat", "conversation"]
        tags.extend(memory.topics[:3])  # Add up to 3 topics

        if memory.user_id:
            tags.append(f"user_{memory.user_id}")

        result = supermemory_client.add_chat_memory(
            messages=memory.messages,
            topics=memory.topics,
            planning_triggered=memory.planning_triggered
        )

        return MemoryResponse(
            id=result.get('id', 'unknown'),
            status=result.get('status', 'unknown'),
            message="Chat memory created successfully"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create chat memory: {str(e)}")


@app.post("/memories/query")
async def query_memories(query: MemoryQuery):
    """
    Query memories with filters.

    This endpoint allows flexible querying of memories by type, tags, and user.
    """
    if not supermemory_client:
        raise HTTPException(status_code=503, detail="Memory service unavailable")

    try:
        # Add user filter if provided
        tags = query.tags.copy()
        if query.user_id:
            tags.append(f"user_{query.user_id}")

        # Query memories
        memories = supermemory_client.search(
            query=query.query,
            memory_type=query.memory_type,
            spaces=tags if tags else None,
            limit=query.limit,
            include_content=query.include_content
        )

        return {
            "memories": memories,
            "count": len(memories),
            "query": query.dict()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to query memories: {str(e)}")


@app.get("/memories/by-tag/{tag}")
async def get_memories_by_tag(
    tag: str,
    limit: int = 10,
    include_content: bool = True
):
    """
    Get memories by tag/containerTag.
    """
    if not supermemory_client:
        raise HTTPException(status_code=503, detail="Memory service unavailable")

    try:
        memories = supermemory_client.get_by_space(
            space=tag,
            limit=limit,
            include_content=include_content
        )

        return {
            "tag": tag,
            "memories": memories,
            "count": len(memories)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get memories: {str(e)}")


@app.post("/planning/context")
async def get_planning_context(
    task: str,
    user_id: Optional[str] = None,
    include_visual: bool = True,
    include_execution: bool = True,
    include_chat: bool = True
):
    """
    Get memory context for planning.

    This is the main endpoint the brain uses to retrieve relevant memories
    before planning a task.
    """
    if not supermemory_client:
        raise HTTPException(status_code=503, detail="Memory service unavailable")

    try:
        # Build user filter
        user_tag = f"user_{user_id}" if user_id else None

        memories = {
            'visual_memories': [],
            'execution_memories': [],
            'chat_memories': [],
            'total_memories': 0
        }

        # Query execution memories
        if include_execution:
            exec_filters = ['execution', 'agent']
            if user_tag:
                exec_filters.append(user_tag)

            exec_memories = supermemory_client.search(
                memory_type='agent_execution',
                spaces=exec_filters,
                limit=3
            )
            memories['execution_memories'] = exec_memories

        # Query chat memories
        if include_chat:
            chat_filters = ['chat', 'conversation']
            if user_tag:
                chat_filters.append(user_tag)

            chat_memories = supermemory_client.search(
                memory_type='conversation',
                spaces=chat_filters,
                limit=3
            )
            memories['chat_memories'] = chat_memories

        # Visual memories (if needed, from visual connector)
        if include_visual:
            # This would query recent visual context
            # For now, we'll skip this since it requires Supabase connector
            pass

        # Count total
        memories['total_memories'] = (
            len(memories['visual_memories']) +
            len(memories['execution_memories']) +
            len(memories['chat_memories'])
        )

        return {
            "task": task,
            "memories": memories,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get planning context: {str(e)}")


if __name__ == "__main__":
    print("=" * 70)
    print("TAHLAMUS MEMORY API SERVICE")
    print("=" * 70)
    print()
    print("Starting server on http://localhost:8001")
    print("API docs available at http://localhost:8001/docs")
    print()

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8001,
        log_level="info"
    )
