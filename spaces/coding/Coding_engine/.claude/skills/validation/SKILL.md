---
name: validation
description: LLM-based completeness verification using Multi-Agent Debate pattern. Verifies each requirement is fully implemented through multiple solver perspectives (Implementation, Testing, Deployment) with majority voting.
---

# Validation Skill

You are the Validator for the Society of Mind autonomous code generation system.

## Purpose

Verify requirement completeness using Multi-Agent Debate:
- Analyze each requirement against generated code
- Run tests to verify behavior
- Deploy to sandbox for runtime verification
- Use majority voting for final verdict

## Trigger Events

| Event | Action |
|-------|--------|
| `CONVERGENCE_REACHED` | Full validation of all requirements |
| `PHASE_4_START` | Begin completeness check |
| `VALIDATION_REQUESTED` | On-demand verification |

## Multi-Agent Debate Pattern

Based on AutoGen 0.4 Multi-Agent Debate design pattern:

```
┌────────────────────────────────────────────────────────────────────┐
│  VERIFICATION DEBATE (per Requirement)                             │
│                                                                    │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐            │
│  │Implementation│  │   Testing    │  │  Deployment  │            │
│  │   Solver     │  │   Solver     │  │    Solver    │            │
│  │              │  │              │  │              │            │
│  │ "Is code     │  │ "Are tests   │  │ "Does it     │            │
│  │  complete?"  │  │  passing?"   │  │  work live?" │            │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘            │
│         │                 │                 │                     │
│         │  Round 1: Initial Analysis        │                     │
│         ├─────────────────┼─────────────────┤                     │
│         │                 │                 │                     │
│         │  Round 2: Peer Review             │                     │
│         ├─────────────────┼─────────────────┤                     │
│         │                 │                 │                     │
│         │  Round 3: Final Verdict           │                     │
│         └─────────────────┴─────────────────┘                     │
│                           │                                       │
│                           ▼                                       │
│              ┌────────────────────────┐                          │
│              │      AGGREGATOR        │                          │
│              │   (Majority Voting)    │                          │
│              │                        │                          │
│              │  2/3 VERIFIED → PASS   │                          │
│              │  2/3 FAILED → FAIL     │                          │
│              └────────────────────────┘                          │
└────────────────────────────────────────────────────────────────────┘
```

## Solver Perspectives

### Implementation Solver

Analyzes code completeness:
```
Questions:
1. Does code exist for this requirement?
2. Are all described features implemented?
3. Is the implementation complete (not stubbed)?
4. Are types properly defined?
5. Does code follow best practices?

Checks:
- File exists: src/components/Login.tsx
- Component exported and used
- All props implemented
- No TODO comments left
- No placeholder content
```

### Testing Solver

Verifies test coverage:
```
Questions:
1. Do tests exist for this requirement?
2. Are all test cases passing?
3. Are edge cases covered?
4. Is coverage above threshold?

Checks:
- Test file exists: Login.test.tsx
- npm run test -- Login → 0 failures
- Coverage: 85% statements
- Error cases tested
```

### Deployment Solver

Validates runtime behavior:
```
Questions:
1. Does the app start without errors?
2. Does the feature work in browser?
3. Are there any console errors?
4. Does E2E test pass?

Checks:
- npm run build → success
- docker run sandbox → app starts
- E2E test: Login flow → pass
- console.error count: 0
```

## Debate Rounds

### Round 1: Initial Analysis

Each solver independently analyzes:
```json
{
  "solver": "implementation",
  "requirement_id": "REQ_001",
  "requirement": "User can login with email and password",
  "verdict": "VERIFIED",
  "confidence": 0.85,
  "evidence": [
    "Login.tsx exists with email/password fields",
    "Form validation implemented",
    "API call to /auth/login on submit"
  ],
  "concerns": [
    "No loading state during API call"
  ]
}
```

### Round 2: Peer Review

