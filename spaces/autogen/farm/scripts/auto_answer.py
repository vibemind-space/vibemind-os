#!/usr/bin/env python3
"""Auto-answer pipeline modals + RegistryAgent mention handler.

Monitors /api/v1/questions/pending and answers them with intelligent defaults.
Also polls RegistryAgent notifications and replies to @mentions with registry data.
"""

import json
import time
import requests
import sys
from pathlib import Path

MINIBOOK_URL = "http://localhost:8899"
POLL_INTERVAL = 3  # seconds
CREDS_FILE = Path(__file__).parent / "minibook" / "swarm_agents.json"


def load_registry_agent_key() -> str | None:
    """Load RegistryAgent API key from swarm_agents.json."""
    try:
        creds = json.loads(CREDS_FILE.read_text())
        return creds.get("RegistryAgent", {}).get("api_key")
    except Exception:
        return None


def answer_question(q: dict) -> dict | None:
    """Determine the right answer for a question type."""
    qtype = q.get("type", "")
    qid = q["id"]
    metadata = q.get("metadata", {})

    if qtype == "mcp_selection":
        # Approve MCP server selection (filesystem, memory, fetch)
        selected = metadata.get("selected_servers", [])
        print(f"  -> Approving MCP selection: {selected}")
        return {"action": "approve", "answer": ""}

    elif qtype == "mcp_config":
        # Approve MCP config (filesystem paths, etc.)
        print(f"  -> Approving MCP config")
        return {"action": "approve", "answer": ""}

    elif qtype == "architecture_review":
        # Approve architecture
        print(f"  -> Approving architecture")
        return {"action": "approve", "answer": ""}

    elif qtype == "tool_approval":
        # Approve tool implementations
        print(f"  -> Approving tool implementation")
        return {"action": "approve", "answer": ""}

    elif qtype == "implementation_review":
        # Approve implementation
        print(f"  -> Approving implementation")
        return {"action": "approve", "answer": ""}

    elif qtype == "todo_implementation":
        # Auto-approve todo implementations
        tool_name = q.get("tool_name", "")
        print(f"  -> Approving todo implementation for {tool_name}")
        return {"action": "approve", "answer": ""}

    else:
        # Default: approve anything
        print(f"  -> Auto-approving unknown type '{qtype}'")
        return {"action": "approve", "answer": ""}


# --- RegistryAgent mention handler ---

def fetch_registry(api_key: str, status: str = None, team_key: str = None) -> list:
    """Fetch registry entries, optionally filtered."""
    params = {}
    if status:
        params["status"] = status
    if team_key:
        params["team_key"] = team_key
    try:
        resp = requests.get(
            f"{MINIBOOK_URL}/api/v1/registry",
            params=params, timeout=5,
        )
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return []


def build_registry_reply(mention_text: str) -> str:
    """Build a reply based on what was asked in the @RegistryAgent mention."""
    mention_lower = mention_text.lower()

    # Check for specific team query
    team_keywords = {
        "core": "core", "outreach": "outreach", "bdr": "bdr",
        "intel": "intel", "research": "research", "qualification": "qualification",
        "revops": "revops", "callintel": "callintel", "workspace": "workspace",
        "content": "content", "wiring": "wiring",
    }
    queried_team = None
    for keyword, team_key in team_keywords.items():
        if keyword in mention_lower:
            queried_team = team_key
            break

    # Check for capability query
    cap_keywords = [
        "sales", "outreach", "intelligence", "qualification",
        "operations", "content", "enrichment", "crm", "call",
    ]
    queried_cap = None
    for cap in cap_keywords:
        if cap in mention_lower:
            queried_cap = cap
            break

    # Fetch registry
    if queried_team:
        entries = fetch_registry(None, team_key=queried_team)
    else:
        entries = fetch_registry(None)

    if not entries:
        return "## Registry Status\n\nNo agents registered yet."

    # Filter by capability if requested
    if queried_cap and not queried_team:
        entries = [e for e in entries if any(queried_cap in c for c in e.get("capabilities", []))]
        if not entries:
            return f"## Registry Status\n\nNo agents found with capability matching '{queried_cap}'."

    # Build response
    validated = [e for e in entries if e["status"] == "validated"]
    candidates = [e for e in entries if e["status"] == "candidate"]

    lines = ["## Registry Status\n"]
    if validated:
        lines.append(f"### Validated Teams ({len(validated)})\n")
        for e in validated:
            caps = ", ".join(e.get("capabilities", []))
            servers = ", ".join(e.get("mcp_servers", []))
            lines.append(
                f"- **{e['team_key']}** (score: {e['eval_score']}/10) "
                f"| Capabilities: {caps} | MCP: {servers}"
            )
        lines.append("")

    if candidates:
        lines.append(f"### Candidate Teams ({len(candidates)})\n")
        for e in candidates:
            lines.append(
                f"- **{e['team_key']}** (score: {e['eval_score']}/10) "
                f"| Status: {e['todo_status']}"
            )
        lines.append("")

    return "\n".join(lines)


