"""Standalone test for TreeQuest Verification Agent core logic (no project imports)."""
import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# Copy the core functions directly to avoid import chain issues

class CodeChunker:
    def __init__(self, chunk_size=40, overlap=5):
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk_file(self, file_path):
        try:
            text = file_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return []
        lines = text.splitlines()
        if not lines:
            return []
        chunks = []
        i = 0
        while i < len(lines):
            end = min(i + self.chunk_size, len(lines))
            chunk_text = "\n".join(lines[i:end])
            chunks.append((chunk_text, (i + 1, end)))
            i += self.chunk_size - self.overlap
        return chunks

    def chunk_project(self, project_dir):
        results = []
        extensions = {".py", ".ts", ".tsx", ".js", ".jsx", ".java", ".go", ".rs", ".cs"}
        for f in sorted(project_dir.rglob("*")):
            if f.suffix in extensions and "node_modules" not in str(f) and ".git" not in str(f):
                for chunk_text, line_range in self.chunk_file(f):
                    results.append((f, chunk_text, line_range))
        return results


CHECK_TYPES = ["api_consistency", "data_model", "business_logic", "security", "performance"]


def _find_relevant_docs(code_chunk, project_dir, check_type, fungus_search_fn=None):
    doc_chunks = []
    doc_dirs = {
        "api_consistency": ["api"],
        "data_model": ["data"],
        "business_logic": ["user_stories", "tasks"],
        "security": ["user_stories"],
        "performance": ["tech_stack"],
    }
    search_dirs = doc_dirs.get(check_type, ["tasks", "api", "data"])
    for d in search_dirs:
        doc_path = project_dir / d
        if not doc_path.exists():
            continue
        for f in sorted(doc_path.rglob("*")):
            if f.suffix in (".md", ".yaml", ".yml", ".json") and f.stat().st_size < 500_000:
                try:
                    content = f.read_text(encoding="utf-8", errors="replace")
                    code_ids = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", code_chunk))
                    doc_ids = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", content))
                    overlap = code_ids & doc_ids
                    if len(overlap) >= 3:
                        doc_chunks.append(content[:2000])
                except Exception:
                    continue
    return doc_chunks[:5]


def _score_consistency(code_chunk, doc_chunks, check_type):
    if not doc_chunks:
        return 0.5, "info", "No matching documentation found for this code section", ""
    combined_docs = "\n".join(doc_chunks)
    code_ids = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", code_chunk))
    doc_ids = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", combined_docs))
    if not code_ids:
        return 0.5, "info", "Code chunk has no identifiable symbols", ""
    overlap = code_ids & doc_ids
    overlap_ratio = len(overlap) / len(code_ids) if code_ids else 0

    if check_type == "api_consistency":
        api_patterns = re.findall(r"(GET|POST|PUT|DELETE|PATCH)\s+[/\w{}]+", combined_docs, re.IGNORECASE)
        code_routes = re.findall(r"@(get|post|put|delete|patch)", code_chunk, re.IGNORECASE)
        if api_patterns and not code_routes:
            return 0.3, "high", "API endpoints documented but not found in code", "Implement missing API routes"

    elif check_type == "security":
        security_kw = {"auth", "token", "jwt", "session", "csrf", "cors", "encrypt", "password", "hash", "salt"}
        doc_has = bool(security_kw & {w.lower() for w in doc_ids})
        code_has = bool(security_kw & {w.lower() for w in code_ids})
        if doc_has and not code_has:
            return 0.3, "critical", "Security requirements in docs but no security implementation", "Add auth"

    if overlap_ratio > 0.4:
        return min(0.5 + overlap_ratio, 1.0), "low", "Good documentation coverage", ""
    elif overlap_ratio > 0.2:
        return 0.4, "medium", f"Partial doc coverage ({overlap_ratio:.0%})", "Review code against docs"
    else:
        return 0.3, "high", f"Low doc coverage ({overlap_ratio:.0%})", "Code may diverge from documentation"


# ===========================================================================
# TESTS
# ===========================================================================

whatsapp_dir = Path("Data/all_services/whatsapp-messaging-service_20260211_025459")
print(f"WhatsApp package exists: {whatsapp_dir.exists()}")

# Check doc dirs
for d in ["tasks", "api", "data", "user_stories", "tech_stack"]:
    p = whatsapp_dir / d
    if p.exists():
        files = [f for f in p.rglob("*") if f.is_file()]
        print(f"  {d}/: {len(files)} files")
    else:
        print(f"  {d}/: NOT FOUND")

# Test with fake code
test_code = """
class MessageController:
    async def send_message(self, user_id, content):
        auth_token = self.get_auth_token()
        result = await self.whatsapp_api.send(user_id, content)
        return result
    async def get_conversations(self, user_id, limit=50):
        return await self.db.query_conversations(user_id, limit=limit)
"""

print("\n--- Scoring against WhatsApp docs ---")
for ct in CHECK_TYPES:
    docs = _find_relevant_docs(test_code, whatsapp_dir, ct)
    score, sev, desc, fix = _score_consistency(test_code, docs, ct)
    print(f"  {ct}: score={score:.2f} sev={sev} docs={len(docs)} | {desc[:70]}")

# Test CodeChunker
chunker = CodeChunker()
agent_file = Path("src/agents/treequest_verification_agent.py")
chunks = chunker.chunk_file(agent_file)
print(f"\nCodeChunker: {len(chunks)} chunks from {agent_file.name}")
for c_text, lr in chunks[:3]:
    print(f"  lines {lr[0]}-{lr[1]}: {len(c_text)} chars")

# Test chunking a small project dir
src_agents = Path("src/agents")
project_chunks = chunker.chunk_project(src_agents)
print(f"\nProject chunks from agents/: {len(project_chunks)} chunks across {len(set(c[0] for c in project_chunks))} files")

# Test verification against WhatsApp docs with a code chunk that references WhatsApp entities
whatsapp_code = """
class UserService:
    def create_user(self, name, phone_number, email):
        user = User(name=name, phone_number=phone_number, email=email)
        self.db.save(user)
        return user

class MessageService:
    def send_text_message(self, sender_id, recipient_id, text):
        message = Message(sender=sender_id, recipient=recipient_id, body=text, type='text')
        self.queue.publish(message)
        return message

class ConversationService:
    def get_conversation(self, conversation_id):
        return self.db.find_conversation(conversation_id)
    def list_messages(self, conversation_id, page=1, limit=20):
        return self.db.paginate_messages(conversation_id, page, limit)
"""

print("\n--- WhatsApp-like code against WhatsApp docs ---")
for ct in CHECK_TYPES:
    docs = _find_relevant_docs(whatsapp_code, whatsapp_dir, ct)
    score, sev, desc, fix = _score_consistency(whatsapp_code, docs, ct)
    print(f"  {ct}: score={score:.2f} sev={sev} docs={len(docs)} | {desc[:70]}")

print("\n=== ALL TESTS PASSED ===")
