"""TODO Tool Implementer — scans tools.py for # TODO markers and generates real implementations.

After OutputEval PASS, this module scans the generated tools.py for mock functions
with # TODO markers and replaces them with real implementations generated via Claude Code.
"""

import re
import json
import asyncio
import aiohttp
import os
import time
import webbrowser
from pathlib import Path


async def scan_todo_tools(tools_py: str) -> list[dict]:
    """Extract all TODO-marked functions from tools.py.

    Returns list of dicts with keys:
        name: function name
        todo: the TODO hint text
        signature: full 'async def ...' line
        full_code: complete function including body
        start_line: line number where function starts
    """
    results = []
    lines = tools_py.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        # Match async function definition
        m = re.match(r'^(async\s+def\s+(\w+)\s*\(.*?\)\s*->\s*str\s*:)', line)
        if m:
            sig = m.group(1)
            func_name = m.group(2)
            start = i
            # Collect the entire function body
            body_lines = [line]
            i += 1
            while i < len(lines):
                # Next function or top-level non-blank non-comment line = end of function
                if i < len(lines) and re.match(r'^(async\s+def|def|class|# ===|# ---)', lines[i]):
                    break
                body_lines.append(lines[i])
                i += 1
            full_code = "\n".join(body_lines).rstrip()

            # Check for TODO marker in docstring or comments
            todo_match = re.search(r'#\s*TODO:\s*(.+)', full_code)
            if todo_match:
                results.append({
                    "name": func_name,
                    "todo": todo_match.group(1).strip(),
                    "signature": sig,
                    "full_code": full_code,
                    "start_line": start,
                })
        else:
            i += 1
    return results


async def generate_real_implementation(tool_info: dict, claude_code_fn, gpt4o_fn=None, user_context: str = "") -> str:
    """Use Claude Code (with GPT-4o fallback) to generate a real implementation for one TODO tool.

    Preserves the exact function signature. Uses httpx for HTTP calls,
    os.environ for API keys.

    Args:
        tool_info: dict from scan_todo_tools
        claude_code_fn: async callable(prompt) -> str (e.g. pipeline._call_claude_code)
        gpt4o_fn: optional async callable(system, user, max_tokens) for fallback

    Returns:
        Complete function code as string, or empty string on failure.
    """
    prompt = (
        f"You are implementing a real async Python tool function to replace a mock.\n\n"
        f"ORIGINAL MOCK:\n```python\n{tool_info['full_code']}\n```\n\n"
        f"TODO HINT: {tool_info['todo']}\n\n"
        f"REQUIREMENTS:\n"
        f"- Keep the EXACT same function signature: {tool_info['signature']}\n"
        f"- Use httpx (async) for HTTP calls\n"
        f"- Read API keys from os.environ.get(\"ENV_VAR_NAME\") with sensible defaults\n"
        f"- Return JSON string (str type)\n"
        f"- Handle errors gracefully (return JSON with \"error\" key and \"mock\": true)\n"
        f"- On SUCCESS, include \"mock\": false in the returned JSON\n"
        f"- Include timeout handling (30s max)\n"
        f"- NO hardcoded API keys or secrets\n"
        f"- Keep the docstring but remove the # TODO line\n"
        f"- If the API endpoint is unknown, use a reasonable placeholder URL "
        f"from os.environ (e.g. os.environ.get('CRM_API_URL', 'https://api.example.com'))\n"
        f"- If the env var is missing, return mock data with \"mock\": true\n\n"
        f"Generate ONLY the complete function code (starting with 'async def'), nothing else. "
        f"No markdown fences, no explanation."
    )

    if user_context:
        prompt += (
            f"\n\nADDITIONAL CONTEXT FROM USER:\n{user_context}\n\n"
        )

    # Try Claude Code first
    result = await claude_code_fn(prompt)
    if result and not result.lower().startswith("error"):
        code = _clean_code_fences(result)
        if code and code.strip().startswith("async def"):
            return code

    # Fallback to GPT-4o
    if gpt4o_fn:
        print(f"[TodoImplementer] Claude Code failed for {tool_info['name']}, trying GPT-4o...")
        try:
            result = await gpt4o_fn(
                "You are an expert Python developer. Generate ONLY the function code, no explanation.",
                prompt, max_tokens=2000)
            if result:
                code = _clean_code_fences(result)
                if code and code.strip().startswith("async def"):
                    return code
        except Exception as e:
            print(f"[TodoImplementer] GPT-4o fallback also failed: {e}")

    return ""


def _clean_code_fences(text: str) -> str:
    """Strip markdown code fences from LLM output."""
    code = text.strip()
    if code.startswith("```python"):
        code = code[len("```python"):].strip()
    if code.startswith("```"):
        code = code[3:].strip()
    if code.endswith("```"):
        code = code[:-3].strip()
    return code


MINIBOOK_URL = os.environ.get("MINIBOOK_URL", "http://localhost:8899")
MINIBOOK_FRONTEND_URL = os.environ.get("MINIBOOK_FRONTEND_URL", "http://localhost:3457")
QUESTION_TIMEOUT = int(os.environ.get("QUESTION_TIMEOUT", "120"))
_BROWSER_OPENED = False  # Track if we've already opened the browser this session


