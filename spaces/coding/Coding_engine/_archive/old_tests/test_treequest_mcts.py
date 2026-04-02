"""Test TreeQuest AB-MCTS verification with actual library."""
import logging as _logging  # Force stdlib logging first
import sys
sys.path.insert(0, "src")
import re
from pathlib import Path
from typing import Optional, Tuple, List
from dataclasses import dataclass

from treequest import ABMCTSA
print("TreeQuest ABMCTSA imported successfully")

# Minimal VerificationState for testing
@dataclass
class VerState:
    code_file: str
    check_type: str
    severity: str
    description: str
    score: float

# Prepare code chunks from real code
whatsapp = Path("Data/all_services/whatsapp-messaging-service_20260211_025459")
CHECK_TYPES = ["api_consistency", "data_model", "business_logic", "security", "performance"]

# Simple code chunks to test
code_chunks = [
    ("src/routes/auth.ts", "class AuthController { login(email, password) { return jwt.sign() } }"),
    ("src/models/User.ts", "class User { id: string; name: string; email: string; phone_number: string; }"),
    ("src/services/message.ts", "class MessageService { async send(to, body) { await whatsapp.send(to, body) } }"),
    ("src/middleware/cors.ts", "app.use(cors({ origin: '*' }))"),
    ("src/config/redis.ts", "const redis = new Redis({ host: 'localhost', port: 6379 })"),
]

# Find docs helper
def find_docs(code_chunk, check_type):
    doc_dirs = {"api_consistency": ["api"], "data_model": ["data"], "business_logic": ["tasks"], "security": ["user_stories"], "performance": ["tech_stack"]}
    docs = []
    for d in doc_dirs.get(check_type, ["tasks"]):
        dp = whatsapp / d
        if not dp.exists(): continue
        for f in sorted(dp.rglob("*")):
            if f.suffix in (".md", ".yaml", ".yml", ".json") and f.stat().st_size < 500000:
                try:
                    content = f.read_text(encoding="utf-8", errors="replace")
                    code_ids = set(re.findall(r"[A-Za-z_]\w{2,}", code_chunk))
                    doc_ids = set(re.findall(r"[A-Za-z_]\w{2,}", content))
                    if len(code_ids & doc_ids) >= 2:
                        docs.append(content[:1000])
                except: continue
    return docs[:3]

# Score function
def score_check(code, docs, check_type):
    if not docs:
        return 0.5, "info", "No docs"
    combined = "\n".join(docs)
    code_ids = set(re.findall(r"[A-Za-z_]\w{2,}", code))
    doc_ids = set(re.findall(r"[A-Za-z_]\w{2,}", combined))
    overlap = len(code_ids & doc_ids) / max(len(code_ids), 1)
    if overlap > 0.4:
        return min(0.5 + overlap, 1.0), "low", "Good coverage"
    elif overlap > 0.2:
        return 0.4, "medium", "Partial coverage"
    else:
        return 0.3, "high", "Low coverage"

# Create generate function
chunk_i = [0]
check_i = [0]

def generate_fn(parent: Optional[VerState] = None) -> Tuple[VerState, float]:
    ci = chunk_i[0] % len(code_chunks)
    ti = check_i[0] % len(CHECK_TYPES)
    check_i[0] += 1
    if check_i[0] % len(CHECK_TYPES) == 0:
        chunk_i[0] += 1

    file_name, code = code_chunks[ci]
    check_type = CHECK_TYPES[ti]
    docs = find_docs(code, check_type)
    score, severity, desc = score_check(code, docs, check_type)

    state = VerState(
        code_file=file_name,
        check_type=check_type,
        severity=severity,
        description=desc,
        score=score,
    )
    # Invert: lower consistency = higher search interest
    return state, 1.0 - score

# Run AB-MCTS - generate_fn must be a dict of {action_name: callable}
generate_fns = {}
for ct in CHECK_TYPES:
    # Create a closure for each check type
    def make_fn(check_type):
        def fn(parent: Optional[VerState] = None) -> Tuple[VerState, float]:
            ci = chunk_i[0] % len(code_chunks)
            chunk_i[0] += 1
            file_name, code = code_chunks[ci]
            docs = find_docs(code, check_type)
            score, severity, desc = score_check(code, docs, check_type)
            state = VerState(code_file=file_name, check_type=check_type, severity=severity, description=desc, score=score)
            return state, 1.0 - score
        return fn
    generate_fns[ct] = make_fn(ct)

print(f"\nRunning AB-MCTS-A with 100 steps, {len(generate_fns)} actions...")
algo = ABMCTSA()
tree_state = algo.init_tree()

for i in range(100):
    tree_state = algo.step(tree_state, generate_fns, inplace=True)

# Get results
pairs = algo.get_state_score_pairs(tree_state)
pairs.sort(key=lambda x: x[1], reverse=True)

print(f"\nTotal nodes explored: {len(pairs)}")
print(f"\nTop 10 findings (highest inconsistency):")
for state, score in pairs[:10]:
    print(f"  [{state.severity:8s}] {state.check_type:20s} | {state.code_file:30s} | score={score:.3f} | {state.description}")

# Stats
severities = {}
for state, _ in pairs:
    severities[state.severity] = severities.get(state.severity, 0) + 1
print(f"\nSeverity distribution: {severities}")

print("\n=== TREEQUEST AB-MCTS TEST PASSED ===")