def handle_registry_mentions(api_key: str):
    """Poll RegistryAgent notifications and reply to @mentions."""
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        resp = requests.get(
            f"{MINIBOOK_URL}/api/v1/notifications",
            params={"unread_only": "true"},
            headers=headers, timeout=5,
        )
        if resp.status_code != 200:
            return

        notifications = resp.json()
        for notif in notifications:
            if notif.get("type") != "mention":
                # Mark non-mention notifications as read
                requests.post(
                    f"{MINIBOOK_URL}/api/v1/notifications/{notif['id']}/read",
                    headers=headers, timeout=5,
                )
                continue

            payload = notif.get("payload", {})
            post_id = payload.get("post_id")
            mentioned_by = payload.get("by", "unknown")

            if not post_id:
                requests.post(
                    f"{MINIBOOK_URL}/api/v1/notifications/{notif['id']}/read",
                    headers=headers, timeout=5,
                )
                continue

            # Fetch the post to get the mention context
            try:
                post_resp = requests.get(
                    f"{MINIBOOK_URL}/api/v1/posts/{post_id}",
                    headers=headers, timeout=5,
                )
                if post_resp.status_code == 200:
                    post_data = post_resp.json()
                    mention_text = post_data.get("content", "")
                else:
                    mention_text = ""
            except Exception:
                mention_text = ""

            # Build and post reply
            reply = build_registry_reply(mention_text)
            print(f"[RegistryAgent] Replying to @mention by {mentioned_by} on post {post_id[:8]}...")

            try:
                requests.post(
                    f"{MINIBOOK_URL}/api/v1/posts/{post_id}/comments",
                    json={"content": reply},
                    headers=headers, timeout=5,
                )
                print(f"[RegistryAgent] Reply posted")
            except Exception as e:
                print(f"[RegistryAgent] Reply failed: {e}")

            # Mark notification as read
            requests.post(
                f"{MINIBOOK_URL}/api/v1/notifications/{notif['id']}/read",
                headers=headers, timeout=5,
            )

    except requests.exceptions.ConnectionError:
        pass
    except Exception as e:
        print(f"[RegistryAgent] Error: {e}")


def main():
    registry_key = load_registry_agent_key()
    if registry_key:
        print(f"RegistryAgent: active (mention handler enabled)")
    else:
        print(f"RegistryAgent: no API key found (mention handler disabled)")

    print(f"Auto-answerer started. Polling {MINIBOOK_URL} every {POLL_INTERVAL}s...")
    print(f"Press Ctrl+C to stop.\n")

    answered_count = 0
    registry_poll_counter = 0
    while True:
        try:
            # --- Question answering ---
            resp = requests.get(f"{MINIBOOK_URL}/api/v1/questions/pending", timeout=5)
            if resp.status_code == 200:
                questions = resp.json()
                for q in questions:
                    qid = q["id"]
                    qtype = q.get("type", "?")
                    msg = q.get("message", "")[:80]
                    print(f"[{time.strftime('%H:%M:%S')}] Question: {qid[:8]}... type={qtype}")
                    print(f"  Message: {msg}")

                    answer = answer_question(q)
                    if answer:
                        r = requests.post(
                            f"{MINIBOOK_URL}/api/v1/questions/{qid}/answer",
                            json={"action": answer["action"], "text": answer.get("answer", "")},
                            timeout=5,
                        )
                        if r.status_code < 400:
                            answered_count += 1
                            print(f"  -> Answered! (total: {answered_count})")
                        else:
                            print(f"  -> FAILED to answer: {r.status_code} {r.text[:100]}")

            # --- RegistryAgent mention handler (every 5th poll = ~15s) ---
            registry_poll_counter += 1
            if registry_key and registry_poll_counter >= 5:
                registry_poll_counter = 0
                handle_registry_mentions(registry_key)

        except requests.exceptions.ConnectionError:
            print("  Backend unreachable, retrying...")
        except KeyboardInterrupt:
            print(f"\nStopped. Answered {answered_count} questions total.")
            sys.exit(0)
        except Exception as e:
            print(f"  Error: {e}")

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
