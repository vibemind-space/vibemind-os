# Testing D·C·A·B with real data — Runbook

Tests the four bausteine (D Ground-Truth + Execution-Log + AutoGen-Fix, C Intent↔Profil↔Event,
A Sequence-Learner, B Contracts) against REAL data, in 3 stages from "no stack needed" to "full brain".

All commands run from `vibemind-os/brain/the_brain/`. Every baustein is flag-gated (default OFF);
these tests turn the relevant flags ON explicitly. Nothing is committed.

Real data found: `data/multihop_history.jsonl` has **508 real plans (454 ok / 54 failed)** — the
54 failures are genuine learning + MISMATCH examples.

---

## Stage 1 — Real data, NO stack required (run this first)

These need no running Brain/Qdrant — just real inputs already on disk / on your machine.

### 1a. Sequence-Learner (A) against your REAL plan history
Learns from all 508 real plans and shows what agent-sequences actually succeeded.

```bash
SEQUENCE_LEARNER_ENABLED=1 python -c "
import json
from core.sequence_learner import SequenceLearner
L = SequenceLearner(path='data/_seqtest.json')   # temp store, won't touch prod
n=0
for line in open('data/multihop_history.jsonl', encoding='utf-8'):
    try:
        L.observe(json.loads(line)); n+=1
    except Exception: pass
print(f'learned from {n} real plans')
print('state:', L.get_state())
# show a few learned buckets + their best sequence
import itertools
for bucket in itertools.islice(L._store.keys(), 5):
    s = L.suggest(task_type=bucket)
    print(f'  intent-bucket {bucket!r:40} -> {s[\"sequence\"] if s else \"(below support)\"}')
"
rm -f data/_seqtest.json
```
**Expect:** it learns real sequences; buckets with ≥2 successes get a suggested sequence.
**This proves A works on YOUR data, not a mock.**

### 1b. World-Observer (D.1) against REAL processes/ports on your PC
Port 5001 is currently open (ProductionPlanner) — a real VERIFIED. A random high port — real REFUTED.

```bash
GROUND_TRUTH_ENABLED=1 python -c "
from core.world_observer import observe
print('port 5001 (live)  :', observe({'check':'port_open','port':5001}).verdict)
print('port 59999 (dead) :', observe({'check':'port_open','port':59999}).verdict)
print('this file exists  :', observe({'check':'file_exists','path':'core/world_observer.py'}).verdict)
print('chrome running?   :', observe({'check':'process_running','name':'chrome'}).verdict)
"
```
**Expect:** VERIFIED for 5001, REFUTED for 59999 — real ground truth, no stack.

### 1c. AutoGen role-fix (D.3) against the REAL llm_config.yml
```bash
VIBEMIND_CONFIG_DIR="$(pwd)" python -c "
import sys; sys.path.insert(0,'../../shared/src')
from vibemind_shared.llm_client import _resolve_role
print('BROKEN brain_planning (prod):', _resolve_role('brain_planning','/x/production').get('model'))
print('FIXED  planning      (prod):', _resolve_role('planning','/x/production').get('model'))
"
```
**Expect:** broken→groq-llama, fixed→gpt-5-pro. Proves the fix matters in production.

### 1d. Contract-Gate (B) — pure logic, no stack
```bash
CONTRACT_ENFORCEMENT_ENABLED=1 python -c "
from core.contract_gate import check_start_when
class H:
    def __init__(s,sw): s.step_id='x'; s.start_when=sw; s.capability='c'; s.execution_target=None
ex={'s1':{'ok':True,'validator_verdict':{}}, 's2':{'ok':False,'validator_verdict':{}}}
print('s1.completed (ran ok)  :', check_start_when(H(['s1.completed']),ex).allowed, '(expect True)')
print('s2.completed (failed)  :', check_start_when(H(['s2.completed']),ex).allowed, '(expect False = blocked)')
print('s9.completed (never)   :', check_start_when(H(['s9.completed']),ex).allowed, '(expect False)')
"
```

---

## Stage 2 — With Qdrant (TriBE profiles C + Execution-Log D.2)

Needs Qdrant on :16333. Start it via the launcher (it brings up the swarm incl. Qdrant), or a
standalone container:
```bash
docker run -d -p 16333:6333 --name qdrant-test qdrant/qdrant   # standalone, if not using the stack
```

