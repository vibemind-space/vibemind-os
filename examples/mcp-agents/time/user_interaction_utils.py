# -*- coding: utf-8 -*-
"""
User interaction utilities for Time MCP plugin.
Simplified version for time operations clarifications.
"""
import asyncio
import time
import uuid
from pathlib import Path
from typing import Any, List, Optional

from autogen_core.tools import FunctionTool
from pydantic import BaseModel


def create_ask_user_tool(
    event_server,
    correlation_id: Optional[str] = None
) -> FunctionTool:
    """Create the ask_user tool for time agent clarifications.

    Args:
        event_server: EventServer instance for broadcasting questions to GUI
        correlation_id: Optional correlation ID for tracking related questions

    Returns:
        FunctionTool instance configured for user interaction
    """

    class AskUserArgs(BaseModel):
        question: str
        suggested_answers: Optional[List[str]] = None

    async def ask_user_impl(question: str, suggested_answers: Optional[List[str]] = None) -> str:
        """Ask the user a clarification question via GUI.

        Args:
            question: The question to ask the user
            suggested_answers: Optional list of suggested answer options

        Returns:
            String containing the user's response or error message
        """
        # Generate unique question ID
        question_id = str(uuid.uuid4())

        # Broadcast question to GUI
        if event_server:
            try:
                event_server.broadcast("user.clarification.request", {
                    "question_id": question_id,
                    "question": question,
                    "suggested_answers": suggested_answers or [],
                    "correlation_id": correlation_id,
                    "ts": time.time()
                })
            except Exception as e:
                print(f"Error broadcasting question: {e}")

        # Print to console for visibility
        print(f"\n{'='*60}")
        print(f"❓ USER QUESTION (ID: {question_id}):")
        print(f"   {question}")
        if suggested_answers:
            print(f"   Suggestions: {suggested_answers}")
        print(f"{'='*60}\n")

        # Wait for user response by polling the response file
        try:
            # Determine response file path
            base_dir = Path(__file__).resolve().parents[4]  # Navigate up to project root
            tmp_dir = base_dir / "data" / "tmp"
            tmp_dir.mkdir(parents=True, exist_ok=True)

            # Use correlation_id for file name, fallback to question_id
            file_id = correlation_id if correlation_id else question_id
            response_file = tmp_dir / f"clarification_{file_id}.txt"

            # Poll for response file (timeout after 60 seconds)
            max_wait = 60
            poll_interval = 0.5
            elapsed = 0
            heartbeat_interval = 5
            last_heartbeat = 0

            print(f"⏳ Waiting for user response (polling {response_file})...")

            # Check for skip file (allows cancellation)
            skip_file = tmp_dir / f"skip_{file_id}.txt"

            while elapsed < max_wait:
                # Check for skip/cancel signal
                if skip_file.exists():
                    try:
                        skip_file.unlink()
                        print(f"⏭️ User skipped clarification")
                        if event_server:
                            event_server.broadcast("user.clarification.skipped", {
                                "correlation_id": correlation_id,
                                "timestamp": time.time()
                            })
                        return "User skipped this question"
                    except Exception:
                        pass

                if response_file.exists():
                    # Read and delete the response file
                    try:
                        answer = response_file.read_text(encoding='utf-8').strip()
                        response_file.unlink()

                        # Broadcast final response event to GUI
                        if event_server:
                            try:
                                event_server.broadcast("user.clarification.response", {
                                    "answer": answer,
                                    "correlation_id": correlation_id,
                                    "timestamp": time.time()
                                })
                            except Exception as e:
                                print(f"Error broadcasting response: {e}")

                        print(f"✅ User answered: {answer}")
                        return f"User provided: {answer}"
                    except Exception as e:
                        print(f"⚠️  Error reading response file: {e}")
                        return "Error: Could not read user response"

                # Send heartbeat status
                if elapsed - last_heartbeat >= heartbeat_interval:
                    if event_server:
                        try:
                            event_server.broadcast("user.clarification.waiting", {
                                "correlation_id": correlation_id,
                                "elapsed": elapsed,
                                "remaining": max_wait - elapsed,
                                "timestamp": time.time()
                            })
                        except Exception:
                            pass
                    last_heartbeat = elapsed

                # Wait before next poll
                await asyncio.sleep(poll_interval)
                elapsed += poll_interval

            # Timeout reached
            print(f"⏰ Timeout waiting for user response (60s)")
            if event_server:
                try:
                    event_server.broadcast("user.clarification.timeout", {
                        "correlation_id": correlation_id,
                        "timestamp": time.time()
                    })
                except Exception:
                    pass
            return "Timeout: User did not respond within 60 seconds. Proceeding without clarification."

        except Exception as e:
            print(f"❌ Error in polling mechanism: {e}")
            return f"Error: Polling failed - {e}"

    return FunctionTool(
        ask_user_impl,
        description="Ask the user a clarification question about time operations or timezone preferences"
    )
