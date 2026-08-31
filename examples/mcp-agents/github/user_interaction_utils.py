# -*- coding: utf-8 -*-
"""
User interaction utilities for GitHub MCP plugin.
Extracted from agent.py for modularity and testability.
"""
import asyncio
import time
import uuid
from pathlib import Path
from typing import Any, List, Optional

from autogen_core.tools import FunctionTool
from pydantic import BaseModel


async def validate_repo_name_with_llm(user_answer: str, llm_client: Any) -> str:
    """Use LLM to validate and format repository name to owner/repo format.

    Args:
        user_answer: Raw user input (e.g., "tensorflow", "microsoft/vscode")
        llm_client: OpenAIChatCompletionClient for LLM validation

    Returns:
        Validated repository name in owner/repo format

    Examples:
        >>> validate_repo_name_with_llm("tensorflow", client)
        "tensorflow/tensorflow"

        >>> validate_repo_name_with_llm("microsoft/vscode", client)
        "microsoft/vscode"
    """
    validation_prompt = f"""You are a GitHub repository name validator.

Task: Parse the user's input and convert it to the standard GitHub format: owner/repo

User input: "{user_answer}"

Rules:
1. If already in owner/repo format (e.g., "microsoft/vscode") → return as-is
2. If only repo name given (e.g., "tensorflow") → suggest popular owner (e.g., "tensorflow/tensorflow")
3. If partial/unclear → suggest most likely full name based on context
4. Return ONLY the owner/repo string, nothing else

Examples:
- Input: "vscode" → Output: "microsoft/vscode"
- Input: "tensorflow" → Output: "tensorflow/tensorflow"
- Input: "react" → Output: "facebook/react"
- Input: "torvalds/linux" → Output: "torvalds/linux" (already correct)

Output:"""

    try:
        # Call LLM to validate (using create method with messages)
        from autogen_core.models import UserMessage

        response = await llm_client.create(
            messages=[UserMessage(content=validation_prompt, source="user")],
            extra_create_args={"temperature": 0.3}  # Low temp for consistent formatting
        )

        # Extract validated name from response
        validated_name = response.content.strip()

        # Safety check: ensure result contains a slash
        if "/" not in validated_name:
            print(f"⚠️  LLM validation failed to add owner, using original: {user_answer}")
            return user_answer

        return validated_name

    except Exception as e:
        print(f"⚠️  LLM validation error: {e}, using original answer")
        return user_answer


def create_ask_user_tool(
    event_server,
    correlation_id: Optional[str] = None,
    llm_client: Optional[Any] = None
) -> FunctionTool:
    """Create the ask_user tool for UserClarificationAgent.

    This tool allows the agent to ask clarification questions to the user via GUI.
    The user's response is polled from a file in the data/tmp directory.

    If llm_client is provided, repository names will be automatically validated
    and formatted to owner/repo format (e.g., "tensorflow" → "tensorflow/tensorflow").

    Args:
        event_server: EventServer instance for broadcasting questions to GUI
        correlation_id: Optional correlation ID for tracking related questions
        llm_client: Optional LLM client for repository name validation

    Returns:
        FunctionTool instance configured for user interaction

    Example:
        >>> from github.user_interaction_utils import create_ask_user_tool
        >>> from github.event_task import EventServer
        >>> event_server = EventServer()
        >>> tool = create_ask_user_tool(event_server, "session-123", llm_client=client)
        >>> # Agent can now call: ask_user(question="...", suggested_answers=[...])
        >>> # Answers will be validated by LLM before returning
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
        
        # Broadcast question to GUI with correct event name
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
            
            # Poll for response file (timeout after 60 seconds to prevent hanging)
            max_wait = 60  # 1 minute (reduced from 5 to prevent app hang)
            poll_interval = 0.5  # 500ms for faster response
            elapsed = 0
            heartbeat_interval = 5  # Broadcast status every 5 seconds
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
                        response_file.unlink()  # Delete file after reading

                        # Validate answer with LLM if client provided (for repo names)
                        if llm_client and answer:
                            print(f"🤖 Validating repository format with LLM...")
                            try:
                                validated_answer = await validate_repo_name_with_llm(answer, llm_client)

                                # If LLM changed the format, show suggestion
                                if validated_answer != answer:
                                    print(f"📝 LLM suggested: {answer} → {validated_answer}")

                                    # Broadcast LLM validation event to GUI
                                    if event_server:
                                        try:
                                            event_server.broadcast("user.clarification.llm_validation", {
                                                "original": answer,
                                                "validated": validated_answer,
                                                "correlation_id": correlation_id,
                                                "timestamp": time.time()
                                            })
                                        except Exception as e:
                                            print(f"Error broadcasting LLM validation: {e}")

                                    # Use validated answer
                                    answer = validated_answer
                                else:
                                    print(f"✓ LLM confirmed format: {answer}")

                            except Exception as e:
                                print(f"⚠️  LLM validation failed: {e}, using original answer")

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

                # Send heartbeat status to prevent timeout appearance
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

            # Timeout reached - broadcast timeout event
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
        description="Ask the user a clarification question when critical information is missing"
    )