async def ask_user(
    question_type: str,
    tool_name: str,
    todo_hint: str = "",
    mock_code: str = "",
    generated_code: str = None,
    options: list = None,
    message: str = None,
    metadata: dict = None,
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
        "metadata": metadata or {},
    }

    try:
        async with aiohttp.ClientSession() as session:
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

            # Auto-open browser so user sees the question modal
            global _BROWSER_OPENED
            if not _BROWSER_OPENED or question_type in ("mcp_config", "mcp_selection"):
                frontend_url = f"{MINIBOOK_FRONTEND_URL}/dashboard?question={question_id}"
                try:
                    webbrowser.open(frontend_url)
                    _BROWSER_OPENED = True
                    print(f"[TodoImplementer] Browser opened: {frontend_url}")
                except Exception:
                    print(f"[TodoImplementer] Open in browser: {frontend_url}")

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


def validate_implementation(tool_info: dict, new_code: str) -> list[str]:
    """Validate new implementation matches original signature.

    Checks: async def, same name, -> str return, no hardcoded secrets, has docstring.
    Returns list of errors (empty = valid).
    """
    errors = []
    name = tool_info["name"]

    if not new_code.strip():
        errors.append("Empty implementation")
        return errors

    if not new_code.strip().startswith("async def"):
        errors.append("Missing 'async def' — must be async function")

    # Check function name matches
    name_match = re.search(r'async\s+def\s+(\w+)', new_code)
    if name_match and name_match.group(1) != name:
        errors.append(f"Function name mismatch: expected '{name}', got '{name_match.group(1)}'")

    if "-> str" not in new_code.split("\n")[0]:
        errors.append("Missing '-> str' return type")

    # Check for hardcoded secrets (API keys that look like real ones)
    if re.search(r'["\'][A-Za-z0-9]{32,}["\']', new_code):
        errors.append("Possible hardcoded API key/secret detected")

    if '"""' not in new_code and "'''" not in new_code:
        errors.append("Missing docstring")

    # Check it still returns a string (has return statement)
    if "return " not in new_code:
        errors.append("No return statement found")

    return errors


def replace_tool_in_code(tools_py: str, tool_name: str, old_code: str, new_impl: str) -> str:
    """Replace a single mock tool function with its real implementation.

    Preserves everything else in tools.py unchanged.
    """
    if old_code not in tools_py:
        return tools_py
    return tools_py.replace(old_code, new_impl)


async def implement_todos(tools_py_path: Path, claude_code_fn, gpt4o_fn=None, max_tools: int = 10) -> dict:
    """Main entry: scan, implement, validate, replace TODO tools.

    Args:
        tools_py_path: Path to tools.py file
        claude_code_fn: async callable(prompt) -> str
        gpt4o_fn: optional async callable(system, user, max_tokens) for fallback
        max_tools: max number of TODOs to implement per run

    Returns: {"implemented": [...], "failed": [...], "skipped": [...], "tools_py_updated": bool}
    """
    result = {"implemented": [], "failed": [], "skipped": [], "tools_py_updated": False}

    if not tools_py_path.exists():
        result["failed"].append({"name": "N/A", "error": f"tools.py not found: {tools_py_path}"})
        return result

    tools_py = tools_py_path.read_text(encoding="utf-8")
    todos = await scan_todo_tools(tools_py)

    if not todos:
        print("[TodoImplementer] No TODO-marked tools found")
        return result

    print(f"[TodoImplementer] Found {len(todos)} TODO tools: {[t['name'] for t in todos]}")

    # Limit to max_tools per run
    if len(todos) > max_tools:
        result["skipped"] = [t["name"] for t in todos[max_tools:]]
        todos = todos[:max_tools]

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
        new_code = await generate_real_implementation(tool_info, claude_code_fn, gpt4o_fn, user_context)
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

            if answer["action"] in ("approve", "timeout"):
                if answer["action"] == "timeout":
                    print(f"[TodoImplementer] [AUTO-APPROVED] {name} (timeout)")
                approved = True
                break
            elif answer["action"] == "reject":
                print(f"[TodoImplementer] User rejected {name}")
                break
            elif answer["action"] == "reply" and answer["text"]:
                print(f"[TodoImplementer] Regenerating {name} with user feedback...")
                user_context = answer["text"]
                new_code = await generate_real_implementation(tool_info, claude_code_fn, gpt4o_fn, user_context)
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
            if name not in [s for s in result["skipped"]] and name not in [f["name"] for f in result["failed"]]:
                result["skipped"].append(name)
            print(f"[TodoImplementer] SKIPPED {name}")

    # Write back if any changes
    if result["implemented"]:
        tools_py_path.write_text(updated_code, encoding="utf-8")
        result["tools_py_updated"] = True
        print(f"[TodoImplementer] Updated tools.py with {len(result['implemented'])} implementations")

    return result