### 2a. TriBE intent-grounding (C) writing real profiles
With Qdrant up + the Brain running (Stage 3) OR a direct script that uses the real embedder.
Quick check that the profile differs with intent (uses TRIBE_DUMMY so no gated weights needed):
```bash
TRIBE_DUMMY=1 TRIBE_ENABLED=1 python -c "
from core.tribe_encoder import predict_text, TribeEncoder, describe_profile
enc=TribeEncoder.get()
print('content only  :', describe_profile(enc.bridge_levels(predict_text('rewrite the module'))))
print('intent-grounded:', describe_profile(enc.bridge_levels(predict_text('[intent: refactor_code] rewrite the module'))))
"
```
For REAL TriBE weights (not dummy): unset TRIBE_DUMMY and ensure `facebook/tribev2` is downloaded
(first call pulls ~GB). Then `GET /api/tribe/status` shows `loaded:true`.

### 2b. Execution-Log collection (D.2) — verify it's created
After the Brain runs with `EXECUTION_LOG_ENABLED=1` (Stage 3), check the collection exists:
```bash
curl -s http://127.0.0.1:16333/collections | python -m json.tool | grep -i execution
```

---

## Stage 3 — Full Brain, end-to-end (the real integration test)

Start the Brain with ALL flags on, run a real multihop plan, observe the whole chain.

### 3a. Start the Brain with all bausteine armed
```bash
GROUND_TRUTH_ENABLED=1 \
EXECUTION_LOG_ENABLED=1 \
TRIBE_PROFILE_ENABLED=1 \
TRIBE_INTENT_GROUNDING=1 \
SEQUENCE_LEARNER_ENABLED=1 \
CONTRACT_ENFORCEMENT_ENABLED=1 \
BRAIN_PORT=5003 \
python start_server.py
```
(Or use the launcher `Vibemind.debug.ps1` and set these in the swarm env — note from memory:
Swarm ignores `env_file:`, so put them as `${VAR}` in the stack file + shell-env at deploy.)

### 3b. Fire a real plan that has a verifiable side-effect
Pick an intent whose action you can ground-truth. Example — anything that opens a port / writes a file.
Then run a multihop and watch the chain:
```bash
curl -s -X POST http://127.0.0.1:5003/api/multihop_execute \
  -H 'content-type: application/json' \
  -d '{"intent":"<your intent with a checkable side-effect>"}'
```

### 3c. Observe the four bausteine in action
```bash
# D.2 — the execution-log diff (claimed vs verified). Look for MISMATCH = lying/broken tools:
curl -s "http://127.0.0.1:5003/api/execution-log/search?diff=MISMATCH" | python -m json.tool
curl -s "http://127.0.0.1:5003/api/execution-log/search?q=browser" | python -m json.tool

# A — what the sequence learner has learned from live runs:
curl -s "http://127.0.0.1:5003/api/sequence-learner/status?task_type=coding" | python -m json.tool

# C — a thought's neural+intent profile:
#   (take a thought_id from the KG, then:)
curl -s "http://127.0.0.1:5003/api/kg/thought/<thought_id>/profile" | python -m json.tool

# D.1 — TriBE/ground-truth diagnostics:
curl -s "http://127.0.0.1:5003/api/tribe/status" | python -m json.tool
```

### 3d. Verify the ground-truth loop closed
After a plan with a `truth:` validator on a hop, the verified outcome becomes a thought
(`verification_reflection`) AND an execution-log record. Check the thought stream / KG for a
`category=verification_reflection` thought referencing the intent.

---

## What "success" looks like per baustein
- **D.1**: a hop with `postcondition` → world checked → `action_verified|refuted` event in thought stream.
- **D.2**: `/api/execution-log/search?diff=MISMATCH` returns the actions that lied. Empty if all honest.
- **D.3**: swarm logs `role=planning` + gpt-5-pro (not the silent groq fallback).
- **C**: thought profile endpoint returns `bridge_levels` + the intent it was grounded on.
- **A**: `/api/sequence-learner/status` shows learned buckets; planner gets a sequence hint.
- **B**: a hop with an unmet `start_when` is blocked (`stats.contract_blocks++`), never runs early.

## Rollback / safety
Every flag defaults OFF. To return to baseline: unset all the `*_ENABLED` env vars and restart.
No schema migrations are destructive (the execlog collection is additive; TriBE neural slot was
already reserved). Nothing is committed yet.
