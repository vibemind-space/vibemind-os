#!/usr/bin/env python3
"""
Qdrant MCP Agent - Vector database operations.

Provides:
- Semantic search across indexed files
- File indexing with embeddings
- Collection management
- Vector similarity queries

Follows Society of Mind pattern with EventServer broadcasting.
Uses custom tools with qdrant-client and sentence-transformers.
"""
import asyncio
import json
import os
import sys
import time
from dataclasses import field
from pathlib import Path
from typing import Optional, List, Dict, Any

# Force UTF-8 encoding for Windows console
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

# Load .env from project root
try:
    import dotenv
    # Path: mcp_plugins/servers/qdrant/agent.py -> go up 3 levels to project root
    env_path = os.path.join(os.path.dirname(__file__), '..', '..', '..', '.env')
    dotenv.load_dotenv(dotenv_path=env_path)
except Exception:
    pass

# Autogen imports
from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_agentchat.conditions import TextMentionTermination
from autogen_core.model_context import BufferedChatCompletionContext
from pydantic import BaseModel

# Import global LLM config
from src.llm_config import get_model

# Shared module imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'shared'))
from event_server import EventServer, start_ui_server
from constants import (
    MCP_EVENT_SESSION_ANNOUNCE,
    SESSION_STATE_RUNNING,
    SESSION_STATE_STOPPED,
    SESSION_STATE_ERROR,
)
from model_init import init_model_client as shared_init_model_client
from logging_utils import setup_logging
from conversation_logger import ConversationLogger, SenseCategory


class QdrantAgentConfig(BaseModel):
    """Configuration for Qdrant MCP Agent."""
    session_id: str
    task: str
    name: str = "qdrant-session"
    model: str = field(default_factory=lambda: get_model("mcp_agent"))
    working_dir: str = "."
    qdrant_url: str = "http://localhost:6333"
    collection: str = "code_index"


# System prompts
QDRANT_OPERATOR_PROMPT = """You are a vector database expert with deep knowledge of Qdrant and semantic search.

Your capabilities include:
- Searching for similar code/text (qdrant_search)
- Indexing files into collections (qdrant_index_file)
- Managing collections (qdrant_create_collection, qdrant_delete_collection)
- Getting collection statistics (qdrant_collection_info)
- Listing all collections (qdrant_list_collections)

Guidelines:
1. Always check if a collection exists before operations
2. Use descriptive queries for better search results
3. Explain what the search results mean
4. Handle connection errors gracefully
5. Suggest relevant files based on search results

When you have completed the task, say "TASK_COMPLETE".
"""

QA_VALIDATOR_PROMPT = """You are a QA Validator for Qdrant vector operations.

Your role:
1. Verify that search results are relevant
2. Check that indexing completed successfully
3. Ensure collections are properly configured
4. Validate that the task was completed correctly

When the task is fully validated, say "TASK_COMPLETE".
"""