Solvers see each other's analysis and refine:
```json
{
  "solver": "testing",
  "round": 2,
  "peer_feedback": "Implementation solver noted missing loading state",
  "updated_verdict": "NEEDS_WORK",
  "updated_confidence": 0.7,
  "new_evidence": [
    "Loading state test would fail",
    "UX expectation: show spinner"
  ]
}
```

### Round 3: Final Verdict

Solvers give final vote:
```json
{
  "solver": "implementation",
  "round": 3,
  "final_verdict": "NEEDS_WORK",
  "reason": "Loading state missing, agreed with Testing solver",
  "suggested_action": {
    "type": "CODE_GEN",
    "description": "Add loading state to Login component",
    "priority": "medium"
  }
}
```

## Aggregator: Majority Voting

```python
def aggregate(responses: list[SolverResponse]) -> VerificationResult:
    verdicts = [r.final_verdict for r in responses]

    verified_count = verdicts.count("VERIFIED")
    failed_count = verdicts.count("FAILED")
    needs_work_count = verdicts.count("NEEDS_WORK")

    total = len(verdicts)

    # Majority vote
    if verified_count > total / 2:
        return VerificationResult(
            verdict="VERIFIED",
            confidence=sum(r.confidence for r in responses) / total
        )
    elif failed_count > total / 2:
        return VerificationResult(
            verdict="FAILED",
            reason=collect_failure_reasons(responses),
            return_to_phase3=True
        )
    else:
        return VerificationResult(
            verdict="NEEDS_WORK",
            actions=collect_suggested_actions(responses),
            return_to_phase3=True
        )
```

## Verification Actions

When requirement needs work:
```
Actions:
- CODE_GEN: Generate missing code
- TEST_GEN: Create missing tests
- REFACTOR: Improve existing code
- FIX_BUG: Fix identified issue
- DEPLOY_TEST: Run additional E2E tests
```

## Completeness Report

```json
{
  "total_requirements": 20,
  "verified": 17,
  "failed": 1,
  "needs_work": 2,
  "completeness_score": 85,
  "detailed_results": [
    {
      "requirement_id": "REQ_001",
      "requirement": "User can login",
      "verdict": "VERIFIED",
      "confidence": 0.92,
      "debate_rounds": 3,
      "solver_votes": {
        "implementation": "VERIFIED",
        "testing": "VERIFIED",
        "deployment": "VERIFIED"
      }
    },
    {
      "requirement_id": "REQ_015",
      "requirement": "User can reset password",
      "verdict": "FAILED",
      "reason": "Password reset API not implemented",
      "solver_votes": {
        "implementation": "FAILED",
        "testing": "FAILED",
        "deployment": "FAILED"
      },
      "actions_needed": [
        {"type": "CODE_GEN", "description": "Implement /auth/reset-password endpoint"}
      ]
    }
  ]
}
```

## Communication

### Publish Events

```python
# On successful verification
event_bus.publish(Event(
    type=EventType.VERIFICATION_PASSED,
    source="validation",
    data={
        "requirements_verified": 20,
        "completeness_score": 100,
        "all_tests_passing": True
    }
))

# On failed verification
event_bus.publish(Event(
    type=EventType.VERIFICATION_FAILED,
    source="validation",
    data={
        "requirements_failed": 2,
        "actions_needed": [
            {"req": "REQ_015", "action": "CODE_GEN", "desc": "Implement password reset"}
        ],
        "return_to_phase3": True
    }
))
```

## Configuration

```json
{
  "llm_verification": true,
  "verification_debate_rounds": 3,
  "verification_confidence_threshold": 0.8,
  "verification_require_unanimous": false,
  "verification_timeout_per_req": 60
}
```

## Best Practices

1. **Independent Analysis** - Each solver works alone first
2. **Evidence-Based** - Cite specific files, lines, tests
3. **Constructive Debate** - Focus on improving, not just criticizing
4. **Actionable Output** - Every FAILED needs a fix suggestion
5. **Confidence Scoring** - Be honest about uncertainty
6. **Timeout Handling** - Don't block on single requirement
7. **Incremental Progress** - Track improvements across iterations
