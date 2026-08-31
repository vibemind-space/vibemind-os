---
agents:
- '*'
app: roarboot
attempts: 1
confidence: 0.6
description: Generates investor-ready Word DOCX of the AI Nation Grant application
  from the Roarboot Fragenkatalog markdown. Cover, TOC, sections, Q&A, status table.
eval_score: 55
expected_state:
  description: DOCX with 50 Q&A entries + status table exists
  verification_tool: docx_verify_file
inputs: []
last_adjusted: '2026-05-08T12:36:33+00:00'
name: roarboot-grant-application-docx
requires_approval: false
successes: 1
---

# roarboot-grant-application-docx

Generates a Word DOCX submission-ready version of the AI Nation Grant
application directly from the structured Markdown Fragenkatalog.

## Pipeline

1. Parse the Fragenkatalog markdown (50 questions across 8 sections)
2. Build DOCX blocks: cover page, TOC, per-section headings, per-question heading + Q/A/status
3. Append status overview table at the end
4. `docx_create_from_data` writes the file
5. `docx_verify_file` checks structure
6. `file_evaluate` quality-checks

## Current state (2026-05-08)

- Total questions: 50
- Answered: 44
- Pre-filled: 3
- Partially: 3
- Progress: 88.0%

## Reproducibility

`python scripts/demo_grant_docx.py` — no args, deterministic, ~5 seconds.
