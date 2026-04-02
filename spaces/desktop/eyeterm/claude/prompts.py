"""Prompt templates for Claude Code interactions within eyeTerm."""

import logging

logger = logging.getLogger(__name__)


PATCH_PROMPT = """Edit the file {file_path} at lines {start}-{end}.
Instruction: {instruction}
Output ONLY a unified diff (git style, with --- a/ and +++ b/ headers). No explanation."""

EXPLAIN_PROMPT = """I'm looking at this UI element:
{element_context}

{user_request}"""

READ_PROMPT = """Read and summarize the content of this UI element:
{element_context}"""


def build_patch_prompt(
    file_path: str, start: int, end: int, instruction: str
) -> str:
    """Build a prompt asking Claude to produce a unified diff for a file edit."""
    return PATCH_PROMPT.format(
        file_path=file_path,
        start=start,
        end=end,
        instruction=instruction,
    )


def build_ask_prompt(user_text: str, element_context: str = "") -> str:
    """Build a general question prompt, optionally enriched with element context."""
    if element_context:
        return EXPLAIN_PROMPT.format(
            element_context=element_context,
            user_request=user_text,
        )
    return user_text


def build_explain_prompt(element_context: str, user_request: str) -> str:
    """Build a prompt for explaining a UI element."""
    return EXPLAIN_PROMPT.format(
        element_context=element_context,
        user_request=user_request,
    )