class QdrantTools:
    """Custom Qdrant tool implementations."""

    def __init__(self, qdrant_url: str = "http://localhost:6333", collection: str = "code_index"):
        self.qdrant_url = qdrant_url
        self.default_collection = collection
        self._client = None
        self._embedder = None

    def _get_client(self):
        """Lazy-load Qdrant client."""
        if self._client is None:
            try:
                from qdrant_client import QdrantClient
                self._client = QdrantClient(url=self.qdrant_url)
            except ImportError:
                raise ImportError("qdrant-client not installed. Run: pip install qdrant-client")
        return self._client

    def _get_embedder(self):
        """Lazy-load sentence transformer embedder."""
        if self._embedder is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._embedder = SentenceTransformer("all-MiniLM-L6-v2")
            except ImportError:
                raise ImportError("sentence-transformers not installed. Run: pip install sentence-transformers")
        return self._embedder

    def _embed(self, text: str) -> List[float]:
        """Generate embedding for text."""
        embedder = self._get_embedder()
        return embedder.encode(text).tolist()

    async def qdrant_search(self, query: str, collection: str = None, top_k: int = 5) -> dict:
        """Search for similar content in Qdrant.

        Args:
            query: Search query text
            collection: Collection name (uses default if not specified)
            top_k: Number of results to return

        Returns:
            Dict with search results including file paths and scores
        """
        try:
            client = self._get_client()
            coll = collection or self.default_collection

            # Generate query embedding
            vector = self._embed(query)

            # Search
            results = client.search(
                collection_name=coll,
                query_vector=vector,
                limit=top_k
            )

            # Format results
            formatted = []
            for r in results:
                formatted.append({
                    "id": r.id,
                    "score": r.score,
                    "file_path": r.payload.get("file_path", "unknown"),
                    "content_preview": r.payload.get("content", "")[:200],
                    "metadata": {k: v for k, v in r.payload.items() if k not in ["content", "file_path"]}
                })

            return {
                "success": True,
                "query": query,
                "collection": coll,
                "results": formatted,
                "result_count": len(formatted)
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def qdrant_index_file(self, file_path: str, collection: str = None, metadata: dict = None) -> dict:
        """Index a file into Qdrant.

        Args:
            file_path: Path to the file to index
            collection: Collection name (uses default if not specified)
            metadata: Additional metadata to store

        Returns:
            Dict with indexing result
        """
        try:
            from qdrant_client.models import PointStruct

            client = self._get_client()
            coll = collection or self.default_collection
            path = Path(file_path)

            if not path.exists():
                return {"success": False, "error": f"File not found: {file_path}"}

            # Read file content
            content = path.read_text(encoding='utf-8', errors='replace')

            # Truncate for embedding (most models have token limits)
            content_for_embed = content[:5000]

            # Generate embedding
            vector = self._embed(content_for_embed)

            # Generate unique ID from file path
            point_id = abs(hash(str(path.resolve()))) % (10**9)

            # Create payload
            payload = {
                "file_path": str(path),
                "content": content[:2000],  # Store preview
                "file_name": path.name,
                "file_ext": path.suffix,
                "file_size": len(content),
                **(metadata or {})
            }

            # Upsert point
            client.upsert(
                collection_name=coll,
                points=[PointStruct(id=point_id, vector=vector, payload=payload)]
            )

            return {
                "success": True,
                "file_path": str(path),
                "point_id": point_id,
                "collection": coll,
                "content_length": len(content)
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def qdrant_create_collection(self, name: str, vector_size: int = 384) -> dict:
        """Create a new Qdrant collection.

        Args:
            name: Collection name
            vector_size: Dimension of vectors (384 for all-MiniLM-L6-v2)

        Returns:
            Dict with creation result
        """
        try:
            from qdrant_client.models import Distance, VectorParams

            client = self._get_client()

            # Check if collection exists
            collections = client.get_collections()
            if any(c.name == name for c in collections.collections):
                return {
                    "success": True,
                    "message": f"Collection '{name}' already exists",
                    "collection": name
                }

            # Create collection
            client.create_collection(
                collection_name=name,
                vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE)
            )

            return {
                "success": True,
                "message": f"Collection '{name}' created",
                "collection": name,
                "vector_size": vector_size
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def qdrant_delete_collection(self, name: str) -> dict:
        """Delete a Qdrant collection.

        Args:
            name: Collection name to delete

        Returns:
            Dict with deletion result
        """
        try:
            client = self._get_client()
            client.delete_collection(name)
            return {
                "success": True,
                "message": f"Collection '{name}' deleted"
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def qdrant_list_collections(self) -> dict:
        """List all Qdrant collections.

        Returns:
            Dict with list of collection names
        """
        try:
            client = self._get_client()
            collections = client.get_collections()
            names = [c.name for c in collections.collections]
            return {
                "success": True,
                "collections": names,
                "count": len(names)
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def qdrant_collection_info(self, name: str = None) -> dict:
        """Get information about a collection.

        Args:
            name: Collection name (uses default if not specified)

        Returns:
            Dict with collection statistics
        """
        try:
            client = self._get_client()
            coll = name or self.default_collection

            info = client.get_collection(coll)
            return {
                "success": True,
                "collection": coll,
                "points_count": info.points_count,
                "vectors_count": info.vectors_count,
                "status": info.status.name if info.status else "unknown",
                "optimizer_status": str(info.optimizer_status),
                "config": {
                    "vector_size": info.config.params.vectors.size if info.config else None,
                    "distance": info.config.params.vectors.distance.name if info.config else None,
                }
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def qdrant_index_directory(self, directory: str, extensions: List[str] = None, collection: str = None) -> dict:
        """Index all files in a directory.

        Args:
            directory: Directory path to index
            extensions: File extensions to include (e.g., [".ts", ".tsx", ".py"])
            collection: Collection name

        Returns:
            Dict with indexing summary
        """
        try:
            dir_path = Path(directory)
            if not dir_path.exists():
                return {"success": False, "error": f"Directory not found: {directory}"}

            exts = extensions or [".ts", ".tsx", ".js", ".jsx", ".py", ".md"]
            indexed = 0
            errors = []

            for ext in exts:
                for file_path in dir_path.rglob(f"*{ext}"):
                    # Skip node_modules, dist, etc.
                    if any(skip in str(file_path) for skip in ["node_modules", "dist", "build", ".git"]):
                        continue

                    result = await self.qdrant_index_file(str(file_path), collection)
                    if result.get("success"):
                        indexed += 1
                    else:
                        errors.append({"file": str(file_path), "error": result.get("error")})

            return {
                "success": True,
                "directory": str(dir_path),
                "indexed_count": indexed,
                "error_count": len(errors),
                "errors": errors[:5] if errors else []  # Limit error details
            }
        except Exception as e:
            return {"success": False, "error": str(e)}


async def run_qdrant_agent(config: QdrantAgentConfig):
    """Run the Qdrant MCP agent with the given configuration."""
    logger = setup_logging(f"qdrant_agent_{config.session_id}")
    event_server = EventServer(session_id=config.session_id, tool_name="qdrant")

    # Initialize ConversationLogger
    conv_logger = ConversationLogger(
        session_id=config.session_id,
        tool_name="qdrant",
        sense_category=SenseCategory.MEMORY
    )

    try:
        # Start the UI server
        httpd, thread, host, port = start_ui_server(
            event_server,
            host="127.0.0.1",
            port=0,
            tool_name="qdrant"
        )
        logger.info(f"UI server started on {host}:{port}")

        # Announce session
        announce_data = {
            "session_id": config.session_id,
            "host": host,
            "port": port,
            "ui_url": f"http://{host}:{port}/"
        }
        print(f"SESSION_ANNOUNCE {json.dumps(announce_data)}", flush=True)
        event_server.broadcast(MCP_EVENT_SESSION_ANNOUNCE, announce_data)

        # Log session start
        conv_logger.log_session_start(config.task, config.model)

        # Get model client
        model_client = shared_init_model_client("qdrant", config.task)
        logger.info(f"Model initialized: {config.model}")

        # Initialize Qdrant tools
        qdrant_tools = QdrantTools(
            qdrant_url=config.qdrant_url,
            collection=config.collection
        )

        # Create tool list
        tools = [
            qdrant_tools.qdrant_search,
            qdrant_tools.qdrant_index_file,
            qdrant_tools.qdrant_create_collection,
            qdrant_tools.qdrant_delete_collection,
            qdrant_tools.qdrant_list_collections,
            qdrant_tools.qdrant_collection_info,
            qdrant_tools.qdrant_index_directory,
        ]

        event_server.broadcast("log", f"Loaded {len(tools)} Qdrant tools")
        event_server.broadcast("log", f"Qdrant URL: {config.qdrant_url}")
        event_server.broadcast("log", f"Default collection: {config.collection}")

        # Create Operator agent
        operator = AssistantAgent(
            name="QdrantOperator",
            model_client=model_client,
            tools=tools,
            system_message=QDRANT_OPERATOR_PROMPT,
            model_context=BufferedChatCompletionContext(buffer_size=20),
        )

        # Create QA Validator agent
        qa_validator = AssistantAgent(
            name="QA_Validator",
            model_client=model_client,
            tools=[],
            system_message=QA_VALIDATOR_PROMPT,
            model_context=BufferedChatCompletionContext(buffer_size=10),
        )

        # Create team
        termination = TextMentionTermination("TASK_COMPLETE")
        team = RoundRobinGroupChat(
            participants=[operator, qa_validator],
            termination_condition=termination,
            max_turns=20,
        )

        # Send running status
        event_server.broadcast("log", f"Starting task: {config.task}")
        event_server.broadcast("status", SESSION_STATE_RUNNING)

        # Run the team
        result = await team.run(task=config.task)

        # Extract result
        result_text = ""
        if result.messages:
            result_text = str(result.messages[-1].content)
        else:
            result_text = "Task completed"

        # Log agent messages
        for msg in result.messages:
            agent_name = getattr(msg, 'source', 'Unknown')
            content = str(msg.content) if hasattr(msg, 'content') else str(msg)
            event_server.broadcast("agent.message", {
                "agent": agent_name,
                "content": content[:500],
                "timestamp": time.time()
            })

        # Send completion
        event_server.broadcast("log", f"Result: {result_text[:200]}...")
        event_server.broadcast("status", SESSION_STATE_STOPPED)

        # Log conversation
        conv_logger.log_conversation_turn(
            agent="QdrantOperator",
            agent_response=result_text,
            final_response=result_text
        )

        # Send final result
        event_server.broadcast("agent.completion", {
            "status": "success",
            "content": result_text,
            "tool": "qdrant",
            "timestamp": time.time()
        })

        logger.info("Task completed successfully")
        return {"success": True, "result": result_text}

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Error: {error_msg}", exc_info=True)
        event_server.broadcast("error", error_msg)
        event_server.broadcast("status", SESSION_STATE_ERROR)
        return {"success": False, "error": error_msg}

    finally:
        await asyncio.sleep(2)
        try:
            httpd.shutdown()
        except Exception:
            pass


async def main():
    """Main entry point with argument parsing."""
    import argparse
    parser = argparse.ArgumentParser(description="Qdrant MCP Agent")
    parser.add_argument('--session-id', required=False, help="Session identifier")
    parser.add_argument('--name', default='qdrant-session', help="Session name")
    parser.add_argument('--model', default=get_model("mcp_agent"), help="Model to use")
    parser.add_argument('--task', default='List all collections', help="Task to execute")
    parser.add_argument('--working-dir', dest='working_dir', default='.', help="Working directory")
    parser.add_argument('--qdrant-url', default='http://localhost:6333', help="Qdrant URL")
    parser.add_argument('--collection', default='code_index', help="Default collection")
    parser.add_argument('config_json', nargs='?', help="JSON config (alternative)")
    args = parser.parse_args()

    try:
        if args.config_json:
            config_dict = json.loads(args.config_json)
        elif args.session_id:
            config_dict = {
                'session_id': args.session_id,
                'name': args.name,
                'model': args.model,
                'task': args.task,
                'working_dir': args.working_dir,
                'qdrant_url': args.qdrant_url,
                'collection': args.collection,
            }
        else:
            import uuid
            config_dict = {
                'session_id': f"qdrant_{uuid.uuid4().hex[:8]}",
                'name': args.name,
                'model': args.model,
                'task': args.task,
                'working_dir': args.working_dir,
                'qdrant_url': args.qdrant_url,
                'collection': args.collection,
            }

        config = QdrantAgentConfig(**config_dict)
        result = await run_qdrant_agent(config)

        if not result.get("success"):
            sys.exit(1)

    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
